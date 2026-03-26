"""HWP/HWPX parser for Korean document formats."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from quantumrag.core.errors import ParseError
from quantumrag.core.logging import get_logger
from quantumrag.core.models import Document, DocumentMetadata, SourceType

logger = get_logger(__name__)


class HWPParser:
    """Parser for HWP and HWPX (Korean Hangul Word Processor) files.

    - HWPX: ZIP archive of XML files (direct XML parsing).
    - HWP: OLE2 compound document (uses olefile, optional dependency).
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [".hwp", ".hwpx"]

    def parse(self, file_path: Path) -> Document:
        """Parse an HWP or HWPX file."""
        if not file_path.exists():
            raise ParseError(f"File not found: {file_path}", file_path=str(file_path))

        ext = file_path.suffix.lower()
        if ext == ".hwpx":
            return self._parse_hwpx(file_path)
        elif ext == ".hwp":
            return self._parse_hwp(file_path)
        else:
            raise ParseError(
                f"Unsupported HWP extension: {ext}",
                file_path=str(file_path),
            )

    def _parse_hwpx(self, file_path: Path) -> Document:
        """Parse HWPX file (ZIP of XML)."""
        try:
            with zipfile.ZipFile(str(file_path), "r") as zf:
                text_parts: list[str] = []

                # HWPX structure: Contents/section*.xml contains body text
                xml_files = sorted(
                    name
                    for name in zf.namelist()
                    if name.startswith("Contents/") and name.endswith(".xml")
                )

                if not xml_files:
                    # Try alternative structure
                    xml_files = sorted(name for name in zf.namelist() if name.endswith(".xml"))

                for xml_file in xml_files:
                    try:
                        xml_data = zf.read(xml_file)
                        text = self._extract_text_from_xml(xml_data)
                        if text.strip():
                            text_parts.append(text.strip())
                    except Exception as e:
                        logger.warning(
                            "hwpx_xml_error",
                            file=xml_file,
                            error=str(e),
                        )

                content = "\n\n".join(text_parts)

                if not content.strip():
                    raise ParseError(
                        "No text content extracted from HWPX file",
                        file_path=str(file_path),
                    )

                return Document(
                    content=content,
                    metadata=DocumentMetadata(
                        source_type=SourceType.FILE,
                        title=file_path.stem,
                        custom={"format": "hwpx"},
                    ),
                    raw_bytes=file_path.read_bytes(),
                )

        except zipfile.BadZipFile:
            raise ParseError(
                "Invalid HWPX file (not a valid ZIP archive)",
                file_path=str(file_path),
            ) from None
        except ParseError:
            raise
        except Exception as e:
            raise ParseError(
                f"Failed to parse HWPX file: {e}",
                file_path=str(file_path),
            ) from e

    def _extract_text_from_xml(self, xml_data: bytes) -> str:
        """Extract text content from HWPX XML data."""
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError:
            return ""

        # Extract all text nodes recursively
        texts: list[str] = []
        for elem in root.iter():
            if elem.text and elem.text.strip():
                texts.append(elem.text.strip())
            if elem.tail and elem.tail.strip():
                texts.append(elem.tail.strip())

        return "\n".join(texts)

    def _parse_hwp(self, file_path: Path) -> Document:
        """Parse HWP (OLE2) file using olefile."""
        try:
            import olefile
        except ImportError:
            raise ParseError(
                "olefile is required to parse HWP files",
                file_path=str(file_path),
                suggestion="Install it with: pip install olefile",
            ) from None

        try:
            ole = olefile.OleFileIO(str(file_path))
        except Exception as e:
            raise ParseError(
                f"Failed to open HWP file: {e}",
                file_path=str(file_path),
                suggestion="The file may be corrupted or password-protected.",
            ) from e

        try:
            content = self._extract_hwp_text(ole, file_path)

            return Document(
                content=content,
                metadata=DocumentMetadata(
                    source_type=SourceType.FILE,
                    title=file_path.stem,
                    custom={"format": "hwp"},
                ),
                raw_bytes=file_path.read_bytes(),
            )
        finally:
            ole.close()

    def _extract_hwp_text(self, ole: object, file_path: Path) -> str:
        """Extract text from HWP OLE streams.

        HWP stores text in BodyText/Section* streams, often in UTF-16LE or EUC-KR.
        """
        texts: list[str] = []

        # Try to read body text sections
        try:
            # ole is an OleFileIO instance
            streams = ole.listdir()  # type: ignore[union-attr]
            section_streams = sorted(s for s in streams if len(s) >= 2 and s[0] == "BodyText")

            for stream_path in section_streams:
                try:
                    data = ole.openstream(stream_path).read()  # type: ignore[union-attr]
                    text = self._decode_hwp_stream(data)
                    if text.strip():
                        texts.append(text.strip())
                except Exception as e:
                    logger.warning(
                        "hwp_stream_error",
                        stream="/".join(stream_path),
                        error=str(e),
                    )
        except Exception as e:
            logger.warning("hwp_extraction_error", error=str(e))

        content = "\n\n".join(texts)

        if not content.strip():
            raise ParseError(
                "No text content extracted from HWP file",
                file_path=str(file_path),
                suggestion="The file may use an unsupported HWP format version.",
            )

        return content

    def _decode_hwp_stream(self, data: bytes) -> str:
        """Decode HWP binary stream data to text.

        HWP body text is stored with control characters mixed in.
        We extract printable text, trying UTF-16LE first then EUC-KR.
        """
        # Try UTF-16LE (common in newer HWP files)
        try:
            text = data.decode("utf-16le", errors="ignore")
            # Filter to printable characters
            clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
            if clean.strip():
                return clean
        except Exception:
            pass

        # Try EUC-KR
        try:
            text = data.decode("euc-kr", errors="ignore")
            clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
            if clean.strip():
                return clean
        except Exception:
            pass

        # Last resort: extract ASCII/printable bytes
        text = data.decode("latin-1", errors="ignore")
        clean = re.sub(r"[^\x20-\x7e\n\r\t\uac00-\ud7a3]", "", text)
        return clean
