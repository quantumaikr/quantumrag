"""Tests for batch query processing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from quantumrag.core.batch import BatchJob, BatchProcessor, BatchQuery, BatchStatus
from quantumrag.core.models import Confidence, QueryResult


def _make_mock_engine():
    engine = MagicMock()

    async def mock_aquery(query, **kwargs):
        return QueryResult(
            answer=f"Answer for: {query}",
            confidence=Confidence.STRONGLY_SUPPORTED,
            sources=[],
        )

    engine.aquery = AsyncMock(side_effect=mock_aquery)
    return engine


class TestBatchQuery:
    def test_auto_id(self) -> None:
        bq = BatchQuery(query="test")
        assert bq.query_id
        assert len(bq.query_id) == 8

    def test_explicit_id(self) -> None:
        bq = BatchQuery(query="test", query_id="custom-id")
        assert bq.query_id == "custom-id"


class TestBatchJob:
    def test_auto_id_and_total(self) -> None:
        queries = [BatchQuery(query=f"Q{i}") for i in range(5)]
        job = BatchJob(queries=queries)
        assert job.job_id
        assert job.total == 5
        assert job.status == BatchStatus.PENDING

    def test_summary(self) -> None:
        queries = [BatchQuery(query="Q1", result={"answer": "A1"})]
        job = BatchJob(queries=queries, status=BatchStatus.COMPLETED)
        job.progress = 1
        summary = job.summary()
        assert summary["total"] == 1
        assert summary["success"] == 1
        assert summary["errors"] == 0

    def test_error_count(self) -> None:
        queries = [
            BatchQuery(query="Q1", result={"answer": "A1"}),
            BatchQuery(query="Q2", error="failed"),
        ]
        job = BatchJob(queries=queries)
        assert job.success_count == 1
        assert job.error_count == 1


class TestBatchProcessor:
    def test_create_job_from_strings(self) -> None:
        engine = _make_mock_engine()
        processor = BatchProcessor(engine)
        job = processor.create_job(["Q1", "Q2", "Q3"])
        assert job.total == 3
        assert job.queries[0].query == "Q1"

    def test_create_job_from_dicts(self) -> None:
        engine = _make_mock_engine()
        processor = BatchProcessor(engine)
        job = processor.create_job([
            {"query": "Q1", "top_k": 5},
            {"query": "Q2", "filters": {"source": "doc1"}},
        ])
        assert job.total == 2
        assert job.queries[0].top_k == 5

    def test_run_batch(self) -> None:
        engine = _make_mock_engine()
        processor = BatchProcessor(engine)
        job = processor.create_job(["Q1", "Q2", "Q3"])
        result = asyncio.run(processor.run(job))

        assert result.status == BatchStatus.COMPLETED
        assert result.progress == 3
        assert result.success_count == 3
        assert all(q.result is not None for q in result.queries)

    def test_run_with_errors(self) -> None:
        engine = _make_mock_engine()

        call_count = 0

        async def failing_aquery(query, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("API error")
            return QueryResult(
                answer=f"Answer: {query}",
                confidence=Confidence.STRONGLY_SUPPORTED,
            )

        engine.aquery = AsyncMock(side_effect=failing_aquery)

        processor = BatchProcessor(engine)
        job = processor.create_job(["Q1", "Q2", "Q3"])
        result = asyncio.run(processor.run(job))

        assert result.status == BatchStatus.COMPLETED
        assert result.success_count == 2
        assert result.error_count == 1

    def test_get_job(self) -> None:
        engine = _make_mock_engine()
        processor = BatchProcessor(engine)
        job = processor.create_job(["Q1"])
        retrieved = processor.get_job(job.job_id)
        assert retrieved is not None
        assert retrieved.job_id == job.job_id

    def test_list_jobs(self) -> None:
        engine = _make_mock_engine()
        processor = BatchProcessor(engine)
        processor.create_job(["Q1"])
        processor.create_job(["Q2"])
        jobs = processor.list_jobs()
        assert len(jobs) == 2

    def test_cancel_job(self) -> None:
        engine = _make_mock_engine()
        processor = BatchProcessor(engine)
        job = processor.create_job(["Q1"])
        assert processor.cancel_job(job.job_id) is True
        assert job.status == BatchStatus.CANCELLED

    def test_cancel_completed_job(self) -> None:
        engine = _make_mock_engine()
        processor = BatchProcessor(engine)
        job = processor.create_job(["Q1"])
        job.status = BatchStatus.COMPLETED
        assert processor.cancel_job(job.job_id) is False

    def test_concurrency(self) -> None:
        engine = _make_mock_engine()
        processor = BatchProcessor(engine, default_concurrency=2)
        job = processor.create_job(["Q1", "Q2", "Q3", "Q4", "Q5"])
        assert job.concurrency == 2
        result = asyncio.run(processor.run(job))
        assert result.success_count == 5
