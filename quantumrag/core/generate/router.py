"""Adaptive query routing — classifies query complexity and type."""

from __future__ import annotations

import re

from quantumrag.core.logging import get_logger
from quantumrag.core.models import QueryComplexity

logger = get_logger("quantumrag.router")

# Keywords indicating complex queries
_COMPLEX_INDICATORS = {
    "compare",
    "contrast",
    "difference",
    "between",
    "versus",
    "vs",
    "analyze",
    "evaluate",
    "assess",
    "implications",
    "relationship",
    "pros and cons",
    "advantages and disadvantages",
    "similarities",
    "correlat",
    "impact",
    "trade-off",
    "tradeoff",
    "비교",
    "분석",
    "평가",
    "차이",
    "관계",
    "영향",
    "종합",
    "장단점",
    "상관관계",
}

# Patterns for Korean temporal/aggregation queries
_TEMPORAL_AGGREGATION_RE = re.compile(
    r"(기간별|월별|분기별|연도별|주별|일별|반기별|연간|분기|추이|변화량)",
)

# Patterns for "what-if" / conditional reasoning queries
_CONDITIONAL_RE = re.compile(
    r"(만약|~?한다면|~?할\s*경우|~?했다면|~?하면|가정|시나리오|만일|~?될\s*경우)",
)

_MEDIUM_INDICATORS = {
    "how",
    "why",
    "explain",
    "describe",
    "what are",
    "list",
    "어떻게",
    "왜",
    "설명",
    "나열",
    "무엇",
    "과정",
}

# Aggregation patterns (superlatives, counting, totals)
_SUPERLATIVE_RE = re.compile(r"가장\s*(많|큰|높|낮|적)")
_COUNTING_RE = re.compile(r"몇\s*(건|개|명|회)")
_TOTAL_RE = re.compile(r"총\s*(합계|규모|금액|인원)")

# No-retrieval patterns (greetings, simple math, time)
_NO_RETRIEVAL_RE = re.compile(
    r"^(?:hi|hello|hey|안녕|감사)|^\d+\s*[+\-*/]\s*\d+|^(?:what time|몇 시)",
    re.IGNORECASE,
)


class QueryRouter:
    """Routes queries to appropriate processing paths based on complexity.

    Simple (70%): Direct factual questions -> nano model, no reranking
    Medium (20%): How/why questions -> mini model, reranking + compression
    Complex (10%): Multi-hop, comparison -> large model, full pipeline
    """

    def classify(self, query: str) -> QueryClassification:
        """Classify query complexity and determine processing path."""
        query_lower = query.lower()
        words = set(re.findall(r"\w+", query_lower))

        # Track how many signal categories matched for confidence scoring
        complex_signals = 0
        medium_signals = 0

        # Check for complex indicators (word match for English, substring for Korean)
        has_complex_keyword = (
            words & _COMPLEX_INDICATORS
            or _contains_any(query_lower, _COMPLEX_INDICATORS)
        )
        has_multi_question = _is_multi_question(query)
        has_conditional = bool(_CONDITIONAL_RE.search(query_lower))

        if has_complex_keyword:
            complex_signals += 1
        if has_multi_question:
            complex_signals += 1
        if has_conditional:
            complex_signals += 1

        has_medium_keyword = (
            words & _MEDIUM_INDICATORS
            or _contains_any(query_lower, _MEDIUM_INDICATORS)
        )
        has_long_query = len(query) > 100
        has_temporal = bool(_TEMPORAL_AGGREGATION_RE.search(query_lower))

        if has_medium_keyword:
            medium_signals += 1
        if has_long_query:
            medium_signals += 1
        if has_temporal:
            medium_signals += 1

        if complex_signals > 0 or has_conditional:
            complexity = QueryComplexity.COMPLEX
            # More matching signals → higher confidence
            confidence = min(0.6 + complex_signals * 0.15, 1.0)
        elif medium_signals > 0:
            complexity = QueryComplexity.MEDIUM
            confidence = min(0.6 + medium_signals * 0.15, 1.0)
        else:
            complexity = QueryComplexity.SIMPLE
            # Simple is the default — lower confidence for very short queries
            confidence = 0.9 if len(query) > 10 else 0.7

        # Determine if retrieval is needed (self-routing)
        needs_retrieval = _needs_retrieval(query_lower)

        result = QueryClassification(
            complexity=complexity,
            needs_retrieval=needs_retrieval,
            query_type=_detect_query_type(query_lower),
            confidence=confidence,
        )
        logger.debug(
            "query_classified",
            complexity=result.complexity.value,
            needs_retrieval=result.needs_retrieval,
            query_type=result.query_type,
            confidence=result.confidence,
        )
        return result


class QueryClassification:
    """Result of query classification."""

    __slots__ = ("complexity", "confidence", "needs_retrieval", "query_type")

    def __init__(
        self,
        complexity: QueryComplexity,
        needs_retrieval: bool = True,
        query_type: str = "factual",
        confidence: float = 1.0,
    ) -> None:
        self.complexity = complexity
        self.needs_retrieval = needs_retrieval
        self.query_type = query_type
        self.confidence = confidence


def _contains_any(text: str, indicators: set[str]) -> bool:
    """Check if text contains any of the indicator strings (substring match)."""
    return any(ind in text for ind in indicators)


def _is_multi_question(query: str) -> bool:
    """Check if query contains multiple sub-questions."""
    question_marks = query.count("?") + query.count("？")
    return question_marks >= 2


def _needs_retrieval(query: str) -> bool:
    """Self-routing: determine if retrieval is needed.

    Skip retrieval for greetings, simple math, etc.
    """
    return not bool(_NO_RETRIEVAL_RE.search(query))


def _detect_query_type(query: str) -> str:
    """Detect the type of query."""
    if any(w in query for w in ["compare", "difference", "비교", "차이", "대비", "vs"]):
        return "comparative"
    if _CONDITIONAL_RE.search(query):
        return "conditional"
    if any(w in query for w in ["how to", "steps", "process", "어떻게", "방법", "과정"]):
        return "procedural"
    if any(w in query for w in ["list", "all", "나열", "모든", "목록"]):
        return "aggregation"
    # Aggregation via temporal patterns (기간별, 월별, 분기별, etc.)
    if _TEMPORAL_AGGREGATION_RE.search(query):
        return "aggregation"
    # Aggregation via superlatives/counting
    if _SUPERLATIVE_RE.search(query) or _COUNTING_RE.search(query):
        return "aggregation"
    if _TOTAL_RE.search(query):
        return "aggregation"
    if any(w in query for w in ["why", "reason", "왜", "이유"]):
        return "analytical"
    return "factual"
