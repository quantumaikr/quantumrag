"""Structural chunking based on section headings.

Innovation: **Contextual Chunk Enrichment** — every chunk is automatically
prefixed with its full heading hierarchy so the LLM and BM25 index always
know *where* the chunk came from.  This eliminates the class of failures
where version numbers / section titles get separated from their content
during sub-splitting.
"""

from __future__ import annotations

import re

from quantumrag.core.ingest.chunker.fixed import FixedSizeChunker
from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk, Document

logger = get_logger(__name__)

# Markdown heading pattern: # Heading, ## Heading, etc.
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# HTML heading pattern: <h1>...</h1> through <h6>...</h6>
_HTML_HEADING = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)


class StructuralChunker:
    """Chunker that splits documents by section headings.

    Detects Markdown (#) and HTML (<h1>-<h6>) headings to identify
    section boundaries. If a section exceeds max_chunk_size, it is
    sub-split using fixed-size chunking.

    **Contextual Chunk Enrichment**: Each chunk is prefixed with a
    breadcrumb of its heading ancestry, e.g.:
        ``[문서제목 > v2.5.0 (2024-10-15) > 새로운 기능]``
    This ensures that version numbers, section names, and document
    titles are always present in every chunk — even after sub-splitting.

    Args:
        max_chunk_size: Maximum chunk size in words before sub-splitting.
        sub_chunk_size: Size for sub-splitting large sections.
        sub_chunk_overlap: Overlap for sub-split chunks.
    """

    def __init__(
        self,
        max_chunk_size: int = 1000,
        sub_chunk_size: int = 512,
        sub_chunk_overlap: int = 50,
    ) -> None:
        self._max_chunk_size = max_chunk_size
        self._sub_chunker = FixedSizeChunker(
            chunk_size=sub_chunk_size,
            overlap=sub_chunk_overlap,
        )

    def chunk(self, document: Document) -> list[Chunk]:
        """Split document into chunks based on section headings.

        Args:
            document: Document to split.

        Returns:
            List of Chunk instances.
        """
        text = document.content.strip()
        if not text:
            return []

        # Extract document title for breadcrumb context
        doc_title = document.metadata.title or ""

        # Build hierarchical sections with heading ancestry
        hier_sections = _split_hierarchical(text)
        if not hier_sections:
            hier_sections = [HierSection(headings=[], content=text)]

        chunks: list[Chunk] = []
        chunk_index = 0

        for hsec in hier_sections:
            section_content = hsec.content.strip()
            if not section_content:
                continue

            # Build breadcrumb prefix: [doc_title > heading1 > heading2]
            breadcrumb = _build_breadcrumb(doc_title, hsec.headings)

            word_count = len(section_content.split())

            if word_count > self._max_chunk_size:
                # Sub-split large sections — each sub-chunk inherits the breadcrumb
                sub_doc = Document(content=section_content, id=document.id)
                sub_chunks = self._sub_chunker.chunk(sub_doc)
                for sub_chunk in sub_chunks:
                    sub_chunk.chunk_index = chunk_index
                    sub_chunk.document_id = document.id
                    if breadcrumb:
                        sub_chunk.content = f"{breadcrumb}\n{sub_chunk.content}"
                    heading_label = hsec.headings[-1] if hsec.headings else ""
                    if heading_label:
                        sub_chunk.metadata["section"] = heading_label
                    sub_chunk.metadata["breadcrumb"] = breadcrumb
                    chunks.append(sub_chunk)
                    chunk_index += 1
            else:
                content = f"{breadcrumb}\n{section_content}" if breadcrumb else section_content
                heading_label = hsec.headings[-1] if hsec.headings else ""
                chunk = Chunk(
                    content=content,
                    document_id=document.id,
                    chunk_index=chunk_index,
                    metadata={
                        "section": heading_label,
                        "breadcrumb": breadcrumb,
                    } if heading_label else {"breadcrumb": breadcrumb} if breadcrumb else {},
                )
                chunks.append(chunk)
                chunk_index += 1

        logger.debug(
            "structural_chunking_done",
            doc_id=document.id,
            chunk_count=len(chunks),
            section_count=len(hier_sections),
        )

        return chunks


class HierSection:
    """A section with its full heading ancestry."""
    __slots__ = ("content", "headings")

    def __init__(self, headings: list[str], content: str) -> None:
        self.headings = headings  # e.g. ["v2.5.0 (2024-10-15)", "새로운 기능"]
        self.content = content


def _build_breadcrumb(doc_title: str, headings: list[str]) -> str:
    """Build a breadcrumb string like ``[문서제목 > 섹션 > 하위섹션]``."""
    parts = []
    if doc_title:
        parts.append(doc_title.strip())
    parts.extend(h.strip() for h in headings if h.strip())
    if not parts:
        return ""
    return "[" + " > ".join(parts) + "]"


def _split_hierarchical(text: str) -> list[HierSection]:
    """Split text into sections preserving full heading hierarchy.

    For Markdown headings, tracks the current heading stack so that
    a ``## Sub`` under ``# Parent`` produces headings=["Parent", "Sub"].
    """
    matches = list(_MD_HEADING.finditer(text))
    if not matches:
        # Try HTML headings (flat, no hierarchy for simplicity)
        html_matches = list(_HTML_HEADING.finditer(text))
        if not html_matches:
            return [HierSection(headings=[], content=text)]
        return _split_html_hierarchical(text, html_matches)

    sections: list[HierSection] = []

    # heading_stack tracks current ancestors: list of (level, heading_text)
    heading_stack: list[tuple[int, str]] = []

    # Content before first heading
    pre_content = text[: matches[0].start()].strip()
    if pre_content:
        sections.append(HierSection(headings=[], content=pre_content))

    for i, match in enumerate(matches):
        level = len(match.group(1))  # number of '#' characters
        heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        # Update heading stack: pop headings of same or lower level
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, heading))

        # Full ancestry = all headings in the stack
        full_headings = [h for _, h in heading_stack]

        sections.append(HierSection(headings=list(full_headings), content=content))

    return sections


def _split_html_hierarchical(
    text: str, matches: list[re.Match[str]]
) -> list[HierSection]:
    """Split HTML headings into hierarchical sections."""
    sections: list[HierSection] = []
    heading_stack: list[tuple[int, str]] = []

    pre_content = text[: matches[0].start()].strip()
    if pre_content:
        sections.append(HierSection(headings=[], content=pre_content))

    for i, match in enumerate(matches):
        level = int(match.group(1))
        heading = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, heading))

        full_headings = [h for _, h in heading_stack]
        sections.append(HierSection(headings=list(full_headings), content=content))

    return sections


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """Split text into (heading, content) pairs using heading detection.

    Tries Markdown headings first, then HTML headings.

    Returns:
        List of (heading_text, section_content) tuples.
    """
    # Try Markdown headings
    sections = _split_markdown_headings(text)
    if len(sections) > 1:
        return sections

    # Try HTML headings
    sections = _split_html_headings(text)
    if len(sections) > 1:
        return sections

    # No headings found, return entire text
    return [("", text)]


def _split_markdown_headings(text: str) -> list[tuple[str, str]]:
    """Split on Markdown heading lines."""
    matches = list(_MD_HEADING.finditer(text))
    if not matches:
        return [("", text)]

    sections: list[tuple[str, str]] = []

    # Content before first heading
    pre_content = text[: matches[0].start()].strip()
    if pre_content:
        sections.append(("", pre_content))

    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        sections.append((heading, content))

    return sections


def _split_html_headings(text: str) -> list[tuple[str, str]]:
    """Split on HTML heading tags."""
    matches = list(_HTML_HEADING.finditer(text))
    if not matches:
        return [("", text)]

    sections: list[tuple[str, str]] = []

    # Content before first heading
    pre_content = text[: matches[0].start()].strip()
    if pre_content:
        sections.append(("", pre_content))

    for i, match in enumerate(matches):
        heading = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        sections.append((heading, content))

    return sections
