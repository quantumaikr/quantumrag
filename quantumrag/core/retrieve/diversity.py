"""Diversity-Aware Context Assembly (Maximal Marginal Relevance).

The insight: after retrieval, we often have 3 chunks about "확정 PoC" but
miss the "진행 중 PoC" chunk. Standard top-k by score reinforces
redundancy. MMR diversifies the context window.

MMR score = λ * relevance(chunk, query) - (1 - λ) * max_similarity(chunk, selected)

At λ=0.7: prioritize relevance but penalize chunks too similar to already-selected ones.
This ensures the context window covers diverse information, not redundant top-k.

Performance: O(k * n) where k = selected count, n = candidate count. ~1ms for typical sizes.
"""

from __future__ import annotations

from quantumrag.core.logging import get_logger
from quantumrag.core.retrieve.fusion import ScoredChunk
from quantumrag.core.utils.text import text_similarity

logger = get_logger("quantumrag.diversity")


def deduplicate_chunks(chunks: list[ScoredChunk], threshold: float = 0.85) -> list[ScoredChunk]:
    """Remove near-duplicate chunks based on content overlap.

    Keeps the higher-scored version when two chunks overlap significantly.
    This is critical after multi-path retrieval (sub-queries, self-correction)
    where the same information may be retrieved multiple times.
    """
    if len(chunks) <= 1:
        return chunks

    result: list[ScoredChunk] = []
    for candidate in chunks:
        is_dup = False
        for selected in result:
            if text_similarity(candidate.chunk.content, selected.chunk.content) > threshold:
                is_dup = True
                break
        if not is_dup:
            result.append(candidate)
    return result


def mmr_reorder(
    chunks: list[ScoredChunk],
    top_k: int,
    lambda_param: float = 0.7,
) -> list[ScoredChunk]:
    """Re-order chunks using Maximal Marginal Relevance.

    Selects chunks that are both relevant (high score) and diverse
    (low overlap with already-selected chunks).

    Args:
        chunks: Scored chunks from retrieval, sorted by relevance
        top_k: Number of chunks to select
        lambda_param: Balance between relevance (1.0) and diversity (0.0)

    Returns:
        Re-ordered list of top_k chunks
    """
    if len(chunks) <= top_k:
        return chunks

    # Normalize scores to [0, 1]
    max_score = max(sc.score for sc in chunks) if chunks else 1.0
    min_score = min(sc.score for sc in chunks) if chunks else 0.0
    score_range = max_score - min_score if max_score != min_score else 1.0

    selected: list[ScoredChunk] = []
    remaining = list(chunks)

    for _ in range(min(top_k, len(chunks))):
        if not remaining:
            break

        best_idx = 0
        best_mmr = float("-inf")

        for i, candidate in enumerate(remaining):
            # Relevance term
            relevance = (candidate.score - min_score) / score_range

            # Diversity term: max overlap with any selected chunk
            max_overlap = 0.0
            if selected:
                for sel in selected:
                    overlap = text_similarity(candidate.chunk.content, sel.chunk.content)
                    max_overlap = max(max_overlap, overlap)

            # MMR score
            mmr = lambda_param * relevance - (1 - lambda_param) * max_overlap

            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i

        selected.append(remaining.pop(best_idx))

    return selected
