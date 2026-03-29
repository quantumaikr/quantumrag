"""LLM-based Query Expansion — bridges the gap between colloquial and formal terms.

Solves the Semantic Gap problem where casual user language ("기술 뺏기지 않으려고")
doesn't match formal document terms ("특허", "지식재산권", "영업비밀 보호").

The expander:
1. Detects informal/colloquial queries
2. Uses a lightweight LLM call to generate formal search terms
3. Combines original + expanded terms for broader retrieval
"""

from __future__ import annotations

import re
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.utils.text import detect_korean

logger = get_logger("quantumrag.query_expander")

_EXPANSION_PROMPT_KO = """사용자 질문을 분석하여 검색에 유용한 키워드를 추가하세요.

규칙:
1. 원래 질문의 의도를 유지하세요
2. 구어체를 공식 용어로 변환하세요
3. 관련 동의어와 상위 개념을 추가하세요
4. 확장된 검색 키워드만 출력하세요 (설명 불필요)
5. 최대 10단어 이내로 출력하세요

예시:
- "돈이 얼마나 남았어?" → "보유 현금 잔액 자금 재무 상태"
- "회사 보안 괜찮아?" → "보안 감사 취약점 보안 수준 평가 결과 Critical High"
- "기술 뺏기지 않으려고 뭐 해놨어?" → "기술 보호 특허 지식재산 영업비밀 보호 조치"
- "일본에서 제일 큰 계약" → "일본 최대 계약 규모 PoC 금액 진행중 확정"
- "해킹 당하면 위험한 거" → "보안 취약점 Critical High 데이터 유출 API 키 SQL Injection 감사"

사용자 질문: {query}

확장된 검색 키워드:"""

_EXPANSION_PROMPT_EN = """Analyze the user question and add useful search keywords.

Rules:
1. Preserve the original question's intent
2. Convert colloquial language to formal terms
3. Add related synonyms and broader concepts
4. Output only expanded search keywords (no explanation)
5. Maximum 10 words

Examples:
- "How much money do we have left?" → "cash balance funds financial reserves status"
- "Is our security okay?" → "security audit vulnerability assessment report critical high"
- "What did we do to protect our tech?" → "technology protection patent IP trade secret measures"

User question: {query}

Expanded search keywords:"""

# Markers for informal/colloquial Korean
_INFORMAL_MARKERS = [
    "어?",
    "야?",
    "거야",
    "해놨",
    "뭐에요",
    "뭐야",
    "했어",
    "뺏기",
    "괜찮",
    "얼마야",
    "해놓",
    "해둔",
    "했나",
    "됐",
    "줘",
    "줘?",
    "거든",
    "거야?",
    "뭔가",
    "어때",
    "냐고",
    "냐?",
    "쩌?",
    "인데?",
]

# English informal markers for bilingual support
_ENGLISH_INFORMAL_MARKERS = [
    "what's",
    "gonna",
    "wanna",
    "dunno",
    "gotta",
    "ain't",
    "kinda",
    "sorta",
    "lemme",
    "gimme",
    "howcome",
    "y'all",
]

# Fallback dictionary for common Korean colloquial → formal expansions
# Used when LLM is unavailable (no API call needed)
_FALLBACK_EXPANSIONS: dict[str, str] = {
    "돈": "자금 재무 현금 금액",
    "얼마": "금액 규모 수치 비용",
    "뺏기": "유출 탈취 침해 보호",
    "괜찮": "상태 수준 평가 결과",
    "해킹": "보안 취약점 침해 공격",
    "사람": "인원 직원 인력 담당자",
    "매출": "수익 실적 매출액 영업이익",
    "계약": "계약 체결 수주 규모 금액",
    "문제": "이슈 장애 결함 리스크",
}


def is_colloquial(query: str) -> bool:
    """Detect if a query uses informal/colloquial language."""
    query_lower = query.lower()
    return any(marker in query for marker in _INFORMAL_MARKERS) or any(
        marker in query_lower for marker in _ENGLISH_INFORMAL_MARKERS
    )


class QueryExpander:
    """Expands colloquial queries with formal search terms via LLM."""

    def __init__(self, llm_provider: Any) -> None:
        self._llm = llm_provider

    async def expand(self, query: str) -> str:
        """Expand a colloquial query with formal search terms.

        Returns the original query combined with expanded terms.
        If the query is already formal, returns it unchanged.
        """
        if not is_colloquial(query):
            return query

        try:
            prompt = _EXPANSION_PROMPT_KO if detect_korean(query) else _EXPANSION_PROMPT_EN
            response = await self._llm.generate(
                prompt.format(query=query),
                temperature=0.0,
                max_tokens=80,
            )
            expanded = response.text.strip()
            expanded = re.sub(r"^(확장|키워드|검색어)[:：]\s*", "", expanded)
            expanded = expanded.split("\n")[0].strip()

            if expanded and expanded != query:
                combined = f"{query} {expanded}"
                logger.info(
                    "query_expanded",
                    original=query,
                    expanded_terms=expanded,
                    combined=combined,
                )
                return combined
        except Exception:
            logger.warning("query_expansion_failed", exc_info=True)
            return _fallback_expand(query)

        return query


def _fallback_expand(query: str) -> str:
    """Expand query using a static dictionary when LLM is unavailable."""
    return _dictionary_expand(query, tag="fallback")


def _dictionary_expand(query: str, tag: str = "dict") -> str:
    """Add cross-language and synonym terms from the static dictionary."""
    extra_terms: list[str] = []
    for keyword, expansions in _FALLBACK_EXPANSIONS.items():
        if keyword in query:
            # Only add terms not already in query
            new_terms = [t for t in expansions.split() if t.lower() not in query.lower()]
            if new_terms:
                extra_terms.append(" ".join(new_terms))
    if extra_terms:
        combined = f"{query} {' '.join(extra_terms)}"
        logger.info(
            f"query_expanded_{tag}",
            original=query,
            combined=combined,
        )
        return combined
    return query
