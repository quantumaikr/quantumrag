"""PDF parser using pymupdf (fitz)."""

from __future__ import annotations

from pathlib import Path

from quantumrag.core.errors import ParseError
from quantumrag.core.logging import get_logger
from quantumrag.core.models import Document, DocumentMetadata, SourceType
from quantumrag.core.utils.text import normalize_extracted_text

logger = get_logger(__name__)


def _table_to_markdown(table) -> str:
    """Convert a pymupdf table object to Markdown table syntax.

    Args:
        table: A pymupdf ``Table`` object returned by ``page.find_tables()``.

    Returns:
        A string containing the table formatted as a Markdown table with
        ``|`` column separators and a header separator row.
    """
    rows = table.extract()
    if not rows:
        return ""

    # First row is treated as the header.
    header = rows[0]
    # Replace None cells with empty strings.
    header = [str(cell) if cell is not None else "" for cell in header]

    lines: list[str] = []
    # Header row
    lines.append("| " + " | ".join(header) + " |")
    # Separator row
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    # Data rows
    for row in rows[1:]:
        cells = [str(cell) if cell is not None else "" for cell in row]
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def _has_find_tables(page) -> bool:
    """Check whether the pymupdf page object supports ``find_tables()``."""
    return callable(getattr(page, "find_tables", None))


def _detect_heading_thresholds(doc) -> tuple[float, float]:
    """Analyze font sizes across the PDF to detect heading thresholds.

    Returns (h1_threshold, h2_threshold) where text at or above h1 is
    rendered as ``# Heading`` and text between h2 and h1 as ``## Heading``.
    """
    size_counts: dict[float, int] = {}
    for page_num in range(len(doc)):
        try:
            page_dict = doc[page_num].get_text("dict")
        except Exception:
            continue
        for block in page_dict.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if len(text) < 2:
                        continue
                    size = round(span.get("size", 0), 1)
                    size_counts[size] = size_counts.get(size, 0) + 1

    if not size_counts:
        return (999.0, 999.0)  # No headings possible

    # Body text is the most frequent font size
    body_size = max(size_counts, key=lambda s: size_counts[s])

    # Heading sizes = significantly larger than body (≥ 1.3x)
    heading_sizes = sorted(
        [s for s in size_counts if s >= body_size * 1.3],
        reverse=True,
    )

    if not heading_sizes:
        return (999.0, 999.0)

    # H1 = top tier (≥ body * 1.6), H2 = remaining heading sizes
    # Subtract 0.5 from thresholds to account for sub-pixel font sizes
    # (e.g., pymupdf reports 16.99pt for nominally 17pt fonts)
    h1_threshold = body_size * 1.6 - 0.5
    h2_threshold = min(heading_sizes) - 0.5

    return (h1_threshold, h2_threshold)


def _extract_page_text(
    page,
    page_num: int,
    h1_threshold: float = 999.0,
    h2_threshold: float = 999.0,
) -> str:
    """Extract text from a single PDF page with structure preservation.

    - Tables detected via ``find_tables()`` are converted to Markdown.
    - Large/bold text is converted to Markdown headings (``#`` / ``##``).
    - This enables downstream structural chunking with breadcrumbs.
    """
    plain_text: str = page.get_text("text")

    try:
        page_dict = page.get_text("dict")
    except Exception:
        return plain_text.strip()

    blocks = page_dict.get("blocks", [])

    # Detect tables if supported
    table_regions: list[tuple[float, float, float, float, str]] = []
    if _has_find_tables(page):
        try:
            tables = page.find_tables()
            if tables and tables.tables:
                for tbl in tables.tables:
                    md = _table_to_markdown(tbl)
                    if md:
                        table_regions.append(
                            (tbl.bbox[0], tbl.bbox[1], tbl.bbox[2], tbl.bbox[3], md)
                        )
                table_regions.sort(key=lambda r: r[1])
        except Exception:
            pass

    def _block_overlaps_table(block_bbox: tuple, table_bbox: tuple) -> bool:
        _, by0, _, by1 = block_bbox
        _, ty0, _, ty1 = table_bbox[:4]
        return by0 < ty1 and by1 > ty0

    output_parts: list[str] = []
    used_tables: set[int] = set()

    for block in sorted(
        blocks,
        key=lambda b: (b.get("bbox", [0, 0])[1], b.get("bbox", [0, 0])[0]),
    ):
        if block.get("type", 0) != 0:
            continue

        block_bbox = block.get("bbox", (0, 0, 0, 0))

        # Check table overlap
        matched_table_idx: int | None = None
        for idx, tr in enumerate(table_regions):
            if idx not in used_tables and _block_overlaps_table(block_bbox, tr):
                matched_table_idx = idx
                break

        if matched_table_idx is not None:
            if matched_table_idx not in used_tables:
                output_parts.append(table_regions[matched_table_idx][4])
                used_tables.add(matched_table_idx)
            continue

        # Reconstruct text with heading detection
        block_text_parts: list[str] = []
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            line_text = "".join(s.get("text", "") for s in spans).strip()
            if not line_text:
                continue

            # Detect heading: check dominant font size in this line
            max_size = max((s.get("size", 0) for s in spans), default=0)
            is_bold = any(s.get("flags", 0) & (1 << 4) for s in spans)

            if max_size >= h1_threshold and is_bold and len(line_text) < 120:
                block_text_parts.append(f"\n# {line_text}")
            elif max_size >= h2_threshold and is_bold and len(line_text) < 120:
                block_text_parts.append(f"\n## {line_text}")
            else:
                block_text_parts.append(line_text)

        if block_text_parts:
            output_parts.append("\n".join(block_text_parts))

    result = "\n\n".join(output_parts)
    return result.strip() if result.strip() else plain_text.strip()


class PDFParser:
    """Parser for PDF files using pymupdf (fitz).

    pymupdf is a lazy/optional dependency. If not installed, a clear
    error message is provided.
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [".pdf"]

    def parse(self, file_path: Path) -> Document:
        """Parse a PDF file and extract text with basic structure preservation.

        Tables detected via pymupdf's ``find_tables()`` API are converted to
        Markdown table syntax so that row/column relationships survive chunking.
        If ``find_tables()`` is unavailable (older pymupdf) or fails, the parser
        gracefully falls back to plain text extraction.

        Args:
            file_path: Path to the PDF file.

        Returns:
            Parsed Document.

        Raises:
            ParseError: If pymupdf is not installed or parsing fails.
        """
        if not file_path.exists():
            raise ParseError(f"File not found: {file_path}", file_path=str(file_path))

        try:
            import fitz  # pymupdf
        except ImportError:
            raise ParseError(
                "pymupdf is required to parse PDF files",
                file_path=str(file_path),
                suggestion="Install it with: pip install pymupdf",
            ) from None

        try:
            doc = fitz.open(str(file_path))
        except Exception as e:
            raise ParseError(
                f"Failed to open PDF: {e}",
                file_path=str(file_path),
            ) from e

        try:
            # Detect heading font sizes for structural extraction
            h1_thresh, h2_thresh = _detect_heading_thresholds(doc)

            pages_text: list[str] = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = _extract_page_text(page, page_num, h1_thresh, h2_thresh)
                if text.strip():
                    pages_text.append(text.strip())

            content = normalize_extracted_text("\n\n".join(pages_text))

            # Extract metadata
            pdf_meta = doc.metadata or {}
            title = pdf_meta.get("title", "") or file_path.stem
            author = pdf_meta.get("author") or None

            doc.close()

            return Document(
                content=content,
                metadata=DocumentMetadata(
                    source_type=SourceType.FILE,
                    title=title,
                    author=author,
                    custom={
                        "page_count": str(len(pages_text)),
                        "format": "pdf",
                    },
                ),
                raw_bytes=file_path.read_bytes(),
            )

        except ParseError:
            raise
        except Exception as e:
            raise ParseError(
                f"Failed to extract text from PDF: {e}",
                file_path=str(file_path),
            ) from e
