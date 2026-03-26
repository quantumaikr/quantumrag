"""Tests for slow retrieval monitoring, slow_retrieval trace flag, and CLI cost command."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from typer.testing import CliRunner

from quantumrag.cli.main import app
from quantumrag.core.models import Chunk
from quantumrag.core.retrieve.fusion import ScoredChunk
from quantumrag.core.retrieve.retriever import Retriever

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scored_chunks(n: int = 3) -> list[ScoredChunk]:
    """Create a list of dummy ScoredChunk objects."""
    chunks: list[ScoredChunk] = []
    for i in range(n):
        chunk = Chunk(
            id=f"chunk-{i}",
            content=f"Content of chunk {i}",
            document_id="doc-1",
            chunk_index=i,
            metadata={"title": f"Doc {i}", "page": i + 1},
        )
        chunks.append(ScoredChunk(chunk=chunk, score=0.9 - i * 0.1))
    return chunks


def _make_fusion_retriever(
    latency_seconds: float = 0.0,
    result_count: int = 3,
) -> MagicMock:
    """Create a mock FusionRetriever whose search takes *latency_seconds*."""
    import asyncio
    import time

    scored = _make_scored_chunks(result_count)
    fusion = MagicMock()

    async def _slow_search(*_args: Any, **_kwargs: Any) -> list[ScoredChunk]:
        if latency_seconds > 0:
            # Busy-wait so that perf_counter advances even without real I/O.
            end = time.perf_counter() + latency_seconds
            while time.perf_counter() < end:
                await asyncio.sleep(0)
        return scored

    fusion.search = AsyncMock(side_effect=_slow_search)
    return fusion


# ---------------------------------------------------------------------------
# Test: Slow retrieval WARNING logged when threshold exceeded
# ---------------------------------------------------------------------------


class TestSlowRetrievalWarning:
    @pytest.mark.asyncio
    async def test_warning_logged_when_threshold_exceeded(self) -> None:
        """A slow retrieval trace step should be recorded when threshold exceeded."""
        fusion = _make_fusion_retriever(latency_seconds=0.05)
        retriever = Retriever(
            fusion_retriever=fusion,
            enable_rerank=False,
            enable_compression=False,
            slow_threshold_ms=10,  # very low threshold so the test triggers it
        )

        result = await retriever.retrieve("test query", top_k=3)

        # Verify the trace contains a slow_retrieval step (which also triggers the log)
        slow_steps = [s for s in result.trace if s.step == "slow_retrieval"]
        assert len(slow_steps) == 1
        assert slow_steps[0].details.get("slow_retrieval") is True

    @pytest.mark.asyncio
    async def test_no_warning_when_under_threshold(self) -> None:
        """No slow_retrieval trace step when retrieval completes within threshold."""
        fusion = _make_fusion_retriever(latency_seconds=0.0)
        retriever = Retriever(
            fusion_retriever=fusion,
            enable_rerank=False,
            enable_compression=False,
            slow_threshold_ms=999_999,  # very high threshold
        )

        result = await retriever.retrieve("fast query", top_k=3)

        slow_steps = [s for s in result.trace if s.step == "slow_retrieval"]
        assert len(slow_steps) == 0


# ---------------------------------------------------------------------------
# Test: slow_retrieval flag in trace details
# ---------------------------------------------------------------------------


class TestSlowRetrievalTraceFlag:
    @pytest.mark.asyncio
    async def test_slow_retrieval_flag_present_when_slow(self) -> None:
        """The trace should contain a step with slow_retrieval: True in details."""
        fusion = _make_fusion_retriever(latency_seconds=0.05)
        retriever = Retriever(
            fusion_retriever=fusion,
            enable_rerank=False,
            enable_compression=False,
            slow_threshold_ms=10,
        )

        result = await retriever.retrieve("slow query", top_k=3)

        slow_steps = [s for s in result.trace if s.details.get("slow_retrieval") is True]
        assert len(slow_steps) == 1, "Expected exactly one trace step with slow_retrieval flag"
        assert slow_steps[0].step == "slow_retrieval"

    @pytest.mark.asyncio
    async def test_slow_retrieval_flag_absent_when_fast(self) -> None:
        """No slow_retrieval flag should appear for fast retrievals."""
        fusion = _make_fusion_retriever(latency_seconds=0.0)
        retriever = Retriever(
            fusion_retriever=fusion,
            enable_rerank=False,
            enable_compression=False,
            slow_threshold_ms=999_999,
        )

        result = await retriever.retrieve("fast query", top_k=3)

        slow_steps = [s for s in result.trace if s.details.get("slow_retrieval") is True]
        assert len(slow_steps) == 0, "No slow_retrieval flag expected for fast retrieval"


# ---------------------------------------------------------------------------
# Test: CLI cost command
# ---------------------------------------------------------------------------

runner = CliRunner()


class TestCLICostCommand:
    def test_cost_no_data(self, tmp_path: Path) -> None:
        """When no budget database exists, the command should say so gracefully."""
        config_path = tmp_path / "quantumrag.yaml"
        # Write a minimal config pointing data_dir to a nonexistent place
        config_path.write_text(
            f'storage:\n  data_dir: "{tmp_path / "empty_data"}"\n',
            encoding="utf-8",
        )
        result = runner.invoke(app, ["cost", "--config", str(config_path)])
        assert result.exit_code == 0
        assert "No cost data found" in result.output

    def test_cost_with_data(self, tmp_path: Path) -> None:
        """When budget data exists, the command should show a formatted table."""
        from quantumrag.core.observability.tracer import BudgetManager

        data_dir = tmp_path / "qr_data"
        data_dir.mkdir()
        db_path = data_dir / "budget.db"

        # Seed some cost records
        manager = BudgetManager(db_path=db_path, daily_limit=5.0, monthly_limit=50.0)
        manager.record_cost(0.0123)
        manager.record_cost(0.0456)

        config_path = tmp_path / "quantumrag.yaml"
        config_path.write_text(
            (
                f'storage:\n  data_dir: "{data_dir}"\n'
                "cost:\n  budget_daily: 5.0\n  budget_monthly: 50.0\n"
            ),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["cost", "--config", str(config_path)])
        assert result.exit_code == 0
        assert "Cost Summary" in result.output
        assert "Daily" in result.output
        assert "Monthly" in result.output
        # The spent column should show the combined cost
        assert "$0.0579" in result.output
        # Budget limits should appear
        assert "$5.0000" in result.output
        assert "$50.0000" in result.output

    def test_cost_unlimited_budget(self, tmp_path: Path) -> None:
        """When no budget limits are set, the command should show 'unlimited'."""
        from quantumrag.core.observability.tracer import BudgetManager

        data_dir = tmp_path / "qr_data"
        data_dir.mkdir()
        db_path = data_dir / "budget.db"

        manager = BudgetManager(db_path=db_path)
        manager.record_cost(0.01)

        config_path = tmp_path / "quantumrag.yaml"
        config_path.write_text(
            f'storage:\n  data_dir: "{data_dir}"\n',
            encoding="utf-8",
        )

        result = runner.invoke(app, ["cost", "--config", str(config_path)])
        assert result.exit_code == 0
        assert "unlimited" in result.output
