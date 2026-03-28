"""Contextual prefix generation for chunks.

Supports two modes:
1. Template-based (free): structural metadata only (breadcrumb, section).
2. LLM-based (Anthropic-style Contextual Retrieval): an LLM generates a
   1-2 sentence preamble describing what the chunk covers and how it fits
   into the overall document.  This improves both embedding and BM25
   retrieval quality.  See: "Introducing Contextual Retrieval" (Anthropic, 2024).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk, Document
from quantumrag.core.utils.text import detect_korean

logger = get_logger(__name__)

_DEFAULT_TEMPLATE_EN = "This chunk is from document '{title}'"
_SECTION_TEMPLATE_EN = "This chunk is from document '{title}', section '{section}'"
_DEFAULT_TEMPLATE_KO = "'{title}' 문서의 내용"
_SECTION_TEMPLATE_KO = "'{title}' 문서, '{section}' 섹션의 내용"

# Pattern to extract salient keywords from chunk content (numbers with units,
# proper nouns in English/Korean, percentage values)
_KEYWORD_PATTERNS = [
    re.compile(r"\d+(?:\.\d+)?(?:\s*[만억천조]|\s*%|원|달러|명|건|개)"),  # numeric + unit
    re.compile(r"[A-Z][a-z]*(?:[A-Z][a-z]*)+"),  # CamelCase terms
    re.compile(r"\b[A-Z]{2,}[a-z]*\b"),  # Acronyms (API, PoC, RGCN)
]

# --- LLM Contextual Preamble prompts ---

_PREAMBLE_SYSTEM = (
    "You are a document analyst. Given a document overview and a chunk of text, "
    "write a brief 1-2 sentence context that situates this chunk within the "
    "overall document. Be specific and factual. Answer only with the context, "
    "nothing else. Use the same language as the chunk."
)

_PREAMBLE_USER = """<document_overview>
{overview}
</document_overview>

<section>
{breadcrumb}
</section>

<chunk>
{content}
</chunk>

Write a short succinct context to situate this chunk within the overall document for improving search retrieval:"""


class ContextualPrefixer:
    """Generates context prefixes for chunks.

    Adds a descriptive prefix to each chunk that provides context
    about the document and section the chunk belongs to. This improves
    retrieval quality for BM25 and embedding search.

    The prefix is stored in ``Chunk.context_prefix``.

    Args:
        template: Template string with ``{title}`` and ``{section}`` placeholders.
            Defaults to a sensible template.
    """

    def __init__(self, template: str | None = None, language: str = "auto") -> None:
        self._template = template
        self._language = language

    def add_context(self, chunks: list[Chunk], document: Document) -> list[Chunk]:
        """Add contextual prefixes to chunks.

        Includes auto-extracted keywords from chunk content for improved
        BM25 retrieval. Uses Korean templates for Korean documents.

        Args:
            chunks: List of chunks to annotate.
            document: Source document for metadata.

        Returns:
            The same list of chunks, with context_prefix set.
        """
        title = document.metadata.title or "Untitled"
        is_korean = self._language == "ko" or (
            self._language == "auto" and detect_korean(document.content[:500])
        )

        for chunk in chunks:
            section = chunk.metadata.get("section", "")
            breadcrumb = chunk.metadata.get("breadcrumb", "")
            prefix = self._generate_prefix(title, section, is_korean)
            # Filter keywords that already appear in title/section/breadcrumb
            exclude_context = f"{title} {section} {breadcrumb}".lower()
            keywords = _extract_keywords(chunk.content, exclude_context=exclude_context)
            if keywords:
                prefix = f"{prefix} | {', '.join(keywords)}"
            chunk.context_prefix = prefix

        logger.debug(
            "context_prefixes_added",
            doc_id=document.id,
            chunk_count=len(chunks),
            language="ko" if is_korean else "en",
        )

        return chunks

    def _generate_prefix(self, title: str, section: str, is_korean: bool = False) -> str:
        """Generate a context prefix string."""
        if self._template:
            return self._template.format(title=title, section=section)

        if is_korean:
            if section:
                return _SECTION_TEMPLATE_KO.format(title=title, section=section)
            return _DEFAULT_TEMPLATE_KO.format(title=title)

        if section:
            return _SECTION_TEMPLATE_EN.format(title=title, section=section)
        return _DEFAULT_TEMPLATE_EN.format(title=title)


def _extract_keywords(content: str, max_keywords: int = 5, exclude_context: str = "") -> list[str]:
    """Extract salient keywords from chunk content (no LLM, regex-only).

    Extracts numeric values with units (금액, 비율), acronyms, and
    CamelCase terms that are useful for BM25 retrieval.

    Filters out keywords that already appear in the exclude_context
    (typically title + section + breadcrumb) since they add no
    discriminative value to the prefix.
    """
    found: list[str] = []
    seen: set[str] = set()
    exclude_lower = exclude_context.lower()
    for pattern in _KEYWORD_PATTERNS:
        for m in pattern.finditer(content):
            kw = m.group().strip()
            if not kw or len(kw) < 2:
                continue
            kw_lower = kw.lower()
            # Skip if already in title/section/breadcrumb context
            if kw_lower in exclude_lower:
                continue
            if kw_lower in seen:
                continue
            seen.add(kw_lower)
            found.append(kw)
            if len(found) >= max_keywords:
                return found
    return found


async def generate_contextual_preambles(
    chunks: list[Chunk],
    document: Document,
    llm_provider: Any,
    max_concurrency: int = 5,
) -> list[Chunk]:
    """Generate LLM-based contextual preambles for chunks (Anthropic-style).

    For each chunk, the LLM produces a 1-2 sentence description of what the
    chunk covers within the document.  The preamble is prepended to the
    existing ``context_prefix`` (breadcrumb).

    Uses a document overview (first ~2000 chars) as shared context, which
    benefits from LLM prompt caching when available.

    Args:
        chunks: Chunks to annotate.
        document: Source document (used for overview).
        llm_provider: LLM provider with ``generate()`` method.
        max_concurrency: Max parallel LLM calls.

    Returns:
        The same list of chunks with enriched ``context_prefix``.
    """
    if not chunks or not llm_provider:
        return chunks

    # Build document overview (first ~2000 chars for prompt caching efficiency)
    title = document.metadata.title or "Untitled"
    overview = document.content[:2000].strip()
    if len(document.content) > 2000:
        overview += "\n..."

    semaphore = asyncio.Semaphore(max_concurrency)
    failed = 0

    async def _generate_one(chunk: Chunk) -> None:
        nonlocal failed
        breadcrumb = chunk.metadata.get("breadcrumb", "")
        prompt = _PREAMBLE_USER.format(
            overview=overview,
            breadcrumb=breadcrumb or title,
            content=chunk.content[:1500],
        )

        async with semaphore:
            try:
                response = await llm_provider.generate(
                    prompt,
                    system=_PREAMBLE_SYSTEM,
                    max_tokens=100,
                    temperature=0.0,
                )
                preamble = response.text.strip()
                if preamble:
                    # Combine: LLM preamble + existing structural prefix
                    existing = chunk.context_prefix
                    chunk.context_prefix = f"{preamble} {existing}" if existing else preamble
            except Exception as e:
                failed += 1
                logger.debug(
                    "preamble_generation_failed",
                    chunk_id=chunk.id,
                    error=str(e),
                )

    await asyncio.gather(*[_generate_one(c) for c in chunks])

    succeeded = len(chunks) - failed
    logger.info(
        "contextual_preambles_generated",
        doc_id=document.id,
        total=len(chunks),
        succeeded=succeeded,
        failed=failed,
    )

    return chunks
