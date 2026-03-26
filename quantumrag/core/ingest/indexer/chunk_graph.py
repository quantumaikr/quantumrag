"""Chunk Constellation Graph — Pre-computed chunk relationship network.

Instead of treating chunks as isolated atoms in a vector space, we build a
relationship graph at indexing time that captures:

1. **Sibling**: Adjacent chunks from the same document (split by size limits)
2. **Parent Section**: Chunks sharing the same breadcrumb parent across documents
3. **Entity Cross-Reference**: Chunks that mention the same named entities

At query time, finding ONE relevant chunk lets us traverse to related
chunks via pre-computed adjacency — reducing missed context from top-k
retrieval.

Performance characteristics:
- Index time: O(n²) entity overlap computation (one-time cost)
- Query time: O(k * avg_degree) graph traversal (pre-computed adjacency)
- Memory: ~50 bytes per edge (chunk_id pairs + weight + type)
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk

logger = get_logger("quantumrag.chunk_graph")


@dataclass(frozen=True, slots=True)
class ChunkEdge:
    """An edge in the chunk constellation graph."""

    source_id: str
    target_id: str
    edge_type: str  # "sibling", "parent", "entity"
    weight: float  # 0.0 - 1.0, strength of relationship


@dataclass
class ChunkGraph:
    """In-memory chunk relationship graph with O(1) neighbor lookup."""

    _adjacency: dict[str, list[ChunkEdge]] = field(default_factory=lambda: defaultdict(list))
    _entity_index: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def add_edge(self, edge: ChunkEdge) -> None:
        """Add a bidirectional edge."""
        self._adjacency[edge.source_id].append(edge)
        # Add reverse edge
        reverse = ChunkEdge(
            source_id=edge.target_id,
            target_id=edge.source_id,
            edge_type=edge.edge_type,
            weight=edge.weight,
        )
        self._adjacency[edge.target_id].append(reverse)

    def get_neighbors(
        self,
        chunk_id: str,
        edge_types: set[str] | None = None,
        min_weight: float = 0.0,
    ) -> list[ChunkEdge]:
        """Get all neighbors of a chunk, optionally filtered by type/weight."""
        edges = self._adjacency.get(chunk_id, [])
        if edge_types:
            edges = [e for e in edges if e.edge_type in edge_types]
        if min_weight > 0:
            edges = [e for e in edges if e.weight >= min_weight]
        return edges

    def get_constellation(
        self,
        chunk_ids: list[str],
        max_hops: int = 1,
        max_expansion: int = 10,
    ) -> list[tuple[str, float]]:
        """Get the constellation of related chunks for a set of seed chunks.

        Returns (chunk_id, accumulated_weight) pairs sorted by weight.
        This is the key query-time operation — O(k * avg_degree) where k
        is the number of seed chunks and avg_degree is typically 3-8.
        """
        scores: dict[str, float] = {}
        visited: set[str] = set(chunk_ids)

        # BFS with weight decay
        frontier = [(cid, 1.0) for cid in chunk_ids]
        for _hop in range(max_hops):
            next_frontier: list[tuple[str, float]] = []
            for cid, parent_weight in frontier:
                for edge in self._adjacency.get(cid, []):
                    if edge.target_id in visited:
                        continue
                    propagated = parent_weight * edge.weight
                    if propagated < 0.1:
                        continue
                    if edge.target_id in scores:
                        scores[edge.target_id] = max(scores[edge.target_id], propagated)
                    else:
                        scores[edge.target_id] = propagated
                    visited.add(edge.target_id)
                    next_frontier.append((edge.target_id, propagated))
            frontier = next_frontier

        # Sort by score and limit
        result = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return result[:max_expansion]

    @property
    def edge_count(self) -> int:
        return sum(len(edges) for edges in self._adjacency.values()) // 2

    @property
    def node_count(self) -> int:
        return len(self._adjacency)


# ──────────────────────────────────────────────────────────────────────
# Graph Builder — runs at index time
# ──────────────────────────────────────────────────────────────────────

# Named entities for cross-reference detection
_ENTITY_PATTERNS = [
    # Korean company names, product names, person names
    re.compile(r"(퀀텀소프트|QuantumSoft|퀀텀아이|Upstage|리턴제로|ReturnZero)"),
    re.compile(r"(뤼튼|Wrtn|포티투마루|42Maru|삼성전자|KB국민은행)"),
    re.compile(r"(네이버|현대자동차|소프트뱅크|NTT|미쓰비시|김앤장)"),
    re.compile(r"(QuantumRAG|QuantumChat|QuantumGuard|QuantumAnalytics)"),
    re.compile(r"(Series [A-Z]|시리즈 [A-Z])"),
    re.compile(r"(v\d+\.\d+(?:\.\d+)?|PAT-\d{3}|SEC-\d{3})"),
    # Monetary amounts (Korean)
    re.compile(r"(\d+(?:\.\d+)?(?:억|천만|백만))"),
]


def _extract_entities(text: str) -> set[str]:
    """Extract named entities from text for cross-reference detection."""
    entities: set[str] = set()
    for pattern in _ENTITY_PATTERNS:
        for match in pattern.finditer(text):
            entities.add(match.group(1))
    return entities


def build_chunk_graph(chunks: list[Chunk]) -> ChunkGraph:
    """Build the chunk constellation graph from a list of chunks.

    Runs at indexing time. Detects:
    1. Sibling relationships (same document, adjacent index)
    2. Parent section relationships (same breadcrumb parent across documents)
    3. Entity cross-references (shared named entities across documents)
    """
    graph = ChunkGraph()

    # Index chunks by document_id for efficient sibling detection
    doc_chunks: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        doc_chunks[chunk.document_id].append(chunk)

    # Sort each document's chunks by index
    for doc_id in doc_chunks:
        doc_chunks[doc_id].sort(key=lambda c: c.chunk_index)

    # 1. Sibling edges — adjacent chunks in same document
    for doc_id, doc_chunk_list in doc_chunks.items():
        for i in range(len(doc_chunk_list) - 1):
            graph.add_edge(ChunkEdge(
                source_id=doc_chunk_list[i].id,
                target_id=doc_chunk_list[i + 1].id,
                edge_type="sibling",
                weight=0.9,  # High weight: adjacent chunks almost always co-relevant
            ))
            # Also connect chunks 2 apart with moderate weight
            if i + 2 < len(doc_chunk_list):
                graph.add_edge(ChunkEdge(
                    source_id=doc_chunk_list[i].id,
                    target_id=doc_chunk_list[i + 2].id,
                    edge_type="sibling",
                    weight=0.6,
                ))

    # 2. Parent section edges — same breadcrumb parent
    breadcrumb_groups: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        bc = chunk.metadata.get("breadcrumb", "")
        if bc:
            # Extract parent by removing last segment
            parts = bc.strip("[]").rsplit(" > ", 1)
            if len(parts) > 1:
                parent_bc = parts[0]
                breadcrumb_groups[parent_bc].append(chunk)

    for parent_bc, group in breadcrumb_groups.items():
        for i, chunk_a in enumerate(group):
            for chunk_b in group[i + 1:]:
                if chunk_a.document_id == chunk_b.document_id:
                    continue  # Already connected as siblings
                graph.add_edge(ChunkEdge(
                    source_id=chunk_a.id,
                    target_id=chunk_b.id,
                    edge_type="parent",
                    weight=0.7,
                ))

    # 3. Entity cross-reference edges — shared entities across documents
    entity_to_chunks: dict[str, list[str]] = defaultdict(list)
    for chunk in chunks:
        entities = _extract_entities(chunk.content)
        for entity in entities:
            entity_to_chunks[entity].append(chunk.id)
            graph._entity_index[entity].add(chunk.id)

    for entity, chunk_ids in entity_to_chunks.items():
        if len(chunk_ids) < 2 or len(chunk_ids) > 20:
            continue  # Skip too common or singleton entities

        # Connect chunks that share this entity (across different documents)
        chunk_doc_map = {c.id: c.document_id for c in chunks}
        for i, cid_a in enumerate(chunk_ids):
            for cid_b in chunk_ids[i + 1:]:
                doc_a = chunk_doc_map.get(cid_a, "")
                doc_b = chunk_doc_map.get(cid_b, "")
                if doc_a != doc_b:
                    # Cross-document entity reference — high value!
                    weight = 0.6 if len(chunk_ids) <= 5 else 0.4
                    graph.add_edge(ChunkEdge(
                        source_id=cid_a,
                        target_id=cid_b,
                        edge_type="entity",
                        weight=weight,
                    ))

    logger.info(
        "chunk_graph_built",
        nodes=graph.node_count,
        edges=graph.edge_count,
        entity_types=len(entity_to_chunks),
    )
    return graph
