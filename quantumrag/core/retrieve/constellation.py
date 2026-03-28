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

Query-Aware Expansion (v9):
When query_domains is provided, graph-discovered chunks whose structured
facts match the query domain receive a score boost.  This ensures that
a finance query prioritises finance-fact chunks over, say, HR chunks
that happen to be graph neighbours.

Performance: Graph traversal is O(k * avg_degree), typically <1ms.
"""

from __future__ import annotations

from typing import Any

from quantumrag.core.ingest.indexer.chunk_graph import ChunkGraph
from quantumrag.core.logging import get_logger
from quantumrag.core.retrieve.fusion import ScoredChunk

logger = get_logger("quantumrag.constellation")

# Map fact types to their source domain for domain-aware boosting
_FACT_TYPE_TO_DOMAIN: dict[str, str] = {
    "customer_contract": "contract",
    "security_issue": "security",
    "security_summary": "security",
    "finance_metric": "finance",
    "fund_allocation": "finance",
    "team_info": "hr",
    "team_leader": "hr",
    "patent": "patent",
    "product_version": "product",
}


def _chunk_matches_domains(chunk: Any, query_domains: list[str]) -> bool:
    """Check if a chunk's facts overlap with the requested query domains."""
    facts = chunk.metadata.get("facts")
    if not facts:
        return False
    chunk_domains = {_FACT_TYPE_TO_DOMAIN.get(f.get("type", ""), "") for f in facts}
    return bool(chunk_domains & set(query_domains))


async def expand_with_constellation(
    chunks: list[ScoredChunk],
    graph: ChunkGraph,
    document_store: Any,
    top_k: int,
    max_expansion: int = 8,
    query_domains: list[str] | None = None,
) -> list[ScoredChunk]:
    """Expand retrieved chunks using the pre-computed constellation graph.

    Args:
        chunks: Initial fusion search results
        graph: Pre-computed chunk constellation graph
        document_store: For fetching full chunk content
        top_k: Original top_k from the query
        max_expansion: Maximum number of chunks to add from graph
        query_domains: Domains detected from the query (e.g., ["contract", "finance"]).
                       When provided, graph-discovered chunks matching these domains
                       get a 1.3x score boost.

    Returns:
        Expanded list of ScoredChunk with graph-discovered chunks included
    """
    if not chunks or not graph:
        return chunks

    seed_ids = [sc.chunk.id for sc in chunks[:top_k]]
    seen_ids = {sc.chunk.id for sc in chunks}

    # Use ALL retrieved chunks as seeds, not just top-k
    all_seed_ids = [sc.chunk.id for sc in chunks]

    # Graph traversal with 2 hops — catches indirect siblings
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
    domain_boost = 1.3  # 30% boost for domain-matching chunks

    async def _add_chunk(cid: str, graph_weight: float, chunk: Any) -> None:
        score = base_score * graph_weight
        # Query-aware boost: reward chunks whose facts match query domain
        if query_domains and _chunk_matches_domains(chunk, query_domains):
            score *= domain_boost
        expanded.append(ScoredChunk(chunk=chunk, score=score))
        seen_ids.add(cid)

    if hasattr(document_store, "get_chunks_batch"):
        chunks_map = await document_store.get_chunks_batch(new_ids)
        for cid, graph_weight in constellation:
            if cid in seen_ids:
                continue
            chunk = chunks_map.get(cid)
            if chunk:
                await _add_chunk(cid, graph_weight, chunk)
    else:
        for cid, graph_weight in constellation:
            if cid in seen_ids:
                continue
            chunk = await document_store.get_chunk(cid)
            if chunk:
                await _add_chunk(cid, graph_weight, chunk)

    # Re-sort by score
    expanded.sort(key=lambda x: x.score, reverse=True)

    added = len(expanded) - len(chunks)
    if added > 0:
        logger.info(
            "constellation_expanded",
            seed_chunks=len(seed_ids),
            graph_expansion=added,
            total=len(expanded),
            domain_aware=bool(query_domains),
        )

    return expanded
