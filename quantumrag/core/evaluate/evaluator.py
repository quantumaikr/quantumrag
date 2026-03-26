"""Main evaluator that orchestrates the evaluation pipeline."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from quantumrag.core.evaluate.metrics import (
    AnswerRelevancy,
    Completeness,
    ContextPrecision,
    Faithfulness,
    LatencyMetric,
    RetrievalRecall,
    compute_token_f1,
)
from quantumrag.core.evaluate.models import QAPair
from quantumrag.core.evaluate.synthetic import SyntheticGenerator
from quantumrag.core.models import EvalMetric, EvalResult

if TYPE_CHECKING:
    from quantumrag.core.engine import Engine


class Evaluator:
    """Run evaluation pipeline and generate reports."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    async def evaluate(
        self,
        benchmark_file: str | Path | None = None,
        sample_count: int = 20,
    ) -> EvalResult:
        """Run full evaluation: generate/load QA pairs, query, compute metrics."""
        # Step 1: Get QA pairs
        if benchmark_file is not None:
            qa_pairs = _load_benchmark(benchmark_file)
        else:
            qa_pairs = await self._generate_qa_pairs(sample_count)

        if not qa_pairs:
            return EvalResult(
                summary="No QA pairs available for evaluation.",
                metrics=[],
                suggestions=["Add documents to the knowledge base before running evaluation."],
                timestamp=datetime.now(),
            )

        # Step 2: Run queries and collect results
        results = await self._run_queries(qa_pairs)

        # Step 3: Compute metrics
        metrics = self._compute_metrics(qa_pairs, results)

        # Step 4: Analyze weaknesses
        metrics_dict = {m.name: m.score for m in metrics}
        suggestions = self._analyze_weaknesses(metrics_dict)

        # Step 5: Build summary
        passed = sum(1 for m in metrics if m.details.get("passed", True))
        total = len(metrics)
        summary = (
            f"Evaluation complete: {passed}/{total} metrics passed. "
            f"Evaluated {len(qa_pairs)} QA pairs."
        )

        return EvalResult(
            summary=summary,
            metrics=metrics,
            suggestions=suggestions,
            timestamp=datetime.now(),
        )

    async def compare(
        self,
        config_a: dict[str, Any],
        config_b: dict[str, Any],
        benchmark_file: str | Path | None = None,
        sample_count: int = 20,
    ) -> dict[str, Any]:
        """Run evaluation with two configs and return a comparison result.

        Useful for A/B testing configuration changes. Each config dict is
        applied to the engine before running the evaluation.

        Args:
            config_a: First engine configuration to test.
            config_b: Second engine configuration to test.
            benchmark_file: Optional path to a benchmark QA file.
            sample_count: Number of QA pairs to evaluate.

        Returns:
            A dict containing both results and per-metric deltas.
        """
        # Save original config
        original_config = self._engine.get_config() if hasattr(self._engine, "get_config") else {}

        # Run evaluation with config A
        if hasattr(self._engine, "apply_config"):
            self._engine.apply_config(config_a)
        result_a = await self.evaluate(benchmark_file=benchmark_file, sample_count=sample_count)

        # Run evaluation with config B
        if hasattr(self._engine, "apply_config"):
            self._engine.apply_config(config_b)
        result_b = await self.evaluate(benchmark_file=benchmark_file, sample_count=sample_count)

        # Restore original config
        if hasattr(self._engine, "apply_config") and original_config:
            self._engine.apply_config(original_config)

        # Build per-metric comparison
        metrics_a = {m.name: m.score for m in result_a.metrics}
        metrics_b = {m.name: m.score for m in result_b.metrics}
        all_metric_names = sorted(set(metrics_a) | set(metrics_b))

        deltas: dict[str, dict[str, float]] = {}
        for name in all_metric_names:
            score_a = metrics_a.get(name, 0.0)
            score_b = metrics_b.get(name, 0.0)
            deltas[name] = {
                "config_a": round(score_a, 4),
                "config_b": round(score_b, 4),
                "delta": round(score_b - score_a, 4),
            }

        # Determine winner
        improvements = sum(1 for d in deltas.values() if d["delta"] > 0)
        regressions = sum(1 for d in deltas.values() if d["delta"] < 0)
        if improvements > regressions:
            winner = "config_b"
        elif regressions > improvements:
            winner = "config_a"
        else:
            winner = "tie"

        return {
            "result_a": result_a,
            "result_b": result_b,
            "deltas": deltas,
            "winner": winner,
        }

    async def _generate_qa_pairs(self, count: int) -> list[QAPair]:
        """Generate QA pairs from indexed documents."""
        try:
            doc_store = self._engine.get_document_store()
            chunks = await doc_store.get_all_chunks()
        except Exception:
            chunks = []

        if not chunks:
            return []

        generator = SyntheticGenerator()
        return await generator.generate(chunks, count=count)

    async def _run_queries(self, qa_pairs: list[QAPair]) -> list[dict[str, Any]]:
        """Run each QA pair through the engine and collect results."""
        results: list[dict[str, Any]] = []

        for qa in qa_pairs:
            t0 = time.perf_counter()
            try:
                query_result = await self._engine.aquery(qa.question)
                latency = time.perf_counter() - t0

                # Collect retrieved chunk IDs from sources
                retrieved_ids = [s.chunk_id for s in query_result.sources]

                # Collect context from source excerpts
                context = " ".join(s.excerpt for s in query_result.sources if s.excerpt)

                results.append({
                    "answer": query_result.answer,
                    "retrieved_ids": retrieved_ids,
                    "context": context,
                    "latency": latency,
                    "confidence": query_result.confidence.value,
                })
            except Exception as e:
                latency = time.perf_counter() - t0
                results.append({
                    "answer": f"Error: {e}",
                    "retrieved_ids": [],
                    "context": "",
                    "latency": latency,
                    "confidence": "error",
                })

        return results

    def _compute_metrics(
        self, qa_pairs: list[QAPair], results: list[dict[str, Any]]
    ) -> list[EvalMetric]:
        """Compute all metrics from QA pairs and query results."""
        metrics: list[EvalMetric] = []

        # Retrieval Recall
        recall_metric = RetrievalRecall()
        recall_scores: list[float] = []
        for qa, result in zip(qa_pairs, results):
            if qa.source_chunk_id:
                score = recall_metric.compute(
                    result["retrieved_ids"], [qa.source_chunk_id], k=5
                )
                recall_scores.append(score)
        if recall_scores:
            avg_recall = sum(recall_scores) / len(recall_scores)
            metrics.append(EvalMetric(
                name="retrieval_recall@5",
                score=round(avg_recall, 4),
                details={"target": 0.8, "passed": avg_recall >= 0.8, "samples": len(recall_scores)},
            ))

        # Faithfulness
        faithfulness_metric = Faithfulness()
        faith_scores: list[float] = []
        for _qa, result in zip(qa_pairs, results):
            if result["context"]:
                score = faithfulness_metric.compute(result["answer"], result["context"])
                faith_scores.append(score)
        if faith_scores:
            avg_faith = sum(faith_scores) / len(faith_scores)
            metrics.append(EvalMetric(
                name="faithfulness",
                score=round(avg_faith, 4),
                details={"target": 0.7, "passed": avg_faith >= 0.7, "samples": len(faith_scores)},
            ))

        # Answer Relevancy
        relevancy_metric = AnswerRelevancy()
        rel_scores: list[float] = []
        for qa, result in zip(qa_pairs, results):
            score = relevancy_metric.compute(qa.question, result["answer"])
            rel_scores.append(score)
        if rel_scores:
            avg_rel = sum(rel_scores) / len(rel_scores)
            metrics.append(EvalMetric(
                name="answer_relevancy",
                score=round(avg_rel, 4),
                details={"target": 0.6, "passed": avg_rel >= 0.6, "samples": len(rel_scores)},
            ))

        # Completeness
        completeness_metric = Completeness()
        comp_scores: list[float] = []
        for qa, result in zip(qa_pairs, results):
            if result["context"]:
                score = completeness_metric.compute(
                    qa.question, result["answer"], result["context"]
                )
                comp_scores.append(score)
        if comp_scores:
            avg_comp = sum(comp_scores) / len(comp_scores)
            metrics.append(EvalMetric(
                name="completeness",
                score=round(avg_comp, 4),
                details={"target": 0.6, "passed": avg_comp >= 0.6, "samples": len(comp_scores)},
            ))

        # Context Precision
        ctx_precision_metric = ContextPrecision()
        ctx_prec_scores: list[float] = []
        for _qa, result in zip(qa_pairs, results):
            if result["context"]:
                # Split context back into per-source excerpts
                contexts = [c for c in result["context"].split("  ") if c.strip()]
                if not contexts:
                    contexts = [result["context"]]
                score = ctx_precision_metric.compute(result["answer"], contexts)
                ctx_prec_scores.append(score)
        if ctx_prec_scores:
            avg_ctx_prec = sum(ctx_prec_scores) / len(ctx_prec_scores)
            metrics.append(EvalMetric(
                name="context_precision",
                score=round(avg_ctx_prec, 4),
                details={
                    "target": 0.7,
                    "passed": avg_ctx_prec >= 0.7,
                    "samples": len(ctx_prec_scores),
                },
            ))

        # Token F1
        f1_scores: list[float] = []
        for qa, result in zip(qa_pairs, results):
            score = compute_token_f1(result["answer"], qa.expected_answer)
            f1_scores.append(score)
        if f1_scores:
            avg_f1 = sum(f1_scores) / len(f1_scores)
            metrics.append(EvalMetric(
                name="token_f1",
                score=round(avg_f1, 4),
                details={"target": 0.5, "passed": avg_f1 >= 0.5, "samples": len(f1_scores)},
            ))

        # Latency
        latencies = [r["latency"] for r in results]
        latency_metric = LatencyMetric()
        latency_stats = latency_metric.compute(latencies)
        metrics.append(EvalMetric(
            name="latency",
            score=round(latency_stats["p50"], 4),
            details={
                "p50": latency_stats["p50"],
                "p95": latency_stats["p95"],
                "p99": latency_stats["p99"],
                "target_p95": 5.0,
                "passed": latency_stats["p95"] <= 5.0,
            },
        ))

        return metrics

    def _analyze_weaknesses(self, metrics: dict[str, float]) -> list[str]:
        """Generate improvement suggestions based on metrics."""
        suggestions: list[str] = []

        recall = metrics.get("retrieval_recall@5")
        if recall is not None and recall < 0.8:
            suggestions.append(
                "Retrieval recall is low. Consider: increasing chunk overlap, "
                "enabling HyPE questions, or tuning fusion weights."
            )

        faithfulness = metrics.get("faithfulness")
        if faithfulness is not None and faithfulness < 0.7:
            suggestions.append(
                "Faithfulness is low. The model may be hallucinating. Consider: "
                "lowering generation temperature, adding more context chunks, "
                "or using a more capable model."
            )

        relevancy = metrics.get("answer_relevancy")
        if relevancy is not None and relevancy < 0.6:
            suggestions.append(
                "Answer relevancy is low. Consider: improving query classification, "
                "enabling query rewriting, or tuning the generation prompt."
            )

        completeness = metrics.get("completeness")
        if completeness is not None and completeness < 0.6:
            suggestions.append(
                "Completeness is low. Answers may miss key aspects. Consider: "
                "retrieving more context chunks, improving chunk coverage, "
                "or prompting the model to be more thorough."
            )

        ctx_precision = metrics.get("context_precision")
        if ctx_precision is not None and ctx_precision < 0.7:
            suggestions.append(
                "Context precision is low. Too many retrieved chunks are unused. Consider: "
                "reducing top-k, improving retrieval relevance, or tuning reranking."
            )

        f1 = metrics.get("token_f1")
        if f1 is not None and f1 < 0.5:
            suggestions.append(
                "Token F1 is low. Answers differ significantly from expected. Consider: "
                "checking chunk quality, improving retrieval, or using a larger model."
            )

        latency_p50 = metrics.get("latency")
        if latency_p50 is not None and latency_p50 > 5.0:
            suggestions.append(
                "Latency is high. Consider: using a smaller/faster model for simple queries, "
                "enabling caching, or reducing the number of retrieved chunks."
            )

        if not suggestions:
            suggestions.append("All metrics are within acceptable ranges. Good job!")

        return suggestions


def _load_benchmark(path: str | Path) -> list[QAPair]:
    """Load QA pairs from a JSON benchmark file."""
    path = Path(path)
    if not path.exists():
        return []

    with open(path) as f:
        data = json.load(f)

    pairs: list[QAPair] = []
    items = data if isinstance(data, list) else data.get("pairs", [])
    for item in items:
        pairs.append(QAPair(
            question=item["question"],
            expected_answer=item["expected_answer"],
            source_chunk_id=item.get("source_chunk_id"),
            metadata=item.get("metadata", {}),
        ))
    return pairs
