"""Answer Completeness Verification (ACV) — detect incomplete multi-part answers.

After generating an answer, this module detects if the query implies multiple
items or parts and checks whether the answer covers all of them. If not, it
identifies what is missing so that targeted re-retrieval can fill the gaps.

Design principles:
- **Zero LLM calls**: all detection and verification is regex/heuristic-based.
  Only the downstream re-retrieval and re-generation (handled by the engine)
  use LLM calls.
- **Minimal overhead**: for simple queries that do not imply multiple parts,
  ``detect_expected_parts`` returns ``None`` immediately.
- **Korean-first**: patterns target Korean enumeration markers, counters, and
  conjunctions, with English fallbacks.

Typical flow (orchestrated by ``engine.py``):
1. ``detect_expected_parts(query)`` -> ``ExpectedParts | None``
2. ``verify_completeness(query, answer, parts)`` -> ``CompletenessResult``
3. If incomplete, engine uses ``CompletenessResult.missing_query`` for
   targeted re-retrieval + merged re-generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.completeness")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ExpectedParts:
    """Describes the multi-part expectation extracted from a query."""

    expected_count: int | None  # None means "all / unknown count"
    expected_items: list[str] = field(default_factory=list)  # specific items
    query_type: str = "collection"  # "count", "enumeration", "comparison", "collection"


@dataclass
class CompletenessResult:
    """Outcome of verifying whether the answer covers all expected parts."""

    is_complete: bool
    found_items: list[str] = field(default_factory=list)
    missing_items: list[str] = field(default_factory=list)
    missing_query: str | None = None  # Reformulated query targeting missing items


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# Explicit count: "3건의", "4개", "5가지", "2곳", "6명" etc.
_EXPLICIT_COUNT_RE = re.compile(r"(\d+)\s*(?:건|개|가지|곳|명|종류|항목|단계|분야|사례|유형|종|차)")

# "모두", "전부", "모든", "각각" -> multi-part with unknown count
_ALL_MULTI_RE = re.compile(r"(?:모두|전부|모든|각각|전체)\s")

# "각각 알려주세요", "각각 설명" -> multi-part
_EACH_RE = re.compile(r"각각\s*(?:알려|설명|비교|정리|나열|요약)")

# Conjunction lists: "A와 B", "A, B, C", "A 및 B", "A와 B와 C"
# We capture comma/와/및/과 separated noun phrases.
_CONJUNCTION_RE = re.compile(
    r"(?:^|[\s,])([가-힣A-Za-z0-9_\-]+)" r"(?:\s*(?:와|과|및|,)\s*" r"([가-힣A-Za-z0-9_\-]+))+"
)

# Comparison: "A vs B", "A와 B 비교", "A와 B 차이", "A와 B 중"
_COMPARISON_RE = re.compile(r"([가-힣A-Za-z0-9_\-]+)\s*(?:vs\.?|VS\.?)\s*([가-힣A-Za-z0-9_\-]+)")

# "A와 B 중", "A와 B 비교", "A와 B 차이"
_COMPARISON_KO_RE = re.compile(
    r"([가-힣A-Za-z0-9_\-]+)\s*(?:와|과)\s*([가-힣A-Za-z0-9_\-]+)\s*(?:중|비교|차이)"
)

# Korean conjunction splitter for extracting items from "A, B, C" or "A와 B와 C"
_SPLIT_CONJ_RE = re.compile(r"\s*(?:,\s*|와\s*|과\s*|및\s*)")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_expected_parts(query: str) -> ExpectedParts | None:
    """Detect if a query implies a multi-part or enumeration answer.

    Returns ``ExpectedParts`` describing what the answer should contain,
    or ``None`` if the query is a simple single-answer question.

    This function is **regex-only** — no LLM calls.
    """
    if not query or len(query) < 3:
        return None

    # 1. Explicit count: "3건의 계약", "5가지 방법"
    m = _EXPLICIT_COUNT_RE.search(query)
    if m:
        count = int(m.group(1))
        if count >= 2:
            logger.debug("detected_explicit_count", count=count, query=query)
            return ExpectedParts(
                expected_count=count,
                expected_items=[],
                query_type="count",
            )

    # 2. Comparison: "A vs B" or "A와 B 비교/차이/중"
    m = _COMPARISON_RE.search(query)
    if m:
        items = [m.group(1).strip(), m.group(2).strip()]
        logger.debug("detected_comparison", items=items, query=query)
        return ExpectedParts(
            expected_count=len(items),
            expected_items=items,
            query_type="comparison",
        )
    m = _COMPARISON_KO_RE.search(query)
    if m:
        items = [m.group(1).strip(), m.group(2).strip()]
        logger.debug("detected_comparison_ko", items=items, query=query)
        return ExpectedParts(
            expected_count=len(items),
            expected_items=items,
            query_type="comparison",
        )

    # 3. Conjunction lists: "A와 B", "A, B, C", "A 및 B"
    #    We use a more careful extraction here.
    items = _extract_conjunction_items(query)
    if items and len(items) >= 2:
        logger.debug("detected_enumeration", items=items, query=query)
        return ExpectedParts(
            expected_count=len(items),
            expected_items=items,
            query_type="enumeration",
        )

    # 4. "각각 알려주세요" or similar
    if _EACH_RE.search(query):
        logger.debug("detected_each_pattern", query=query)
        return ExpectedParts(
            expected_count=None,
            expected_items=[],
            query_type="collection",
        )

    # 5. "모두", "전부", "전체" -> unknown count multi-part
    if _ALL_MULTI_RE.search(query):
        logger.debug("detected_all_multi", query=query)
        return ExpectedParts(
            expected_count=None,
            expected_items=[],
            query_type="collection",
        )

    return None


def verify_completeness(
    query: str,
    answer: str,
    parts: ExpectedParts,
) -> CompletenessResult:
    """Check if the answer covers all expected parts from the query.

    Uses heuristic matching — no LLM calls.  Returns a
    ``CompletenessResult`` describing what was found and what is missing.
    """
    if not answer:
        return CompletenessResult(
            is_complete=False,
            found_items=[],
            missing_items=parts.expected_items[:],
            missing_query=query,
        )

    # --- Item-based verification ---
    if parts.expected_items:
        return _verify_items(query, answer, parts)

    # --- Count-based verification ---
    if parts.expected_count is not None:
        return _verify_count(query, answer, parts)

    # --- Collection ("모두"/"각각") with unknown count and no items ---
    # We cannot verify without items or count; assume complete.
    return CompletenessResult(is_complete=True, found_items=[], missing_items=[])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_conjunction_items(query: str) -> list[str]:
    """Extract noun-phrase items joined by Korean conjunctions or commas.

    Examples:
        "매출과 비용 및 이익을 알려줘" -> ["매출", "비용", "이익"]
        "A, B, C에 대해" -> ["A", "B", "C"]
        "서울과 부산 비교" -> [] (handled by comparison pattern instead)
    """
    # Find the longest span that contains conjunctions / commas between nouns
    # Strategy: scan for sequences of (word conj word conj word ...)
    # We look for "word(와|과|및|,)word" chains.
    pattern = re.compile(
        r"([가-힣A-Za-z0-9_\-]{1,30})"
        r"(?:\s*(?:와|과|및|,)\s*"
        r"([가-힣A-Za-z0-9_\-]{1,30}))"
        r"+"
    )
    m = pattern.search(query)
    if not m:
        return []

    # Extract the full matched span and split by conjunctions
    span = query[m.start() : m.end()]
    items = _SPLIT_CONJ_RE.split(span)
    items = [item.strip() for item in items if item.strip()]

    # Filter out very short noise tokens (single jamo, particles)
    items = [item for item in items if len(item) >= 1]

    return items


def _verify_items(
    query: str,
    answer: str,
    parts: ExpectedParts,
) -> CompletenessResult:
    """Verify that each expected item appears in the answer."""
    answer_lower = answer.lower()
    found: list[str] = []
    missing: list[str] = []

    for item in parts.expected_items:
        # Case-insensitive substring match
        if item.lower() in answer_lower:
            found.append(item)
        else:
            missing.append(item)

    if not missing:
        return CompletenessResult(
            is_complete=True,
            found_items=found,
            missing_items=[],
            missing_query=None,
        )

    missing_query = _build_missing_query(query, missing)
    logger.info(
        "completeness_items_missing",
        found=found,
        missing=missing,
        missing_query=missing_query,
    )
    return CompletenessResult(
        is_complete=False,
        found_items=found,
        missing_items=missing,
        missing_query=missing_query,
    )


def _verify_count(
    query: str,
    answer: str,
    parts: ExpectedParts,
) -> CompletenessResult:
    """Verify the answer contains at least the expected number of distinct items."""
    assert parts.expected_count is not None

    # Heuristic: count bullet points, numbered items, or newline-separated items
    distinct = _count_distinct_items(answer)

    if distinct >= parts.expected_count:
        return CompletenessResult(
            is_complete=True,
            found_items=[f"({distinct} items detected)"],
            missing_items=[],
            missing_query=None,
        )

    shortfall = parts.expected_count - distinct
    logger.info(
        "completeness_count_short",
        expected=parts.expected_count,
        found=distinct,
        shortfall=shortfall,
    )
    # Re-query asking for the missing count
    missing_query = f"{query} (나머지 {shortfall}건 추가로 알려주세요)"
    return CompletenessResult(
        is_complete=False,
        found_items=[f"({distinct} items detected)"],
        missing_items=[f"({shortfall} items missing)"],
        missing_query=missing_query,
    )


def _count_distinct_items(answer: str) -> int:
    """Count the number of distinct items/bullet points in the answer text.

    Recognises:
    - Numbered lists: "1.", "2.", "1)", "2)"
    - Bullet points: "- ", "* ", "• "
    - Bold markdown headers used as list items: "**item**:"
    """
    # Numbered items (1. / 1) / (1))
    numbered = set(re.findall(r"(?:^|\n)\s*(\d+)[.)]\s", answer))
    if len(numbered) >= 2:
        return len(numbered)

    # Bullet points
    bullets = re.findall(r"(?:^|\n)\s*[-*•]\s+", answer)
    if len(bullets) >= 2:
        return len(bullets)

    # Bold markdown items: **something**:
    bold_items = re.findall(r"\*\*[^*]+\*\*\s*[:：]", answer)
    if len(bold_items) >= 2:
        return len(bold_items)

    # Fallback: count non-empty lines that look like separate items
    lines = [line.strip() for line in answer.split("\n") if line.strip()]
    # If there are many short lines, they might be list items
    if len(lines) >= 3 and all(len(line) < 200 for line in lines):
        return len(lines)

    # Cannot determine — return 1 as a conservative estimate
    return 1


def _build_missing_query(query: str, missing_items: list[str]) -> str:
    """Build a targeted re-retrieval query focused on missing items."""
    if len(missing_items) == 1:
        return f"{missing_items[0]} {query}"

    joined = ", ".join(missing_items)
    return f"{joined} {query}"
