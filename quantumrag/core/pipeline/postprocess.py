"""Post-generation correction pipeline.

Replaces the inline correction cascade in engine.py with a modular,
composable pipeline. Each correction step is a PostProcessor that
can inspect the result, decide whether to act, and optionally trigger
re-retrieval + re-generation.

Design principles:
- Each processor is independent and testable
- Early-exit: if a processor upgrades confidence, later processors skip
- Shared context via CorrectionContext (no global state)
- Zero overhead on happy path (processors check preconditions first)
"""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Confidence, QueryResult, TraceStep

logger = get_logger("quantumrag.postprocess")


# ---------------------------------------------------------------------------
# Protocols for engine capabilities (avoids circular imports)
# ---------------------------------------------------------------------------


@runtime_checkable
class Retriever(Protocol):
    """Minimal retrieval interface needed by post-processors."""

    async def retrieve(
        self,
        query: str,
        classification: Any,
        top_k: int,
        filters: Any,
        rerank: Any,
        pipeline_ctx: Any,
    ) -> Any: ...

    async def retrieve_bm25_dominant(
        self,
        query: str,
        classification: Any,
        top_k: int,
        filters: Any,
        rerank: Any,
        pipeline_ctx: Any,
    ) -> Any: ...


@runtime_checkable
class Generator(Protocol):
    """Minimal generation interface needed by post-processors."""

    async def generate(self, query: str, chunks: list[Any], sources: list[Any]) -> QueryResult: ...


# ---------------------------------------------------------------------------
# Shared context passed through the correction pipeline
# ---------------------------------------------------------------------------


@dataclass
class CorrectionContext:
    """Shared state for the correction pipeline.

    Carries everything a PostProcessor needs to make decisions and
    perform re-retrieval / re-generation without accessing the engine.
    """

    query: str
    result: QueryResult
    chunks: list[Any]  # ScoredChunk list
    sources: list[Any]  # Source list
    classification: Any  # QueryClassification
    top_k: int
    filters: Any
    rerank: Any
    pipeline_ctx: Any
    generator: Generator
    retriever: Retriever
    trace: list[TraceStep]
    use_map_reduce: bool = False
    config: Any = None  # QuantumRAGConfig (optional)

    # Track which processors fired (for diagnostics)
    applied_processors: list[str] = field(default_factory=list)

    # Time budget: max seconds for entire correction pipeline
    # Processors should check remaining time before expensive operations
    time_budget_s: float = 20.0
    pipeline_start: float = field(default_factory=time.perf_counter)

    # Token usage accumulator across all generation calls
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_estimated_cost: float = 0.0
    generation_count: int = 0

    @property
    def elapsed_s(self) -> float:
        return time.perf_counter() - self.pipeline_start

    @property
    def time_remaining_s(self) -> float:
        return max(0, self.time_budget_s - self.elapsed_s)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class PostProcessor(ABC):
    """Base class for post-generation correction steps.

    Subclasses implement:
    - should_run(): precondition check (zero cost)
    - process(): actual correction logic
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for trace/logging."""

    @abstractmethod
    def should_run(self, ctx: CorrectionContext) -> bool:
        """Check if this processor should execute.

        Must be fast (no I/O). Return False to skip.
        """

    @abstractmethod
    async def process(self, ctx: CorrectionContext) -> CorrectionContext:
        """Execute the correction step.

        May modify ctx.result, ctx.chunks, ctx.sources.
        Must append to ctx.trace.
        """


# ---------------------------------------------------------------------------
# Concrete processors
# ---------------------------------------------------------------------------


class RetrievalRetryProcessor(PostProcessor):
    """Re-retrieve with BM25-dominant strategy on INSUFFICIENT_EVIDENCE.

    Triggers when the initial answer has insufficient confidence but
    retrieval did return some chunks — the content exists but was
    missed by the semantic search.
    """

    @property
    def name(self) -> str:
        return "retrieval_retry"

    def should_run(self, ctx: CorrectionContext) -> bool:
        if ctx.use_map_reduce:
            return False
        if not ctx.config or not ctx.config.retrieval.retrieval_retry:
            return False
        if ctx.time_remaining_s < 10:
            return False
        # Skip retry for COMPLEX queries — they already have sub-query fusion
        # and retry would double the LLM calls with diminishing returns
        from quantumrag.core.models import QueryComplexity

        if hasattr(ctx.classification, "complexity"):
            if ctx.classification.complexity == QueryComplexity.COMPLEX:
                return False
        return ctx.result.confidence == Confidence.INSUFFICIENT_EVIDENCE and bool(ctx.chunks)

    async def process(self, ctx: CorrectionContext) -> CorrectionContext:
        t0 = time.perf_counter()
        retry_top_k = max(ctx.top_k, 10)  # Same as original, not 3x

        retry_result = await ctx.retriever.retrieve_bm25_dominant(
            ctx.query,
            ctx.classification,
            retry_top_k,
            ctx.filters,
            ctx.rerank,
            ctx.pipeline_ctx,
        )

        # Supplementary English-term BM25 for mixed-language queries
        try:
            en_terms = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", ctx.query)
            if en_terms and len(en_terms) >= 2 and hasattr(ctx.retriever, "search_bm25_raw"):
                en_hits = await ctx.retriever.search_bm25_raw(" ".join(en_terms), top_k=retry_top_k)
                if en_hits:
                    retry_result.chunks.extend(en_hits[:10])
        except Exception:
            pass

        # Merge original + retry, dedup
        seen = {sc.chunk.id for sc in ctx.chunks}
        for sc in retry_result.chunks:
            if sc.chunk.id not in seen:
                ctx.chunks.append(sc)
                seen.add(sc.chunk.id)
        ctx.chunks.sort(key=lambda x: x.score, reverse=True)

        # Re-generate
        ctx.result = await ctx.generator.generate(
            ctx.query, ctx.chunks, ctx.sources + retry_result.sources
        )

        ms = (time.perf_counter() - t0) * 1000
        ctx.trace.append(
            TraceStep(
                step="retrieval_retry",
                result=f"BM25-dominant retry with {len(ctx.chunks)} chunks",
                latency_ms=ms,
                details={"retry_top_k": retry_top_k},
            )
        )
        ctx.result.metadata["retrieval_retry"] = True
        ctx.applied_processors.append(self.name)
        return ctx


class SelfCorrectProcessor(PostProcessor):
    """Detect insufficient answers via pattern matching and re-retrieve.

    Only fires if RetrievalRetry was NOT applied (they serve the same
    purpose with different strategies — no point running both).
    """

    @property
    def name(self) -> str:
        return "self_correct"

    def should_run(self, ctx: CorrectionContext) -> bool:
        if ctx.use_map_reduce:
            return False
        if "retrieval_retry" in ctx.applied_processors:
            return False
        if ctx.time_remaining_s < 10:
            return False

        from quantumrag.core.generate.self_correct import answer_is_insufficient

        return (
            ctx.result.confidence == Confidence.INSUFFICIENT_EVIDENCE
            and answer_is_insufficient(ctx.result.answer)
            and bool(ctx.chunks)
        )

    async def process(self, ctx: CorrectionContext) -> CorrectionContext:
        from quantumrag.core.generate.self_correct import extract_missing_focus

        t0 = time.perf_counter()
        retry_query = extract_missing_focus(ctx.query, ctx.result.answer) or ctx.query

        retry_result = await ctx.retriever.retrieve(
            retry_query,
            ctx.classification,
            ctx.top_k * 2,
            ctx.filters,
            ctx.rerank,
            ctx.pipeline_ctx,
        )

        seen = {sc.chunk.id for sc in ctx.chunks}
        for sc in retry_result.chunks:
            if sc.chunk.id not in seen:
                ctx.chunks.append(sc)
                seen.add(sc.chunk.id)
        ctx.chunks.sort(key=lambda x: x.score, reverse=True)

        ctx.result = await ctx.generator.generate(
            ctx.query, ctx.chunks, ctx.sources + retry_result.sources
        )

        ms = (time.perf_counter() - t0) * 1000
        ctx.trace.append(
            TraceStep(
                step="self_correct",
                result=f"re-retrieved with {len(ctx.chunks)} chunks",
                latency_ms=ms,
                details={"retry_query": retry_query},
            )
        )
        ctx.applied_processors.append(self.name)
        return ctx


class FactVerificationProcessor(PostProcessor):
    """Cross-check answer against structured facts extracted at ingest time.

    Unlike self-correct (detects "I don't know"), this detects WRONG answers
    by comparing mentioned entities against the fact index.
    """

    @property
    def name(self) -> str:
        return "fact_verification"

    def should_run(self, ctx: CorrectionContext) -> bool:
        if ctx.use_map_reduce:
            return False
        return ctx.result.confidence != Confidence.INSUFFICIENT_EVIDENCE and bool(ctx.chunks)

    async def process(self, ctx: CorrectionContext) -> CorrectionContext:
        from quantumrag.core.generate.fact_verifier import (
            build_correction_hint,
            verify_against_facts,
        )

        t0 = time.perf_counter()
        verification = verify_against_facts(ctx.result.answer, ctx.chunks, ctx.query)
        ms = (time.perf_counter() - t0) * 1000

        if not verification.is_valid:
            correction_hint = build_correction_hint(verification)
            if correction_hint:
                corrected_query = f"{correction_hint}\n\n질문: {ctx.query}"
                ctx.result = await ctx.generator.generate(corrected_query, ctx.chunks, ctx.sources)
                ctx.trace.append(
                    TraceStep(
                        step="fact_verification",
                        result=f"hallucination detected: {verification.hallucinated_entities}",
                        latency_ms=ms,
                        details={
                            "warnings": verification.warnings,
                            "corrected": True,
                        },
                    )
                )
                ctx.result.metadata["fact_verified"] = True
        else:
            ctx.trace.append(TraceStep(step="fact_verification", result="passed", latency_ms=ms))

        ctx.applied_processors.append(self.name)
        return ctx


class CompletenessProcessor(PostProcessor):
    """Verify multi-part answers cover all expected items.

    Detects queries that expect multiple items (e.g., "3가지 방법은?")
    and checks if the answer covers all of them.
    """

    @property
    def name(self) -> str:
        return "completeness"

    def should_run(self, ctx: CorrectionContext) -> bool:
        if ctx.use_map_reduce:
            return False
        return ctx.result.confidence != Confidence.INSUFFICIENT_EVIDENCE

    async def process(self, ctx: CorrectionContext) -> CorrectionContext:
        from quantumrag.core.generate.completeness import (
            detect_expected_parts,
            verify_completeness,
        )

        parts = detect_expected_parts(ctx.query)
        if not parts:
            return ctx

        completeness = verify_completeness(ctx.query, ctx.result.answer, parts)
        if not completeness.is_complete and completeness.missing_query:
            t0 = time.perf_counter()

            retry_result = await ctx.retriever.retrieve(
                completeness.missing_query,
                ctx.classification,
                ctx.top_k * 2,
                ctx.filters,
                ctx.rerank,
                ctx.pipeline_ctx,
            )

            seen = {sc.chunk.id for sc in ctx.chunks}
            for sc in retry_result.chunks:
                if sc.chunk.id not in seen:
                    ctx.chunks.append(sc)
                    seen.add(sc.chunk.id)
            ctx.chunks.sort(key=lambda x: x.score, reverse=True)

            ctx.result = await ctx.generator.generate(
                ctx.query, ctx.chunks, ctx.sources + retry_result.sources
            )

            ms = (time.perf_counter() - t0) * 1000
            ctx.trace.append(
                TraceStep(
                    step="completeness_verification",
                    result=(
                        f"missing {completeness.missing_items}, "
                        f"re-retrieved with {len(ctx.chunks)} chunks"
                    ),
                    latency_ms=ms,
                    details={
                        "missing_query": completeness.missing_query,
                        "found_items": completeness.found_items,
                        "missing_items": completeness.missing_items,
                        "query_type": parts.query_type,
                    },
                )
            )
            ctx.result.metadata["completeness_retry"] = True
            ctx.applied_processors.append(self.name)

        return ctx


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


class CorrectionPipeline:
    """Orchestrates post-generation correction processors.

    Runs each processor in order. If a processor upgrades the result
    confidence above INSUFFICIENT_EVIDENCE, subsequent retry-type
    processors are skipped (early exit).
    """

    def __init__(self, processors: list[PostProcessor] | None = None) -> None:
        self._processors = processors or self._default_processors()

    @staticmethod
    def _default_processors() -> list[PostProcessor]:
        """Standard correction chain: retry → self-correct → verify → completeness."""
        return [
            RetrievalRetryProcessor(),
            SelfCorrectProcessor(),
            FactVerificationProcessor(),
            CompletenessProcessor(),
        ]

    async def run(self, ctx: CorrectionContext) -> CorrectionContext:
        """Execute the correction pipeline."""
        for processor in self._processors:
            try:
                if not processor.should_run(ctx):
                    continue

                logger.info("postprocessor_running", processor=processor.name)
                ctx = await processor.process(ctx)
                logger.info(
                    "postprocessor_done",
                    processor=processor.name,
                    confidence=ctx.result.confidence.value,
                )
            except Exception as e:
                logger.debug(
                    "postprocessor_failed",
                    processor=processor.name,
                    error=str(e),
                )

        # Accumulate token usage from all generation calls
        _accumulate_token_usage(ctx)

        # Assemble final trace
        ctx.result.trace = ctx.trace + ctx.result.trace
        return ctx


def _accumulate_token_usage(ctx: CorrectionContext) -> None:
    """Sum token usage from all trace steps and expose in result metadata."""
    for step in ctx.trace + ctx.result.trace:
        if step.step == "generate" and step.details:
            ctx.total_tokens_in += step.details.get("tokens_in", 0)
            ctx.total_tokens_out += step.details.get("tokens_out", 0)
            ctx.total_estimated_cost += step.details.get("cost", 0.0)
            ctx.generation_count += 1

    ctx.result.metadata["token_usage"] = {
        "total_tokens_in": ctx.total_tokens_in,
        "total_tokens_out": ctx.total_tokens_out,
        "total_tokens": ctx.total_tokens_in + ctx.total_tokens_out,
        "total_estimated_cost": round(ctx.total_estimated_cost, 6),
        "generation_count": ctx.generation_count,
        "correction_processors": ctx.applied_processors,
    }
