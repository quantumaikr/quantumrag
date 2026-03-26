"""Tests for the evaluation system."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantumrag.core.evaluate.evaluator import Evaluator, _load_benchmark
from quantumrag.core.evaluate.metrics import (
    AnswerRelevancy,
    Faithfulness,
    LatencyMetric,
    RetrievalRecall,
    compute_token_f1,
)
from quantumrag.core.evaluate.synthetic import SyntheticGenerator
from quantumrag.core.models import Chunk, Confidence, QueryResult, Source

# ---------------------------------------------------------------------------
# Synthetic QA Generation
# ---------------------------------------------------------------------------


class TestSyntheticGenerator:
    def test_template_generate_basic(self) -> None:
        chunks = [
            Chunk(
                id="c1",
                content="Machine learning is a subset of artificial intelligence. "
                "It uses algorithms to learn from data and make predictions.",
                document_id="d1",
                chunk_index=0,
            ),
            Chunk(
                id="c2",
                content="The revenue increased by 25% in Q3 2024. "
                "This was driven by strong product sales and new market expansion.",
                document_id="d1",
                chunk_index=1,
            ),
        ]
        generator = SyntheticGenerator()
        pairs = generator._template_generate(chunks, count=5)

        assert len(pairs) > 0
        for pair in pairs:
            assert pair.question
            assert pair.expected_answer
            assert pair.source_chunk_id in {"c1", "c2"}
            assert "strategy" in pair.metadata

    def test_template_generate_empty_chunks(self) -> None:
        generator = SyntheticGenerator()
        pairs = generator._template_generate([], count=5)
        assert pairs == []

    def test_template_generate_short_content(self) -> None:
        chunks = [
            Chunk(id="c1", content="Short.", document_id="d1", chunk_index=0),
        ]
        generator = SyntheticGenerator()
        pairs = generator._template_generate(chunks, count=5)
        # Short content may not generate any pairs
        assert isinstance(pairs, list)

    def test_template_generate_respects_count(self) -> None:
        chunks = [
            Chunk(
                id=f"c{i}",
                content=f"This is document {i} about topic {i}. "
                f"It contains important information worth {i * 100} dollars. "
                f"The results show a {i * 10}% improvement over baseline methods.",
                document_id="d1",
                chunk_index=i,
            )
            for i in range(20)
        ]
        generator = SyntheticGenerator()
        pairs = generator._template_generate(chunks, count=3)
        assert len(pairs) <= 3

    @pytest.mark.asyncio
    async def test_generate_falls_back_to_template(self) -> None:
        """When no LLM is provided, generate() uses template fallback."""
        chunks = [
            Chunk(
                id="c1",
                content="Python is a popular programming language used for web development. "
                "It was created by Guido van Rossum and released in 1991.",
                document_id="d1",
                chunk_index=0,
            ),
        ]
        generator = SyntheticGenerator(llm_provider=None)
        pairs = await generator.generate(chunks, count=5)
        assert len(pairs) > 0

    @pytest.mark.asyncio
    async def test_generate_with_failing_llm_falls_back(self) -> None:
        """When LLM fails, generate() falls back to template."""
        mock_llm = AsyncMock()
        mock_llm.generate.side_effect = RuntimeError("API error")

        chunks = [
            Chunk(
                id="c1",
                content="Quantum computing leverages quantum mechanical phenomena. "
                "It can solve certain problems exponentially faster than classical computers.",
                document_id="d1",
                chunk_index=0,
            ),
        ]
        generator = SyntheticGenerator(llm_provider=mock_llm)
        pairs = await generator.generate(chunks, count=5)
        assert len(pairs) > 0


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TestRetrievalRecall:
    def test_perfect_recall(self) -> None:
        metric = RetrievalRecall()
        score = metric.compute(["a", "b", "c"], ["a", "b"], k=5)
        assert score == 1.0

    def test_partial_recall(self) -> None:
        metric = RetrievalRecall()
        score = metric.compute(["a", "b", "c"], ["a", "d"], k=5)
        assert score == 0.5

    def test_zero_recall(self) -> None:
        metric = RetrievalRecall()
        score = metric.compute(["a", "b", "c"], ["x", "y"], k=5)
        assert score == 0.0

    def test_k_limits_retrieved(self) -> None:
        metric = RetrievalRecall()
        # "d" is at position 4 (index 3), within k=3 it shouldn't be found
        score = metric.compute(["a", "b", "c", "d"], ["d"], k=3)
        assert score == 0.0
        # But with k=4 it should
        score = metric.compute(["a", "b", "c", "d"], ["d"], k=4)
        assert score == 1.0

    def test_empty_relevant(self) -> None:
        metric = RetrievalRecall()
        score = metric.compute(["a", "b"], [], k=5)
        assert score == 1.0

    def test_empty_retrieved(self) -> None:
        metric = RetrievalRecall()
        score = metric.compute([], ["a"], k=5)
        assert score == 0.0


class TestFaithfulness:
    def test_fully_faithful(self) -> None:
        metric = Faithfulness()
        context = "The company reported revenue of 10 million dollars in 2024."
        answer = "The company reported revenue of 10 million dollars."
        score = metric.compute(answer, context)
        assert score >= 0.8

    def test_unfaithful(self) -> None:
        metric = Faithfulness()
        context = "The company reported revenue of 10 million dollars."
        answer = "Cats are wonderful pets that bring joy to families."
        score = metric.compute(answer, context)
        assert score < 0.5

    def test_empty_answer(self) -> None:
        metric = Faithfulness()
        score = metric.compute("", "Some context here.")
        assert score == 1.0  # No sentences to check

    def test_empty_context(self) -> None:
        metric = Faithfulness()
        score = metric.compute("Some answer here.", "")
        assert score == 0.0

    def test_multi_sentence(self) -> None:
        metric = Faithfulness()
        context = "Python is a programming language. It supports multiple paradigms."
        answer = "Python is a programming language. It is used for cooking."
        score = metric.compute(answer, context)
        # First sentence is supported, second is not
        assert 0.0 < score < 1.0


class TestAnswerRelevancy:
    def test_relevant_answer(self) -> None:
        metric = AnswerRelevancy()
        question = "What is machine learning?"
        answer = "Machine learning is a method where algorithms learn patterns from data."
        score = metric.compute(question, answer)
        assert score > 0.0

    def test_irrelevant_answer(self) -> None:
        metric = AnswerRelevancy()
        question = "What is machine learning?"
        answer = "The weather today is sunny and warm."
        score = metric.compute(question, answer)
        # Should have very low overlap
        assert score < 0.5

    def test_empty_question(self) -> None:
        metric = AnswerRelevancy()
        score = metric.compute("", "Some answer.")
        assert score == 0.0

    def test_empty_answer(self) -> None:
        metric = AnswerRelevancy()
        score = metric.compute("What is Python?", "")
        assert score == 0.0

    def test_score_bounded(self) -> None:
        metric = AnswerRelevancy()
        score = metric.compute("test query words", "test query words and more content here")
        assert 0.0 <= score <= 1.0


class TestLatencyMetric:
    def test_basic_latencies(self) -> None:
        metric = LatencyMetric()
        result = metric.compute([1.0, 2.0, 3.0, 4.0, 5.0])
        assert "p50" in result
        assert "p95" in result
        assert "p99" in result
        assert result["p50"] == 3.0

    def test_empty_latencies(self) -> None:
        metric = LatencyMetric()
        result = metric.compute([])
        assert result == {"p50": 0.0, "p95": 0.0, "p99": 0.0}

    def test_single_latency(self) -> None:
        metric = LatencyMetric()
        result = metric.compute([42.0])
        assert result["p50"] == 42.0
        assert result["p95"] == 42.0
        assert result["p99"] == 42.0

    def test_percentile_ordering(self) -> None:
        metric = LatencyMetric()
        latencies = [float(i) for i in range(1, 101)]
        result = metric.compute(latencies)
        assert result["p50"] <= result["p95"] <= result["p99"]


class TestTokenF1:
    def test_identical(self) -> None:
        score = compute_token_f1(
            "Machine learning uses algorithms",
            "Machine learning uses algorithms",
        )
        assert score == 1.0

    def test_no_overlap(self) -> None:
        score = compute_token_f1("cats dogs pets", "revenue profit growth")
        assert score == 0.0

    def test_partial_overlap(self) -> None:
        score = compute_token_f1(
            "machine learning algorithms data",
            "machine learning models training",
        )
        assert 0.0 < score < 1.0

    def test_empty_prediction(self) -> None:
        score = compute_token_f1("", "some reference text")
        assert score == 0.0

    def test_empty_reference(self) -> None:
        score = compute_token_f1("some prediction text", "")
        assert score == 0.0


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class TestEvaluator:
    def _make_mock_engine(self) -> MagicMock:
        engine = MagicMock()
        engine.get_document_store = MagicMock()
        return engine

    @pytest.mark.asyncio
    async def test_evaluate_no_qa_pairs(self) -> None:
        engine = self._make_mock_engine()
        doc_store = AsyncMock()
        doc_store.get_all_chunks = AsyncMock(return_value=[])
        engine.get_document_store.return_value = doc_store

        evaluator = Evaluator(engine)
        result = await evaluator.evaluate(sample_count=5)

        assert "No QA pairs" in result.summary
        assert len(result.suggestions) > 0

    @pytest.mark.asyncio
    async def test_evaluate_with_benchmark_file(self, tmp_path: Path) -> None:
        benchmark = [
            {"question": "What is Python?", "expected_answer": "A programming language."},
            {"question": "What is RAG?", "expected_answer": "Retrieval augmented generation."},
        ]
        benchmark_file = tmp_path / "benchmark.json"
        benchmark_file.write_text(json.dumps(benchmark))

        engine = self._make_mock_engine()
        engine.aquery = AsyncMock(return_value=QueryResult(
            answer="Python is a programming language.",
            sources=[
                Source(chunk_id="c1", excerpt="Python is a programming language used widely."),
            ],
            confidence=Confidence.STRONGLY_SUPPORTED,
        ))

        evaluator = Evaluator(engine)
        result = await evaluator.evaluate(benchmark_file=str(benchmark_file))

        assert result.summary
        assert len(result.metrics) > 0
        assert isinstance(result.timestamp, datetime)

        metric_names = {m.name for m in result.metrics}
        assert "answer_relevancy" in metric_names
        assert "latency" in metric_names

    @pytest.mark.asyncio
    async def test_evaluate_with_query_errors(self, tmp_path: Path) -> None:
        """Evaluator handles query errors gracefully."""
        benchmark = [
            {"question": "What is X?", "expected_answer": "X is something."},
        ]
        benchmark_file = tmp_path / "benchmark.json"
        benchmark_file.write_text(json.dumps(benchmark))

        engine = self._make_mock_engine()
        engine.aquery = AsyncMock(side_effect=RuntimeError("Query failed"))

        evaluator = Evaluator(engine)
        result = await evaluator.evaluate(benchmark_file=str(benchmark_file))

        assert result.summary
        assert len(result.metrics) > 0

    @pytest.mark.asyncio
    async def test_evaluate_computes_all_metrics(self, tmp_path: Path) -> None:
        benchmark = [
            {
                "question": "What is the revenue?",
                "expected_answer": "The revenue was 10 million dollars.",
                "source_chunk_id": "c1",
            },
        ]
        benchmark_file = tmp_path / "benchmark.json"
        benchmark_file.write_text(json.dumps(benchmark))

        engine = self._make_mock_engine()
        engine.aquery = AsyncMock(return_value=QueryResult(
            answer="The revenue was 10 million dollars in 2024.",
            sources=[
                Source(
                    chunk_id="c1",
                    excerpt="The revenue was 10 million dollars in 2024.",
                ),
            ],
            confidence=Confidence.STRONGLY_SUPPORTED,
        ))

        evaluator = Evaluator(engine)
        result = await evaluator.evaluate(benchmark_file=str(benchmark_file))

        metric_names = {m.name for m in result.metrics}
        assert "retrieval_recall@5" in metric_names
        assert "faithfulness" in metric_names
        assert "answer_relevancy" in metric_names
        assert "token_f1" in metric_names
        assert "latency" in metric_names


# ---------------------------------------------------------------------------
# Weakness Analysis
# ---------------------------------------------------------------------------


class TestWeaknessAnalysis:
    def test_all_metrics_good(self) -> None:
        evaluator = Evaluator(MagicMock())
        suggestions = evaluator._analyze_weaknesses({
            "retrieval_recall@5": 0.95,
            "faithfulness": 0.85,
            "answer_relevancy": 0.75,
            "token_f1": 0.65,
            "latency": 1.0,
        })
        assert len(suggestions) == 1
        assert "Good job" in suggestions[0]

    def test_low_recall(self) -> None:
        evaluator = Evaluator(MagicMock())
        suggestions = evaluator._analyze_weaknesses({
            "retrieval_recall@5": 0.3,
            "faithfulness": 0.85,
            "answer_relevancy": 0.75,
            "token_f1": 0.65,
            "latency": 1.0,
        })
        assert any("recall" in s.lower() for s in suggestions)

    def test_low_faithfulness(self) -> None:
        evaluator = Evaluator(MagicMock())
        suggestions = evaluator._analyze_weaknesses({
            "retrieval_recall@5": 0.9,
            "faithfulness": 0.3,
            "answer_relevancy": 0.75,
            "token_f1": 0.65,
            "latency": 1.0,
        })
        assert any("faithfulness" in s.lower() for s in suggestions)

    def test_low_relevancy(self) -> None:
        evaluator = Evaluator(MagicMock())
        suggestions = evaluator._analyze_weaknesses({
            "retrieval_recall@5": 0.9,
            "faithfulness": 0.85,
            "answer_relevancy": 0.2,
            "token_f1": 0.65,
            "latency": 1.0,
        })
        assert any("relevancy" in s.lower() for s in suggestions)

    def test_high_latency(self) -> None:
        evaluator = Evaluator(MagicMock())
        suggestions = evaluator._analyze_weaknesses({
            "retrieval_recall@5": 0.9,
            "faithfulness": 0.85,
            "answer_relevancy": 0.75,
            "token_f1": 0.65,
            "latency": 10.0,
        })
        assert any("latency" in s.lower() for s in suggestions)

    def test_multiple_weaknesses(self) -> None:
        evaluator = Evaluator(MagicMock())
        suggestions = evaluator._analyze_weaknesses({
            "retrieval_recall@5": 0.2,
            "faithfulness": 0.3,
            "answer_relevancy": 0.1,
            "token_f1": 0.1,
            "latency": 20.0,
        })
        assert len(suggestions) == 5


# ---------------------------------------------------------------------------
# Benchmark Loading
# ---------------------------------------------------------------------------


class TestBenchmarkLoading:
    def test_load_list_format(self, tmp_path: Path) -> None:
        data = [
            {"question": "Q1", "expected_answer": "A1"},
            {"question": "Q2", "expected_answer": "A2", "source_chunk_id": "c1"},
        ]
        path = tmp_path / "bench.json"
        path.write_text(json.dumps(data))
        pairs = _load_benchmark(path)
        assert len(pairs) == 2
        assert pairs[0].question == "Q1"
        assert pairs[1].source_chunk_id == "c1"

    def test_load_dict_format(self, tmp_path: Path) -> None:
        data = {"pairs": [{"question": "Q1", "expected_answer": "A1"}]}
        path = tmp_path / "bench.json"
        path.write_text(json.dumps(data))
        pairs = _load_benchmark(path)
        assert len(pairs) == 1

    def test_load_nonexistent(self) -> None:
        pairs = _load_benchmark("/nonexistent/file.json")
        assert pairs == []
