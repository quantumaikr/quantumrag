"""Conversational query rewriting & query decomposition for multi-turn dialogue.

Two key innovations:

1. **Entity Memory Tracker** — Maintains an explicit entity stack across
   conversation turns. Each entity has a *type* (company, product, person, etc.)
   and *name*, allowing precise pronoun resolution even after topic changes.

2. **Query Decomposition** — Complex multi-hop questions are split into
   independent sub-queries that can be searched in parallel, dramatically
   improving recall for questions that span multiple documents.

Usage:
    rewriter = QueryRewriter(max_turns=5)
    rewritten = await rewriter.rewrite(
        query="What about its revenue?",
        history=[
            ConversationTurn(role="user", content="Tell me about Apple Inc."),
            ConversationTurn(role="assistant", content="Apple Inc. is a ..."),
        ],
    )
    # => "What about Apple Inc.'s revenue?"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.rewriter")

# English pronouns that signal coreference
_EN_PRONOUNS: re.Pattern[str] = re.compile(
    r"\b(it|its|this|that|they|them|their|these|those|the company|the document)\b",
    re.IGNORECASE,
)

# Korean demonstrative + noun phrases (order matters: longer patterns first)
_KO_DEMO_NOUN: re.Pattern[str] = re.compile(
    r"(그\s*회사|이\s*회사|그\s*제품|이\s*제품|그\s*서비스|이\s*서비스"
    r"|그\s*사람|이\s*사람|그\s*문서|이\s*문서|그\s*곳|이\s*곳)",
)
# Standalone Korean pronouns (only match when NOT followed by a noun)
_KO_PRONOUNS: re.Pattern[str] = re.compile(
    r"(그것|이것|저것|거기|여기|그들|그녀|그의|이런|그런)",
)

# Entity type mapping for Korean demonstrative resolution
_DEMO_TO_TYPE: dict[str, str] = {
    "회사": "company",
    "제품": "product",
    "서비스": "service",
    "사람": "person",
    "문서": "document",
    "곳": "place",
}

_REWRITE_SYSTEM_PROMPT = (
    "You are a query rewriter for a retrieval-augmented generation system. "
    "Your task is to rewrite a follow-up query into a standalone query that "
    "can be understood without the conversation history.\n\n"
    "Rules:\n"
    "1. Resolve all pronouns and references using the conversation context.\n"
    "2. Preserve the original intent and specificity of the question.\n"
    "3. Output ONLY the rewritten query, nothing else.\n"
    "4. If the query is already standalone, return it unchanged.\n"
    "5. Keep the same language as the original query."
)

_REWRITE_USER_TEMPLATE = (
    "Conversation history:\n{history}\n\nFollow-up query: {query}\n\nRewritten standalone query:"
)

# Query decomposition patterns — questions with multiple parts
_MULTI_PART_SIGNALS = re.compile(
    r"(그리고|또한|아울러|동시에|뿐만\s*아니라|and also|and\s|in addition)"
    r"|(,\s*그리고)"
    r"|(얼마.*(?:이고|이며).*(?:어떤|무엇))"
    r"|((?:어떤|무엇).*(?:이고|이며).*(?:얼마|몇))",
    re.IGNORECASE,
)

# Patterns to detect compound questions with comma/conjunction
_COMPOUND_Q = re.compile(r"(.+?(?:이고|이며|인가요|인가)\s*,?\s*)(.+\??)$")


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """A single turn in a conversation."""

    role: str  # "user" or "assistant"
    content: str


@dataclass(frozen=True, slots=True)
class TrackedEntity:
    """An entity tracked across conversation turns."""

    name: str
    entity_type: str  # "company", "product", "person", "concept", etc.
    turn_index: int  # when it was last mentioned


@dataclass
class QueryRewriter:
    """Rewrites follow-up queries into standalone queries.

    Supports two strategies:
    - LLM-based rewriting (when *llm_provider* is supplied)
    - Heuristic fallback with Entity Memory Tracker

    Parameters:
        llm_provider: Optional LLM provider for high-quality rewriting.
        max_turns: Maximum number of conversation turns to keep as context.
    """

    llm_provider: Any | None = field(default=None)
    max_turns: int = field(default=5)

    async def rewrite(
        self,
        query: str,
        history: list[ConversationTurn] | None = None,
    ) -> str:
        """Rewrite *query* using conversation *history*.

        Returns the query unchanged when history is empty or only a single
        user turn (no prior assistant context to resolve references from).
        """
        if not history or len(history) < 2:
            logger.debug("rewrite_skipped", reason="insufficient_history")
            return query

        # Truncate to the most recent turns
        truncated = history[-self.max_turns * 2 :]

        # Check if the query actually needs rewriting
        if not self._needs_rewriting(query):
            logger.debug("rewrite_skipped", reason="no_references_detected")
            return query

        # Try LLM rewriting first
        if self.llm_provider is not None:
            try:
                return await self._llm_rewrite(query, truncated)
            except Exception:
                logger.warning(
                    "llm_rewrite_failed",
                    exc_info=True,
                )

        # Fallback to heuristic with entity memory
        return self._heuristic_rewrite(query, truncated)

    # ------------------------------------------------------------------
    # LLM-based rewriting
    # ------------------------------------------------------------------

    async def _llm_rewrite(
        self,
        query: str,
        history: list[ConversationTurn],
    ) -> str:
        """Use an LLM to produce a standalone query."""
        history_text = "\n".join(f"{turn.role}: {turn.content}" for turn in history)
        user_prompt = _REWRITE_USER_TEMPLATE.format(history=history_text, query=query)

        response = await self.llm_provider.generate(
            user_prompt,
            system=_REWRITE_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=256,
        )
        rewritten = response.text.strip()

        if rewritten:
            logger.info(
                "query_rewritten",
                original=query,
                rewritten=rewritten,
                method="llm",
            )
            return rewritten

        # If the LLM returned empty, fall through to heuristic
        return self._heuristic_rewrite(query, history)

    # ------------------------------------------------------------------
    # Heuristic rewriting with Entity Memory
    # ------------------------------------------------------------------

    def _heuristic_rewrite(
        self,
        query: str,
        history: list[ConversationTurn],
    ) -> str:
        """Rule-based pronoun resolution using Entity Memory Tracker."""
        # Build entity memory from conversation history
        entities = _build_entity_memory(history)
        if not entities:
            return query

        rewritten = query

        # Resolve Korean demonstrative+noun phrases with TYPE-AWARE matching
        for match in _KO_DEMO_NOUN.finditer(query):
            phrase = match.group(0)
            # Extract the noun type: "그 회사" -> "회사" -> "company"
            for ko_noun, etype in _DEMO_TO_TYPE.items():
                if ko_noun in phrase:
                    # Find the most recent entity of matching type
                    entity = _find_entity_by_type(entities, etype)
                    if entity:
                        rewritten = rewritten.replace(phrase, entity.name, 1)
                    break

        # If no type-specific match worked, fall back to most recent entity
        if rewritten == query:
            fallback = entities[0] if entities else None
            if fallback:
                rewritten = _KO_DEMO_NOUN.sub(fallback.name, rewritten)

        # Replace standalone Korean pronouns with most recent entity
        if _KO_PRONOUNS.search(rewritten):
            top_entity = entities[0] if entities else None
            if top_entity:
                rewritten = _KO_PRONOUNS.sub(top_entity.name, rewritten)

        # Replace English pronouns
        if _EN_PRONOUNS.search(rewritten):
            top_entity = entities[0] if entities else None
            if top_entity:
                rewritten = _EN_PRONOUNS.sub(top_entity.name, rewritten)

        if rewritten != query:
            logger.info(
                "query_rewritten",
                original=query,
                rewritten=rewritten,
                method="heuristic_entity_memory",
            )

        return rewritten

    def _needs_rewriting(self, query: str) -> bool:
        """Return True if the query contains pronoun/reference markers."""
        return bool(
            _EN_PRONOUNS.search(query) or _KO_DEMO_NOUN.search(query) or _KO_PRONOUNS.search(query)
        )


# ──────────────────────────────────────────────────────────────────────
# Entity Memory Tracker
# ──────────────────────────────────────────────────────────────────────

# Known company names for entity classification
_KNOWN_COMPANIES = {
    "퀀텀소프트",
    "QuantumSoft",
    "퀀텀아이",
    "Upstage",
    "리턴제로",
    "ReturnZero",
    "뤼튼",
    "Wrtn",
    "포티투마루",
    "42Maru",
    "삼성전자",
    "KB국민은행",
    "네이버",
    "현대자동차",
    "소프트뱅크",
    "NTT",
    "미쓰비시",
}

_KNOWN_PRODUCTS = {
    "QuantumRAG",
    "QuantumChat",
    "QuantumGuard",
    "QuantumAnalytics",
}

_KNOWN_PERSONS = {
    "김태현",
    "박서연",
    "이준호",
    "정민지",
    "최영수",
    "강지훈",
    "김하은",
    "한소희",
    "오지현",
    "임수정",
    "윤재석",
    "조은서",
    "박지영",
    "이서준",
}


def _classify_entity(name: str) -> str:
    """Classify an entity name into a type."""
    if name in _KNOWN_COMPANIES or any(c in name for c in ("회사", "은행", "법인", "그룹")):
        return "company"
    if name in _KNOWN_PRODUCTS or any(p in name for p in ("Quantum", "v2.", "v3.")):
        return "product"
    if name in _KNOWN_PERSONS:
        return "person"
    return "concept"


def _build_entity_memory(history: list[ConversationTurn]) -> list[TrackedEntity]:
    """Build an ordered list of entities from conversation history.

    Extracts entities from:
    1. **Bold text** in assistant responses
    2. Known proper nouns in user queries
    3. Parenthesized names

    Returns entities ordered by recency (most recent first), deduplicated.
    """
    entities: list[TrackedEntity] = []
    seen_names: set[str] = set()

    for i, turn in enumerate(reversed(history)):
        turn_idx = len(history) - 1 - i

        if turn.role == "assistant":
            content = turn.content.strip()
            # Extract **bold** entities
            for bold_match in re.finditer(r"\*\*([^*]{2,30})\*\*", content):
                name = bold_match.group(1).strip()
                if name not in seen_names and not re.match(
                    r"^(신뢰도|답변|결론|요약|참고|출처|Confidence)", name
                ):
                    etype = _classify_entity(name)
                    entities.append(
                        TrackedEntity(name=name, entity_type=etype, turn_index=turn_idx)
                    )
                    seen_names.add(name)

            # Extract parenthesized names: "퀀텀아이 (Upstage)"
            for paren_match in re.finditer(r"([\w가-힣]{2,20})\s*\([A-Za-z\s.]+\)", content):
                name = paren_match.group(1).strip()
                if name not in seen_names:
                    etype = _classify_entity(name)
                    entities.append(
                        TrackedEntity(name=name, entity_type=etype, turn_index=turn_idx)
                    )
                    seen_names.add(name)

        elif turn.role == "user":
            content = turn.content.strip()
            # Extract known proper nouns from user queries
            all_known = _KNOWN_COMPANIES | _KNOWN_PRODUCTS | _KNOWN_PERSONS
            for known in all_known:
                if known in content and known not in seen_names:
                    etype = _classify_entity(known)
                    entities.append(
                        TrackedEntity(name=known, entity_type=etype, turn_index=turn_idx)
                    )
                    seen_names.add(known)

            # Extract topic words from "about X" / "regarding X" patterns
            # Handles both "Tell me about Python" and "Tell me about microservices"
            for topic_match in re.finditer(r"(?:about|regarding|of)\s+(\w[\w\s.#+]*\w)", content):
                candidate = topic_match.group(1).strip()
                # Take the first meaningful word(s) — stop at common conjunctions/verbs
                candidate = re.split(r"\s+(?:and|or|is|are|was|were|in|on|for|with)\b", candidate)[
                    0
                ].strip()
                if candidate and candidate not in seen_names and len(candidate) >= 2:
                    entities.append(
                        TrackedEntity(name=candidate, entity_type="concept", turn_index=turn_idx)
                    )
                    seen_names.add(candidate)

            # Korean: extract quoted or topic-marked nouns ("~에 대해", "~을 알려줘")
            for ko_topic in re.finditer(
                r"([\w가-힣]{2,20})(?:에\s*대해|을\s*|를\s*|이란|이라는)", content
            ):
                name = ko_topic.group(1).strip()
                if name not in seen_names and len(name) >= 2:
                    entities.append(
                        TrackedEntity(name=name, entity_type="concept", turn_index=turn_idx)
                    )
                    seen_names.add(name)

    return entities


def _find_entity_by_type(entities: list[TrackedEntity], entity_type: str) -> TrackedEntity | None:
    """Find the most recent entity of a given type."""
    for e in entities:
        if e.entity_type == entity_type:
            return e
    return None


# ──────────────────────────────────────────────────────────────────────
# Query Decomposition
# ──────────────────────────────────────────────────────────────────────


def decompose_query(query: str) -> list[str]:
    """Decompose a complex multi-part query into independent sub-queries.

    This enables parallel retrieval for each sub-query, dramatically
    improving recall for questions that span multiple documents.

    Handles three patterns:
    1. Compound questions: "A이고, B는?"
    2. Conjunction questions: "A 그리고 B"
    3. Comparative questions: "A 대비 B의 장점은?" → multi-perspective search

    Examples:
        "CTO가 겸임하는 팀은 어디이고, 그 팀의 예산은?"
        → ["CTO가 겸임하는 팀은 어디인가요?", "CTO 겸임 팀의 예산은 얼마인가요?"]

        "42Maru 대비 퀀텀소프트의 기술적 장점은?"
        → ["42Maru의 기술적 특징은?", "퀀텀소프트의 기술적 장점과 차별화 요소는?", original]

    Returns:
        List of sub-queries. Returns [query] if decomposition is not needed.
    """
    query = query.strip()
    if not query:
        return [query]

    # Pattern -1: Cross-document validation — "A의 X와 B의 X가 일치하나요?"
    # FDO Fix P5: Split into separate retrieval per document source
    cross_doc = _decompose_cross_validation(query)
    if cross_doc:
        return cross_doc

    # Pattern 0: Comparative queries — "A 대비/비교 B의 X"
    # These need multi-perspective retrieval to capture both sides
    comparative = _decompose_comparative(query)
    if comparative:
        return comparative

    # Pattern 1: Korean compound with "이고/이며" conjunction
    # e.g., "A는 어디이고, B는 얼마인가요?"
    # Note: "이고/이며" must be followed by a comma or space + more content
    m = re.match(
        r"(.+?(?:은|는|이|가)\s+.+?(?:이고|이며|이고요))\s*,?\s*(.+\??)$",
        query,
    )
    if m:
        part1 = m.group(1).rstrip(",").strip()
        part2 = m.group(2).strip()
        # Skip decomposition if either part is too short to be a useful query
        if len(part2) < 10:
            return [query]
        # Ensure each part ends with a question mark
        if not part1.endswith("?"):
            part1 = re.sub(r"(이고|이며|이고요)$", "인가요?", part1)
        if not part2.endswith("?"):
            part2 += "?"
        return [part1, part2]

    # Pattern 2: "A와 B를 각각 알려주세요" / "A 그리고 B"
    m = re.match(
        r"(.+?)(?:\s*(?:그리고|,\s*그리고|,\s*또한|아울러)\s*)(.+)$",
        query,
    )
    if m:
        part1 = m.group(1).strip()
        part2 = m.group(2).strip()
        if not part1.endswith("?"):
            part1 += "?"
        if not part2.endswith("?"):
            part2 += "?"
        # Only decompose if both parts are substantial
        if len(part1) > 10 and len(part2) > 10:
            return [part1, part2]

    # Pattern 3: Multi-hop conditional — "X가 성공/실패하면 총 Y는?"
    # Need to decompose into: (1) current Y baseline, (2) X details
    multi_hop = _decompose_multi_hop(query)
    if multi_hop:
        return multi_hop

    return [query]


# Multi-hop conditional patterns
# "X이/가 성공/실패하면 (총/누적) Y은/는 ...?"
_MULTI_HOP_CONDITIONAL = re.compile(
    r"(.+?)(?:이|가)\s*(?:성공|실패|성사|전환|추가|도입)하면\s+"
    r"(?:총\s+|누적\s+|현재\s+)?(.+?)(?:은|는|이|가|에)\s+(.+)",
    re.UNICODE,
)

# "N건이 모두 성사되면 Y?"
_MULTI_HOP_AGGREGATE = re.compile(
    r"(.+?)(?:이|가)\s*(?:모두\s+)?(?:성사|성공|완료)(?:되면|하면)\s+(.+)"
)

# "X하면 현재 Y로 ...?" (failure-based conditional)
_MULTI_HOP_FAILURE = re.compile(
    r"(.+?)(?:이|가)\s*(?:실패|중단|포기)하면\s+(?:현재\s+)?(.+?)(?:로|으로)\s+(.+)"
)


def _decompose_multi_hop(query: str) -> list[str] | None:
    """Decompose multi-hop conditional queries.

    "Series C 200억원이 성공하면 총 누적 투자액은 얼마인가요?"
    → ["현재 누적 투자액은 얼마인가요?", "Series C 금액은 얼마인가요?", original]

    "일본 PoC 3건이 모두 성사되면 ARR에 어떤 영향이 있나요?"
    → ["현재 ARR은 얼마인가요?", "일본 PoC 3건의 각각의 세부 규모는?", original]

    "Series C가 실패하면 현재 런웨이로 언제까지 운영 가능한가요?"
    → ["현재 런웨이는 얼마인가요?", "Series C 준비 상황은?", original]
    """
    # Pattern: "X가 실패하면 현재 Y로 ...?"
    m = _MULTI_HOP_FAILURE.search(query)
    if m:
        subject = m.group(1).strip()
        target = m.group(2).strip()
        baseline_q = f"현재 {target}는 얼마인가요?"
        detail_q = f"{subject} 준비 상황은?"
        return [baseline_q, detail_q, query]

    # Pattern: "X가 성공/성사하면 (총/누적) Y는?"
    m = _MULTI_HOP_CONDITIONAL.search(query)
    if m:
        subject = m.group(1).strip()
        target = m.group(2).strip()
        # Generate baseline query + detail query
        baseline_q = f"현재 {target}은 얼마인가요?"
        detail_q = f"{subject}의 금액은 얼마인가요?"
        return [baseline_q, detail_q, query]

    # Pattern: "N건이 모두 성사되면 Y는?"
    m = _MULTI_HOP_AGGREGATE.search(query)
    if m:
        subject = m.group(1).strip()
        rest = m.group(2).strip()
        # Extract target concept before particles
        for particle in ["에", "은", "는", "이", "가"]:
            if particle in rest:
                target = rest.split(particle)[0]
                break
        else:
            target = rest
        baseline_q = f"현재 {target}은 얼마인가요?"
        detail_q = f"{subject}의 각각의 세부 규모는?"
        return [baseline_q, detail_q, query]

    return None


# Comparative query patterns
_COMPARATIVE_PATTERNS = [
    # "A 대비 B의 X는?" or "A와 비교해서 B의 X"
    re.compile(r"(.+?)\s*(?:대비|와\s*비교|에\s*비해|보다)\s+(.+?)(?:의|에서의?)\s+(.+)"),
    # "A vs B X" or "A와 B 비교"
    re.compile(r"(.+?)\s*(?:vs\.?|versus)\s+(.+?)(?:의|에서의?)\s+(.+)"),
]


def _decompose_comparative(query: str) -> list[str] | None:
    """Decompose a comparative query into multi-perspective sub-queries."""
    for pattern in _COMPARATIVE_PATTERNS:
        m = pattern.search(query)
        if m:
            entity_a = m.group(1).strip().rstrip("와의")
            entity_b = m.group(2).strip().rstrip("와의")
            aspect = m.group(3).strip().rstrip("?")

            sub_queries = [
                f"{entity_a}의 {aspect}은?",
                f"{entity_b}의 {aspect}과 차별화 요소는?",
                query,  # Include original for context retrieval
            ]
            logger.info(
                "comparative_decomposition",
                original=query,
                entity_a=entity_a,
                entity_b=entity_b,
                aspect=aspect,
            )
            return sub_queries
    return None


# ── FDO Fix P5: Cross-document validation decomposition ──────────────────

# "A의 X와 B의 X가 일치하나요?" patterns
_CROSS_VALIDATION_PATTERNS = [
    # "회의록의 채용 계획과 로드맵의 채용 계획이 일치하나요?"
    re.compile(
        r"(.+?)(?:의|에서의?)\s+(.+?)(?:와|과)\s+(.+?)(?:의|에서의?)\s+(.+?)(?:이|가)\s*(?:일치|같|동일|다른가|차이)"
    ),
    # "A와 B의 X가 같은가요?"
    re.compile(
        r"(.+?)(?:와|과)\s+(.+?)(?:의|에서의?)\s+(.+?)(?:이|가)\s*(?:일치|같|동일|다른가|차이)"
    ),
]


def _decompose_cross_validation(query: str) -> list[str] | None:
    """Decompose cross-document validation into per-source sub-queries.

    "회의록의 채용 계획과 로드맵의 채용 계획이 일치하나요?"
    → ["회의록의 채용 계획은?", "로드맵의 채용 계획은?", original]
    """
    for pattern in _CROSS_VALIDATION_PATTERNS:
        m = pattern.search(query)
        if m:
            groups = m.groups()
            if len(groups) == 4:
                source_a, topic_a, source_b, topic_b = groups
                sub_queries = [
                    f"{source_a}의 {topic_a}은?",
                    f"{source_b}의 {topic_b}은?",
                    query,
                ]
            elif len(groups) == 3:
                source_a, source_b, topic = groups
                sub_queries = [
                    f"{source_a}의 {topic}은?",
                    f"{source_b}의 {topic}은?",
                    query,
                ]
            else:
                continue

            logger.info(
                "cross_validation_decomposition",
                original=query,
                sub_queries=sub_queries,
            )
            return sub_queries
    return None
