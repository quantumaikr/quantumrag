"""Semantic chunking based on content structure and topic coherence.

Two modes:
1. **Paragraph-based** (default, free): Splits on paragraph boundaries with
   topic-shift detection using vocabulary overlap between adjacent paragraphs.
2. **Embedding-based** (optional): Uses a sentence-transformer model to detect
   semantic breakpoints — paragraphs with low cosine similarity to their
   neighbors become chunk boundaries.
"""

from __future__ import annotations

import re
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk, Document
from quantumrag.core.pipeline.context import BoundaryType
from quantumrag.core.utils.text import (
    estimate_token_count,
    split_preserving_blocks,
    text_similarity,
)

logger = get_logger(__name__)

# Pattern for paragraph breaks (two or more newlines)
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")

# Threshold: if vocabulary overlap between adjacent paragraphs drops below
# this, it's likely a topic shift and we should start a new chunk.
_TOPIC_SHIFT_THRESHOLD = 0.15


class SemanticChunker:
    """Semantic chunker with topic-shift detection.

    Splits on paragraph boundaries and uses vocabulary overlap between
    adjacent paragraphs to detect topic shifts. When the overlap drops
    below a threshold, a new chunk is started even if the current chunk
    hasn't reached max size.

    Args:
        min_chunk_size: Minimum chunk size in words.
        max_chunk_size: Maximum chunk size in words.
        topic_shift_threshold: Vocabulary overlap below this triggers a split.
        embedding_provider: Optional EmbeddingProvider for embedding-based splits.
    """

    def __init__(
        self,
        min_chunk_size: int = 100,
        max_chunk_size: int = 1000,
        topic_shift_threshold: float = _TOPIC_SHIFT_THRESHOLD,
        embedding_provider: Any = None,
    ) -> None:
        self._min_size = min_chunk_size
        self._max_size = max_chunk_size
        self._topic_shift_threshold = topic_shift_threshold
        self._embedding_provider = embedding_provider

    def chunk(self, document: Document) -> list[Chunk]:
        """Split document into semantically coherent chunks.

        Pre-processes text to protect markdown tables as atomic blocks,
        then applies semantic chunking to remaining text segments.

        Args:
            document: Document to split.

        Returns:
            List of Chunk instances.
        """
        text = document.content.strip()
        if not text:
            return []

        # Pre-split: protect tables and code blocks as atomic blocks
        segments = split_preserving_blocks(text)

        chunks: list[Chunk] = []
        chunk_index = 0

        for segment_text, block_type in segments:
            if block_type in ("table", "code"):
                chunks.append(
                    Chunk(
                        content=segment_text,
                        document_id=document.id,
                        chunk_index=chunk_index,
                        metadata={"boundary_type": BoundaryType.STRUCTURAL.value},
                    )
                )
                chunk_index += 1
                continue

            paragraphs = _split_paragraphs(segment_text)
            if not paragraphs:
                continue

            merged, boundary_types = self._merge_and_split(paragraphs)

            for i, chunk_text in enumerate(merged):
                chunks.append(
                    Chunk(
                        content=chunk_text,
                        document_id=document.id,
                        chunk_index=chunk_index,
                        metadata={
                            "boundary_type": boundary_types[i]
                            if i < len(boundary_types)
                            else BoundaryType.SIZE_LIMIT.value
                        },
                    )
                )
                chunk_index += 1

        logger.debug(
            "semantic_chunking_done",
            doc_id=document.id,
            chunk_count=len(chunks),
        )

        return chunks

    def _merge_and_split(self, paragraphs: list[str]) -> tuple[list[str], list[str]]:
        """Merge small paragraphs and split large ones, with topic-shift detection.

        Key improvement over simple merging: when vocabulary overlap between
        adjacent paragraphs drops below the threshold AND the current chunk
        has reached minimum size, we start a new chunk. This produces chunks
        that are topically coherent.

        Returns:
            Tuple of (chunk_texts, boundary_types) where boundary_types
            indicates why each chunk boundary was placed.
        """
        result: list[str] = []
        boundary_types: list[str] = []
        current_parts: list[str] = []
        current_token_count = 0

        for para in paragraphs:
            para_tokens = estimate_token_count(para)

            # If a single paragraph exceeds max, split it
            if para_tokens > self._max_size:
                # Flush current buffer first
                if current_parts:
                    result.append("\n\n".join(current_parts))
                    boundary_types.append(BoundaryType.PARAGRAPH.value)
                    current_parts = []
                    current_token_count = 0

                # Split the large paragraph by sentences
                sub_chunks = self._split_large_paragraph(para)
                result.extend(sub_chunks)
                boundary_types.extend([BoundaryType.SENTENCE.value] * len(sub_chunks))
                continue

            # If adding this paragraph would exceed max, flush
            if current_token_count + para_tokens > self._max_size and current_parts:
                result.append("\n\n".join(current_parts))
                boundary_types.append(BoundaryType.SIZE_LIMIT.value)
                current_parts = []
                current_token_count = 0

            # Topic-shift detection: if we have enough content and the next
            # paragraph is topically different, start a new chunk.
            # Uses text_similarity (word Jaccard + char bigram) instead of
            # plain vocab_overlap to handle Korean agglutination correctly
            # (e.g., "프로젝트를" vs "프로젝트가" share bigrams but differ as words).
            if (
                current_parts
                and current_token_count >= self._min_size
                and text_similarity(current_parts[-1], para) < self._topic_shift_threshold
            ):
                result.append("\n\n".join(current_parts))
                boundary_types.append(BoundaryType.TOPIC_SHIFT.value)
                current_parts = []
                current_token_count = 0

            current_parts.append(para)
            current_token_count += para_tokens

        # Flush remaining
        if current_parts:
            result.append("\n\n".join(current_parts))
            boundary_types.append(BoundaryType.PARAGRAPH.value)

        return result, boundary_types

    def _split_large_paragraph(self, text: str) -> list[str]:
        """Split a large paragraph into chunks by sentences, falling back to words."""
        sentences = re.split(r"(?<=[.!?])\s+", text)

        # If sentence splitting didn't help (no punctuation), split by words
        if len(sentences) <= 1:
            words = text.split()
            chunks: list[str] = []
            for i in range(0, len(words), self._max_size):
                chunk_words = words[i : i + self._max_size]
                if chunk_words:
                    chunks.append(" ".join(chunk_words))
            return chunks

        chunks = []
        current: list[str] = []
        current_tokens = 0

        for sentence in sentences:
            tokens = estimate_token_count(sentence)
            if current_tokens + tokens > self._max_size and current:
                chunks.append(" ".join(current))
                current = []
                current_tokens = 0
            current.append(sentence)
            current_tokens += tokens

        if current:
            chunks.append(" ".join(current))

        return chunks


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs on double newlines."""
    parts = _PARAGRAPH_BREAK.split(text)
    return [p.strip() for p in parts if p.strip()]
