"""Parser framework for document ingestion."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Protocol, runtime_checkable

from quantumrag.core.errors import ParseError
from quantumrag.core.logging import get_logger
from quantumrag.core.models import Document

logger = get_logger(__name__)


@runtime_checkable
class Parser(Protocol):
    """Protocol for document parsers."""

    def parse(self, file_path: Path) -> Document:
        """Parse a file and return a Document.

        Args:
            file_path: Path to the file to parse.

        Returns:
            Parsed Document instance.

        Raises:
            ParseError: If parsing fails.
        """
        ...

    @property
    def supported_extensions(self) -> list[str]:
        """Return list of supported file extensions (e.g., ['.txt', '.text'])."""
        ...


class ParserRegistry:
    """Registry mapping file extensions and MIME types to parser classes.

    Usage:
        registry = ParserRegistry()
        registry.register(PlainTextParser())
        parser = registry.get_parser(".txt")
        doc = parser.parse(Path("file.txt"))
    """

    def __init__(self) -> None:
        self._extension_map: dict[str, Parser] = {}
        self._mime_map: dict[str, Parser] = {}

    def register(self, parser: Parser, mime_types: list[str] | None = None) -> None:
        """Register a parser for its supported extensions and optional MIME types.

        Args:
            parser: Parser instance to register.
            mime_types: Optional list of MIME types this parser handles.
        """
        for ext in parser.supported_extensions:
            ext_lower = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            self._extension_map[ext_lower] = parser
            logger.debug("registered_parser", extension=ext_lower, parser=type(parser).__name__)

        if mime_types:
            for mime in mime_types:
                self._mime_map[mime.lower()] = parser

    def get_parser(self, file_path: str | Path) -> Parser:
        """Get the appropriate parser for a file.

        Tries extension-based lookup first, then MIME type detection.

        Args:
            file_path: Path to the file (or just an extension string like '.txt').

        Returns:
            Matching Parser instance.

        Raises:
            ParseError: If no parser is found for the file type.
        """
        file_str = str(file_path)
        # If caller passed just an extension like ".md", use it directly
        if file_str.startswith(".") and "/" not in file_str and "\\" not in file_str:
            ext = file_str.lower()
        else:
            ext = Path(file_path).suffix.lower()
        path = Path(file_path)

        # Try extension first
        if ext in self._extension_map:
            return self._extension_map[ext]

        # Try MIME type detection
        mime_type = _detect_mime_type(path)
        if mime_type and mime_type in self._mime_map:
            return self._mime_map[mime_type]

        raise ParseError(
            f"No parser registered for file type '{ext}'",
            file_path=str(file_path),
            suggestion=f"Supported extensions: {', '.join(sorted(self._extension_map.keys()))}",
        )

    @property
    def supported_extensions(self) -> list[str]:
        """Return all registered extensions."""
        return sorted(self._extension_map.keys())

    def has_parser(self, ext: str) -> bool:
        """Check if a parser is registered for the given extension."""
        ext_lower = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        return ext_lower in self._extension_map


def _detect_mime_type(path: Path) -> str | None:
    """Detect MIME type via magic bytes if available, falling back to extension.

    Args:
        path: File path to detect.

    Returns:
        MIME type string or None.
    """
    # Try python-magic for magic-bytes detection
    if path.exists():
        try:
            import magic

            mime = magic.from_file(str(path), mime=True)
            if mime:
                return mime.lower()
        except ImportError:
            pass
        except Exception:
            pass

    # Fallback to mimetypes from stdlib
    mime_type, _ = mimetypes.guess_type(str(path))
    return mime_type.lower() if mime_type else None


def create_default_registry() -> ParserRegistry:
    """Create a ParserRegistry with all built-in parsers registered.

    Returns:
        ParserRegistry with all available parsers.
    """
    registry = ParserRegistry()

    # Import and register built-in parsers
    from quantumrag.core.ingest.parser.text import (
        CSVParser,
        HTMLParser,
        MarkdownParser,
        PlainTextParser,
    )

    registry.register(PlainTextParser(), mime_types=["text/plain"])
    registry.register(MarkdownParser(), mime_types=["text/markdown"])
    registry.register(HTMLParser(), mime_types=["text/html"])
    registry.register(CSVParser(), mime_types=["text/csv"])

    # PDF parser
    from quantumrag.core.ingest.parser.pdf import PDFParser

    registry.register(PDFParser(), mime_types=["application/pdf"])

    # Office parsers
    from quantumrag.core.ingest.parser.office import DocxParser, PptxParser, XlsxParser

    registry.register(
        DocxParser(),
        mime_types=["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    )
    registry.register(
        PptxParser(),
        mime_types=["application/vnd.openxmlformats-officedocument.presentationml.presentation"],
    )
    registry.register(
        XlsxParser(),
        mime_types=["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    )

    # HWP parser
    from quantumrag.core.ingest.parser.hwp import HWPParser

    registry.register(HWPParser())

    return registry
