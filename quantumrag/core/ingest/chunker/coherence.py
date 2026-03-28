"""Chunk Coherence Gate — post-processing step to fix bad chunk boundaries.

After any chunking strategy produces chunks, this gate evaluates each chunk's
self-containedness and merges chunks that are broken at unnatural boundaries.
"""

from __future__ import annotations

import re

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk
from quantumrag.core.pipeline.signals import read_chunk_signal

logger = get_logger(__name__)

# Regex patterns for boundary quality detection
_HEADING_RE = re.compile(r"^\s*#{1,6}\s")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)]\s)")
_SENTENCE_END_RE = re.compile(r"[.!?]\s*$")
_KOREAN_SENTENCE_END_RE = re.compile(r"[다요까죠네]\s*[.!?]?\s*$")
_UPPERCASE_START_RE = re.compile(r"^\s*[A-Z]")
_KOREAN_START_RE = re.compile(r"^\s*[\uAC00-\uD7AF]")
_LOWERCASE_MID_SENTENCE_RE = re.compile(r"^\s*[a-z]")
# Korean particles/postpositions that indicate mid-sentence start.
# If a chunk starts with a Korean character whose final consonant (받침)
# pattern suggests it's a particle (은/는/이/가/를/을/에/도/로/과/와/의),
# it's likely continuing from a previous sentence.
_KOREAN_PARTICLE_START_RE = re.compile(
    r"^\s*(?:은|는|이|가|를|을|에|도|로|과|와|의|으로|에서|까지|부터|에게|한테|께)\s"
)
_TABLE_ROW_RE = re.compile(r"\|.+\|")
_TABLE_SEPARATOR_RE = re.compile(r"\|[-:]+\|")
_MARKDOWN_TABLE_RE = re.compile(r"(?:^|\n)\s*\|.+\|.*(?:\n\s*\|[-:| ]+\|)", re.MULTILINE)
_COMPLETE_LIST_ITEM_RE = re.compile(r"(?:[-*+]|\d+[.)]).+$")


def _count_words(text: str) -> int:
    """Count words in text, handling both Latin and CJK scripts."""
    # For CJK text, each character roughly corresponds to a word
    latin_words = len(text.split())
    return latin_words


def _contains_table(text: str) -> bool:
    """Check if text contains a markdown table."""
    lines = text.strip().split("\n")
    pipe_lines = [line for line in lines if _TABLE_ROW_RE.match(line.strip())]
    # A table needs at least a header row and a separator row
    if len(pipe_lines) >= 2:
        for line in pipe_lines:
            if _TABLE_SEPARATOR_RE.match(line.strip()):
                return True
    return False


def _score_start_quality(text: str) -> float:
    """Score how well a chunk starts at a natural boundary (0.0 to 0.5)."""
    stripped = text.lstrip()
    if not stripped:
        return 0.25  # Empty chunk gets neutral score

    score = 0.0

    # Heading marker is the strongest start signal
    if _HEADING_RE.match(stripped):
        score += 0.3

    # Bullet or numbered list item
    if _BULLET_RE.match(stripped):
        score += 0.2

    # Starts with uppercase letter (natural English sentence start)
    if _UPPERCASE_START_RE.match(stripped):
        score += 0.2

    # Korean: starts with a content word (not a particle) = natural start
    if _KOREAN_START_RE.match(stripped):
        if _KOREAN_PARTICLE_START_RE.match(stripped):
            # Starts with a particle (은/는/이/가/를/을...) → mid-sentence
            score -= 0.3
        else:
            score += 0.2

    # Starts mid-sentence (lowercase English, no structural marker)
    if _LOWERCASE_MID_SENTENCE_RE.match(stripped) and not _BULLET_RE.match(stripped):
        score -= 0.3

    return max(0.0, min(0.5, score))


def _score_end_quality(text: str) -> float:
    """Score how well a chunk ends at a natural boundary (0.0 to 0.5)."""
    stripped = text.rstrip()
    if not stripped:
        return 0.25

    score = 0.0

    # Ends with sentence-ending punctuation
    if _SENTENCE_END_RE.search(stripped):
        score += 0.3

    # Ends with Korean sentence-ending suffix
    if _KOREAN_SENTENCE_END_RE.search(stripped):
        score += 0.3

    # Ends with a complete markdown element (table row or list item)
    last_line = stripped.split("\n")[-1].strip()
    if _TABLE_ROW_RE.match(last_line):
        score += 0.2
    if _COMPLETE_LIST_ITEM_RE.match(last_line):
        score += 0.2

    # Ends mid-sentence: no terminal punctuation and not a structural element
    if (
        not _SENTENCE_END_RE.search(stripped)
        and not _KOREAN_SENTENCE_END_RE.search(stripped)
        and not _TABLE_ROW_RE.match(last_line)
        and not _COMPLETE_LIST_ITEM_RE.match(last_line)
    ):
        score -= 0.3

    return max(0.0, min(0.5, score))


def compute_coherence(chunk: Chunk) -> float:
    """Compute a coherence score (0.0-1.0) for a chunk.

    Integrates with pipeline signals when available: if a chunk already has
    a signal_completeness score, blends it with boundary-based scoring to
    avoid duplicating the completeness analysis done in signals.py.
    """
    # Table protection: chunks containing tables are always coherent
    if _contains_table(chunk.content):
        return 1.0

    start_score = _score_start_quality(chunk.content)
    end_score = _score_end_quality(chunk.content)
    boundary_score = start_score + end_score

    # Blend with signal completeness if available
    signal = read_chunk_signal(chunk)
    if signal is not None and signal.completeness > 0:
        # Weighted blend: 60% boundary quality, 40% signal completeness
        return 0.6 * boundary_score + 0.4 * signal.completeness

    return boundary_score


class ChunkCoherenceGate:
    """Post-processing gate that evaluates and fixes chunk boundary quality.

    After any chunking strategy produces chunks, this gate:
    1. Scores each chunk for self-containedness (coherence)
    2. Merges poorly-bounded chunks with their neighbors
    3. Protects table-containing chunks from being split

    Args:
        threshold: Minimum coherence score (0.0-1.0). Chunks below this
            are candidates for merging. Default 0.4.
        max_merged_size: Maximum word count for a merged chunk. If merging
            would exceed this, the merge is skipped. Default 1500.
    """

    def __init__(self, threshold: float = 0.4, max_merged_size: int = 1500) -> None:
        self.threshold = threshold
        self.max_merged_size = max_merged_size

    def refine(self, chunks: list[Chunk]) -> list[Chunk]:
        """Refine a list of chunks by merging those with poor boundary coherence.

        Args:
            chunks: List of chunks from any chunking strategy.

        Returns:
            Refined list of chunks with improved boundary coherence.
        """
        if not chunks:
            return chunks

        # Compute coherence scores for all chunks
        scores = [compute_coherence(c) for c in chunks]

        # Track which chunks have been merged (absorbed into another)
        merged_into: dict[int, int] = {}  # index -> index it was merged into

        # Single pass: check each chunk and merge if needed
        for i, (chunk, score) in enumerate(zip(chunks, scores)):
            if i in merged_into:
                continue
            if score >= self.threshold:
                continue

            # Find best adjacent chunk to merge with (same document only)
            prev_idx = self._find_prev_unmerged(i, merged_into)
            next_idx = self._find_next_unmerged(i, len(chunks), merged_into)

            candidates: list[tuple[int, float]] = []

            # Check previous chunk
            if prev_idx is not None and chunks[prev_idx].document_id == chunk.document_id:
                # Boundary quality at the join: prev's end + current's start
                boundary_score = _score_end_quality(
                    chunks[prev_idx].content
                ) + _score_start_quality(chunk.content)
                candidates.append((prev_idx, boundary_score))

            # Check next chunk
            if next_idx is not None and chunks[next_idx].document_id == chunk.document_id:
                # Boundary quality at the join: current's end + next's start
                boundary_score = _score_end_quality(chunk.content) + _score_start_quality(
                    chunks[next_idx].content
                )
                candidates.append((next_idx, boundary_score))

            if not candidates:
                continue

            # Pick the neighbor with the lowest boundary quality at the join point
            candidates.sort(key=lambda x: x[1])
            merge_target_idx = candidates[0][0]

            # Check size constraint
            combined_text = chunks[merge_target_idx].content + "\n\n" + chunk.content
            if merge_target_idx > i:
                combined_text = chunk.content + "\n\n" + chunks[merge_target_idx].content

            if _count_words(combined_text) > self.max_merged_size:
                logger.debug(
                    "coherence_merge_skipped_size",
                    chunk_index=chunk.chunk_index,
                    word_count=_count_words(combined_text),
                    max_size=self.max_merged_size,
                )
                continue

            # Perform merge: absorb the low-coherence chunk into its neighbor
            if merge_target_idx < i:
                # Merge current into previous
                chunks[merge_target_idx] = chunks[merge_target_idx].model_copy(
                    update={"content": chunks[merge_target_idx].content + "\n\n" + chunk.content}
                )
                merged_into[i] = merge_target_idx
            else:
                # Merge next into current
                chunks[i] = chunk.model_copy(
                    update={"content": chunk.content + "\n\n" + chunks[merge_target_idx].content}
                )
                merged_into[merge_target_idx] = i

            # Update the score for the merged chunk
            target = merge_target_idx if merge_target_idx < i else i
            scores[target] = compute_coherence(chunks[target])

            logger.debug(
                "coherence_merge",
                merged_chunk=chunk.chunk_index,
                into_chunk=chunks[target].chunk_index,
                old_score=score,
                new_score=scores[target],
            )

        # Build result: exclude merged chunks and re-index
        result: list[Chunk] = []
        for i, chunk in enumerate(chunks):
            if i not in merged_into:
                result.append(chunk.model_copy(update={"chunk_index": len(result)}))

        logger.debug(
            "coherence_gate_complete",
            input_chunks=len(chunks),
            output_chunks=len(result),
            merges=len(merged_into),
        )
        return result

    @staticmethod
    def _find_prev_unmerged(i: int, merged_into: dict[int, int]) -> int | None:
        """Find the nearest previous chunk that hasn't been merged away."""
        idx = i - 1
        while idx >= 0:
            if idx not in merged_into:
                return idx
            idx -= 1
        return None

    @staticmethod
    def _find_next_unmerged(i: int, length: int, merged_into: dict[int, int]) -> int | None:
        """Find the nearest next chunk that hasn't been merged away."""
        idx = i + 1
        while idx < length:
            if idx not in merged_into:
                return idx
            idx += 1
        return None
