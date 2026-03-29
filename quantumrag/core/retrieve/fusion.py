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
        # Chunk→document mapping built during search for coherence boost
        self._chunk_doc_map: dict[str, str] = {}

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
        weights: dict[str, float] | None = None,
    ) -> list[ScoredChunk]:
        """Run fusion search across all three indexes.

        Args:
            query: Search query text.
            top_k: Number of results to return.
            filters: Optional metadata filters.
            weights: Per-query weight overrides for RRF fusion.  Keys are
                ``"original"``, ``"hype"``, ``"bm25"``.  When *None* the
                instance-level ``self._weights`` are used.
        """
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

        # Adaptive fetch: scale with corpus size for better recall in larger corpora
        # Small corpus (< 100 chunks): 3x is enough
        # Large corpus (500+ chunks): need 5x to find signal in noise
        corpus_scale = 1.0
        try:
            count_fn = getattr(self._bm25_store, "count", None)
            if count_fn:
                result = count_fn()
                # Handle both sync and async count()
                if asyncio.iscoroutine(result):
                    bm25_count = await result
                else:
                    bm25_count = result
                if bm25_count and bm25_count > 200:
                    corpus_scale = min(bm25_count / 200, 2.0)
        except Exception:
            pass
        fetch_k = int(top_k * 3 * corpus_scale)
        original_task = self._vector_store.search(query_vector, top_k=fetch_k, filters=filters)
        hype_task = self._hype_vector_store.search(query_vector, top_k=fetch_k, filters=filters)
        bm25_task = self._bm25_store.search(query, top_k=fetch_k, filters=filters)

        original_results, hype_results, bm25_results = await asyncio.gather(
            original_task, hype_task, bm25_task
        )

        # Build chunk→document map from search results for coherence boost
        self._chunk_doc_map.clear()
        for result in original_results:
            doc_id = (result.metadata or {}).get("document_id", "")
            if doc_id:
                self._chunk_doc_map[result.id] = doc_id
        for result in bm25_results:  # type: ignore[union-attr]
            doc_id = (getattr(result, "metadata", None) or {}).get("document_id", "")
            if doc_id:
                self._chunk_doc_map[result.id] = doc_id

        # Map HyPE results back to chunk IDs
        hype_chunk_results = self._map_hype_to_chunks(hype_results)

        # Fuse with RRF (use per-query weights when provided)
        effective_weights = weights if weights is not None else self._weights
        fused = self._reciprocal_rank_fusion(
            original=original_results,
            hype=hype_chunk_results,
            bm25=bm25_results,
            weights=effective_weights,
        )

        # Document-level coherence boost: if multiple chunks from the same
        # document appear in top results, they are likely more relevant.
        # Boost scores of chunks from well-represented documents.
        fused = self._apply_document_coherence_boost(fused, top_k)

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
            weights=effective_weights,
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
        weights: dict[str, float] | None = None,
    ) -> list[tuple[str, float]]:
        """Combine results using Score-Weighted Reciprocal Rank Fusion.

        Enhanced RRF that incorporates raw similarity scores, not just ranks.
        This prevents low-similarity results from ranking high just because
        they appeared in multiple indexes.

        Formula: score[doc] = sum(weight * raw_score / (k + rank)) per index

        Args:
            weights: Optional weight overrides.  Falls back to
                ``self._weights`` when *None*.
        """
        scores: dict[str, float] = {}
        k = self._rrf_k

        w = weights if weights is not None else self._weights
        w_original = w.get("original", 0.4)
        w_hype = w.get("hype", 0.35)
        w_bm25 = w.get("bm25", 0.25)

        # Score-weighted RRF: multiply by raw similarity score
        # High-similarity results get full weight, low-similarity get reduced weight
        for rank, result in enumerate(original):
            raw_score = max(result.score, 0.0)
            scores[result.id] = scores.get(result.id, 0.0) + w_original * raw_score / (k + rank + 1)

        for rank, result in enumerate(hype):
            raw_score = max(result.score, 0.0)
            scores[result.id] = scores.get(result.id, 0.0) + w_hype * raw_score / (k + rank + 1)

        # Normalize BM25 scores to [0,1] using min-max within this result set
        # instead of capping at 1.0 (which loses signal discrimination)
        bm25_scores = [
            max(getattr(r, "score", 1.0), 0.0)
            for r in bm25  # type: ignore[union-attr]
        ]
        bm25_max = max(bm25_scores) if bm25_scores else 1.0
        bm25_min = min(bm25_scores) if bm25_scores else 0.0
        bm25_range = bm25_max - bm25_min if bm25_max > bm25_min else 1.0

        for rank, result in enumerate(bm25):  # type: ignore[assignment]
            raw = max(getattr(result, "score", 1.0), 0.0)
            # Min-max normalization preserves relative differences
            # When all scores are identical (or single result), use raw/max
            if bm25_max > bm25_min:
                normalized = (raw - bm25_min) / bm25_range
            else:
                normalized = min(raw / bm25_max, 1.0) if bm25_max > 0 else 1.0
            scores[result.id] = scores.get(result.id, 0.0) + w_bm25 * normalized / (k + rank + 1)

        # Normalize to [0, 1]
        max_score = max(scores.values()) if scores else 1.0
        if max_score > 0:
            scores = {cid: s / max_score for cid, s in scores.items()}

        # Sort by fused score descending
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    def _apply_document_coherence_boost(
        self,
        fused: list[tuple[str, float]],
        top_k: int,
    ) -> list[tuple[str, float]]:
        """Boost scores when multiple chunks from the same document appear in results.

        If a document has N chunks in the top candidates, each gets a small
        boost proportional to N. This helps when the correct answer is spread
        across multiple chunks of the same source document.

        Uses chunk metadata from BM25 results (which carry document_id) and
        the vector store's stored metadata to map chunk_id → document_id.
        Falls back to a prefix heuristic when metadata is unavailable.
        """
        if len(fused) < 2:
            return fused

        candidate_pool = fused[: top_k * 4]
        chunk_to_doc: dict[str, str] = {}

        # Try to resolve document_id via document_store metadata
        for chunk_id, _ in candidate_pool:
            # Use stored _chunk_doc_map if available (populated during search)
            doc_id = self._chunk_doc_map.get(chunk_id, "")
            if not doc_id:
                # Heuristic fallback: first 12 chars of chunk_id often share
                # a common prefix for chunks from the same document, but this
                # is unreliable.  Skip boost for unknown chunks.
                continue
            chunk_to_doc[chunk_id] = doc_id

        if not chunk_to_doc:
            return fused

        # Count chunks per document in candidate pool
        doc_counts: dict[str, int] = {}
        for doc_id in chunk_to_doc.values():
            doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1

        # Apply boost: +5% per additional chunk from same document (max +20%)
        boosted: list[tuple[str, float]] = []
        for chunk_id, score in fused:
            doc_id = chunk_to_doc.get(chunk_id, "")
            if doc_id and doc_counts.get(doc_id, 1) > 1:
                n_extra = min(doc_counts[doc_id] - 1, 4)  # Cap at 4 extras
                boost = 1.0 + n_extra * 0.05
                boosted.append((chunk_id, score * boost))
            else:
                boosted.append((chunk_id, score))

        boosted.sort(key=lambda x: x[1], reverse=True)
        return boosted


class ScoredChunk:
    """A chunk with its retrieval score."""

    __slots__ = ("chunk", "score")

    def __init__(self, chunk: Chunk, score: float) -> None:
        self.chunk = chunk
        self.score = score
