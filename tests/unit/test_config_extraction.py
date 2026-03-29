"""Tests for Sprint E2.2 — extracted magic numbers in config."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantumrag.core.config import GenerationOutputConfig, QuantumRAGConfig, RetrievalConfig
from quantumrag.core.generate.generator import Generator
from quantumrag.core.models import Chunk, Confidence
from quantumrag.core.retrieve.fusion import ScoredChunk
from quantumrag.core.retrieve.retriever import Retriever
from quantumrag.core.utils.text import detect_korean

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scored_chunk(
    content: str, score: float = 0.5, chunk_id: str = "c1", **meta: Any
) -> ScoredChunk:
    return ScoredChunk(
        chunk=Chunk(
            id=chunk_id,
            content=content,
            document_id="doc1",
            chunk_index=0,
            metadata=meta,
        ),
        score=score,
    )


def _make_fusion_mock(chunks: list[ScoredChunk] | None = None) -> MagicMock:
    fusion = MagicMock()
    fusion.search = AsyncMock(return_value=chunks or [])
    return fusion


# ---------------------------------------------------------------------------
# 1. Fusion candidate multiplier config
# ---------------------------------------------------------------------------


class TestFusionCandidateMultiplier:
    def test_retrieval_config_default(self) -> None:
        cfg = RetrievalConfig()
        assert cfg.fusion_candidate_multiplier == 5

    def test_full_config_default(self) -> None:
        cfg = QuantumRAGConfig.default()
        assert cfg.retrieval.fusion_candidate_multiplier == 5

    @pytest.mark.asyncio
    async def test_retriever_uses_multiplier(self) -> None:
        chunks = [_make_scored_chunk(f"c{i}", chunk_id=f"c{i}") for i in range(20)]
        fusion = _make_fusion_mock(chunks)
        retriever = Retriever(
            fusion_retriever=fusion,
            enable_rerank=False,
            enable_compression=False,
            fusion_candidate_multiplier=5,
        )
        await retriever.retrieve("test", top_k=4)
        # Should call search with top_k * 5 = 20
        fusion.search.assert_awaited_once()
        call_kwargs = fusion.search.call_args
        assert call_kwargs.kwargs["top_k"] == 20

    @pytest.mark.asyncio
    async def test_retriever_default_multiplier(self) -> None:
        chunks = [_make_scored_chunk(f"c{i}", chunk_id=f"c{i}") for i in range(15)]
        fusion = _make_fusion_mock(chunks)
        retriever = Retriever(
            fusion_retriever=fusion,
            enable_rerank=False,
            enable_compression=False,
        )
        await retriever.retrieve("test", top_k=5)
        call_kwargs = fusion.search.call_args
        assert call_kwargs.kwargs["top_k"] == 15  # 5 * 3


# ---------------------------------------------------------------------------
# 2. Confidence thresholds in generator
# ---------------------------------------------------------------------------


class TestConfidenceThresholds:
    def test_generation_config_defaults(self) -> None:
        cfg = GenerationOutputConfig()
        assert cfg.high_confidence_threshold == 0.8
        assert cfg.low_confidence_threshold == 0.5
        assert cfg.no_answer_penalty == 0.3

    def test_strongly_supported_from_score(self) -> None:
        llm = MagicMock()
        gen = Generator(llm_provider=llm, high_confidence_threshold=0.7)
        chunks = [_make_scored_chunk("text", score=0.75)]
        # Score 0.75 > 0.7 threshold -> STRONGLY_SUPPORTED
        result = gen._extract_confidence("some answer", chunks)
        assert result == Confidence.STRONGLY_SUPPORTED

    def test_partially_supported_from_score(self) -> None:
        llm = MagicMock()
        gen = Generator(llm_provider=llm, low_confidence_threshold=0.4)
        chunks = [_make_scored_chunk("text", score=0.45)]
        result = gen._extract_confidence("some answer", chunks)
        assert result == Confidence.PARTIALLY_SUPPORTED

    def test_insufficient_evidence_from_low_score(self) -> None:
        llm = MagicMock()
        gen = Generator(
            llm_provider=llm,
            high_confidence_threshold=0.8,
            low_confidence_threshold=0.5,
        )
        chunks = [_make_scored_chunk("text", score=0.3)]
        result = gen._extract_confidence("some answer", chunks)
        assert result == Confidence.INSUFFICIENT_EVIDENCE

    def test_custom_thresholds_override(self) -> None:
        llm = MagicMock()
        gen = Generator(
            llm_provider=llm,
            high_confidence_threshold=0.9,
            low_confidence_threshold=0.7,
        )
        # Score 0.85 is above default 0.8 but below custom 0.9
        chunks = [_make_scored_chunk("text", score=0.85)]
        result = gen._extract_confidence("some answer", chunks)
        assert result == Confidence.PARTIALLY_SUPPORTED

    @pytest.mark.asyncio
    async def test_no_answer_penalty_used(self) -> None:
        llm = MagicMock()
        gen = Generator(
            llm_provider=llm,
            confidence_threshold=0.6,
            no_answer_penalty=0.5,
        )
        # threshold * penalty = 0.6 * 0.5 = 0.3; score 0.25 < 0.3 -> insufficient
        chunks = [_make_scored_chunk("text", score=0.25)]
        sources = []
        result = await gen.generate("q", chunks, sources)
        assert result.confidence == Confidence.INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------------------
# 3. Korean detection threshold constant
# ---------------------------------------------------------------------------


class TestKoreanDetectionThreshold:
    def test_korean_text_detected(self) -> None:
        # More than 20% Korean characters
        assert detect_korean("안녕하세요 hello") is True

    def test_english_not_detected(self) -> None:
        assert detect_korean("hello world") is False

    def test_boundary(self) -> None:
        # Exactly at boundary — 1 Korean char out of 5 total = 0.2, not > 0.2
        assert detect_korean("가abcd") is False


# ---------------------------------------------------------------------------
# 4. Context size limit
# ---------------------------------------------------------------------------


class TestMaxContextChars:
    def test_generation_config_default(self) -> None:
        cfg = GenerationOutputConfig()
        assert cfg.max_context_chars == 16000

    def test_context_within_limit(self) -> None:
        llm = MagicMock()
        gen = Generator(llm_provider=llm, max_context_chars=8000)
        chunks = [_make_scored_chunk("short text", chunk_id=f"c{i}") for i in range(3)]
        ctx = gen._build_context(chunks)
        assert "[Source 1]" in ctx
        assert "[Source 3]" in ctx

    def test_context_truncated_at_limit(self) -> None:
        llm = MagicMock()
        gen = Generator(llm_provider=llm, max_context_chars=100)
        chunks = [
            _make_scored_chunk("A" * 80, chunk_id="c0"),
            _make_scored_chunk("B" * 80, chunk_id="c1"),
            _make_scored_chunk("C" * 80, chunk_id="c2"),
        ]
        ctx = gen._build_context(chunks)
        # First chunk always included; second would exceed limit
        assert "[Source 1]" in ctx
        assert "[Source 2]" not in ctx

    def test_first_chunk_always_included(self) -> None:
        """Even if a single chunk exceeds the limit, the first chunk is included."""
        llm = MagicMock()
        gen = Generator(llm_provider=llm, max_context_chars=10)
        chunks = [_make_scored_chunk("A" * 200, chunk_id="c0")]
        ctx = gen._build_context(chunks)
        assert "[Source 1]" in ctx
        assert "A" * 200 in ctx

    def test_exact_limit(self) -> None:
        llm = MagicMock()
        gen = Generator(llm_provider=llm, max_context_chars=500)
        # Build chunks that fit exactly and one that exceeds
        chunks = [_make_scored_chunk("x" * 50, chunk_id=f"c{i}") for i in range(10)]
        ctx = gen._build_context(chunks)
        assert len(ctx) <= 600  # generous upper bound including headers


# ---------------------------------------------------------------------------
# 5. Config roundtrip — new fields in YAML template
# ---------------------------------------------------------------------------


class TestConfigYamlRoundtrip:
    def test_new_retrieval_field_in_yaml(self, tmp_path: Any) -> None:
        cfg = QuantumRAGConfig.default()
        cfg.retrieval.fusion_candidate_multiplier = 5
        out = tmp_path / "cfg.yaml"
        cfg.to_yaml(out)
        restored = QuantumRAGConfig.from_yaml(out)
        assert restored.retrieval.fusion_candidate_multiplier == 5

    def test_new_generation_fields_in_yaml(self, tmp_path: Any) -> None:
        cfg = QuantumRAGConfig.default()
        cfg.generation.high_confidence_threshold = 0.9
        cfg.generation.low_confidence_threshold = 0.6
        cfg.generation.no_answer_penalty = 0.4
        cfg.generation.max_context_chars = 4000
        out = tmp_path / "cfg.yaml"
        cfg.to_yaml(out)
        restored = QuantumRAGConfig.from_yaml(out)
        assert restored.generation.high_confidence_threshold == 0.9
        assert restored.generation.low_confidence_threshold == 0.6
        assert restored.generation.no_answer_penalty == 0.4
        assert restored.generation.max_context_chars == 4000
