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
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk, Document

logger = get_logger(__name__)

_DEFAULT_TEMPLATE = "This chunk is from document '{title}'"
_SECTION_TEMPLATE = "This chunk is from document '{title}', section '{section}'"

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

    def __init__(self, template: str | None = None) -> None:
        self._template = template

    def add_context(self, chunks: list[Chunk], document: Document) -> list[Chunk]:
        """Add contextual prefixes to chunks.

        Args:
            chunks: List of chunks to annotate.
            document: Source document for metadata.

        Returns:
            The same list of chunks, with context_prefix set.
        """
        title = document.metadata.title or "Untitled"

        for chunk in chunks:
            section = chunk.metadata.get("section", "")
            prefix = self._generate_prefix(title, section)
            chunk.context_prefix = prefix

        logger.debug(
            "context_prefixes_added",
            doc_id=document.id,
            chunk_count=len(chunks),
        )

        return chunks

    def _generate_prefix(self, title: str, section: str) -> str:
        """Generate a context prefix string."""
        if self._template:
            return self._template.format(title=title, section=section)

        if section:
            return _SECTION_TEMPLATE.format(title=title, section=section)
        return _DEFAULT_TEMPLATE.format(title=title)


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
                    chunk.context_prefix = (
                        f"{preamble} {existing}" if existing else preamble
                    )
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
