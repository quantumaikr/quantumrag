"""Derived Index Enrichment — generate synonym/hierarchy terms at ingest time.

Solves the fundamental keyword gap where "Critical" chunks aren't found
by "High 이상" queries. At ingest time, we expand implicit relationships
into explicit searchable terms.

Expansion types:
    - Severity hierarchy: Critical → "High 이상", "Medium 이상"
    - Temporal normalization: 2024-07-20 → "하반기", "Q3"
    - Amount normalization: 3.2억 → "약 3억", "억 단위"
    - Status synonyms: 완료 → "조치 완료된", "해결됨"
    - Version normalization: v2.4.0 → "v2.4", "2.4 버전"
"""

from __future__ import annotations

import re
from typing import Any

from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.derived_index")

# ── Severity hierarchy ──────────────────────────────────────────────────────

_SEVERITY_LEVELS = {
    # Korean and English severity terms, ordered high → low
    "critical": 4,
    "심각": 4,
    "high": 3,
    "높음": 3,
    "medium": 2,
    "중간": 2,
    "보통": 2,
    "low": 1,
    "낮음": 1,
}

_SEVERITY_LABELS_KO = {4: "심각", 3: "높음", 2: "중간", 1: "낮음"}
_SEVERITY_LABELS_EN = {4: "Critical", 3: "High", 2: "Medium", 1: "Low"}

_SEVERITY_PATTERN = re.compile(
    r"\b(Critical|High|Medium|Low)\b|"
    r"(심각|높음|중간|보통|낮음)",
    re.IGNORECASE,
)


def _expand_severity(text: str) -> list[str]:
    """Expand severity terms with hierarchy inclusion.

    If a chunk contains "Critical", it should also be findable by
    "High 이상", "Medium 이상", etc.
    """
    terms: list[str] = []
    found_levels: set[int] = set()

    for m in _SEVERITY_PATTERN.finditer(text):
        matched = m.group(0).lower()
        level = _SEVERITY_LEVELS.get(matched)
        if level:
            found_levels.add(level)

    for level in found_levels:
        # Add "X 이상" for all levels below this one
        for lower_level in range(1, level):
            ko = _SEVERITY_LABELS_KO[lower_level]
            en = _SEVERITY_LABELS_EN[lower_level]
            terms.append(f"{ko} 이상")
            terms.append(f"{ko} 등급 이상")
            terms.append(f"{en} 이상")
            terms.append(f"{en} 등급 이상")

    return terms


# ── Temporal normalization ──────────────────────────────────────────────────

_DATE_PATTERN = re.compile(r"(\d{4})[.-/](\d{1,2})[.-/](\d{1,2})")
_YEAR_MONTH_PATTERN = re.compile(r"(\d{4})년\s*(\d{1,2})월")


def _month_to_half(month: int) -> str:
    return "상반기" if month <= 6 else "하반기"


def _month_to_quarter(month: int) -> str:
    return f"Q{(month - 1) // 3 + 1}"


def _expand_temporal(text: str) -> list[str]:
    """Expand dates into half-year, quarter, and month terms."""
    terms: list[str] = []
    seen: set[tuple[int, int]] = set()

    for pattern in [_DATE_PATTERN, _YEAR_MONTH_PATTERN]:
        for m in pattern.finditer(text):
            year = int(m.group(1))
            month = int(m.group(2))
            if (year, month) in seen:
                continue
            seen.add((year, month))

            half = _month_to_half(month)
            quarter = _month_to_quarter(month)
            terms.append(f"{year}년 {half}")
            terms.append(f"{quarter} {year}")
            terms.append(f"{year}년 {quarter}")
            terms.append(f"{month}월")

    return terms


# ── Amount normalization ────────────────────────────────────────────────────

_AMOUNT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(억|천만|백만|만)\s*(?:원|달러|엔)?"
)


def _expand_amount(text: str) -> list[str]:
    """Expand monetary amounts with approximate and unit terms."""
    terms: list[str] = []

    for m in _AMOUNT_PATTERN.finditer(text):
        value = float(m.group(1))
        unit = m.group(2)

        if unit == "억":
            approx = round(value)
            terms.append(f"약 {approx}억")
            terms.append("억 단위")
            terms.append(f"{approx}억원대")
        elif unit in ("천만", "백만", "만"):
            terms.append(f"{unit}원 단위")

    return terms


# ── Status synonyms ─────────────────────────────────────────────────────────

_STATUS_SYNONYMS = {
    "완료": ["조치 완료된", "조치 완료", "해결됨", "처리 완료"],
    "미조치": ["미해결", "대기 중", "미완료", "조치 미완료"],
    "진행 중": ["진행중", "처리 중", "작업 중"],
    "진행중": ["진행 중", "처리 중", "작업 중"],
    "예정": ["계획됨", "계획", "예정된"],
    "보류": ["보류 중", "일시 중단"],
}

_STATUS_PATTERN = re.compile(
    r"(?:조치\s*상태|상태)\s*[:：]?\s*(완료|미조치|진행\s*중|진행중|예정|보류)"
)


def _expand_status(text: str) -> list[str]:
    """Expand status terms with synonyms."""
    terms: list[str] = []
    for m in _STATUS_PATTERN.finditer(text):
        status = m.group(1).strip()
        synonyms = _STATUS_SYNONYMS.get(status, [])
        terms.extend(synonyms)
    return terms


# ── Version normalization ───────────────────────────────────────────────────

_VERSION_PATTERN = re.compile(r"v?(\d+)\.(\d+)(?:\.(\d+))?")


def _expand_version(text: str) -> list[str]:
    """Expand version numbers with common aliases."""
    terms: list[str] = []
    seen: set[str] = set()

    for m in _VERSION_PATTERN.finditer(text):
        major = m.group(1)
        minor = m.group(2)
        key = f"{major}.{minor}"
        if key in seen:
            continue
        seen.add(key)
        terms.append(f"v{major}.{minor}")
        terms.append(f"{major}.{minor} 버전")

    return terms


# ── Public API ──────────────────────────────────────────────────────────────

def generate_derived_terms(content: str) -> str:
    """Generate all derived/synonym terms for a chunk's content.

    Returns a space-separated string of derived terms to be appended
    to the BM25 index (not to the chunk content itself).
    """
    all_terms: list[str] = []
    all_terms.extend(_expand_severity(content))
    all_terms.extend(_expand_temporal(content))
    all_terms.extend(_expand_amount(content))
    all_terms.extend(_expand_status(content))
    all_terms.extend(_expand_version(content))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in all_terms:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    if unique:
        logger.debug("derived_terms_generated", count=len(unique))

    return " ".join(unique)
