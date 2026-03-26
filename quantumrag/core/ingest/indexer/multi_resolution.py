"""Multi-Resolution Index — index content at document, section, and chunk levels.

Creates synthetic summary chunks at coarser granularities so that broad queries
("보안 감사 결과 요약", "High 이상 이슈 모두 나열") can match at the right level
and then expand to detailed chunks.

Resolution levels:
    - document: Full document summary (1 per doc)
    - section:  Section-level summary (1 per H2/breadcrumb group)
    - chunk:    Original chunks (unchanged)
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk, Document

logger = get_logger("quantumrag.multi_resolution")

# Max content length for summary generation
_MAX_SECTION_CONTENT = 3000
_MAX_DOC_CONTENT = 5000


def build_multi_resolution_chunks(
    chunks: list[Chunk],
    document: Document,
) -> list[Chunk]:
    """Build document-level and section-level summary chunks.

    Uses rule-based summarization (no LLM) — extracts key lines and
    entities to create searchable summaries.

    Args:
        chunks: Original chunks from the document.
        document: Source document.

    Returns:
        List of new summary chunks (document + section level).
        Original chunks are NOT included — caller should extend.
    """
    if not chunks:
        return []

    summary_chunks: list[Chunk] = []

    # Mark original chunks with resolution level
    for c in chunks:
        c.metadata["resolution"] = "chunk"

    # Build section summaries
    section_summaries = _build_section_summaries(chunks, document)
    summary_chunks.extend(section_summaries)

    # Build document summary
    doc_summary = _build_document_summary(chunks, section_summaries, document)
    if doc_summary:
        summary_chunks.append(doc_summary)

    if summary_chunks:
        logger.info(
            "multi_resolution_built",
            doc_id=document.id,
            sections=len(section_summaries),
            total_summary_chunks=len(summary_chunks),
        )

    return summary_chunks


def _build_section_summaries(
    chunks: list[Chunk],
    document: Document,
) -> list[Chunk]:
    """Group chunks by section and create a summary chunk per section."""
    # Group by top-level breadcrumb section
    sections: dict[str, list[Chunk]] = defaultdict(list)

    for c in chunks:
        breadcrumb = c.metadata.get("breadcrumb", "")
        section = c.metadata.get("section", "")
        # Use first breadcrumb component as section key
        if breadcrumb:
            parts = breadcrumb.strip("[]").split(" > ")
            key = parts[1] if len(parts) > 1 else parts[0]
        elif section:
            key = section
        else:
            key = "기타"
        sections[key].append(c)

    summaries: list[Chunk] = []
    for section_name, section_chunks in sections.items():
        if len(section_chunks) < 3:
            # Small sections don't need a summary (reduces index noise)
            continue

        # Build section summary: combine key facts from each chunk
        content_parts: list[str] = []
        all_facts: list[dict[str, Any]] = []

        for sc in section_chunks:
            # Extract first meaningful line from each chunk
            lines = [l.strip() for l in sc.content.split("\n") if l.strip()]
            if lines:
                # Take heading + first content line
                preview = " ".join(lines[:2])
                if len(preview) > 200:
                    preview = preview[:200] + "..."
                content_parts.append(preview)

            # Collect facts
            chunk_facts = sc.metadata.get("facts", [])
            all_facts.extend(chunk_facts)

        # Build summary content
        summary_content = f"[섹션 요약: {section_name}]\n"
        summary_content += "\n".join(f"- {part}" for part in content_parts)

        # Add fact summary if available
        if all_facts:
            summary_content += "\n\n[핵심 사실]\n"
            for fact in all_facts[:10]:  # Limit to 10 facts per section
                entity = fact.get("entity", "")
                ftype = fact.get("type", "")
                severity = fact.get("severity", "")
                status = fact.get("status", "")
                parts = [p for p in [entity, ftype, severity, status] if p]
                if parts:
                    summary_content += f"- {', '.join(parts)}\n"

        if len(summary_content) > _MAX_SECTION_CONTENT:
            summary_content = summary_content[:_MAX_SECTION_CONTENT] + "..."

        summary_chunk = Chunk(
            id=uuid.uuid4().hex,
            content=summary_content,
            document_id=document.id,
            chunk_index=-1,  # Negative index for synthetic chunks
            metadata={
                "resolution": "section",
                "section": section_name,
                "breadcrumb": f"[{document.metadata.title} > {section_name}]",
                "child_chunk_ids": [sc.id for sc in section_chunks],
                "facts": all_facts[:10],
            },
            context_prefix=f"섹션 요약 — {document.metadata.title or 'Document'}, {section_name}",
        )
        summaries.append(summary_chunk)

    return summaries


def _build_document_summary(
    chunks: list[Chunk],
    section_summaries: list[Chunk],
    document: Document,
) -> Chunk | None:
    """Create a single document-level summary chunk."""
    title = document.metadata.title or "Untitled"

    # Collect all facts across the document
    all_facts: list[dict[str, Any]] = []
    for c in chunks:
        all_facts.extend(c.metadata.get("facts", []))

    # Build document overview
    parts: list[str] = [f"[문서 요약: {title}]"]

    # Add section listing
    if section_summaries:
        parts.append("\n[구성 섹션]")
        for ss in section_summaries:
            section_name = ss.metadata.get("section", "?")
            child_count = len(ss.metadata.get("child_chunk_ids", []))
            parts.append(f"- {section_name} ({child_count}개 항목)")

    # Add key entity summary
    entities_by_type: dict[str, list[str]] = defaultdict(list)
    for fact in all_facts:
        entity = fact.get("entity", "")
        ftype = fact.get("type", "")
        if entity and ftype:
            entities_by_type[ftype].append(entity)

    if entities_by_type:
        parts.append("\n[주요 항목]")
        for ftype, entities in entities_by_type.items():
            unique = list(dict.fromkeys(entities))  # Deduplicate, preserve order
            parts.append(f"- {ftype}: {', '.join(unique[:15])}")

    # Add severity/status distribution for security docs
    severity_counts: dict[str, int] = defaultdict(int)
    status_counts: dict[str, int] = defaultdict(int)
    for fact in all_facts:
        if fact.get("type") == "security_issue":
            sev = fact.get("severity", "")
            stat = fact.get("status", "")
            if sev:
                severity_counts[sev] += 1
            if stat:
                status_counts[stat] += 1

    if severity_counts:
        dist = ", ".join(f"{k}: {v}건" for k, v in severity_counts.items())
        parts.append(f"\n[등급 분포] {dist}")
    if status_counts:
        dist = ", ".join(f"{k}: {v}건" for k, v in status_counts.items())
        parts.append(f"[조치 현황] {dist}")

    content = "\n".join(parts)
    if len(content) > _MAX_DOC_CONTENT:
        content = content[:_MAX_DOC_CONTENT] + "..."

    return Chunk(
        id=uuid.uuid4().hex,
        content=content,
        document_id=document.id,
        chunk_index=-2,  # -2 for document-level
        metadata={
            "resolution": "document",
            "section": "문서 요약",
            "breadcrumb": f"[{title}]",
            "child_chunk_ids": [c.id for c in chunks],
            "facts": all_facts[:20],
        },
        context_prefix=f"문서 요약 — {title}",
    )
