"""Tests for fusion retrieval — RRF scoring and score-weighted fusion."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from quantumrag.core.retrieve.fusion import FusionRetriever
from quantumrag.core.storage.base import BM25SearchResult, VectorSearchResult


def _make_vector_result(id: str, score: float) -> VectorSearchResult:
    return VectorSearchResult(id=id, score=score, metadata={})


def _make_bm25_result(id: str, score: float) -> BM25SearchResult:
    return BM25SearchResult(id=id, score=score)


class TestRRF:
    """Test Reciprocal Rank Fusion scoring."""

    def _make_retriever(self, weights: dict[str, float] | None = None) -> FusionRetriever:
        return FusionRetriever(
            vector_store=MagicMock(),
            hype_vector_store=MagicMock(),
            bm25_store=MagicMock(),
            embedding_provider=MagicMock(),
            document_store=MagicMock(),
            weights=weights,
        )

    def test_single_index_ranking(self) -> None:
        r = self._make_retriever({"original": 1.0, "hype": 0.0, "bm25": 0.0})
        original = [_make_vector_result("a", 0.9), _make_vector_result("b", 0.5)]
        fused = r._reciprocal_rank_fusion(original, [], [])
        ids = [item[0] for item in fused]
        assert ids[0] == "a"
        assert ids[1] == "b"
        # Higher raw score should get higher fused score
        assert fused[0][1] > fused[1][1]

    def test_score_weighting_suppresses_low_similarity(self) -> None:
        r = self._make_retriever({"original": 1.0, "hype": 0.0, "bm25": 0.0})
        # "a" has high similarity, "b" has low
        original = [_make_vector_result("a", 0.95), _make_vector_result("b", 0.1)]
        fused = r._reciprocal_rank_fusion(original, [], [])
        scores = {item[0]: item[1] for item in fused}
        # Score ratio should reflect raw score difference
        assert scores["a"] / scores["b"] > 5  # Much higher, not just rank-based

    def test_multi_index_boost(self) -> None:
        r = self._make_retriever({"original": 0.35, "hype": 0.15, "bm25": 0.50})
        # "a" appears in all three indexes
        original = [_make_vector_result("a", 0.8), _make_vector_result("b", 0.7)]
        hype = [_make_vector_result("a", 0.7)]
        bm25 = [_make_bm25_result("a", 0.9), _make_bm25_result("c", 0.6)]
        fused = r._reciprocal_rank_fusion(original, hype, bm25)
        ids = [item[0] for item in fused]
        # "a" should be first (appears in all 3)
        assert ids[0] == "a"

    def test_bm25_dominant_weights(self) -> None:
        r = self._make_retriever({"original": 0.15, "hype": 0.15, "bm25": 0.70})
        original = [_make_vector_result("a", 0.9)]
        bm25 = [_make_bm25_result("b", 0.9)]
        fused = r._reciprocal_rank_fusion(original, [], bm25)
        scores = {item[0]: item[1] for item in fused}
        # BM25 result should score higher with 0.70 weight
        assert scores["b"] > scores["a"]

    def test_empty_results(self) -> None:
        r = self._make_retriever()
        fused = r._reciprocal_rank_fusion([], [], [])
        assert fused == []

    def test_normalization(self) -> None:
        r = self._make_retriever({"original": 0.35, "hype": 0.15, "bm25": 0.50})
        original = [_make_vector_result("a", 1.0)]
        fused = r._reciprocal_rank_fusion(original, [], [])
        # Max score should be normalized to 1.0
        assert fused[0][1] == 1.0

    def test_default_weights(self) -> None:
        r = self._make_retriever()
        # Default from config: original=0.35, hype=0.15, bm25=0.50
        # But FusionRetriever.__init__ fallback is {"original": 0.4, "hype": 0.35, "bm25": 0.25}
        # Engine overrides with config values at construction time
        assert sum(r._weights.values()) == pytest.approx(1.0)


class TestHypeMapping:
    """Test HyPE result mapping to source chunks."""

    def _make_retriever(self) -> FusionRetriever:
        return FusionRetriever(
            vector_store=MagicMock(),
            hype_vector_store=MagicMock(),
            bm25_store=MagicMock(),
            embedding_provider=MagicMock(),
            document_store=MagicMock(),
        )

    def test_maps_hype_to_chunk_id(self) -> None:
        r = self._make_retriever()
        hype_results = [
            VectorSearchResult(id="chunk1_hype_0", score=0.8, metadata={"chunk_id": "chunk1"}),
            VectorSearchResult(id="chunk1_hype_1", score=0.7, metadata={"chunk_id": "chunk1"}),
            VectorSearchResult(id="chunk2_hype_0", score=0.6, metadata={"chunk_id": "chunk2"}),
        ]
        mapped = r._map_hype_to_chunks(hype_results)
        ids = {m.id for m in mapped}
        assert ids == {"chunk1", "chunk2"}
        # chunk1 should keep best score (0.8)
        chunk1 = next(m for m in mapped if m.id == "chunk1")
        assert chunk1.score == 0.8

    def test_extracts_chunk_id_from_format(self) -> None:
        r = self._make_retriever()
        hype_results = [
            VectorSearchResult(id="abc123_hype_2", score=0.5, metadata={}),
        ]
        mapped = r._map_hype_to_chunks(hype_results)
        assert mapped[0].id == "abc123"

    def test_empty_input(self) -> None:
        r = self._make_retriever()
        assert r._map_hype_to_chunks([]) == []


class TestDocCoherenceBoost:
    """Test document coherence boost in engine."""

    def test_boost_applied(self) -> None:
        from quantumrag.core.engine import _apply_doc_coherence_boost

        chunk1 = MagicMock()
        chunk1.chunk.document_id = "doc1"
        chunk1.score = 0.8

        chunk2 = MagicMock()
        chunk2.chunk.document_id = "doc1"
        chunk2.score = 0.7

        chunk3 = MagicMock()
        chunk3.chunk.document_id = "doc2"
        chunk3.score = 0.75

        result = _apply_doc_coherence_boost([chunk1, chunk2, chunk3])
        # doc1 chunks should be boosted (2 siblings → +5%)
        assert result[0].score > 0.8  # chunk1 boosted
        # doc2 single chunk should not be boosted
        assert chunk3.score == 0.75

    def test_no_boost_single_docs(self) -> None:
        from quantumrag.core.engine import _apply_doc_coherence_boost

        chunk1 = MagicMock()
        chunk1.chunk.document_id = "doc1"
        chunk1.score = 0.8

        result = _apply_doc_coherence_boost([chunk1])
        assert chunk1.score == 0.8  # No boost
