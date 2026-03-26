"""Tests for retrieval components."""

from __future__ import annotations

import pytest

from quantumrag.core.generate.router import QueryRouter
from quantumrag.core.models import Chunk, QueryComplexity
from quantumrag.core.retrieve.compressor import (
    ExtractiveCompressor,
    NoopCompressor,
)
from quantumrag.core.retrieve.fusion import ScoredChunk
from quantumrag.core.retrieve.reranker import NoopReranker
from quantumrag.core.utils.text import split_sentences


class TestQueryRouter:
    def setup_method(self) -> None:
        self.router = QueryRouter()

    def test_simple_factual(self) -> None:
        result = self.router.classify("What is the company revenue?")
        assert result.complexity == QueryComplexity.SIMPLE
        assert result.needs_retrieval is True

    def test_medium_how_question(self) -> None:
        result = self.router.classify("How does the authentication system work?")
        assert result.complexity == QueryComplexity.MEDIUM

    def test_medium_why_question(self) -> None:
        result = self.router.classify("Why did the revenue decrease?")
        assert result.complexity == QueryComplexity.MEDIUM

    def test_complex_comparison(self) -> None:
        result = self.router.classify("Compare the revenue between Q1 and Q2")
        assert result.complexity == QueryComplexity.COMPLEX

    def test_complex_multi_question(self) -> None:
        result = self.router.classify("What was the revenue? And how does it compare to last year?")
        assert result.complexity == QueryComplexity.COMPLEX

    def test_korean_simple(self) -> None:
        result = self.router.classify("매출액은 얼마인가요?")
        assert result.complexity == QueryComplexity.SIMPLE

    def test_korean_complex(self) -> None:
        result = self.router.classify("1분기와 2분기의 매출을 비교해주세요")
        assert result.complexity == QueryComplexity.COMPLEX

    def test_self_routing_greeting(self) -> None:
        result = self.router.classify("안녕하세요")
        assert result.needs_retrieval is False

    def test_self_routing_math(self) -> None:
        result = self.router.classify("3 + 5")
        assert result.needs_retrieval is False

    def test_query_type_comparative(self) -> None:
        result = self.router.classify("What is the difference between A and B?")
        assert result.query_type == "comparative"

    def test_query_type_procedural(self) -> None:
        result = self.router.classify("How to set up the system?")
        assert result.query_type == "procedural"

    def test_query_type_factual(self) -> None:
        result = self.router.classify("What is the capital?")
        assert result.query_type == "factual"


def _make_scored_chunk(content: str, score: float = 0.5, chunk_id: str = "c1") -> ScoredChunk:
    return ScoredChunk(
        chunk=Chunk(id=chunk_id, content=content, document_id="doc1", chunk_index=0),
        score=score,
    )


class TestNoopReranker:
    @pytest.mark.asyncio
    async def test_returns_top_k(self) -> None:
        reranker = NoopReranker()
        chunks = [_make_scored_chunk(f"chunk {i}", chunk_id=f"c{i}") for i in range(10)]
        result = await reranker.rerank("query", chunks, top_k=3)
        assert len(result) == 3


class TestExtractiveCompressor:
    @pytest.mark.asyncio
    async def test_compression(self) -> None:
        compressor = ExtractiveCompressor()
        chunk = _make_scored_chunk(
            "Machine learning is a subset of AI. "
            "It uses data to learn patterns. "
            "Deep learning is a type of ML. "
            "Neural networks are the foundation.",
        )
        result = await compressor.compress("machine learning", [chunk], ratio=0.5)
        assert len(result) == 1
        # Should have fewer sentences
        original_len = len(chunk.chunk.content)
        compressed_len = len(result[0].chunk.content)
        assert compressed_len <= original_len

    @pytest.mark.asyncio
    async def test_short_chunk_preserved(self) -> None:
        compressor = ExtractiveCompressor()
        chunk = _make_scored_chunk("Short text.")
        result = await compressor.compress("query", [chunk], ratio=0.5)
        assert result[0].chunk.content == "Short text."

    @pytest.mark.asyncio
    async def test_noop_at_full_ratio(self) -> None:
        compressor = ExtractiveCompressor()
        chunk = _make_scored_chunk("Full text preserved. Multiple sentences here.")
        result = await compressor.compress("query", [chunk], ratio=1.0)
        assert result[0].chunk.content == chunk.chunk.content


class TestNoopCompressor:
    @pytest.mark.asyncio
    async def test_passthrough(self) -> None:
        compressor = NoopCompressor()
        chunks = [_make_scored_chunk("text")]
        result = await compressor.compress("query", chunks)
        assert len(result) == 1


class TestSentenceSplitting:
    def test_english(self) -> None:
        sentences = split_sentences("Hello world. How are you? I'm fine!")
        assert len(sentences) == 3

    def test_korean(self) -> None:
        sentences = split_sentences("안녕하세요. 반갑습니다.")
        assert len(sentences) == 2

    def test_empty(self) -> None:
        sentences = split_sentences("")
        assert sentences == []
