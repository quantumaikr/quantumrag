"""Query-Aware Fusion Weight classifier.

Detects query characteristics and returns adaptive fusion weights so the
retrieval pipeline can emphasise the index that best suits the query type.

Three query types:
- **term_specific**: Contains precise terms (numbers with Korean units, acronyms,
  quoted strings) → BM25-dominant weights.
- **comparative**: Contains comparison keywords → HyPE-dominant weights.
- **conceptual** (default): Standard balanced weights.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Pre-compiled patterns
# ---------------------------------------------------------------------------

# Numbers followed by Korean monetary/scale units (만, 억, 천)
_KOREAN_UNIT_RE = re.compile(r"\d+\s*[만억천]")

# Uppercase acronyms of 2+ characters (e.g., RGCN, OVON, SAR)
# Excludes common generic acronyms that are used conceptually and
# should not force BM25-dominant retrieval weights.
_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
_GENERIC_ACRONYMS: frozenset[str] = frozenset(
    {
        "AI",
        "IT",
        "ML",
        "DL",
        "NLP",
        "LLM",
        "GPT",
        "UI",
        "UX",
        "DB",
        "OS",
        "PC",
        "TV",
        "HR",
        "PR",
        "QA",
        "VP",
        "CEO",
        "CTO",
        "CFO",
        "COO",
        "FAQ",
        "OK",
        "PM",
        "KPI",
        "OKR",
        "ROI",
        "SLA",
        "SDK",
        "IDE",
        "CI",
        "CD",
        "REST",
        "HTTP",
        "HTTPS",
        "URL",
        "URI",
        "HTML",
        "CSS",
        "JSON",
        "XML",
        "CSV",
        "PDF",
        "SQL",
        "SSH",
        "FTP",
    }
)

# Mixed-case technical terms (e.g., ZeroH, HyPE, QuantumRAG, QuantumGuard)
_MIXED_CASE_TERM_RE = re.compile(r"\b[A-Z][a-z]+[A-Z][a-zA-Z]*\b|\b[A-Z]{2,}[a-z]+[A-Z]*\b")

# Quoted terms (single or double quotes, or Korean quotation marks)
_QUOTED_RE = re.compile(r"""["'\u201c\u201d\u2018\u2019].+?["'\u201c\u201d\u2018\u2019]""")

# Korean queries asking for specific values — need precise retrieval
_VALUE_ASKING_RE = re.compile(
    r"(?:얼마|몇\s*[%개건명억만천원달러]|전망[은이가]?\s*(?:어떻|얼마)|"
    r"모금액|성장률|증가율|비율|규모[는은이가]?\s*(?:어떻|얼마)|"
    r"발급자\s*수|수치|금액|"
    r"\d+위|1위|순위|점수|벤치마크|점유율|최대|최소)"
)

# Comparison keywords (Korean and English)
_COMPARATIVE_KEYWORDS = re.compile(
    r"비교|차이|vs\.?|다른|대비|장단점",
    re.IGNORECASE,
)

# SQL-like or code-like patterns — should NOT be classified as term_specific
_CODE_LIKE_RE = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE)\b.*\b(FROM|INTO|SET|TABLE|WHERE)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Weight presets
# ---------------------------------------------------------------------------

WEIGHT_PRESETS: dict[str, dict[str, float]] = {
    "term_specific": {"original": 0.20, "hype": 0.15, "bm25": 0.65},
    "comparative": {"original": 0.30, "hype": 0.50, "bm25": 0.20},
    "conceptual": {"original": 0.40, "hype": 0.35, "bm25": 0.25},
}


def detect_query_type(query: str) -> tuple[str, dict[str, float]]:
    """Classify *query* and return ``(query_type_name, weights_dict)``.

    Detection order matters — ``term_specific`` is checked first because a
    query like ``"RGCN과 GAT의 차이"`` should prioritise exact-term matching
    even though it also contains a comparison keyword.
    """
    # 0. Guard: code-like / SQL-like input → conceptual (let LLM handle)
    if _CODE_LIKE_RE.search(query):
        return "conceptual", WEIGHT_PRESETS["conceptual"]

    # 1. term_specific: numbers+units, domain-specific acronyms, mixed-case
    #    terms, quoted terms, or queries asking for specific values.
    #    Generic acronyms (AI, IT, ML, etc.) are excluded — they appear in
    #    conceptual questions where semantic search should dominate.
    has_specific_acronym = False
    acronym_match = _ACRONYM_RE.findall(query)
    if acronym_match:
        has_specific_acronym = any(a not in _GENERIC_ACRONYMS for a in acronym_match)

    # English technical terms in Korean context (e.g., "Singleton 패턴",
    # "Decorator 패턴", "Protocol과", "deque의") — signals precise term lookup
    # Matches both capitalized (Singleton) and lowercase (deque, asyncio) terms
    has_en_term_in_ko = bool(
        re.search(r"[A-Za-z]{3,}", query) and re.search(r"[\uac00-\ud7a3]", query)
    )

    if (
        _KOREAN_UNIT_RE.search(query)
        or has_specific_acronym
        or _MIXED_CASE_TERM_RE.search(query)
        or _QUOTED_RE.search(query)
        or _VALUE_ASKING_RE.search(query)
        or has_en_term_in_ko
    ):
        return "term_specific", WEIGHT_PRESETS["term_specific"]

    # 2. comparative: comparison keywords
    if _COMPARATIVE_KEYWORDS.search(query):
        return "comparative", WEIGHT_PRESETS["comparative"]

    # 3. conceptual (default)
    return "conceptual", WEIGHT_PRESETS["conceptual"]
