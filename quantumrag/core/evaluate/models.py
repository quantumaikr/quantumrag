"""Data models for the evaluation system."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QAPair:
    """A question-answer pair for evaluation."""

    question: str
    expected_answer: str
    source_chunk_id: str | None = None
    metadata: dict = field(default_factory=dict)
