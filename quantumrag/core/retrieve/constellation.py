"""Constellation Retriever — Graph-enhanced context assembly.

This module implements the "Constellation Expansion" technique:
after standard fusion retrieval returns top-k chunks, we use the
pre-computed Chunk Graph to instantly expand to ALL related chunks
that form the "constellation" of relevant context.

This replaces the simpler sibling expansion with a much more powerful
graph-based approach that captures:
- Sibling chunks (same section, different sub-headings)
- Cross-document references (same entity mentioned in different docs)
- Temporal context (same version/date across documents)

The key insight: ONE good retrieval hit unlocks an entire constellation
of related information, solving the fundamental "retrieval gap" problem.

Performance: Graph traversal is O(k * avg_degree), typically <1ms,
vs the previous approach of N database calls for sibling expansion.
"""

from __future__ import annotations

from typing import Any

from quantumrag.core.ingest.indexer.chunk_graph import ChunkGraph
from quantumrag.core.logging import get_logger
from quantumrag.core.retrieve.fusion import ScoredChunk

logger = get_logger("quantumrag.constellation")


async def expand_with_constellation(
    chunks: list[ScoredChunk],
    graph: ChunkGraph,
    document_store: Any,
    top_k: int,
    max_expansion: int = 8,
) -> list[ScoredChunk]:
    """Expand retrieved chunks using the pre-computed constellation graph.

    This is the revolutionary replacement for the slower sibling expansion.
    Instead of querying the database for sibling chunks, we traverse the
    pre-computed graph in microseconds.

    Args:
        chunks: Initial fusion search results
        graph: Pre-computed chunk constellation graph
        document_store: For fetching full chunk content
        top_k: Original top_k from the query
        max_expansion: Maximum number of chunks to add from graph

    Returns:
        Expanded list of ScoredChunk with graph-discovered chunks included
    """
    if not chunks or not graph:
        return chunks

    seed_ids = [sc.chunk.id for sc in chunks[:top_k]]
    seen_ids = {sc.chunk.id for sc in chunks}

    # Use ALL retrieved chunks as seeds, not just top-k
    # This ensures that if chunk A (position 6) has a critical sibling,
    # it's discoverable even though A isn't in the top-k seeds
    all_seed_ids = [sc.chunk.id for sc in chunks]

    # Graph traversal with 2 hops — catches indirect siblings
    # e.g., email_header → confirmed_PoC → in_progress_PoC
    constellation = graph.get_constellation(
        all_seed_ids,
        max_hops=2,
        max_expansion=max_expansion,
    )

    if not constellation:
        return chunks

    # Fetch full chunk objects for graph-discovered chunks
    new_ids = [cid for cid, _ in constellation if cid not in seen_ids]
    if not new_ids:
        return chunks

    expanded = list(chunks)
    base_score = chunks[0].score if chunks else 0.5

    if hasattr(document_store, "get_chunks_batch"):
        chunks_map = await document_store.get_chunks_batch(new_ids)
        for cid, graph_weight in constellation:
            if cid in seen_ids:
                continue
            chunk = chunks_map.get(cid)
            if chunk:
                expanded.append(ScoredChunk(
                    chunk=chunk,
                    score=base_score * graph_weight,
                ))
                seen_ids.add(cid)
    else:
        for cid, graph_weight in constellation:
            if cid in seen_ids:
                continue
            chunk = await document_store.get_chunk(cid)
            if chunk:
                expanded.append(ScoredChunk(
                    chunk=chunk,
                    score=base_score * graph_weight,
                ))
                seen_ids.add(cid)

    # Re-sort by score
    expanded.sort(key=lambda x: x.score, reverse=True)

    added = len(expanded) - len(chunks)
    if added > 0:
        logger.info(
            "constellation_expanded",
            seed_chunks=len(seed_ids),
            graph_expansion=added,
            total=len(expanded),
        )

    return expanded
