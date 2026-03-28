"""Parser framework for document ingestion."""

from __future__ import annotations

import mimetypes
import time
from dataclasses import dataclass, field
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


@dataclass
class ParserVariant:
    """A named parser variant for A/B testing.

    Attributes:
        name: Unique identifier for this variant (e.g., "pymupdf", "pdfplumber").
        parser: The parser instance.
        description: Optional human-readable description.
    """

    name: str
    parser: Parser
    description: str = ""


@dataclass
class BenchmarkResult:
    """Result of benchmarking a single parser variant on a file.

    Attributes:
        variant_name: Name of the parser variant.
        file_path: Path to the file that was parsed.
        parse_time_ms: Time taken to parse in milliseconds.
        text_length: Length of extracted text in characters.
        word_count: Number of whitespace-delimited words.
        success: Whether parsing succeeded.
        error: Error message if parsing failed.
    """

    variant_name: str
    file_path: str
    parse_time_ms: float = 0.0
    text_length: int = 0
    word_count: int = 0
    success: bool = True
    error: str = ""


@dataclass
class ComparisonReport:
    """Report comparing two or more parser variants on the same file.

    Attributes:
        file_path: Path to the file that was parsed.
        results: List of BenchmarkResult, one per variant.
        text_diff_ratio: Ratio of text length difference to the longer text (0.0 = identical length).
    """

    file_path: str
    results: list[BenchmarkResult] = field(default_factory=list)
    text_diff_ratio: float = 0.0


class ParserBenchmark:
    """Compare parser variants on the same file(s).

    Usage:
        benchmark = ParserBenchmark()
        report = benchmark.compare(
            file_path=Path("doc.pdf"),
            variants=[
                ParserVariant("pymupdf", PDFParser()),
                ParserVariant("pdfplumber", PDFPlumberParser()),
            ],
        )
        for r in report.results:
            print(f"{r.variant_name}: {r.text_length} chars in {r.parse_time_ms:.1f}ms")
    """

    def compare(
        self,
        file_path: Path,
        variants: list[ParserVariant],
    ) -> ComparisonReport:
        """Run all variants on a single file and produce a comparison report.

        Args:
            file_path: Path to the file to parse.
            variants: Parser variants to compare.

        Returns:
            ComparisonReport with per-variant results.
        """
        results: list[BenchmarkResult] = []

        for variant in variants:
            result = self._run_single(file_path, variant)
            results.append(result)

        report = ComparisonReport(file_path=str(file_path), results=results)

        # Compute text diff ratio between the two longest successful outputs
        successful = [r for r in results if r.success]
        if len(successful) >= 2:
            lengths = sorted([r.text_length for r in successful], reverse=True)
            max_len = lengths[0]
            if max_len > 0:
                report.text_diff_ratio = (lengths[0] - lengths[1]) / max_len

        return report

    def _run_single(self, file_path: Path, variant: ParserVariant) -> BenchmarkResult:
        """Run a single variant and capture metrics."""
        start = time.perf_counter()
        try:
            doc = variant.parser.parse(file_path)
            elapsed_ms = (time.perf_counter() - start) * 1000
            content = doc.content
            return BenchmarkResult(
                variant_name=variant.name,
                file_path=str(file_path),
                parse_time_ms=elapsed_ms,
                text_length=len(content),
                word_count=len(content.split()),
                success=True,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return BenchmarkResult(
                variant_name=variant.name,
                file_path=str(file_path),
                parse_time_ms=elapsed_ms,
                success=False,
                error=str(e),
            )


class ParserRegistry:
    """Registry mapping file extensions and MIME types to parser classes.

    Supports variant-based registration for A/B testing. Each extension can
    have multiple parser variants, but only one is active at a time.

    Usage:
        registry = ParserRegistry()
        registry.register(PlainTextParser())
        parser = registry.get_parser(".txt")
        doc = parser.parse(Path("file.txt"))

    Variant usage:
        registry.register_variant(".pdf", ParserVariant("pymupdf", PDFParser()))
        registry.register_variant(".pdf", ParserVariant("pdfplumber", PDFPlumberParser()))
        variants = registry.get_parser_variants(".pdf")
    """

    def __init__(self) -> None:
        self._extension_map: dict[str, Parser] = {}
        self._mime_map: dict[str, Parser] = {}
        # variant_name -> Parser, keyed by normalized extension
        self._variants: dict[str, dict[str, ParserVariant]] = {}

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

    def register_variant(
        self,
        extension: str,
        variant: ParserVariant,
        mime_types: list[str] | None = None,
    ) -> None:
        """Register a named parser variant for a file extension.

        The first variant registered for an extension also becomes the active
        parser (via :meth:`register`), unless one is already registered.

        Args:
            extension: File extension (e.g., ".pdf").
            variant: ParserVariant to register.
            mime_types: Optional MIME types handled by this variant.
        """
        ext_lower = extension.lower() if extension.startswith(".") else f".{extension.lower()}"

        if ext_lower not in self._variants:
            self._variants[ext_lower] = {}

        self._variants[ext_lower][variant.name] = variant
        logger.debug(
            "registered_variant",
            extension=ext_lower,
            variant=variant.name,
            parser=type(variant.parser).__name__,
        )

        # If no active parser for this extension yet, set this variant as active
        if ext_lower not in self._extension_map:
            self._extension_map[ext_lower] = variant.parser
            if mime_types:
                for mime in mime_types:
                    self._mime_map[mime.lower()] = variant.parser

    def get_parser_variants(self, extension: str) -> dict[str, ParserVariant]:
        """Get all registered variants for a file extension.

        Args:
            extension: File extension (e.g., ".pdf").

        Returns:
            Dict mapping variant name to ParserVariant. Empty dict if none registered.
        """
        ext_lower = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        return dict(self._variants.get(ext_lower, {}))

    def set_active_variant(
        self,
        extension: str,
        variant_name: str,
        mime_types: list[str] | None = None,
    ) -> None:
        """Set the active parser variant for an extension.

        Args:
            extension: File extension (e.g., ".pdf").
            variant_name: Name of the variant to activate.
            mime_types: Optional MIME types to re-map to this variant.

        Raises:
            ParseError: If the variant is not found.
        """
        ext_lower = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        variants = self._variants.get(ext_lower, {})

        if variant_name not in variants:
            available = list(variants.keys()) if variants else []
            raise ParseError(
                f"Variant '{variant_name}' not found for extension '{ext_lower}'",
                suggestion=f"Available variants: {', '.join(available)}"
                if available
                else "No variants registered.",
            )

        variant = variants[variant_name]
        self._extension_map[ext_lower] = variant.parser
        if mime_types:
            for mime in mime_types:
                self._mime_map[mime.lower()] = variant.parser

        logger.debug(
            "activated_variant",
            extension=ext_lower,
            variant=variant_name,
        )

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
                return str(mime).lower()
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

    # PDF parser (default: pymupdf)
    from quantumrag.core.ingest.parser.pdf import PDFParser

    registry.register(PDFParser(), mime_types=["application/pdf"])
    registry.register_variant(
        ".pdf",
        ParserVariant("pymupdf", PDFParser(), description="PDF parser using pymupdf (fitz)"),
        mime_types=["application/pdf"],
    )

    # PDF pdfplumber variant
    from quantumrag.core.ingest.parser.pdf_pdfplumber import PDFPlumberParser

    registry.register_variant(
        ".pdf",
        ParserVariant("pdfplumber", PDFPlumberParser(), description="PDF parser using pdfplumber"),
    )

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

    # HWP parser (default variant)
    from quantumrag.core.ingest.parser.hwp import HWPParser

    registry.register(HWPParser())
    registry.register_variant(
        ".hwp",
        ParserVariant("default", HWPParser(), description="HWP parser using olefile"),
    )
    registry.register_variant(
        ".hwpx",
        ParserVariant("default", HWPParser(), description="HWPX parser using XML extraction"),
    )

    # HWP pyhwpx variant
    from quantumrag.core.ingest.parser.hwp_pyhwpx import HWPXPyhwpxParser

    registry.register_variant(
        ".hwpx",
        ParserVariant("pyhwpx", HWPXPyhwpxParser(), description="HWPX parser using pyhwpx"),
    )

    return registry


def create_registry_with_variants(
    variant_overrides: dict[str, str] | None = None,
) -> ParserRegistry:
    """Create a ParserRegistry with specific variants activated per extension.

    Starts from the default registry, then activates the specified variants.

    Args:
        variant_overrides: Mapping of extension to variant name, e.g.
            ``{".pdf": "pdfplumber", ".hwpx": "pyhwpx"}``.

    Returns:
        ParserRegistry with the requested variants active.

    Example:
        registry = create_registry_with_variants({".pdf": "pdfplumber"})
        parser = registry.get_parser("report.pdf")  # uses pdfplumber
    """
    registry = create_default_registry()

    if variant_overrides:
        # Map extensions to their known MIME types for re-mapping
        mime_map: dict[str, list[str]] = {
            ".pdf": ["application/pdf"],
        }
        for ext, variant_name in variant_overrides.items():
            registry.set_active_variant(
                ext,
                variant_name,
                mime_types=mime_map.get(ext.lower()),
            )

    return registry
