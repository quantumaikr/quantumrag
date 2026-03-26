"""Speculative RAG - parallel sub-query processing for complex queries."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Confidence, QueryResult, Source, TraceStep

logger = get_logger("quantumrag.speculative")


class SpeculativeRAG:
    """Process complex queries by decomposing and running parallel sub-queries.

    For complex multi-hop queries, this runs sub-queries in parallel,
    collects their results, then merges them into a single coherent answer.
    """

    async def process(
        self,
        query: str,
        sub_queries: list[str],
        retriever: Any,
        generator: Any,
        verifier_llm: Any | None = None,
    ) -> QueryResult:
        """Run sub-queries in parallel, then merge results.

        Args:
            query: The original complex query.
            sub_queries: Decomposed sub-queries.
            retriever: Retriever instance with a retrieve() method.
            generator: Generator instance with a generate() method.
            verifier_llm: Optional LLM to verify/merge final answer.

        Returns:
            Merged QueryResult.
        """
        t0 = time.perf_counter()
        trace_steps: list[TraceStep] = []

        trace_steps.append(
            TraceStep(
                step="decompose",
                result=f"{len(sub_queries)} sub-queries",
                details={"sub_queries": sub_queries},
            )
        )

        # Run sub-queries in parallel
        tasks = [self._run_sub_query(sq, retriever, generator) for sq in sub_queries]
        sub_results: list[QueryResult | None] = await asyncio.gather(*tasks, return_exceptions=False)

        # Filter out failures
        valid_results = [r for r in sub_results if r is not None]

        trace_steps.append(
            TraceStep(
                step="parallel_retrieve_generate",
                result=f"{len(valid_results)}/{len(sub_queries)} succeeded",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        )

        if not valid_results:
            return QueryResult(
                answer="I could not find sufficient information to answer the question.",
                confidence=Confidence.INSUFFICIENT_EVIDENCE,
                trace=trace_steps,
            )

        # Merge results
        merged = self._merge_results(query, valid_results, trace_steps)

        # Optionally verify with a verifier LLM
        if verifier_llm is not None:
            merged = await self._verify(query, merged, verifier_llm, trace_steps)

        elapsed = (time.perf_counter() - t0) * 1000
        trace_steps.append(
            TraceStep(step="speculative_total", latency_ms=elapsed)
        )

        return merged

    async def _run_sub_query(
        self,
        query: str,
        retriever: Any,
        generator: Any,
    ) -> QueryResult | None:
        """Run a single sub-query through retrieve + generate."""
        try:
            chunks, sources = await retriever.retrieve(query)
            result = await generator.generate(query, chunks, sources)
            return result
        except Exception:
            logger.warning("sub_query_failed", query=query, exc_info=True)
            return None

    def _merge_results(
        self,
        original_query: str,
        results: list[QueryResult],
        trace_steps: list[TraceStep],
    ) -> QueryResult:
        """Merge multiple sub-query results into a single result."""
        all_sources: list[Source] = []
        answer_parts: list[str] = []
        seen_source_ids: set[str] = set()

        for r in results:
            answer_parts.append(r.answer)
            for src in r.sources:
                if src.chunk_id not in seen_source_ids:
                    seen_source_ids.add(src.chunk_id)
                    all_sources.append(src)

        # Determine overall confidence (worst among sub-results)
        confidence_order = [
            Confidence.INSUFFICIENT_EVIDENCE,
            Confidence.PARTIALLY_SUPPORTED,
            Confidence.STRONGLY_SUPPORTED,
        ]
        min_confidence = min(
            (r.confidence for r in results),
            key=lambda c: confidence_order.index(c),
        )

        merged_answer = "\n\n".join(answer_parts)

        return QueryResult(
            answer=merged_answer,
            sources=all_sources,
            confidence=min_confidence,
            trace=trace_steps,
            metadata={"sub_results_count": len(results)},
        )

    async def _verify(
        self,
        query: str,
        merged: QueryResult,
        verifier_llm: Any,
        trace_steps: list[TraceStep],
    ) -> QueryResult:
        """Use a verifier LLM to synthesize a coherent final answer."""
        prompt = (
            "Given the original question and multiple partial answers, "
            "synthesize a single coherent answer.\n\n"
            f"Original question: {query}\n\n"
            f"Partial answers:\n{merged.answer}\n\n"
            "Synthesized answer:"
        )
        try:
            t0 = time.perf_counter()
            response = await verifier_llm.generate(prompt, max_tokens=1024, temperature=0.1)
            trace_steps.append(
                TraceStep(
                    step="verify_merge",
                    result="verified",
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            )
            merged.answer = response.text.strip()
        except Exception:
            logger.warning("verification_failed", exc_info=True)

        return merged
