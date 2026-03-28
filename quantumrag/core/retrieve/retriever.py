"""Retriever orchestrator — search -> rerank -> compress pipeline.

Includes 2-Pass Retrieval with Sibling Expansion: after initial fusion search,
automatically includes sibling chunks from the same parent section to capture
fragmented information (e.g., "확정 PoC" + "진행 중 PoC" siblings).
"""

from __future__ import annotations

import time
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Source, TraceStep
from quantumrag.core.pipeline.context import InformationType, PipelineContext
from quantumrag.core.pipeline.signals import (
    chunk_needs_expansion,
    chunk_should_skip_compression,
    read_chunk_signal,
)
from quantumrag.core.retrieve.compressor import Compressor, ExtractiveCompressor, NoopCompressor
from quantumrag.core.retrieve.fusion import FusionRetriever, ScoredChunk
from quantumrag.core.retrieve.query_classifier import detect_query_type
from quantumrag.core.retrieve.reranker import NoopReranker, Reranker

logger = get_logger("quantumrag.retriever")


def _share_parent_section(chunk_a: Any, chunk_b: Any) -> bool:
    """Check if two chunks share a parent breadcrumb section.

    Compares breadcrumb prefixes: if chunk_a is [Doc > Section > Sub1]
    and chunk_b is [Doc > Section > Sub2], they share parent [Doc > Section].
    Also matches chunks from the same document that are adjacent by index.
    """
    bc_a = chunk_a.metadata.get("breadcrumb", "")
    bc_b = chunk_b.metadata.get("breadcrumb", "")

    if bc_a and bc_b:
        # Extract parent by removing the last segment
        parts_a = bc_a.strip("[]").rsplit(" > ", 1)
        parts_b = bc_b.strip("[]").rsplit(" > ", 1)
        if len(parts_a) > 1 and len(parts_b) > 1 and parts_a[0] == parts_b[0]:
            return True

    # Fallback: same document and close chunk index
    doc_a = chunk_a.metadata.get(
        "document_id", chunk_a.document_id if hasattr(chunk_a, "document_id") else ""
    )
    doc_b = chunk_b.metadata.get(
        "document_id", chunk_b.document_id if hasattr(chunk_b, "document_id") else ""
    )
    if doc_a and doc_a == doc_b:
        idx_a = chunk_a.metadata.get("chunk_index", -1)
        idx_b = chunk_b.metadata.get("chunk_index", -1)
        if idx_a >= 0 and idx_b >= 0 and abs(idx_a - idx_b) <= 2:
            return True

    return False


class Retriever:
    """Orchestrates the full retrieval pipeline: search -> rerank -> compress.

    Includes 2-Pass Retrieval:
    - Pass 1: Standard Triple Index Fusion search
    - Pass 2: Sibling/adjacent chunk expansion for captured chunks
    """

    def __init__(
        self,
        fusion_retriever: FusionRetriever,
        reranker: Reranker | None = None,
        compressor: Compressor | None = None,
        enable_rerank: bool = True,
        enable_compression: bool = True,
        compression_ratio: float = 0.5,
        slow_threshold_ms: int = 2000,
        fusion_candidate_multiplier: int = 3,
        document_store: Any | None = None,
        enable_sibling_expansion: bool = True,
    ) -> None:
        self._fusion = fusion_retriever
        self._reranker: Reranker = reranker if reranker and enable_rerank else NoopReranker()
        self._compressor: Compressor = (
            compressor
            if compressor and enable_compression
            else (ExtractiveCompressor() if enable_compression else NoopCompressor())
        )
        self._compression_ratio = compression_ratio
        self._slow_threshold_ms = slow_threshold_ms
        self._fusion_candidate_multiplier = fusion_candidate_multiplier
        self._document_store = document_store
        self._enable_sibling_expansion = enable_sibling_expansion and document_store is not None

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
        skip_rerank: bool = False,
        skip_compression: bool = False,
        pipeline_context: PipelineContext | None = None,
    ) -> RetrievalResult:
        """Execute the full retrieval pipeline.

        Args:
            query: Search query.
            top_k: Number of results.
            filters: Optional metadata filters.
            skip_rerank: Skip reranking step.
            skip_compression: Skip compression step.
            pipeline_context: Optional pipeline context with signals.
        """
        trace_steps: list[TraceStep] = []

        # Apply pipeline context hints
        effective_top_k = top_k
        if pipeline_context:
            effective_top_k = pipeline_context.get_effective_top_k(top_k)
            hints = pipeline_context.retrieval_hints
            if hints.skip_rerank:
                skip_rerank = True
            if hints.skip_compression:
                skip_compression = True

        # Step 0.5: Detect query type for adaptive fusion weights
        query_type, adaptive_weights = detect_query_type(query)

        # Step 1: Fusion search (Pass 1) with query-aware weights
        t0 = time.perf_counter()
        candidates = await self._fusion.search(
            query,
            top_k=effective_top_k * self._fusion_candidate_multiplier,
            filters=filters,
            weights=adaptive_weights,
        )
        search_ms = (time.perf_counter() - t0) * 1000
        trace_steps.append(
            TraceStep(
                step="fusion_search",
                result=f"{len(candidates)} candidates (query_type={query_type})",
                latency_ms=search_ms,
                details={"query_type": query_type, "fusion_weights": adaptive_weights},
            )
        )
        logger.debug(
            "adaptive_fusion_weights",
            query_type=query_type,
            weights=adaptive_weights,
        )

        # Step 1.1: Signal-aware score boost
        # Boost TABULAR chunks for term_specific queries (numeric/value queries)
        # and chunks with high numeric density for value-asking queries
        if query_type == "term_specific" and candidates:
            boosted = 0
            for sc in candidates:
                signal = read_chunk_signal(sc.chunk)
                if signal is None:
                    continue
                if signal.information_type == InformationType.TABULAR:
                    sc.score *= 1.15
                    boosted += 1
                elif signal.numeric_density > 0.3:
                    sc.score *= 1.10
                    boosted += 1
            if boosted:
                candidates.sort(key=lambda x: x.score, reverse=True)
                logger.debug("signal_score_boost", query_type=query_type, boosted=boosted)

        # Step 1.5: Sibling Expansion (Pass 2)
        # Signal-aware: also expand chunks whose signal says they need context
        expand_needed = self._enable_sibling_expansion
        if pipeline_context and pipeline_context.retrieval_hints.force_sibling_expansion:
            expand_needed = True
        if not expand_needed and candidates:
            # Check if any top chunk signals that it needs context
            expand_needed = any(
                chunk_needs_expansion(sc.chunk) for sc in candidates[:effective_top_k]
            )

        if expand_needed and candidates:
            t_expand = time.perf_counter()
            candidates = await self._expand_siblings(candidates, effective_top_k)
            expand_ms = (time.perf_counter() - t_expand) * 1000
            trace_steps.append(
                TraceStep(
                    step="sibling_expansion",
                    result=f"{len(candidates)} after expansion",
                    latency_ms=expand_ms,
                )
            )

        # Step 2: Rerank
        if not skip_rerank:
            t1 = time.perf_counter()
            candidates = await self._reranker.rerank(query, candidates, top_k=effective_top_k)
            rerank_ms = (time.perf_counter() - t1) * 1000
            trace_steps.append(
                TraceStep(
                    step="rerank",
                    result=f"{len(candidates)} after reranking",
                    latency_ms=rerank_ms,
                )
            )
        else:
            candidates = candidates[:effective_top_k]

        # Step 2.5: Diversity-Aware Reordering (MMR)
        if len(candidates) > effective_top_k:
            from quantumrag.core.retrieve.diversity import mmr_reorder

            t_mmr = time.perf_counter()
            candidates = mmr_reorder(candidates, top_k=effective_top_k * 2, lambda_param=0.7)
            mmr_ms = (time.perf_counter() - t_mmr) * 1000
            if mmr_ms > 1:  # Only trace if non-trivial
                trace_steps.append(
                    TraceStep(
                        step="mmr_diversity",
                        result=f"{len(candidates)} after diversity reorder",
                        latency_ms=mmr_ms,
                    )
                )

        # Step 3: Compress (signal-aware: skip for tabular/legal/code chunks)
        if not skip_compression:
            # Separate chunks that should and shouldn't be compressed
            to_compress = []
            preserved = []
            for sc in candidates:
                if chunk_should_skip_compression(sc.chunk):
                    preserved.append(sc)
                else:
                    to_compress.append(sc)

            if to_compress:
                t2 = time.perf_counter()
                compressed = await self._compressor.compress(
                    query, to_compress, ratio=self._compression_ratio
                )
                compress_ms = (time.perf_counter() - t2) * 1000
                candidates = compressed + preserved
                candidates.sort(key=lambda x: x.score, reverse=True)
                trace_steps.append(
                    TraceStep(
                        step="compress",
                        result=f"{len(to_compress)} compressed, {len(preserved)} preserved (signal)",
                        latency_ms=compress_ms,
                    )
                )
            else:
                trace_steps.append(
                    TraceStep(
                        step="compress",
                        result=f"skipped: all {len(candidates)} chunks signal no-compress",
                        latency_ms=0,
                    )
                )

        # Check total elapsed time for slow retrieval monitoring
        total_elapsed_ms = sum(step.latency_ms for step in trace_steps)
        if total_elapsed_ms > self._slow_threshold_ms:
            logger.warning(
                "slow_retrieval_detected",
                query=query,
                filters=filters,
                elapsed_ms=round(total_elapsed_ms, 2),
                threshold_ms=self._slow_threshold_ms,
            )
            trace_steps.append(
                TraceStep(
                    step="slow_retrieval",
                    result=f"Retrieval took {total_elapsed_ms:.0f}ms (threshold: {self._slow_threshold_ms}ms)",
                    latency_ms=total_elapsed_ms,
                    details={"slow_retrieval": True},
                )
            )

        # Build sources (deduplicate by chunk_id in case expansion added duplicates)
        sources = [
            Source(
                chunk_id=sc.chunk.id,
                document_title=sc.chunk.metadata.get("title", ""),
                page=sc.chunk.metadata.get("page"),
                section=sc.chunk.metadata.get("section"),
                excerpt=sc.chunk.content[:200],
                relevance_score=sc.score,
            )
            for sc in candidates
        ]

        return RetrievalResult(
            chunks=candidates,
            sources=sources,
            trace=trace_steps,
        )

    async def _expand_siblings(self, chunks: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
        """2nd pass: expand with sibling/adjacent chunks from same document sections.

        For each retrieved chunk, fetch all chunks from the same document and
        include siblings that share a parent section (breadcrumb). This catches
        cases where related info (e.g., "확정 PoC" and "진행 중 PoC") was split
        into separate chunks.
        """
        expanded = list(chunks)
        seen_ids = {sc.chunk.id for sc in chunks}

        # Group chunks by document_id to minimize DB calls
        doc_ids: set[str] = set()
        for sc in chunks[:top_k]:  # Only expand top-k, not all candidates
            doc_id = (
                sc.chunk.document_id
                if hasattr(sc.chunk, "document_id")
                else sc.chunk.metadata.get("document_id", "")
            )
            if doc_id:
                doc_ids.add(doc_id)

        if not doc_ids or not self._document_store:
            return expanded

        # Fetch all chunks for relevant documents
        for doc_id in doc_ids:
            try:
                doc_chunks = await self._document_store.get_chunks(doc_id)
            except Exception:
                continue

            # Find sibling chunks for each retrieved chunk from this document
            for sc in chunks[:top_k]:
                sc_doc_id = (
                    sc.chunk.document_id
                    if hasattr(sc.chunk, "document_id")
                    else sc.chunk.metadata.get("document_id", "")
                )
                if sc_doc_id != doc_id:
                    continue

                for sibling in doc_chunks:
                    if sibling.id in seen_ids:
                        continue
                    if _share_parent_section(sc.chunk, sibling):
                        # Inherit a discounted score from the parent chunk
                        expanded.append(
                            ScoredChunk(
                                chunk=sibling,
                                score=sc.score * 0.75,
                            )
                        )
                        seen_ids.add(sibling.id)

        # Re-sort by score and limit
        expanded.sort(key=lambda x: x.score, reverse=True)
        limit = top_k * self._fusion_candidate_multiplier
        if len(expanded) > limit:
            expanded = expanded[:limit]

        if len(expanded) > len(chunks):
            logger.debug(
                "sibling_expansion_added",
                original=len(chunks),
                expanded=len(expanded),
                added=len(expanded) - len(chunks),
            )

        return expanded


class RetrievalResult:
    """Result from the retrieval pipeline."""

    __slots__ = ("chunks", "sources", "trace")

    def __init__(
        self,
        chunks: list[ScoredChunk],
        sources: list[Source],
        trace: list[TraceStep],
    ) -> None:
        self.chunks = chunks
        self.sources = sources
        self.trace = trace
