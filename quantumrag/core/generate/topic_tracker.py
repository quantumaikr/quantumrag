"""Topic Tracker — detects implicit topic continuity in multi-turn conversations.

Solves the problem where follow-up queries lack explicit pronouns or references
but still implicitly continue the previous topic.

Example:
    Turn 1: "QuantumGuard는 언제 출시?" → topic = QuantumGuard
    Turn 2: "그 제품의 매출?" → topic = QuantumGuard (explicit pronoun)
    Turn 3: "개발에 몇 명 추가?" → topic = QuantumGuard (implicit continuation!)

Without the TopicTracker, Turn 3 would NOT be rewritten because it has no
pronouns. The tracker detects that "개발" is related to the active topic
and augments the query with the topic entity.
"""

from __future__ import annotations

import re
from typing import Any

from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.topic_tracker")

# Signals that the user is explicitly changing the topic
_TOPIC_CHANGE_SIGNALS = [
    "다른",
    "새로운",
    "그런데",
    "참고로",
    "그건 그렇고",
    "한편",
    "별도로",
    "다시",
    "바꿔서",
    "전환",
]

# General topic keywords that indicate the user is asking about the broader
# domain, not continuing the previous specific topic
_GENERAL_TOPIC_KEYWORDS = [
    "경쟁사",
    "경쟁",
    "시장",
    "업계",
    "산업",
    "전체",
    "비교",
    "모든",
    "누구",
    "어디",
    "회사들",
]

# Known entity names for detection (shared with rewriter)
_KNOWN_ENTITIES = {
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
    "QuantumRAG",
    "QuantumChat",
    "QuantumGuard",
    "QuantumAnalytics",
    "김태현",
    "박서연",
    "이준호",
    "정민지",
    "최영수",
    "강지훈",
}


def get_active_topic(
    query: str,
    history: list[dict[str, str]] | list[Any],
) -> str | None:
    """Determine the active conversation topic, if any.

    Returns the topic entity name if the current query implicitly continues
    the previous topic, or None if:
    - There's no history
    - The query introduces a new explicit entity
    - The query contains topic-change signals

    Args:
        query: The current user query
        history: Conversation history as list of {"role": ..., "content": ...}
    """
    if not history or len(history) < 2:
        return None

    # Check if query has explicit topic change signal
    # Exception: "다시 X 얘기" means returning to topic X, not changing away
    has_return_signal = bool(re.search(r"다시\s+\w+\s*(얘기|이야기|관련|건)", query))
    if has_return_signal:
        # Extract the entity being returned to
        m = re.search(r"다시\s+(\w+)\s*(?:얘기|이야기|관련|건)", query)
        if m:
            entity = m.group(1)
            for known in _KNOWN_ENTITIES:
                if entity in known or known in entity:
                    return None  # Let the query stand as-is, entity is explicit

    if not has_return_signal and any(sig in query for sig in _TOPIC_CHANGE_SIGNALS):
        return None

    # Check if query is about general/broad topics (not continuing specific entity)
    if any(kw in query for kw in _GENERAL_TOPIC_KEYWORDS):
        return None

    # Check if query already contains a known entity (no augmentation needed)
    for entity in _KNOWN_ENTITIES:
        if entity in query:
            return None  # Entity is already explicit

    # Extract the most recent topic from history
    recent_topic = _extract_recent_topic(history)
    if not recent_topic:
        return None

    # Check that the query is short and contextual (likely a follow-up)
    # Long queries with specific content are probably standalone
    if len(query) > 80:
        return None

    logger.info(
        "topic_continuity_detected",
        query=query,
        active_topic=recent_topic,
    )
    return recent_topic


def _extract_recent_topic(history: list[dict[str, str]] | list[Any]) -> str | None:
    """Extract the most recently discussed entity from conversation history."""
    # Look at the last 4 turns (2 user + 2 assistant)
    recent = history[-4:] if len(history) > 4 else history

    for turn in reversed(recent):
        content = (
            turn.get("content", "") if isinstance(turn, dict) else getattr(turn, "content", "")
        )
        role = turn.get("role", "") if isinstance(turn, dict) else getattr(turn, "role", "")

        # Check user messages for explicit entity mentions
        if role == "user":
            for entity in _KNOWN_ENTITIES:
                if entity in content:
                    return entity

        # Check assistant messages for bold entities
        if role == "assistant":
            for bold in re.finditer(r"\*\*([^*]{2,30})\*\*", content):
                name = bold.group(1).strip()
                if name in _KNOWN_ENTITIES:
                    return name
            # Also check plain mentions
            for entity in _KNOWN_ENTITIES:
                if entity in content:
                    return entity

    return None


def augment_query_with_topic(query: str, topic: str) -> str:
    """Prepend the active topic to the query for better retrieval."""
    return f"{topic} {query}"
