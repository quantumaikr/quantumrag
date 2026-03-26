"""Context compression — reduces token count while preserving relevant information."""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from quantumrag.core.logging import get_logger
from quantumrag.core.retrieve.fusion import ScoredChunk
from quantumrag.core.utils.text import split_sentences, tokenize

logger = get_logger("quantumrag.compressor")


@runtime_checkable
class Compressor(Protocol):
    """Protocol for context compression."""

    async def compress(
        self, query: str, chunks: list[ScoredChunk], ratio: float = 0.5
    ) -> list[ScoredChunk]:
        """Compress chunks, keeping approximately `ratio` of content."""
        ...


class ExtractiveCompressor:
    """Extractive compression — keeps only query-relevant sentences.

    This is a simple, cost-free approach that:
    1. Splits each chunk into sentences
    2. Scores each sentence by keyword overlap with query
    3. Keeps top sentences up to the target ratio
    """

    async def compress(
        self, query: str, chunks: list[ScoredChunk], ratio: float = 0.5
    ) -> list[ScoredChunk]:
        if ratio >= 1.0:
            return chunks

        query_words = set(tokenize(query))
        compressed = []

        for sc in chunks:
            sentences = split_sentences(sc.chunk.content)
            if len(sentences) <= 2:
                compressed.append(sc)
                continue

            # Score sentences by query relevance
            scored = []
            for sent in sentences:
                sent_words = set(tokenize(sent))
                overlap = len(query_words & sent_words)
                # Boost sentences containing numbers or named-entity-like tokens
                # (capitalized words, numbers are often key factual content)
                if _has_factual_content(sent):
                    overlap += 1
                scored.append((sent, overlap))

            # Always include first and last sentence (context boundaries)
            keep_count = max(1, int(len(sentences) * ratio))
            boundary_indices = {0, len(sentences) - 1}
            inner_budget = max(0, keep_count - len(boundary_indices))

            # Rank non-boundary sentences by score
            inner_indices = sorted(
                (i for i in range(len(scored)) if i not in boundary_indices),
                key=lambda i: scored[i][1],
                reverse=True,
            )[:inner_budget]

            top_indices = sorted(boundary_indices | set(inner_indices))

            compressed_text = " ".join(sentences[i] for i in top_indices)

            # Create a new chunk with compressed content
            from quantumrag.core.models import Chunk

            new_chunk = Chunk(
                id=sc.chunk.id,
                content=compressed_text,
                document_id=sc.chunk.document_id,
                chunk_index=sc.chunk.chunk_index,
                metadata=sc.chunk.metadata,
                context_prefix=sc.chunk.context_prefix,
                hype_questions=sc.chunk.hype_questions,
                parent_chunk_id=sc.chunk.parent_chunk_id,
            )
            compressed.append(ScoredChunk(chunk=new_chunk, score=sc.score))

        total_orig = sum(len(sc.chunk.content) for sc in chunks)
        total_comp = sum(len(sc.chunk.content) for sc in compressed)
        actual_ratio = total_comp / total_orig if total_orig > 0 else 1.0
        logger.debug(
            "compressed", original_chars=total_orig, compressed_chars=total_comp, ratio=actual_ratio
        )
        return compressed


class NoopCompressor:
    """Pass-through compressor (for when compression is disabled)."""

    async def compress(
        self, query: str, chunks: list[ScoredChunk], ratio: float = 0.5
    ) -> list[ScoredChunk]:
        return chunks


def _has_factual_content(sentence: str) -> bool:
    """Check if a sentence contains numbers or named-entity-like tokens.

    Sentences with numbers, dates, percentages, or proper nouns are
    more likely to contain important factual information.
    """
    # Contains numbers (including Korean number patterns like 3건, 50%)
    if re.search(r"\d", sentence):
        return True
    # Contains capitalized words that look like proper nouns (English named entities)
    tokens = sentence.split()
    return any(t[0].isupper() and len(t) > 1 for t in tokens if t and t[0].isalpha())


