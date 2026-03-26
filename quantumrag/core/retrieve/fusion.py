"""Triple Index Fusion retrieval — combines Original Embedding, HyPE Embedding, and BM25."""

from __future__ import annotations

import asyncio
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk
from quantumrag.core.storage.base import BM25SearchResult, VectorSearchResult

logger = get_logger("quantumrag.retrieve")


class FusionRetriever:
    """Fuses results from Triple Index using Reciprocal Rank Fusion (RRF).

    The three indexes:
    1. Original Embedding: direct semantic match
    2. HyPE Embedding: question-to-question match
    3. Contextual BM25: keyword + context match
    """

    def __init__(
        self,
        vector_store: Any,  # VectorStore for original embeddings
        hype_vector_store: Any,  # VectorStore for HyPE embeddings
        bm25_store: Any,  # BM25Store
        embedding_provider: Any,  # EmbeddingProvider
        document_store: Any,  # DocumentStore for chunk retrieval
        weights: dict[str, float] | None = None,
        rrf_k: int = 60,  # RRF constant
    ) -> None:
        self._vector_store = vector_store
        self._hype_vector_store = hype_vector_store
        self._bm25_store = bm25_store
        self._embedding_provider = embedding_provider
        self._document_store = document_store
        self._weights = weights or {"original": 0.4, "hype": 0.35, "bm25": 0.25}
        self._rrf_k = rrf_k
        # LRU embedding cache — avoids redundant embedding calls for similar queries
        self._embed_cache: dict[str, list[float]] = {}
        self._cache_max = 32

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredChunk]:
        """Run fusion search across all three indexes."""
        # Embed query once, use for both vector searches (with cache)
        if query in self._embed_cache:
            query_vector = self._embed_cache[query]
        else:
            query_vector = await self._embedding_provider.embed_query(query)
            if len(self._embed_cache) >= self._cache_max:
                # Evict oldest entry
                oldest = next(iter(self._embed_cache))
                del self._embed_cache[oldest]
            self._embed_cache[query] = query_vector

        # Run all three searches in parallel
        original_task = self._vector_store.search(query_vector, top_k=top_k * 2, filters=filters)
        hype_task = self._hype_vector_store.search(query_vector, top_k=top_k * 2, filters=filters)
        bm25_task = self._bm25_store.search(query, top_k=top_k * 2, filters=filters)

        original_results, hype_results, bm25_results = await asyncio.gather(
            original_task, hype_task, bm25_task
        )

        # Map HyPE results back to chunk IDs
        hype_chunk_results = self._map_hype_to_chunks(hype_results)

        # Fuse with RRF
        fused = self._reciprocal_rank_fusion(
            original=original_results,
            hype=hype_chunk_results,
            bm25=bm25_results,
        )

        # Take top_k and retrieve full chunks in a single batch query
        top_ids = [item[0] for item in fused[:top_k]]
        top_scores = {item[0]: item[1] for item in fused[:top_k]}

        # Use batch retrieval if available, otherwise fall back to individual queries
        if hasattr(self._document_store, "get_chunks_batch"):
            chunks_map = await self._document_store.get_chunks_batch(top_ids)
            scored_chunks = [
                ScoredChunk(chunk=chunks_map[cid], score=top_scores[cid])
                for cid in top_ids
                if cid in chunks_map
            ]
        else:
            scored_chunks = []
            for chunk_id in top_ids:
                chunk = await self._document_store.get_chunk(chunk_id)
                if chunk:
                    scored_chunks.append(ScoredChunk(chunk=chunk, score=top_scores[chunk_id]))

        logger.debug(
            "fusion_search_complete",
            query_len=len(query),
            original_hits=len(original_results),
            hype_hits=len(hype_results),
            bm25_hits=len(bm25_results),
            fused_results=len(scored_chunks),
        )
        return scored_chunks

    def _map_hype_to_chunks(
        self, hype_results: list[VectorSearchResult]
    ) -> list[VectorSearchResult]:
        """Map HyPE question results back to their source chunk IDs."""
        chunk_scores: dict[str, float] = {}
        chunk_metadata: dict[str, dict[str, Any]] = {}

        for result in hype_results:
            chunk_id = result.metadata.get("chunk_id", "")
            if not chunk_id:
                # Try extracting from ID format: {chunk_id}_hype_{n}
                parts = result.id.rsplit("_hype_", 1)
                chunk_id = parts[0] if len(parts) == 2 else result.id

            # Keep the best score for each chunk
            if chunk_id not in chunk_scores or result.score > chunk_scores[chunk_id]:
                chunk_scores[chunk_id] = result.score
                chunk_metadata[chunk_id] = result.metadata

        return [
            VectorSearchResult(id=cid, score=score, metadata=chunk_metadata.get(cid))
            for cid, score in chunk_scores.items()
        ]

    def _reciprocal_rank_fusion(
        self,
        original: list[VectorSearchResult],
        hype: list[VectorSearchResult],
        bm25: list[BM25SearchResult],
    ) -> list[tuple[str, float]]:
        """Combine results using Reciprocal Rank Fusion.

        RRF score = sum(weight / (k + rank)) for each result list
        """
        scores: dict[str, float] = {}
        k = self._rrf_k

        w_original = self._weights.get("original", 0.4)
        w_hype = self._weights.get("hype", 0.35)
        w_bm25 = self._weights.get("bm25", 0.25)

        for rank, result in enumerate(original):
            scores[result.id] = scores.get(result.id, 0.0) + w_original / (k + rank + 1)

        for rank, result in enumerate(hype):
            scores[result.id] = scores.get(result.id, 0.0) + w_hype / (k + rank + 1)

        for rank, result in enumerate(bm25):
            scores[result.id] = scores.get(result.id, 0.0) + w_bm25 / (k + rank + 1)

        # Normalize scores to [0, 1] range.
        # Max possible RRF score = sum(weights) / (k + 1) when a doc is rank-1 in all lists.
        max_score = (w_original + w_hype + w_bm25) / (k + 1)
        if max_score > 0:
            scores = {cid: s / max_score for cid, s in scores.items()}

        # Sort by fused score descending
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class ScoredChunk:
    """A chunk with its retrieval score."""

    __slots__ = ("chunk", "score")

    def __init__(self, chunk: Chunk, score: float) -> None:
        self.chunk = chunk
        self.score = score
