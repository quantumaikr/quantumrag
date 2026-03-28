"""Chunk Denoising Layer — post-parse, pre-chunk text cleaning.

Removes noise from parsed document text, especially HWPX government documents.
Regex-based only (no LLM calls).
"""

from __future__ import annotations

import re

from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.ingest.denoiser")

# Pre-compiled patterns
_HWPX_IMAGE_BLOCK = re.compile(
    r"그림입니다\.\s*\n" r"(?:원본 그림의 (?:이름|크기|용량)[^\n]*\n)*",
    re.MULTILINE,
)
# Page numbers: standalone digits on a line, but only if they look like
# sequential page numbers (1-4 digits). Lines with 5+ digits are likely
# data values (account numbers, IDs) and should be preserved.
# Also skip if the previous/next line contains a pipe (table context).
_STANDALONE_PAGE_NUMBER_SIMPLE = re.compile(r"^\d{1,4}$", re.MULTILINE)
_FOOTNOTE_MARKER = re.compile(r"^(?:\(\^?\d+\)|\^?\d+\.)$", re.MULTILINE)
_EXCESSIVE_NEWLINES = re.compile(r"\n{3,}")
_ZERO_WIDTH_AND_CONTROL = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\u200b-\u200f\u2028-\u202f\ufeff\u2060\u00ad]"
)
_SPECIAL_CHAR_ONLY_LINE = re.compile(r"^[─━═■□●○◆◇▲△▽▼☆★\-=_|+*~#\s]+$", re.MULTILINE)


class TextDenoiser:
    """Removes noise from parsed document text before chunking."""

    def denoise(self, text: str) -> str:
        """Apply all denoising rules and return cleaned text."""
        original_len = len(text)

        text = self.remove_hwpx_image_blocks(text)
        text = self.remove_standalone_page_numbers(text)
        text = self.remove_footnote_markers(text)
        text = self.remove_zero_width_and_control_chars(text)
        text = self.remove_special_char_only_lines(text)
        text = self.normalize_excessive_newlines(text)

        removed = original_len - len(text)
        if removed > 0:
            logger.debug(
                "denoised",
                chars_removed=removed,
                original_len=original_len,
                cleaned_len=len(text),
            )
        return text

    def remove_hwpx_image_blocks(self, text: str) -> str:
        """Remove HWPX image metadata blocks (lines starting with '그림입니다.')."""
        return _HWPX_IMAGE_BLOCK.sub("", text)

    def remove_standalone_page_numbers(self, text: str) -> str:
        """Remove lines that are only digits (likely page numbers).

        Safety: preserves standalone numbers that appear inside tables
        (adjacent to pipe-delimited lines) or that are 5+ digits (likely
        data values like IDs or account numbers).
        """
        lines = text.split("\n")
        result: list[str] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Only consider 1-4 digit standalone lines
            if _STANDALONE_PAGE_NUMBER_SIMPLE.fullmatch(stripped):
                # Check if adjacent lines look like table rows (contain |)
                prev_line = lines[i - 1].strip() if i > 0 else ""
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if "|" in prev_line or "|" in next_line:
                    result.append(line)  # preserve — likely table data
                    continue
                # Skip this line (likely a page number)
                continue
            result.append(line)
        return "\n".join(result)

    def remove_footnote_markers(self, text: str) -> str:
        """Remove standalone footnote markers like '^1.', '^2.', '(^3)'."""
        return _FOOTNOTE_MARKER.sub("", text)

    def normalize_excessive_newlines(self, text: str) -> str:
        """Collapse 3+ consecutive newlines to 2."""
        return _EXCESSIVE_NEWLINES.sub("\n\n", text)

    def remove_zero_width_and_control_chars(self, text: str) -> str:
        """Remove zero-width characters and control characters (except \\n, \\t)."""
        return _ZERO_WIDTH_AND_CONTROL.sub("", text)

    def remove_special_char_only_lines(self, text: str) -> str:
        """Strip lines that contain only special/decorative characters."""
        return _SPECIAL_CHAR_ONLY_LINE.sub("", text)
