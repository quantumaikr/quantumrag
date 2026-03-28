"""HWPX parser using pyhwpx — an alternative variant for HWPX files."""

from __future__ import annotations

from pathlib import Path

from quantumrag.core.errors import ParseError
from quantumrag.core.logging import get_logger
from quantumrag.core.models import Document, DocumentMetadata, SourceType
from quantumrag.core.utils.text import normalize_extracted_text

logger = get_logger(__name__)


class HWPXPyhwpxParser:
    """Parser for HWPX files using pyhwpx.

    pyhwpx is a lazy/optional dependency that provides more robust HWPX
    parsing with better handling of complex formatting, tables, and
    embedded objects compared to raw XML extraction.

    This variant only supports .hwpx files (not legacy .hwp).
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [".hwpx"]

    def parse(self, file_path: Path) -> Document:
        """Parse an HWPX file using pyhwpx.

        Args:
            file_path: Path to the HWPX file.

        Returns:
            Parsed Document.

        Raises:
            ParseError: If pyhwpx is not installed or parsing fails.
        """
        if not file_path.exists():
            raise ParseError(f"File not found: {file_path}", file_path=str(file_path))

        try:
            from pyhwpx import Hwp
        except ImportError:
            raise ParseError(
                "pyhwpx is required for the pyhwpx HWPX parser variant",
                file_path=str(file_path),
                suggestion="Install it with: pip install pyhwpx",
            ) from None

        try:
            hwp = Hwp()
            hwp.open(str(file_path))

            try:
                content = hwp.get_text()
            except AttributeError:
                # Fallback: some pyhwpx versions use different API
                content = hwp.text if hasattr(hwp, "text") else ""

            if not isinstance(content, str):
                content = str(content)

            content = normalize_extracted_text(content)

            if not content:
                raise ParseError(
                    "No text content extracted from HWPX file via pyhwpx",
                    file_path=str(file_path),
                )

            try:
                hwp.close()
            except Exception:
                pass

            return Document(
                content=content,
                metadata=DocumentMetadata(
                    source_type=SourceType.FILE,
                    title=file_path.stem,
                    custom={
                        "format": "hwpx",
                        "parser_variant": "pyhwpx",
                    },
                ),
                raw_bytes=file_path.read_bytes(),
            )

        except ParseError:
            raise
        except Exception as e:
            raise ParseError(
                f"Failed to parse HWPX file with pyhwpx: {e}",
                file_path=str(file_path),
            ) from e
