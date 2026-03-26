"""PDF parser using pymupdf (fitz)."""

from __future__ import annotations

from pathlib import Path

from quantumrag.core.errors import ParseError
from quantumrag.core.logging import get_logger
from quantumrag.core.models import Document, DocumentMetadata, SourceType

logger = get_logger(__name__)


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
            pages_text: list[str] = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                if text.strip():
                    pages_text.append(text.strip())

            content = "\n\n".join(pages_text)

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
