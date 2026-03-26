"""Batch query processing — run many queries asynchronously."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from quantumrag.core.logging import get_logger

logger = get_logger(__name__)


class BatchStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchQuery:
    """A single query in a batch."""

    query: str
    query_id: str = ""
    filters: dict[str, Any] | None = None
    top_k: int | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: float = 0.0

    def __post_init__(self) -> None:
        if not self.query_id:
            self.query_id = uuid.uuid4().hex[:8]


@dataclass
class BatchJob:
    """A batch of queries to process."""

    job_id: str = ""
    queries: list[BatchQuery] = field(default_factory=list)
    status: BatchStatus = BatchStatus.PENDING
    created_at: float = 0.0
    completed_at: float = 0.0
    concurrency: int = 5
    progress: int = 0
    total: int = 0

    def __post_init__(self) -> None:
        if not self.job_id:
            self.job_id = uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = time.time()
        self.total = len(self.queries)

    @property
    def success_count(self) -> int:
        return sum(1 for q in self.queries if q.result and not q.error)

    @property
    def error_count(self) -> int:
        return sum(1 for q in self.queries if q.error)

    @property
    def elapsed_seconds(self) -> float:
        end = self.completed_at or time.time()
        return end - self.created_at

    def summary(self) -> dict[str, Any]:
        latencies = [q.latency_ms for q in self.queries if q.latency_ms > 0]
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "total": self.total,
            "completed": self.progress,
            "success": self.success_count,
            "errors": self.error_count,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "avg_latency_ms": (
                round(sum(latencies) / len(latencies), 1) if latencies else 0
            ),
        }


class BatchProcessor:
    """Process batches of queries with controlled concurrency.

    Usage::

        processor = BatchProcessor(engine)
        job = processor.create_job([
            "What is the revenue?",
            "Who is the CEO?",
            "What are the risks?",
        ])
        result = await processor.run(job)
    """

    def __init__(self, engine: Any, default_concurrency: int = 5) -> None:
        self._engine = engine
        self._default_concurrency = default_concurrency
        self._jobs: dict[str, BatchJob] = {}

    def create_job(
        self,
        queries: list[str] | list[dict[str, Any]],
        concurrency: int | None = None,
    ) -> BatchJob:
        """Create a new batch job from a list of queries."""
        batch_queries: list[BatchQuery] = []
        for q in queries:
            if isinstance(q, str):
                batch_queries.append(BatchQuery(query=q))
            elif isinstance(q, dict):
                batch_queries.append(
                    BatchQuery(
                        query=q["query"],
                        filters=q.get("filters"),
                        top_k=q.get("top_k"),
                    )
                )

        job = BatchJob(
            queries=batch_queries,
            concurrency=concurrency or self._default_concurrency,
        )
        self._jobs[job.job_id] = job
        logger.info("batch_job_created", job_id=job.job_id, queries=len(batch_queries))
        return job

    async def run(self, job: BatchJob) -> BatchJob:
        """Execute a batch job with concurrency control."""
        job.status = BatchStatus.RUNNING
        semaphore = asyncio.Semaphore(job.concurrency)

        async def process_query(bq: BatchQuery) -> None:
            async with semaphore:
                t0 = time.perf_counter()
                try:
                    result = await self._engine.aquery(
                        bq.query,
                        filters=bq.filters,
                        top_k=bq.top_k,
                    )
                    bq.result = {
                        "answer": result.answer,
                        "confidence": result.confidence.value if hasattr(result.confidence, "value") else str(result.confidence),
                        "sources": [
                            {"document": s.document, "excerpt": s.excerpt[:200]}
                            for s in result.sources
                        ] if result.sources else [],
                    }
                except Exception as e:
                    bq.error = str(e)
                    logger.warning(
                        "batch_query_failed",
                        query_id=bq.query_id,
                        error=str(e),
                    )
                finally:
                    bq.latency_ms = (time.perf_counter() - t0) * 1000
                    job.progress += 1

        try:
            await asyncio.gather(
                *(process_query(q) for q in job.queries),
                return_exceptions=True,
            )
            job.status = BatchStatus.COMPLETED
        except Exception:
            job.status = BatchStatus.FAILED
        finally:
            job.completed_at = time.time()

        logger.info("batch_job_complete", **job.summary())
        return job

    def get_job(self, job_id: str) -> BatchJob | None:
        """Get a batch job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all batch jobs with summaries."""
        return [job.summary() for job in self._jobs.values()]

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or running job."""
        job = self._jobs.get(job_id)
        if not job or job.status in (BatchStatus.COMPLETED, BatchStatus.CANCELLED):
            return False
        job.status = BatchStatus.CANCELLED
        return True
