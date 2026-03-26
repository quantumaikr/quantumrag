"""Document parse quality checker."""

from __future__ import annotations

import re
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Document
from quantumrag.core.utils.text import ends_with_terminator

logger = get_logger(__name__)

# Characters that typically indicate encoding errors or failed text extraction
_BROKEN_CHARS_PATTERN = re.compile(r"[\ufffd\ufffe\ufeff]|\\x[0-9a-fA-F]{2}")

# Minimum content length to consider a document valid
_MIN_CONTENT_LENGTH = 10

# Common boilerplate patterns (page numbers, copyright, confidential)
_BOILERPLATE_RE = re.compile(
    r"^(page\s*\d+|페이지\s*\d+|\d+/\d+|copyright|©|confidential|기밀)",
    re.IGNORECASE,
)


class QualityChecker:
    """Scores document parse quality on a 0.0-1.0 scale.

    Checks performed:
    - Empty or near-empty content
    - Encoding error indicators (replacement characters, etc.)
    - Content density (ratio of meaningful text to total length)
    - Whitespace ratio

    Usage:
        checker = QualityChecker()
        score = checker.check(document)
        # score is written to document.metadata.quality_score
    """

    def __init__(
        self,
        min_length: int = _MIN_CONTENT_LENGTH,
    ) -> None:
        self._min_length = min_length

    def check(self, document: Document) -> float:
        """Score document quality and update metadata.

        Args:
            document: Document to check.

        Returns:
            Quality score between 0.0 and 1.0.
        """
        content = document.content
        scores: list[float] = []

        # Check 1: Content length
        length_score = self._check_content_length(content)
        scores.append(length_score)

        if length_score == 0.0:
            # No point checking further if content is empty
            document.metadata.quality_score = 0.0
            return 0.0

        # Check 2: Encoding errors (broken characters)
        encoding_score = self._check_encoding_errors(content)
        scores.append(encoding_score)

        # Check 3: Content density (non-whitespace ratio)
        density_score = self._check_content_density(content)
        scores.append(density_score)

        # Check 4: Repetition check
        repetition_score = self._check_repetition(content)
        scores.append(repetition_score)

        # Weighted average
        weights = [0.3, 0.3, 0.2, 0.2]
        total = sum(s * w for s, w in zip(scores, weights))

        # Clamp to [0.0, 1.0]
        quality = max(0.0, min(1.0, total))
        document.metadata.quality_score = round(quality, 3)

        logger.debug(
            "quality_check",
            doc_id=document.id,
            score=document.metadata.quality_score,
            length_score=length_score,
            encoding_score=encoding_score,
            density_score=density_score,
            repetition_score=repetition_score,
        )

        return document.metadata.quality_score

    def _check_content_length(self, content: str) -> float:
        """Score based on content length."""
        length = len(content.strip())
        if length == 0:
            return 0.0
        if length < self._min_length:
            return 0.3
        if length < 100:
            return 0.7
        return 1.0

    def _check_encoding_errors(self, content: str) -> float:
        """Score based on presence of encoding error characters."""
        if not content:
            return 0.0

        broken_count = len(_BROKEN_CHARS_PATTERN.findall(content))
        total_chars = len(content)

        if broken_count == 0:
            return 1.0

        error_ratio = broken_count / total_chars
        if error_ratio > 0.1:
            return 0.1
        if error_ratio > 0.05:
            return 0.3
        if error_ratio > 0.01:
            return 0.6
        return 0.8

    def _check_content_density(self, content: str) -> float:
        """Score based on ratio of non-whitespace to total content."""
        if not content:
            return 0.0

        non_whitespace = len(content.replace(" ", "").replace("\n", "").replace("\t", ""))
        total = len(content)

        if total == 0:
            return 0.0

        density = non_whitespace / total

        if density < 0.1:
            return 0.2
        if density < 0.3:
            return 0.5
        if density > 0.95:
            # Extremely dense text (no spaces) is suspicious
            return 0.7
        return 1.0

    def _check_repetition(self, content: str) -> float:
        """Score based on content repetition (low repetition is better)."""
        if len(content) < 100:
            return 1.0

        # Check for repeated lines
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return 0.5

        unique_lines = set(lines)
        if len(lines) == 0:
            return 0.5

        uniqueness = len(unique_lines) / len(lines)

        if uniqueness < 0.3:
            return 0.2
        if uniqueness < 0.5:
            return 0.5
        return 1.0


class ChunkQualityChecker:
    """Post-chunking quality validation for individual chunks.

    Detects common chunking problems:
    - Chunks that are too short to be useful
    - Chunks that are mostly metadata/boilerplate (headers, footers)
    - Chunks that lost coherence during splitting (sentence fragments)
    """

    def __init__(
        self,
        min_words: int = 15,
        max_metadata_ratio: float = 0.7,
    ) -> None:
        self._min_words = min_words
        self._max_metadata_ratio = max_metadata_ratio

    def filter_chunks(self, chunks: list) -> list:
        """Filter out low-quality chunks, returning only viable ones.

        Args:
            chunks: List of Chunk objects to validate.

        Returns:
            Filtered list with low-quality chunks removed.
        """
        from quantumrag.core.models import Chunk

        valid: list[Chunk] = []
        removed = 0

        for chunk in chunks:
            score = self.score_chunk(chunk)
            if score >= 0.3:
                chunk.metadata["chunk_quality"] = round(score, 2)
                valid.append(chunk)
            else:
                removed += 1

        if removed:
            logger.info("chunks_filtered", removed=removed, kept=len(valid))

        return valid

    def score_chunk(self, chunk: Any) -> float:
        """Score a single chunk's quality (0.0-1.0)."""
        content = chunk.content.strip()

        # Empty or very short
        words = content.split()
        if len(words) < self._min_words:
            return 0.1

        # Mostly boilerplate/metadata patterns
        boilerplate_lines = 0
        total_lines = 0
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            total_lines += 1
            if _BOILERPLATE_RE.match(stripped):
                boilerplate_lines += 1

        if total_lines > 0 and boilerplate_lines / total_lines > self._max_metadata_ratio:
            return 0.2

        # Sentence fragment detection: if content doesn't end with a sentence
        # terminator and is short, it's likely a fragment
        if len(words) < 30 and not ends_with_terminator(content):
            return 0.4

        return 1.0
