"""Basic text parsers: plain text, Markdown, HTML, CSV."""

from __future__ import annotations

import csv
import html
import io
import re
from pathlib import Path

from quantumrag.core.errors import ParseError
from quantumrag.core.logging import get_logger
from quantumrag.core.models import Document, DocumentMetadata, SourceType

logger = get_logger(__name__)


def _read_file_bytes(file_path: Path) -> bytes:
    """Read file as bytes, raising ParseError if file not found or unreadable."""
    if not file_path.exists():
        raise ParseError(f"File not found: {file_path}", file_path=str(file_path))
    if not file_path.is_file():
        raise ParseError(f"Not a file: {file_path}", file_path=str(file_path))
    try:
        return file_path.read_bytes()
    except OSError as e:
        raise ParseError(f"Cannot read file: {e}", file_path=str(file_path)) from e


def _decode_bytes(data: bytes, file_path: Path) -> str:
    """Decode bytes to string with encoding auto-detection.

    Tries UTF-8 first, then charset-normalizer/chardet, then latin-1 fallback.
    """
    # Try UTF-8 first (most common)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # Try charset-normalizer (preferred) or chardet
    try:
        from charset_normalizer import from_bytes

        result = from_bytes(data).best()
        if result is not None:
            return str(result)
    except ImportError:
        pass

    try:
        import chardet

        detected = chardet.detect(data)
        encoding = detected.get("encoding")
        if encoding:
            try:
                return data.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                pass
    except ImportError:
        pass

    # Try common Korean encodings
    for enc in ("euc-kr", "cp949"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            pass

    # Last resort: latin-1 (never fails)
    logger.warning("encoding_fallback", file=str(file_path), encoding="latin-1")
    return data.decode("latin-1")


class PlainTextParser:
    """Parser for plain text files (.txt, .text, .log)."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".txt", ".text", ".log"]

    def parse(self, file_path: Path) -> Document:
        """Parse a plain text file."""
        data = _read_file_bytes(file_path)
        content = _decode_bytes(data, file_path)

        return Document(
            content=content,
            metadata=DocumentMetadata(
                source_type=SourceType.FILE,
                title=file_path.stem,
            ),
            raw_bytes=data,
        )


class MarkdownParser:
    """Parser for Markdown files (.md, .markdown).

    Extracts YAML frontmatter as metadata if present.
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [".md", ".markdown"]

    def parse(self, file_path: Path) -> Document:
        """Parse a Markdown file, extracting frontmatter metadata."""
        data = _read_file_bytes(file_path)
        content = _decode_bytes(data, file_path)

        metadata_dict: dict[str, str] = {}
        body = content

        # Extract YAML frontmatter (--- delimited at start of file)
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter_text = parts[1].strip()
                body = parts[2].strip()
                metadata_dict = _parse_frontmatter(frontmatter_text, file_path)

        title = metadata_dict.get("title", file_path.stem)
        author = metadata_dict.get("author")

        # Remove parsed keys from custom
        custom = {k: v for k, v in metadata_dict.items() if k not in ("title", "author")}

        return Document(
            content=body,
            metadata=DocumentMetadata(
                source_type=SourceType.FILE,
                title=title,
                author=author,
                custom=custom,
            ),
            raw_bytes=data,
        )


def _parse_frontmatter(text: str, file_path: Path) -> dict[str, str]:
    """Parse YAML frontmatter text into a dict."""
    try:
        import yaml

        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict):
            return {k: str(v) for k, v in parsed.items()}
    except Exception as e:
        logger.warning("frontmatter_parse_error", file=str(file_path), error=str(e))
    return {}


class HTMLParser:
    """Parser for HTML files (.html, .htm).

    Uses simple tag stripping (no external dependencies).
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [".html", ".htm"]

    def parse(self, file_path: Path) -> Document:
        """Parse an HTML file, extracting clean text."""
        data = _read_file_bytes(file_path)
        content = _decode_bytes(data, file_path)

        title = _extract_html_title(content) or file_path.stem
        clean_text = strip_html_tags(content)

        return Document(
            content=clean_text,
            metadata=DocumentMetadata(
                source_type=SourceType.FILE,
                title=title,
            ),
            raw_bytes=data,
        )


def _extract_html_title(html_content: str) -> str | None:
    """Extract <title> content from HTML."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
    if match:
        return html.unescape(match.group(1)).strip()
    return None


def strip_html_tags(html_content: str) -> str:
    """Strip HTML tags and decode entities, returning clean text.

    Handles script/style removal and whitespace normalization.
    """
    # Remove script and style blocks
    text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.IGNORECASE | re.DOTALL)

    # Add newlines for block elements
    block_tags = r"</?(p|div|br|hr|h[1-6]|li|tr|blockquote|pre|section|article)[^>]*>"
    text = re.sub(block_tags, "\n", text, flags=re.IGNORECASE)

    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)

    # Decode HTML entities
    text = html.unescape(text)

    # Normalize whitespace
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)

    return text.strip()


class CSVParser:
    """Parser for CSV files (.csv, .tsv).

    Converts CSV data to a structured text representation.
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [".csv", ".tsv"]

    def parse(self, file_path: Path) -> Document:
        """Parse a CSV file into structured text."""
        data = _read_file_bytes(file_path)
        text = _decode_bytes(data, file_path)

        try:
            dialect = csv.Sniffer().sniff(text[:4096])
        except csv.Error:
            dialect = csv.excel  # type: ignore[assignment]

        reader = csv.reader(io.StringIO(text), dialect)
        rows = list(reader)

        if not rows:
            return Document(
                content="",
                metadata=DocumentMetadata(
                    source_type=SourceType.FILE,
                    title=file_path.stem,
                ),
                raw_bytes=data,
            )

        # First row as headers
        headers = rows[0]
        data_rows = rows[1:]

        # Build structured text representation
        parts: list[str] = []
        parts.append(f"Table: {file_path.stem}")
        parts.append(f"Columns: {', '.join(headers)}")
        parts.append(f"Rows: {len(data_rows)}")
        parts.append("")

        for i, row in enumerate(data_rows):
            row_parts = []
            for j, cell in enumerate(row):
                header = headers[j] if j < len(headers) else f"Column {j + 1}"
                row_parts.append(f"{header}: {cell}")
            parts.append(f"Row {i + 1}: {' | '.join(row_parts)}")

        content = "\n".join(parts)

        return Document(
            content=content,
            metadata=DocumentMetadata(
                source_type=SourceType.FILE,
                title=file_path.stem,
                custom={"row_count": str(len(data_rows)), "column_count": str(len(headers))},
            ),
            raw_bytes=data,
        )
