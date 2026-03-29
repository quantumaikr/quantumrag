"""Tests for Cohere/Jina rerankers and BudgetManager."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantumrag.core.errors import BudgetExceededError
from quantumrag.core.models import Chunk
from quantumrag.core.observability.tracer import BudgetManager
from quantumrag.core.retrieve.fusion import ScoredChunk
from quantumrag.core.retrieve.reranker import (
    CohereReranker,
    JinaReranker,
    create_reranker,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunks(n: int = 5) -> list[ScoredChunk]:
    """Create *n* dummy scored chunks."""
    return [
        ScoredChunk(
            chunk=Chunk(
                id=f"chunk-{i}",
                content=f"Content of chunk {i}",
                document_id="doc-1",
                chunk_index=i,
            ),
            score=1.0 - i * 0.1,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# CohereReranker
# ---------------------------------------------------------------------------


class TestCohereReranker:
    @pytest.mark.asyncio
    async def test_rerank_calls_api_and_returns_reranked(self) -> None:
        chunks = _make_chunks(4)

        # Simulate cohere response: reverse order, with relevance scores
        mock_result_0 = SimpleNamespace(index=3, relevance_score=0.95)
        mock_result_1 = SimpleNamespace(index=1, relevance_score=0.80)
        mock_response = SimpleNamespace(results=[mock_result_0, mock_result_1])

        mock_client = MagicMock()
        mock_client.rerank.return_value = mock_response

        reranker = CohereReranker(api_key="test-key", model="rerank-v3.5")
        reranker._client = mock_client  # inject mock

        result = await reranker.rerank("test query", chunks, top_k=2)

        assert len(result) == 2
        assert result[0].chunk.id == "chunk-3"
        # Score is blended: 0.7 * reranker_score + 0.3 * original_score
        # chunk-3 original=0.7, reranker=0.95 → 0.7*0.95 + 0.3*0.7 = 0.875
        assert result[0].score == pytest.approx(0.875)
        assert result[1].chunk.id == "chunk-1"

        mock_client.rerank.assert_called_once()
        call_kwargs = mock_client.rerank.call_args
        assert call_kwargs.kwargs["query"] == "test query"
        assert call_kwargs.kwargs["model"] == "rerank-v3.5"

    @pytest.mark.asyncio
    async def test_fallback_on_api_error(self) -> None:
        chunks = _make_chunks(4)

        mock_client = MagicMock()
        mock_client.rerank.side_effect = RuntimeError("API down")

        reranker = CohereReranker(api_key="test-key")
        reranker._client = mock_client

        result = await reranker.rerank("query", chunks, top_k=2)

        # Should fall back to original order, sliced to top_k
        assert len(result) == 2
        assert result[0].chunk.id == "chunk-0"
        assert result[1].chunk.id == "chunk-1"

    @pytest.mark.asyncio
    async def test_fallback_when_cohere_not_installed(self) -> None:
        chunks = _make_chunks(3)
        reranker = CohereReranker(api_key="test-key")

        with patch.dict("sys.modules", {"cohere": None}):
            reranker._client = None  # reset so _ensure_client re-imports
            result = await reranker.rerank("q", chunks, top_k=2)

        assert len(result) == 2
        assert result[0].chunk.id == "chunk-0"


# ---------------------------------------------------------------------------
# JinaReranker
# ---------------------------------------------------------------------------


class TestJinaReranker:
    @pytest.mark.asyncio
    async def test_rerank_calls_api_and_returns_reranked(self) -> None:
        chunks = _make_chunks(4)

        jina_response_json = {
            "results": [
                {"index": 2, "relevance_score": 0.99},
                {"index": 0, "relevance_score": 0.75},
            ]
        }

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = jina_response_json

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            reranker = JinaReranker(api_key="jina-key", model="jina-reranker-v2-base-multilingual")
            result = await reranker.rerank("test query", chunks, top_k=2)

        assert len(result) == 2
        assert result[0].chunk.id == "chunk-2"
        # Blended: 0.7 * 0.99 + 0.3 * 0.8 = 0.933
        assert result[0].score == pytest.approx(0.933)
        assert result[1].chunk.id == "chunk-0"

    @pytest.mark.asyncio
    async def test_fallback_on_http_error(self) -> None:
        chunks = _make_chunks(4)

        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = RuntimeError("Connection refused")
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            reranker = JinaReranker(api_key="jina-key")
            result = await reranker.rerank("query", chunks, top_k=2)

        assert len(result) == 2
        assert result[0].chunk.id == "chunk-0"

    @pytest.mark.asyncio
    async def test_fallback_when_httpx_not_installed(self) -> None:
        chunks = _make_chunks(3)
        reranker = JinaReranker(api_key="jina-key")

        with patch.dict("sys.modules", {"httpx": None}):
            result = await reranker.rerank("q", chunks, top_k=2)

        assert len(result) == 2
        assert result[0].chunk.id == "chunk-0"


# ---------------------------------------------------------------------------
# create_reranker factory
# ---------------------------------------------------------------------------


class TestCreateReranker:
    def test_flashrank(self) -> None:
        r = create_reranker("flashrank")
        assert type(r).__name__ == "FlashRankReranker"

    def test_cohere(self) -> None:
        r = create_reranker("cohere", api_key="ck")
        assert type(r).__name__ == "CohereReranker"

    def test_jina(self) -> None:
        r = create_reranker("jina", api_key="jk")
        assert type(r).__name__ == "JinaReranker"

    def test_unknown_falls_back_to_noop(self) -> None:
        r = create_reranker("unknown_provider")
        assert type(r).__name__ == "NoopReranker"


# ---------------------------------------------------------------------------
# BudgetManager
# ---------------------------------------------------------------------------


class TestBudgetManager:
    def test_daily_limit_raises(self, tmp_path: Path) -> None:
        mgr = BudgetManager(db_path=tmp_path / "budget.db", daily_limit=1.00)

        mgr.record_cost(0.60)
        mgr.check_budget()  # still under

        mgr.record_cost(0.50)
        with pytest.raises(BudgetExceededError, match="Daily budget exceeded"):
            mgr.check_budget()

    def test_monthly_limit_raises(self, tmp_path: Path) -> None:
        mgr = BudgetManager(db_path=tmp_path / "budget.db", monthly_limit=5.00)

        mgr.record_cost(4.00)
        mgr.check_budget()  # under

        mgr.record_cost(1.50)
        with pytest.raises(BudgetExceededError, match="Monthly budget exceeded"):
            mgr.check_budget()

    def test_no_limit_never_raises(self, tmp_path: Path) -> None:
        mgr = BudgetManager(db_path=tmp_path / "budget.db")
        mgr.record_cost(999.99)
        mgr.check_budget()  # should not raise

    def test_usage_summary(self, tmp_path: Path) -> None:
        mgr = BudgetManager(db_path=tmp_path / "budget.db", daily_limit=10.0, monthly_limit=100.0)
        mgr.record_cost(2.50)
        mgr.record_cost(1.25)

        summary = mgr.get_usage_summary()
        assert summary["daily_total"] == pytest.approx(3.75)
        assert summary["monthly_total"] == pytest.approx(3.75)
        assert summary["daily_limit"] == 10.0
        assert summary["monthly_limit"] == 100.0
        assert summary["daily_remaining"] == pytest.approx(6.25)
        assert summary["monthly_remaining"] == pytest.approx(96.25)

    def test_persistence_across_instances(self, tmp_path: Path) -> None:
        db = tmp_path / "budget.db"

        mgr1 = BudgetManager(db_path=db, daily_limit=5.0)
        mgr1.record_cost(2.00)

        # New instance pointing at the same DB
        mgr2 = BudgetManager(db_path=db, daily_limit=5.0)
        summary = mgr2.get_usage_summary()
        assert summary["daily_total"] == pytest.approx(2.00)

        mgr2.record_cost(3.50)
        with pytest.raises(BudgetExceededError):
            mgr2.check_budget()

    def test_budget_exceeded_error_attributes(self, tmp_path: Path) -> None:
        mgr = BudgetManager(db_path=tmp_path / "budget.db", daily_limit=0.50)
        mgr.record_cost(0.60)

        with pytest.raises(BudgetExceededError) as exc_info:
            mgr.check_budget()

        err = exc_info.value
        assert err.period == "daily"
        assert err.limit == 0.50
        assert err.current_spend >= 0.60
