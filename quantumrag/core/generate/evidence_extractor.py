"""Evidence-First Generation — Structure-agnostic fact extraction from chunks.

This module solves the **Retrieval-Generation Gap**: the fundamental problem
where an LLM has the right chunks but generates incorrect answers because
document structure creates implicit bias.

Example of the problem:
    A document has "확정 PoC (2건)" listing items A and B, then "진행 중 (1건)"
    listing item C. When asked "총 PoC 3건의 합계", the LLM often ignores C
    because it's under a different section header — even though the query
    explicitly says "3건".

Solution: **Evidence Extraction**
    Before generating the final answer, we extract individual facts from each
    chunk into a uniform, flat structure. This removes the document hierarchy
    that causes LLM bias.

    Raw chunks → Evidence Table → Answer Generation

    The evidence table presents all facts uniformly — no section headers,
    no status grouping, no hierarchical nesting. Each fact stands on its own.

This is a zero-cost approach when possible (rule-based extraction), with an
optional LLM-based fallback for complex chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.retrieve.fusion import ScoredChunk

logger = get_logger("quantumrag.evidence_extractor")


@dataclass
class Evidence:
    """A single extracted fact from a chunk."""

    fact: str  # The extracted fact text
    source_idx: int  # Which source [1], [2], etc.
    entity: str = ""  # Primary entity (company, product, person)
    value: str = ""  # Numeric value if present
    status: str = ""  # Status label (확정, 진행 중, etc.) — preserved but flattened


@dataclass
class EvidenceTable:
    """Flat collection of extracted evidence, free from document structure bias."""

    evidences: list[Evidence] = field(default_factory=list)
    query: str = ""

    def to_context_string(self) -> str:
        """Format evidence as a uniform, flat context for LLM generation.

        Key design: NO hierarchical grouping, NO section headers.
        Each fact is presented as an equal peer, eliminating structural bias.
        """
        if not self.evidences:
            return ""

        parts: list[str] = []
        for ev in self.evidences:
            line = f"[{ev.source_idx}] {ev.fact}"
            parts.append(line)

        return "\n".join(parts)


# ─────────────────────────────────────────────────────────
# Rule-based evidence extraction (zero LLM cost)
# ─────────────────────────────────────────────────────────

# Patterns to detect structured list items in Korean business documents
_LIST_ITEM_PATTERN = re.compile(
    r"(?:^|\n)\s*"
    r"(?:\d+\.\s*|\-\s*|\*\s*|•\s*)"  # List markers: 1. / - / * / •
    r"(?:\*{0,2})"  # Optional bold markers
    r"(.+?)(?:\n|$)",
)

# Detect monetary amounts
_AMOUNT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:억|천만|백만)?\s*(?:원|달러|USD|엔)?"
)

# Detect status labels that create bias
_STATUS_LABELS = re.compile(
    r"(?:확정|진행\s*중|계획|예정|검토|미정|완료|보류|중단)"
)

# Section headers that create hierarchical bias
_SECTION_HEADER_PATTERN = re.compile(
    r"^#{1,4}\s+(.+?)$", re.MULTILINE
)


def extract_evidence_from_chunks(
    chunks: list[ScoredChunk],
    query: str,
) -> EvidenceTable:
    """Extract structured evidence from chunks using rule-based parsing.

    This is the core of Evidence-First Generation:
    1. Parse each chunk for individual facts
    2. Strip section headers and status groupings
    3. Present each fact as a peer in a flat table

    Returns an EvidenceTable that can be formatted for LLM consumption.
    """
    table = EvidenceTable(query=query)

    for source_idx, sc in enumerate(chunks, 1):
        content = sc.chunk.content
        facts = _extract_facts_from_content(content, source_idx)

        if facts:
            table.evidences.extend(facts)
        else:
            # Fallback: use the whole chunk as a single evidence
            table.evidences.append(Evidence(
                fact=_clean_content(content),
                source_idx=source_idx,
            ))

    return table


def _extract_facts_from_content(content: str, source_idx: int) -> list[Evidence]:
    """Extract individual facts from a chunk's content.

    Key insight: We split content at list item boundaries so that each
    item becomes an independent fact. Section headers are captured as
    metadata (status) but NOT used for grouping.
    """
    facts: list[Evidence] = []

    # Track the current section header (for status metadata only)
    current_section = ""
    lines = content.split("\n")

    # Detect if this chunk has structured list items
    has_list_items = bool(_LIST_ITEM_PATTERN.search(content))

    if not has_list_items:
        # No list structure — return empty to use fallback
        return []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect section headers
        header_match = re.match(r"^#{1,4}\s+(.+)$", stripped)
        if header_match:
            current_section = header_match.group(1).strip()
            continue

        # Detect list items
        item_match = re.match(
            r"(?:\d+\.\s*|\-\s*|\*\s*|•\s*)(?:\*{0,2})(.+?)(?:\*{0,2})$",
            stripped,
        )
        if item_match:
            fact_text = item_match.group(1).strip()
            # Clean bold markers
            fact_text = re.sub(r"\*{1,2}", "", fact_text).strip()

            # Extract entity (first bold or first noun phrase)
            entity = ""
            entity_match = re.match(r"(.+?)\s*[—\-:：]", fact_text)
            if entity_match:
                entity = entity_match.group(1).strip()

            # Extract monetary value
            value = ""
            value_match = _AMOUNT_PATTERN.search(fact_text)
            if value_match:
                value = value_match.group(0)

            # Extract status from section header
            status = ""
            status_match = _STATUS_LABELS.search(current_section)
            if status_match:
                status = status_match.group(0)

            # Build the fact with status INLINE (not as a section header)
            # This is the key normalization: "진행 중" becomes just a label
            # on the same line, not a section that devalues everything below it
            if status and status not in fact_text:
                fact_with_status = f"{fact_text} (상태: {status})"
            else:
                fact_with_status = fact_text

            facts.append(Evidence(
                fact=fact_with_status,
                source_idx=source_idx,
                entity=entity,
                value=value,
                status=status,
            ))
        elif stripped and not stripped.startswith("#"):
            # Non-list line that might contain important context
            # Include it if it has substantive content
            if len(stripped) > 20:
                facts.append(Evidence(
                    fact=stripped,
                    source_idx=source_idx,
                ))

    return facts


def _clean_content(content: str) -> str:
    """Clean chunk content by normalizing section headers.

    Instead of removing headers entirely, we flatten them into inline labels.
    "### 진행 중 (1건)\n3. NTT..." becomes "NTT... (상태: 진행 중)"
    """
    # Replace section headers with inline status markers
    result = content
    sections = list(_SECTION_HEADER_PATTERN.finditer(content))

    if not sections:
        return content.strip()

    # Process from end to start to preserve positions
    for match in reversed(sections):
        header_text = match.group(1).strip()
        status_match = _STATUS_LABELS.search(header_text)
        if status_match:
            # Replace the section header with nothing — its status will be
            # added inline to the items below it
            result = result[:match.start()] + result[match.end():]

    return result.strip()


# ─────────────────────────────────────────────────────────
# LLM-based evidence extraction (for complex chunks)
# ─────────────────────────────────────────────────────────

_EXTRACTION_PROMPT = """다음 텍스트에서 질문에 관련된 모든 개별 사실을 추출하세요.

중요 규칙:
1. 모든 항목을 빠짐없이 추출하세요 — "확정", "진행 중", "계획" 등 상태와 관계없이
2. 각 사실을 독립적인 한 줄로 작성하세요
3. 수치(금액, 인원, 비율)가 있으면 반드시 포함하세요
4. 상태 정보는 괄호 안에 표시하세요: (확정), (진행 중), (완료) 등
5. 줄 번호를 붙이세요: 1. 2. 3. ...

질문: {query}
텍스트: {content}

추출된 사실:"""


async def extract_evidence_with_llm(
    chunks: list[ScoredChunk],
    query: str,
    llm_provider: Any,
) -> EvidenceTable:
    """Extract evidence using LLM for higher accuracy.

    More expensive but catches nuanced facts that rule-based extraction misses.
    Use for complex queries or when rule-based extraction finds too few facts.
    """
    import asyncio

    table = EvidenceTable(query=query)

    async def _extract_one(sc: ScoredChunk, idx: int) -> list[Evidence]:
        try:
            response = await llm_provider.generate(
                _EXTRACTION_PROMPT.format(query=query, content=sc.chunk.content),
                temperature=0.0,
                max_tokens=200,
            )
            return _parse_llm_evidence(response.text, idx)
        except Exception:
            logger.warning("llm_evidence_extraction_failed", source_idx=idx)
            return [Evidence(fact=sc.chunk.content[:500], source_idx=idx)]

    tasks = [_extract_one(sc, i + 1) for i, sc in enumerate(chunks)]
    results = await asyncio.gather(*tasks)

    for evidences in results:
        table.evidences.extend(evidences)

    return table


def _parse_llm_evidence(text: str, source_idx: int) -> list[Evidence]:
    """Parse LLM output into Evidence objects."""
    evidences: list[Evidence] = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Remove line numbers: "1. fact" → "fact"
        fact = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
        if fact:
            evidences.append(Evidence(
                fact=fact,
                source_idx=source_idx,
            ))
    return evidences


# ─────────────────────────────────────────────────────────
# Query-aware evidence selection
# ─────────────────────────────────────────────────────────

def should_use_evidence_extraction(query: str, chunks: list[ScoredChunk]) -> bool:
    """Determine if evidence extraction would benefit this query.

    Evidence extraction is most valuable when:
    1. Query asks about multiple items (aggregation/enumeration)
    2. Chunks contain structured lists with status groupings
    3. Query mentions specific counts ("3건", "모든", "전체")
    """
    # Aggregation/enumeration signals
    count_pattern = re.compile(r"\d+\s*건|\d+\s*개|총|합계|모든|전체|모두")
    if count_pattern.search(query):
        return True

    # Superlative queries ("가장 큰", "제일")
    superlative_pattern = re.compile(r"가장|제일|최대|최소|최고|최저")
    if superlative_pattern.search(query):
        return True

    # Check if any chunk has structured lists with status headers
    for sc in chunks[:5]:  # Check top-5 only for performance
        content = sc.chunk.content
        has_status = bool(_STATUS_LABELS.search(content))
        has_list = bool(_LIST_ITEM_PATTERN.search(content))
        if has_status and has_list:
            return True

    return False
