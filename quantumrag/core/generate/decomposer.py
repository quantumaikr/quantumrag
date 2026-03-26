"""Query decomposition for complex multi-hop queries."""

from __future__ import annotations

import re
from typing import Any

from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.decomposer")

# Conjunction patterns that indicate multiple sub-queries
_EN_CONJUNCTIONS = re.compile(
    r"\b(?:and also|and then|and|but also|as well as|in addition to|furthermore|moreover)\b",
    re.IGNORECASE,
)
_KO_CONJUNCTIONS = re.compile(
    r"(?:또한|그리고|뿐만 아니라|아울러|더불어|및)",
)
_MULTI_QUESTION = re.compile(r"[?？]")


class QueryDecomposer:
    """Decomposes complex queries into sub-queries."""

    def __init__(self, llm_provider: Any | None = None) -> None:
        self._llm = llm_provider

    async def decompose(self, query: str) -> list[str]:
        """Break complex query into sub-queries.

        Falls back to heuristic decomposition if no LLM.
        """
        if self._llm is not None:
            return await self._llm_decompose(query)
        return self._heuristic_decompose(query)

    async def _llm_decompose(self, query: str) -> list[str]:
        """Use LLM to decompose the query into sub-queries."""
        prompt = (
            "Break the following complex question into simple, independent sub-questions. "
            "Return one sub-question per line, with no numbering or bullets.\n\n"
            f"Question: {query}\n\nSub-questions:"
        )
        try:
            response = await self._llm.generate(prompt, max_tokens=512, temperature=0.0)
            lines = [line.strip() for line in response.text.strip().splitlines()]
            sub_queries = [line for line in lines if line and len(line) > 5]
            if sub_queries:
                return sub_queries
        except Exception:
            logger.warning("llm_decompose_failed, falling back to heuristic", exc_info=True)

        return self._heuristic_decompose(query)

    def _heuristic_decompose(self, query: str) -> list[str]:
        """Rule-based decomposition for common patterns.

        Splits on conjunctions, multiple question marks, and Korean conjunctions.
        """
        # Strategy 1: Split on multiple question marks
        questions = _MULTI_QUESTION.split(query)
        questions = [q.strip() for q in questions if q.strip() and len(q.strip()) > 5]
        if len(questions) >= 2:
            # Re-add question marks
            return [q + "?" if not q.endswith(("?", "？")) else q for q in questions]

        # Strategy 2: Split on English conjunctions
        parts = _EN_CONJUNCTIONS.split(query)
        parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 5]
        if len(parts) >= 2:
            return [p + "?" if not p.endswith(("?", "？", ".")) else p for p in parts]

        # Strategy 3: Split on Korean conjunctions
        parts = _KO_CONJUNCTIONS.split(query)
        parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
        if len(parts) >= 2:
            return [p + "?" if not p.endswith(("?", "？", ".")) else p for p in parts]

        # No decomposition needed — return original query
        return [query]
