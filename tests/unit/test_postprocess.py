"""Tests for the post-generation correction pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from quantumrag.core.models import Confidence, QueryResult, Source, TraceStep
from quantumrag.core.pipeline.postprocess import (
    CompletenessProcessor,
    CorrectionContext,
    CorrectionPipeline,
    FactVerificationProcessor,
    RetrievalRetryProcessor,
    SelfCorrectProcessor,
    _accumulate_token_usage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    answer: str = "Test answer",
    confidence: Confidence = Confidence.STRONGLY_SUPPORTED,
    trace: list[TraceStep] | None = None,
    metadata: dict[str, Any] | None = None,
) -> QueryResult:
    return QueryResult(
        answer=answer,
        sources=[Source(chunk_id="c1", excerpt="test")],
        confidence=confidence,
        trace=trace or [],
        metadata=metadata or {},
    )


@dataclass
class FakeChunk:
    id: str = "chunk-1"
    content: str = "Fake chunk content"
    document_id: str = "doc-1"
    chunk_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeScoredChunk:
    chunk: FakeChunk = field(default_factory=FakeChunk)
    score: float = 0.9


class FakeRetrievalResult:
    def __init__(self) -> None:
        self.chunks = [FakeScoredChunk()]
        self.sources = [Source(chunk_id="c2", excerpt="retry source")]
        self.trace: list[TraceStep] = []


def _make_ctx(
    confidence: Confidence = Confidence.STRONGLY_SUPPORTED,
    answer: str = "Test answer",
    chunks: list | None = None,
    use_map_reduce: bool = False,
    retrieval_retry_config: bool = True,
) -> CorrectionContext:
    result = _make_result(answer=answer, confidence=confidence)
    generator = AsyncMock()
    generator.generate.return_value = _make_result(
        answer="Corrected answer", confidence=Confidence.STRONGLY_SUPPORTED
    )

    retriever = AsyncMock()
    retriever.retrieve.return_value = FakeRetrievalResult()
    retriever.retrieve_bm25_dominant.return_value = FakeRetrievalResult()

    config = MagicMock()
    config.retrieval.retrieval_retry = retrieval_retry_config

    return CorrectionContext(
        query="Test query",
        result=result,
        chunks=chunks if chunks is not None else [FakeScoredChunk()],
        sources=[Source(chunk_id="c1", excerpt="test")],
        classification=MagicMock(),
        top_k=10,
        filters=None,
        rerank=None,
        pipeline_ctx=None,
        generator=generator,
        retriever=retriever,
        trace=[],
        use_map_reduce=use_map_reduce,
        config=config,
    )


# ---------------------------------------------------------------------------
# RetrievalRetryProcessor
# ---------------------------------------------------------------------------


class TestRetrievalRetryProcessor:
    def test_should_not_run_on_strongly_supported(self) -> None:
        ctx = _make_ctx(confidence=Confidence.STRONGLY_SUPPORTED)
        proc = RetrievalRetryProcessor()
        assert proc.should_run(ctx) is False

    def test_should_not_run_on_map_reduce(self) -> None:
        ctx = _make_ctx(confidence=Confidence.INSUFFICIENT_EVIDENCE, use_map_reduce=True)
        proc = RetrievalRetryProcessor()
        assert proc.should_run(ctx) is False

    def test_should_not_run_when_config_disabled(self) -> None:
        ctx = _make_ctx(
            confidence=Confidence.INSUFFICIENT_EVIDENCE,
            retrieval_retry_config=False,
        )
        proc = RetrievalRetryProcessor()
        assert proc.should_run(ctx) is False

    def test_should_run_on_insufficient_with_chunks(self) -> None:
        ctx = _make_ctx(confidence=Confidence.INSUFFICIENT_EVIDENCE)
        proc = RetrievalRetryProcessor()
        assert proc.should_run(ctx) is True

    def test_should_not_run_with_empty_chunks(self) -> None:
        ctx = _make_ctx(confidence=Confidence.INSUFFICIENT_EVIDENCE, chunks=[])
        proc = RetrievalRetryProcessor()
        assert proc.should_run(ctx) is False

    def test_process_calls_bm25_dominant(self) -> None:
        ctx = _make_ctx(confidence=Confidence.INSUFFICIENT_EVIDENCE)
        proc = RetrievalRetryProcessor()
        ctx = asyncio.run(proc.process(ctx))

        ctx.retriever.retrieve_bm25_dominant.assert_called_once()
        assert "retrieval_retry" in ctx.applied_processors

    def test_name(self) -> None:
        assert RetrievalRetryProcessor().name == "retrieval_retry"


# ---------------------------------------------------------------------------
# SelfCorrectProcessor
# ---------------------------------------------------------------------------


class TestSelfCorrectProcessor:
    def test_should_not_run_when_retry_already_applied(self) -> None:
        ctx = _make_ctx(confidence=Confidence.INSUFFICIENT_EVIDENCE)
        ctx.applied_processors.append("retrieval_retry")
        proc = SelfCorrectProcessor()
        assert proc.should_run(ctx) is False

    def test_should_not_run_on_sufficient_answer(self) -> None:
        ctx = _make_ctx(confidence=Confidence.STRONGLY_SUPPORTED)
        proc = SelfCorrectProcessor()
        assert proc.should_run(ctx) is False

    def test_should_not_run_on_map_reduce(self) -> None:
        ctx = _make_ctx(confidence=Confidence.INSUFFICIENT_EVIDENCE, use_map_reduce=True)
        proc = SelfCorrectProcessor()
        assert proc.should_run(ctx) is False

    def test_should_run_on_insufficient_short_answer(self) -> None:
        ctx = _make_ctx(
            confidence=Confidence.INSUFFICIENT_EVIDENCE,
            answer="정보가 없습니다.",  # Short + insufficiency pattern
        )
        proc = SelfCorrectProcessor()
        assert proc.should_run(ctx) is True

    def test_process_calls_retrieve(self) -> None:
        ctx = _make_ctx(
            confidence=Confidence.INSUFFICIENT_EVIDENCE,
            answer="충분한 정보가 없습니다.",
        )
        proc = SelfCorrectProcessor()
        ctx = asyncio.run(proc.process(ctx))

        ctx.retriever.retrieve.assert_called_once()
        assert "self_correct" in ctx.applied_processors

    def test_name(self) -> None:
        assert SelfCorrectProcessor().name == "self_correct"


# ---------------------------------------------------------------------------
# FactVerificationProcessor
# ---------------------------------------------------------------------------


class TestFactVerificationProcessor:
    def test_should_not_run_on_insufficient(self) -> None:
        ctx = _make_ctx(confidence=Confidence.INSUFFICIENT_EVIDENCE)
        proc = FactVerificationProcessor()
        assert proc.should_run(ctx) is False

    def test_should_run_on_supported(self) -> None:
        ctx = _make_ctx(confidence=Confidence.STRONGLY_SUPPORTED)
        proc = FactVerificationProcessor()
        assert proc.should_run(ctx) is True

    def test_should_not_run_on_map_reduce(self) -> None:
        ctx = _make_ctx(confidence=Confidence.STRONGLY_SUPPORTED, use_map_reduce=True)
        proc = FactVerificationProcessor()
        assert proc.should_run(ctx) is False

    def test_should_not_run_with_empty_chunks(self) -> None:
        ctx = _make_ctx(confidence=Confidence.STRONGLY_SUPPORTED, chunks=[])
        proc = FactVerificationProcessor()
        assert proc.should_run(ctx) is False

    def test_name(self) -> None:
        assert FactVerificationProcessor().name == "fact_verification"


# ---------------------------------------------------------------------------
# CompletenessProcessor
# ---------------------------------------------------------------------------


class TestCompletenessProcessor:
    def test_should_not_run_on_insufficient(self) -> None:
        ctx = _make_ctx(confidence=Confidence.INSUFFICIENT_EVIDENCE)
        proc = CompletenessProcessor()
        assert proc.should_run(ctx) is False

    def test_should_run_on_supported(self) -> None:
        ctx = _make_ctx(confidence=Confidence.STRONGLY_SUPPORTED)
        proc = CompletenessProcessor()
        assert proc.should_run(ctx) is True

    def test_should_not_run_on_map_reduce(self) -> None:
        ctx = _make_ctx(confidence=Confidence.STRONGLY_SUPPORTED, use_map_reduce=True)
        proc = CompletenessProcessor()
        assert proc.should_run(ctx) is False

    def test_process_skips_when_no_parts_detected(self) -> None:
        ctx = _make_ctx(confidence=Confidence.STRONGLY_SUPPORTED)
        ctx.query = "단순한 질문입니다"
        proc = CompletenessProcessor()
        ctx = asyncio.run(proc.process(ctx))
        # Should not trigger retrieval for simple queries
        ctx.retriever.retrieve.assert_not_called()

    def test_name(self) -> None:
        assert CompletenessProcessor().name == "completeness"


# ---------------------------------------------------------------------------
# CorrectionPipeline
# ---------------------------------------------------------------------------


class TestCorrectionPipeline:
    def test_default_processors_count(self) -> None:
        pipeline = CorrectionPipeline()
        assert len(pipeline._processors) == 4

    def test_happy_path_skips_retry_processors(self) -> None:
        """When confidence is high, retry processors should not fire."""
        ctx = _make_ctx(confidence=Confidence.STRONGLY_SUPPORTED)
        pipeline = CorrectionPipeline()
        result_ctx = asyncio.run(pipeline.run(ctx))

        # Retry/self-correct should not fire on strong confidence
        assert "retrieval_retry" not in result_ctx.applied_processors
        assert "self_correct" not in result_ctx.applied_processors
        # Fact verification runs on supported answers (hallucination check)
        assert "fact_verification" in result_ctx.applied_processors
        ctx.retriever.retrieve_bm25_dominant.assert_not_called()

    def test_retry_and_self_correct_mutual_exclusion(self) -> None:
        """When retrieval retry runs, self-correct should skip."""
        ctx = _make_ctx(
            confidence=Confidence.INSUFFICIENT_EVIDENCE,
            answer="충분한 정보가 없습니다.",
        )
        pipeline = CorrectionPipeline()
        result_ctx = asyncio.run(pipeline.run(ctx))

        # RetrievalRetry should fire (config enabled + INSUFFICIENT)
        assert "retrieval_retry" in result_ctx.applied_processors
        # SelfCorrect should NOT fire (mutual exclusion)
        assert "self_correct" not in result_ctx.applied_processors

    def test_pipeline_assembles_trace(self) -> None:
        ctx = _make_ctx(confidence=Confidence.STRONGLY_SUPPORTED)
        ctx.trace = [TraceStep(step="test_step", result="ok", latency_ms=0)]
        pipeline = CorrectionPipeline()
        result_ctx = asyncio.run(pipeline.run(ctx))

        # Trace should include the pre-existing step
        all_steps = [s.step for s in result_ctx.result.trace]
        assert "test_step" in all_steps

    def test_custom_processor_list(self) -> None:
        pipeline = CorrectionPipeline(processors=[RetrievalRetryProcessor()])
        assert len(pipeline._processors) == 1

    def test_processor_exception_does_not_crash_pipeline(self) -> None:
        """If a processor throws, pipeline continues with remaining."""

        class BrokenProcessor(RetrievalRetryProcessor):
            def should_run(self, ctx: CorrectionContext) -> bool:
                return True

            async def process(self, ctx: CorrectionContext) -> CorrectionContext:
                raise RuntimeError("Intentional failure")

        ctx = _make_ctx(confidence=Confidence.STRONGLY_SUPPORTED)
        pipeline = CorrectionPipeline(processors=[BrokenProcessor()])
        result_ctx = asyncio.run(pipeline.run(ctx))

        # Pipeline should survive the exception
        assert result_ctx.result.answer == "Test answer"


# ---------------------------------------------------------------------------
# Token Accumulation
# ---------------------------------------------------------------------------


class TestTokenAccumulation:
    def test_accumulates_from_trace(self) -> None:
        ctx = _make_ctx()
        ctx.trace = [
            TraceStep(
                step="generate",
                result="100 tokens",
                latency_ms=500,
                details={"tokens_in": 200, "tokens_out": 100, "cost": 0.001},
            ),
        ]
        ctx.result.trace = [
            TraceStep(
                step="generate",
                result="50 tokens",
                latency_ms=300,
                details={"tokens_in": 150, "tokens_out": 50, "cost": 0.0005},
            ),
        ]

        _accumulate_token_usage(ctx)

        usage = ctx.result.metadata["token_usage"]
        assert usage["total_tokens_in"] == 350
        assert usage["total_tokens_out"] == 150
        assert usage["total_tokens"] == 500
        assert usage["generation_count"] == 2
        assert usage["total_estimated_cost"] == 0.0015

    def test_no_generate_steps(self) -> None:
        ctx = _make_ctx()
        ctx.trace = [
            TraceStep(step="retrieve", result="ok", latency_ms=100),
        ]
        ctx.result.trace = []

        _accumulate_token_usage(ctx)

        usage = ctx.result.metadata["token_usage"]
        assert usage["total_tokens"] == 0
        assert usage["generation_count"] == 0
