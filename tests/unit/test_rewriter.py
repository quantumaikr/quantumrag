"""Tests for conversational query rewriting."""

from __future__ import annotations

import pytest

from quantumrag.core.generate.rewriter import ConversationTurn, QueryRewriter


class TestConversationTurn:
    def test_creation(self) -> None:
        turn = ConversationTurn(role="user", content="Hello")
        assert turn.role == "user"
        assert turn.content == "Hello"

    def test_frozen(self) -> None:
        turn = ConversationTurn(role="user", content="Hello")
        with pytest.raises(AttributeError):
            turn.role = "assistant"  # type: ignore[misc]


class TestQueryRewriterSingleTurn:
    """No rewriting should happen when history is empty or single-turn."""

    @pytest.mark.asyncio
    async def test_empty_history(self) -> None:
        rewriter = QueryRewriter()
        result = await rewriter.rewrite("What is Python?", history=None)
        assert result == "What is Python?"

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        rewriter = QueryRewriter()
        result = await rewriter.rewrite("What is Python?", history=[])
        assert result == "What is Python?"

    @pytest.mark.asyncio
    async def test_single_user_turn(self) -> None:
        rewriter = QueryRewriter()
        history = [ConversationTurn(role="user", content="Hello")]
        result = await rewriter.rewrite("What is Python?", history=history)
        assert result == "What is Python?"


class TestHeuristicRewriting:
    """Pronoun resolution via heuristic fallback."""

    @pytest.mark.asyncio
    async def test_english_pronoun_it(self) -> None:
        rewriter = QueryRewriter()
        history = [
            ConversationTurn(role="user", content="Tell me about Python"),
            ConversationTurn(role="assistant", content="Python is a programming language."),
        ]
        result = await rewriter.rewrite("What are its main features?", history=history)
        assert "Python" in result
        assert "its" not in result.lower().split()

    @pytest.mark.asyncio
    async def test_english_pronoun_this(self) -> None:
        rewriter = QueryRewriter()
        history = [
            ConversationTurn(role="user", content="Tell me about TensorFlow"),
            ConversationTurn(role="assistant", content="TensorFlow is a ML framework."),
        ]
        result = await rewriter.rewrite("How does this compare to PyTorch?", history=history)
        assert "TensorFlow" in result

    @pytest.mark.asyncio
    async def test_english_pronoun_that(self) -> None:
        rewriter = QueryRewriter()
        history = [
            ConversationTurn(role="user", content="Tell me about React"),
            ConversationTurn(role="assistant", content="React is a UI library."),
        ]
        result = await rewriter.rewrite("Who created that?", history=history)
        assert "React" in result

    @pytest.mark.asyncio
    async def test_english_pronoun_they(self) -> None:
        rewriter = QueryRewriter()
        history = [
            ConversationTurn(role="user", content="Tell me about microservices"),
            ConversationTurn(role="assistant", content="Microservices are..."),
        ]
        result = await rewriter.rewrite("How do they communicate?", history=history)
        assert "microservices" in result

    @pytest.mark.asyncio
    async def test_no_rewriting_without_pronouns(self) -> None:
        rewriter = QueryRewriter()
        history = [
            ConversationTurn(role="user", content="Tell me about Python"),
            ConversationTurn(role="assistant", content="Python is a programming language."),
        ]
        result = await rewriter.rewrite("What is Java?", history=history)
        assert result == "What is Java?"


class TestKoreanPronounResolution:
    """Korean pronoun/demonstrative resolution."""

    @pytest.mark.asyncio
    async def test_korean_geugeot(self) -> None:
        rewriter = QueryRewriter()
        history = [
            ConversationTurn(role="user", content="Tell me about 양자 컴퓨팅"),
            ConversationTurn(role="assistant", content="양자 컴퓨팅은..."),
        ]
        result = await rewriter.rewrite("그것의 장점은?", history=history)
        assert "양자 컴퓨팅" in result

    @pytest.mark.asyncio
    async def test_korean_igeot(self) -> None:
        rewriter = QueryRewriter()
        history = [
            ConversationTurn(role="user", content="Tell me about 머신러닝"),
            ConversationTurn(role="assistant", content="머신러닝은..."),
        ]
        result = await rewriter.rewrite("이것은 어떻게 작동하나요?", history=history)
        assert "머신러닝" in result

    @pytest.mark.asyncio
    async def test_korean_geogi(self) -> None:
        rewriter = QueryRewriter()
        history = [
            ConversationTurn(role="user", content="Tell me about 서울"),
            ConversationTurn(role="assistant", content="서울은 한국의 수도입니다."),
        ]
        result = await rewriter.rewrite("거기 날씨는 어때?", history=history)
        assert "서울" in result


class TestMaxHistoryTruncation:
    """Ensure conversation history is truncated to max_turns."""

    @pytest.mark.asyncio
    async def test_truncation_default(self) -> None:
        rewriter = QueryRewriter(max_turns=2)
        # Build 6 turns (3 pairs) -- only last 4 (2*2) should be used
        history = [
            ConversationTurn(role="user", content="Tell me about Django"),
            ConversationTurn(role="assistant", content="Django is a web framework."),
            ConversationTurn(role="user", content="Tell me about Flask"),
            ConversationTurn(role="assistant", content="Flask is a micro framework."),
            ConversationTurn(role="user", content="Tell me about FastAPI"),
            ConversationTurn(role="assistant", content="FastAPI is an async framework."),
        ]
        # "it" should resolve to FastAPI (most recent user turn in truncated window)
        result = await rewriter.rewrite("How fast is it?", history=history)
        assert "FastAPI" in result

    @pytest.mark.asyncio
    async def test_max_turns_one(self) -> None:
        rewriter = QueryRewriter(max_turns=1)
        history = [
            ConversationTurn(role="user", content="Tell me about Rust"),
            ConversationTurn(role="assistant", content="Rust is a systems language."),
            ConversationTurn(role="user", content="Tell me about Go"),
            ConversationTurn(role="assistant", content="Go is a compiled language."),
        ]
        # With max_turns=1, only the last 2 turns are kept
        result = await rewriter.rewrite("Is it memory-safe?", history=history)
        assert "Go" in result

    @pytest.mark.asyncio
    async def test_custom_max_turns(self) -> None:
        rewriter = QueryRewriter(max_turns=10)
        assert rewriter.max_turns == 10


class TestNeedsRewriting:
    """Test the _needs_rewriting detection method."""

    def test_detects_english_pronoun(self) -> None:
        rewriter = QueryRewriter()
        assert rewriter._needs_rewriting("What is it?") is True
        assert rewriter._needs_rewriting("Tell me about this") is True
        assert rewriter._needs_rewriting("How do they work?") is True

    def test_detects_korean_pronoun(self) -> None:
        rewriter = QueryRewriter()
        assert rewriter._needs_rewriting("그것의 장점은?") is True
        assert rewriter._needs_rewriting("이것은 뭐야?") is True
        assert rewriter._needs_rewriting("거기 날씨는?") is True

    def test_no_pronouns(self) -> None:
        rewriter = QueryRewriter()
        assert rewriter._needs_rewriting("What is Python?") is False
        assert rewriter._needs_rewriting("Explain quantum computing") is False
