"""Fixed-size chunking with overlap and sentence boundary respect."""

from __future__ import annotations

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk, Document
from quantumrag.core.utils.text import (
    estimate_token_count,
    split_preserving_blocks,
    split_sentences_with_fallback,
)

logger = get_logger(__name__)


class FixedSizeChunker:
    """Token-based fixed-size chunker with overlap.

    Uses simple word-based approximation for token counting (no external
    tokenizer needed for MVP). Respects sentence boundaries when possible.

    Args:
        chunk_size: Target chunk size in words (approximate tokens).
        overlap: Number of overlap words between consecutive chunks.
    """

    def __init__(self, chunk_size: int = 512, overlap: int = 50) -> None:
        self._chunk_size = max(chunk_size, 1)
        self._overlap = min(overlap, chunk_size // 2)

    def chunk(self, document: Document) -> list[Chunk]:
        """Split document into fixed-size chunks.

        Pre-processes text to protect markdown tables as atomic blocks,
        then splits remaining text into fixed-size chunks with overlap.
        Uses Korean-aware token estimation for accurate size control.

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
                # Atomic blocks (tables, code) are emitted as-is, never split
                chunks.append(
                    Chunk(
                        content=segment_text,
                        document_id=document.id,
                        chunk_index=chunk_index,
                    )
                )
                chunk_index += 1
                continue

            # Normal text: sentence-based fixed-size chunking
            sub_chunks = self._chunk_text_segment(segment_text, document.id, chunk_index)
            chunks.extend(sub_chunks)
            chunk_index += len(sub_chunks)

        logger.debug(
            "fixed_chunking_done",
            doc_id=document.id,
            chunk_count=len(chunks),
            chunk_size=self._chunk_size,
            overlap=self._overlap,
        )

        return chunks

    def _chunk_text_segment(self, text: str, document_id: str, start_index: int) -> list[Chunk]:
        """Chunk a non-table text segment into fixed-size pieces."""
        sentences = split_sentences_with_fallback(text)
        if not sentences:
            return []

        chunks: list[Chunk] = []
        current_token_count = 0
        current_sentences: list[str] = []
        chunk_index = start_index

        for sentence in sentences:
            sentence_tokens = estimate_token_count(sentence)
            if sentence_tokens == 0:
                continue

            # If a single sentence exceeds chunk_size, split it by words
            if sentence_tokens > self._chunk_size:
                # Flush current buffer first
                if current_sentences:
                    chunk_text = " ".join(current_sentences)
                    chunks.append(
                        Chunk(
                            content=chunk_text,
                            document_id=document_id,
                            chunk_index=chunk_index,
                        )
                    )
                    chunk_index += 1
                    current_sentences = []
                    current_token_count = 0

                # Split the long sentence into word-based sub-chunks
                sentence_words = sentence.split()
                for i in range(0, len(sentence_words), self._chunk_size - self._overlap):
                    sub_words = sentence_words[i : i + self._chunk_size]
                    if sub_words:
                        chunks.append(
                            Chunk(
                                content=" ".join(sub_words),
                                document_id=document_id,
                                chunk_index=chunk_index,
                            )
                        )
                        chunk_index += 1
                continue

            # If adding this sentence exceeds chunk_size and we have content,
            # finalize the current chunk
            if current_sentences and current_token_count + sentence_tokens > self._chunk_size:
                chunk_text = " ".join(current_sentences)
                chunks.append(
                    Chunk(
                        content=chunk_text,
                        document_id=document_id,
                        chunk_index=chunk_index,
                    )
                )
                chunk_index += 1

                # Compute overlap: take last N words worth of sentences
                overlap_text = _compute_overlap(current_sentences, self._overlap)
                current_sentences = [overlap_text] if overlap_text else []
                current_token_count = estimate_token_count(overlap_text) if overlap_text else 0

            current_sentences.append(sentence)
            current_token_count += sentence_tokens

        # Final chunk
        if current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append(
                Chunk(
                    content=chunk_text,
                    document_id=document_id,
                    chunk_index=chunk_index,
                )
            )

        return chunks


def _compute_overlap(sentences: list[str], overlap_words: int) -> str:
    """Compute overlap text from the end of a sentence list.

    Takes complete sentences from the end until we reach the overlap word count.
    """
    if overlap_words <= 0:
        return ""

    result_sentences: list[str] = []
    word_count = 0

    for sentence in reversed(sentences):
        words = sentence.split()
        word_count += len(words)
        result_sentences.insert(0, sentence)
        if word_count >= overlap_words:
            break

    return " ".join(result_sentences)
