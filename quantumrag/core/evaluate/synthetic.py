"""Synthetic QA pair generation from indexed documents."""

from __future__ import annotations

import enum
import random
import re
from typing import Any

from quantumrag.core.evaluate.models import QAPair
from quantumrag.core.models import Chunk
from quantumrag.core.utils.text import has_korean as _has_korean
from quantumrag.core.utils.text import split_sentences


class Difficulty(enum.Enum):
    """Difficulty levels for synthetic QA generation."""

    EASY = "easy"        # Factual, single-hop questions
    MEDIUM = "medium"    # Multi-hop questions requiring info from multiple sentences
    HARD = "hard"        # Reasoning/aggregation questions


class SyntheticGenerator:
    """Generate Q&A pairs from indexed documents for evaluation."""

    def __init__(self, llm_provider: Any = None) -> None:
        self._llm = llm_provider

    async def generate(
        self,
        chunks: list[Chunk],
        count: int = 20,
        difficulty: Difficulty | None = None,
    ) -> list[QAPair]:
        """Generate Q&A pairs from chunks using LLM or template-based fallback.

        Args:
            chunks: Source chunks to generate questions from.
            count: Number of QA pairs to generate.
            difficulty: Optional difficulty filter (EASY, MEDIUM, HARD).
                If None, generates a mix of all difficulties.
        """
        if self._llm is not None:
            try:
                return await self._llm_generate(chunks, count)
            except Exception:
                pass
        return self._template_generate(chunks, count, difficulty=difficulty)

    async def _llm_generate(self, chunks: list[Chunk], count: int) -> list[QAPair]:
        """LLM-based generation for higher quality QA pairs."""
        pairs: list[QAPair] = []
        chunks_to_use = _select_diverse_chunks(chunks, count)

        for chunk in chunks_to_use:
            if len(pairs) >= count:
                break
            prompt = (
                "Given the following text, generate a factual question and its answer. "
                "Respond in the format:\nQuestion: <question>\nAnswer: <answer>\n\n"
                f"Text: {chunk.content[:1000]}"
            )
            response = await self._llm.generate(prompt)
            qa = _parse_llm_response(response, chunk.id)
            if qa:
                pairs.append(qa)

        return pairs[:count]

    def _template_generate(
        self,
        chunks: list[Chunk],
        count: int,
        difficulty: Difficulty | None = None,
    ) -> list[QAPair]:
        """Template-based generation (no LLM needed, free)."""
        pairs: list[QAPair] = []
        chunks_to_use = _select_diverse_chunks(chunks, count)

        for chunk in chunks_to_use:
            if len(pairs) >= count:
                break

            generated = _generate_from_chunk(chunk, difficulty=difficulty)
            pairs.extend(generated)

        return pairs[:count]


def _select_diverse_chunks(chunks: list[Chunk], count: int) -> list[Chunk]:
    """Select a diverse set of chunks, preferring longer content."""
    if not chunks:
        return []
    sorted_chunks = sorted(chunks, key=lambda c: len(c.content), reverse=True)
    # Take more chunks than needed to allow for failed generation
    selected = sorted_chunks[: count * 2]
    random.shuffle(selected)
    return selected


def _generate_from_chunk(
    chunk: Chunk, difficulty: Difficulty | None = None
) -> list[QAPair]:
    """Generate QA pairs from a single chunk using templates.

    Args:
        chunk: Source chunk to generate questions from.
        difficulty: Optional difficulty filter. If None, generates all levels.
    """
    pairs: list[QAPair] = []
    content = chunk.content.strip()
    if not content:
        return pairs

    sentences = split_sentences(content)
    if not sentences:
        return pairs

    is_korean = _has_korean(content)

    # --- EASY: Factual, single-hop questions ---
    if difficulty is None or difficulty == Difficulty.EASY:
        # Strategy 1: "What" question from first meaningful sentence
        for sent in sentences:
            sent = sent.strip()
            if len(sent) > 20:
                topic = _extract_topic(sent)
                if is_korean:
                    question = random.choice([
                        f"{topic}에 대해 문서에서 무엇이라고 설명하나요?",
                        f"{topic}에 관한 내용은 무엇인가요?",
                        f"{topic}에 대해 알려주세요.",
                    ])
                else:
                    question = f"What does the document say about: {topic}?"
                pairs.append(QAPair(
                    question=question,
                    expected_answer=sent,
                    source_chunk_id=chunk.id,
                    metadata={"strategy": "topic_question", "difficulty": Difficulty.EASY.value},
                ))
                break

        # Strategy 2: Factual question if numbers or named entities are present
        for sent in sentences:
            numbers = re.findall(r'\b\d+(?:\.\d+)?%?\b', sent)
            if numbers and len(sent) > 20:
                topic = _extract_topic(sent)
                if is_korean:
                    question = random.choice([
                        f"{topic}와 관련된 주요 수치는 무엇인가요?",
                        f"{topic}에서 언급된 숫자나 값을 알려주세요.",
                    ])
                else:
                    question = f"What are the key figures or values mentioned regarding: {topic}?"
                pairs.append(QAPair(
                    question=question,
                    expected_answer=sent,
                    source_chunk_id=chunk.id,
                    metadata={"strategy": "factual_question", "difficulty": Difficulty.EASY.value},
                ))
                break

    # --- MEDIUM: Multi-hop questions requiring multiple sentences ---
    if (difficulty is None or difficulty == Difficulty.MEDIUM) and len(sentences) >= 2:
            # Combine two sentences for a multi-hop question
            sent_a = sentences[0].strip()
            sent_b = sentences[-1].strip()
            if len(sent_a) > 20 and len(sent_b) > 20:
                topic_a = _extract_topic(sent_a)
                topic_b = _extract_topic(sent_b)
                if is_korean:
                    question = f"{topic_a}와(과) {topic_b}의 관계는 무엇인가요?"
                else:
                    question = f"What is the relationship between {topic_a} and {topic_b}?"
                pairs.append(QAPair(
                    question=question,
                    expected_answer=f"{sent_a} {sent_b}",
                    source_chunk_id=chunk.id,
                    metadata={"strategy": "multi_hop_question", "difficulty": Difficulty.MEDIUM.value},
                ))

    # --- HARD: Reasoning/aggregation questions ---
    if (difficulty is None or difficulty == Difficulty.HARD) and len(sentences) >= 2:
            longest = max(sentences, key=len)
            if len(longest) > 30:
                topic = _extract_topic(longest)
                if is_korean:
                    question = random.choice([
                        f"{topic}에 대한 내용을 종합적으로 요약해 주세요.",
                        f"{topic}에서 도출할 수 있는 결론은 무엇인가요?",
                    ])
                else:
                    question = random.choice([
                        f"Can you summarize the information about: {topic}?",
                        f"What conclusions can be drawn about: {topic}?",
                    ])
                pairs.append(QAPair(
                    question=question,
                    expected_answer=longest.strip(),
                    source_chunk_id=chunk.id,
                    metadata={"strategy": "reasoning_question", "difficulty": Difficulty.HARD.value},
                ))

    return pairs


def _extract_topic(sentence: str) -> str:
    """Extract a rough topic from a sentence (first N meaningful words)."""
    words = sentence.split()
    # Remove common stop words from the start
    stop_words = {"the", "a", "an", "this", "that", "these", "those", "is", "are", "was", "were"}
    meaningful = [w for w in words if w.lower().strip(",.!?;:") not in stop_words]
    topic_words = meaningful[:5]
    if not topic_words:
        topic_words = words[:5]
    return " ".join(topic_words)


def _parse_llm_response(response: str, chunk_id: str) -> QAPair | None:
    """Parse LLM response into a QAPair."""
    q_match = re.search(r'[Qq]uestion:\s*(.+?)(?:\n|$)', response)
    a_match = re.search(r'[Aa]nswer:\s*(.+?)(?:\n|$)', response)
    if q_match and a_match:
        return QAPair(
            question=q_match.group(1).strip(),
            expected_answer=a_match.group(1).strip(),
            source_chunk_id=chunk_id,
            metadata={"strategy": "llm_generated"},
        )
    return None
