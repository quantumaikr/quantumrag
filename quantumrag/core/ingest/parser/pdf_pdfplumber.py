"""PDF parser using pdfplumber — an alternative variant to pymupdf."""

from __future__ import annotations

from pathlib import Path

from quantumrag.core.errors import ParseError
from quantumrag.core.logging import get_logger
from quantumrag.core.models import Document, DocumentMetadata, SourceType
from quantumrag.core.utils.text import normalize_extracted_text

logger = get_logger(__name__)


class PDFPlumberParser:
    """Parser for PDF files using pdfplumber.

    pdfplumber is a lazy/optional dependency. If not installed, a clear
    error message is provided. It tends to produce cleaner text extraction
    for table-heavy documents compared to pymupdf.
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [".pdf"]

    def parse(self, file_path: Path) -> Document:
        """Parse a PDF file using pdfplumber.

        Args:
            file_path: Path to the PDF file.

        Returns:
            Parsed Document.

        Raises:
            ParseError: If pdfplumber is not installed or parsing fails.
        """
        if not file_path.exists():
            raise ParseError(f"File not found: {file_path}", file_path=str(file_path))

        try:
            import pdfplumber
        except ImportError:
            raise ParseError(
                "pdfplumber is required for the pdfplumber PDF parser variant",
                file_path=str(file_path),
                suggestion="Install it with: pip install pdfplumber",
            ) from None

        try:
            with pdfplumber.open(str(file_path)) as pdf:
                pages_text: list[str] = []
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    if text.strip():
                        pages_text.append(text.strip())

                content = normalize_extracted_text("\n\n".join(pages_text))

                # Extract metadata from PDF info dict
                pdf_meta = pdf.metadata or {}
                title = pdf_meta.get("Title", "") or file_path.stem
                author = pdf_meta.get("Author") or None

                return Document(
                    content=content,
                    metadata=DocumentMetadata(
                        source_type=SourceType.FILE,
                        title=title,
                        author=author,
                        custom={
                            "page_count": str(len(pages_text)),
                            "format": "pdf",
                            "parser_variant": "pdfplumber",
                        },
                    ),
                    raw_bytes=file_path.read_bytes(),
                )

        except ParseError:
            raise
        except Exception as e:
            raise ParseError(
                f"Failed to extract text from PDF with pdfplumber: {e}",
                file_path=str(file_path),
            ) from e
