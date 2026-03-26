"""Query tracing — store and retrieve full processing traces."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantumrag.core.errors import BudgetExceededError
from quantumrag.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TraceRecord:
    """A complete trace of a query's processing."""

    trace_id: str = ""
    query: str = ""
    answer: str = ""
    confidence: str = ""
    complexity: str = ""
    query_type: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    total_latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    estimated_cost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not self.trace_id:
            self.trace_id = uuid.uuid4().hex[:12]
        if not self.timestamp:
            self.timestamp = time.time()


class TraceStore:
    """Persistent storage for query traces.

    Stores traces in SQLite for later analysis and debugging.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute(
            """CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                answer TEXT NOT NULL DEFAULT '',
                confidence TEXT NOT NULL DEFAULT '',
                complexity TEXT NOT NULL DEFAULT '',
                query_type TEXT NOT NULL DEFAULT '',
                steps TEXT NOT NULL DEFAULT '[]',
                sources TEXT NOT NULL DEFAULT '[]',
                total_latency_ms REAL NOT NULL DEFAULT 0,
                tokens_in INTEGER NOT NULL DEFAULT 0,
                tokens_out INTEGER NOT NULL DEFAULT 0,
                estimated_cost REAL NOT NULL DEFAULT 0,
                metadata TEXT NOT NULL DEFAULT '{}',
                timestamp REAL NOT NULL
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON traces(timestamp)"
        )
        conn.commit()
        conn.close()

    def store(self, trace: TraceRecord) -> None:
        """Store a trace record."""
        conn = sqlite3.connect(str(self._db_path))
        conn.execute(
            """INSERT OR REPLACE INTO traces
               (trace_id, query, answer, confidence, complexity, query_type,
                steps, sources, total_latency_ms, tokens_in, tokens_out,
                estimated_cost, metadata, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trace.trace_id,
                trace.query,
                trace.answer,
                trace.confidence,
                trace.complexity,
                trace.query_type,
                json.dumps(trace.steps),
                json.dumps(trace.sources),
                trace.total_latency_ms,
                trace.tokens_in,
                trace.tokens_out,
                trace.estimated_cost,
                json.dumps(trace.metadata),
                trace.timestamp,
            ),
        )
        conn.commit()
        conn.close()

    def get(self, trace_id: str) -> TraceRecord | None:
        """Retrieve a trace by ID."""
        conn = sqlite3.connect(str(self._db_path))
        row = conn.execute(
            "SELECT * FROM traces WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_trace(row)

    def list_traces(
        self,
        limit: int = 50,
        offset: int = 0,
        since: float | None = None,
    ) -> list[TraceRecord]:
        """List traces with optional time filter."""
        conn = sqlite3.connect(str(self._db_path))

        if since:
            rows = conn.execute(
                "SELECT * FROM traces WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (since, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM traces ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()

        conn.close()
        return [self._row_to_trace(r) for r in rows]

    def get_stats(self, since: float | None = None) -> dict[str, Any]:
        """Get aggregate statistics from traces."""
        conn = sqlite3.connect(str(self._db_path))

        where = "WHERE timestamp >= ?" if since else ""
        params: tuple[Any, ...] = (since,) if since else ()

        row = conn.execute(
            f"""SELECT
                COUNT(*) as total,
                AVG(total_latency_ms) as avg_latency,
                MAX(total_latency_ms) as max_latency,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                SUM(estimated_cost) as total_cost
            FROM traces {where}""",
            params,
        ).fetchone()

        # Latency percentiles
        latencies = conn.execute(
            f"SELECT total_latency_ms FROM traces {where} ORDER BY total_latency_ms",
            params,
        ).fetchall()
        conn.close()

        lat_values = [r[0] for r in latencies] if latencies else []

        return {
            "total_queries": row[0] if row else 0,
            "avg_latency_ms": row[1] or 0.0 if row else 0.0,
            "max_latency_ms": row[2] or 0.0 if row else 0.0,
            "p50_latency_ms": _percentile(lat_values, 50),
            "p95_latency_ms": _percentile(lat_values, 95),
            "p99_latency_ms": _percentile(lat_values, 99),
            "total_tokens_in": row[3] or 0 if row else 0,
            "total_tokens_out": row[4] or 0 if row else 0,
            "total_cost": row[5] or 0.0 if row else 0.0,
        }

    def cleanup(self, older_than: float) -> int:
        """Remove traces older than the given timestamp."""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.execute(
            "DELETE FROM traces WHERE timestamp < ?", (older_than,)
        )
        count = cursor.rowcount
        conn.commit()
        conn.close()
        logger.info("traces_cleaned", removed=count)
        return count

    @staticmethod
    def _row_to_trace(row: tuple[Any, ...]) -> TraceRecord:
        return TraceRecord(
            trace_id=row[0],
            query=row[1],
            answer=row[2],
            confidence=row[3],
            complexity=row[4],
            query_type=row[5],
            steps=json.loads(row[6]),
            sources=json.loads(row[7]),
            total_latency_ms=row[8],
            tokens_in=row[9],
            tokens_out=row[10],
            estimated_cost=row[11],
            metadata=json.loads(row[12]),
            timestamp=row[13],
        )


class CostTracker:
    """Track API costs across queries."""

    def __init__(self) -> None:
        self._total_cost = 0.0
        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._query_count = 0
        self._budget_limit: float | None = None

    def set_budget(self, limit: float) -> None:
        """Set a cost budget limit. Exceeding triggers a warning."""
        self._budget_limit = limit

    def record(
        self,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost: float = 0.0,
    ) -> None:
        """Record token usage and cost for a query."""
        self._total_tokens_in += tokens_in
        self._total_tokens_out += tokens_out
        self._total_cost += cost
        self._query_count += 1

        if self._budget_limit and self._total_cost > self._budget_limit:
            logger.warning(
                "budget_exceeded",
                total_cost=f"${self._total_cost:.4f}",
                budget=f"${self._budget_limit:.4f}",
            )

    @property
    def is_over_budget(self) -> bool:
        if self._budget_limit is None:
            return False
        return self._total_cost > self._budget_limit

    def summary(self) -> dict[str, Any]:
        """Get cost summary."""
        return {
            "total_cost": self._total_cost,
            "total_tokens_in": self._total_tokens_in,
            "total_tokens_out": self._total_tokens_out,
            "query_count": self._query_count,
            "avg_cost_per_query": (
                self._total_cost / self._query_count if self._query_count > 0 else 0.0
            ),
            "budget_limit": self._budget_limit,
            "budget_remaining": (
                self._budget_limit - self._total_cost
                if self._budget_limit
                else None
            ),
        }

    def reset(self) -> None:
        """Reset all counters."""
        self._total_cost = 0.0
        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._query_count = 0


def _percentile(values: list[float], p: int) -> float:
    """Compute the p-th percentile of a sorted list."""
    if not values:
        return 0.0
    k = (len(values) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(values):
        return values[-1]
    return values[f] + (k - f) * (values[c] - values[f])


class BudgetManager:
    """Persistent budget management for LLM API spending.

    Tracks cumulative daily and monthly costs in a SQLite database and
    raises :class:`BudgetExceededError` when a configured limit is hit.
    """

    def __init__(
        self,
        db_path: str | Path,
        daily_limit: float | None = None,
        monthly_limit: float | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._daily_limit = daily_limit
        self._monthly_limit = monthly_limit
        self._init_db()

    # -- public API ----------------------------------------------------------

    def record_cost(self, cost: float) -> None:
        """Record a cost entry and log it persistently."""
        now = time.time()
        conn = self._connect()
        conn.execute(
            "INSERT INTO budget_records (cost, timestamp) VALUES (?, ?)",
            (cost, now),
        )
        conn.commit()
        conn.close()
        logger.debug("budget_cost_recorded", cost=cost)

    def check_budget(self) -> None:
        """Raise :class:`BudgetExceededError` if any limit is exceeded."""
        summary = self.get_usage_summary()

        if self._daily_limit is not None and summary["daily_total"] >= self._daily_limit:
            raise BudgetExceededError(
                f"Daily budget exceeded: ${summary['daily_total']:.4f} >= ${self._daily_limit:.4f}",
                current_spend=summary["daily_total"],
                limit=self._daily_limit,
                period="daily",
            )

        if self._monthly_limit is not None and summary["monthly_total"] >= self._monthly_limit:
            raise BudgetExceededError(
                f"Monthly budget exceeded: ${summary['monthly_total']:.4f} >= ${self._monthly_limit:.4f}",
                current_spend=summary["monthly_total"],
                limit=self._monthly_limit,
                period="monthly",
            )

    def get_usage_summary(self) -> dict[str, Any]:
        """Return daily and monthly spend totals."""
        now = datetime.now(tz=timezone.utc)
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp()
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp()

        conn = self._connect()
        daily_row = conn.execute(
            "SELECT COALESCE(SUM(cost), 0) FROM budget_records WHERE timestamp >= ?",
            (day_start,),
        ).fetchone()
        monthly_row = conn.execute(
            "SELECT COALESCE(SUM(cost), 0) FROM budget_records WHERE timestamp >= ?",
            (month_start,),
        ).fetchone()
        conn.close()

        daily_total: float = daily_row[0] if daily_row else 0.0
        monthly_total: float = monthly_row[0] if monthly_row else 0.0

        return {
            "daily_total": daily_total,
            "monthly_total": monthly_total,
            "daily_limit": self._daily_limit,
            "monthly_limit": self._monthly_limit,
            "daily_remaining": (
                max(self._daily_limit - daily_total, 0.0) if self._daily_limit is not None else None
            ),
            "monthly_remaining": (
                max(self._monthly_limit - monthly_total, 0.0)
                if self._monthly_limit is not None
                else None
            ),
        }

    # -- internals -----------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def _init_db(self) -> None:
        conn = self._connect()
        conn.execute(
            """CREATE TABLE IF NOT EXISTS budget_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cost REAL NOT NULL,
                timestamp REAL NOT NULL
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_budget_timestamp ON budget_records(timestamp)"
        )
        conn.commit()
        conn.close()
