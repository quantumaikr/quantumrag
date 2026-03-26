"""Tests for semantic cache and observability modules."""

from __future__ import annotations

import time
from pathlib import Path

from quantumrag.core.cache.semantic import CacheEntry, SemanticCache, _cosine_similarity
from quantumrag.core.observability.tracer import CostTracker, TraceRecord, TraceStore

# --- SemanticCache ---


class TestSemanticCache:
    def test_put_and_get(self) -> None:
        cache = SemanticCache(ttl_seconds=60)
        cache.put("What is RAG?", "RAG is retrieval-augmented generation.")
        entry = cache.get("What is RAG?")
        assert entry is not None
        assert entry.answer == "RAG is retrieval-augmented generation."

    def test_case_insensitive_matching(self) -> None:
        cache = SemanticCache(ttl_seconds=60)
        cache.put("What is RAG?", "answer")
        entry = cache.get("what is rag?")
        assert entry is not None

    def test_cache_miss(self) -> None:
        cache = SemanticCache(ttl_seconds=60)
        entry = cache.get("unknown query")
        assert entry is None

    def test_ttl_expiration(self) -> None:
        cache = SemanticCache(ttl_seconds=0.01)
        cache.put("test query", "test answer")
        time.sleep(0.02)
        entry = cache.get("test query")
        assert entry is None

    def test_invalidate_specific(self) -> None:
        cache = SemanticCache(ttl_seconds=60)
        cache.put("q1", "a1")
        cache.put("q2", "a2")
        removed = cache.invalidate("q1")
        assert removed == 1
        assert cache.get("q1") is None
        assert cache.get("q2") is not None

    def test_invalidate_all(self) -> None:
        cache = SemanticCache(ttl_seconds=60)
        cache.put("q1", "a1")
        cache.put("q2", "a2")
        removed = cache.invalidate()
        assert removed == 2
        assert cache.get("q1") is None

    def test_max_entries_eviction(self) -> None:
        cache = SemanticCache(ttl_seconds=60, max_entries=3)
        cache.put("q1", "a1")
        cache.put("q2", "a2")
        cache.put("q3", "a3")
        cache.put("q4", "a4")  # Should evict oldest
        assert len(cache._cache) == 3

    def test_stats(self) -> None:
        cache = SemanticCache(ttl_seconds=60)
        cache.put("q1", "a1")
        cache.get("q1")
        cache.get("q1")
        cache.get("unknown")

        stats = cache.stats()
        assert stats["entries"] == 1
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] > 0.5

    def test_semantic_match(self) -> None:
        cache = SemanticCache(ttl_seconds=60, similarity_threshold=0.9)
        emb1 = [1.0, 0.0, 0.0]
        emb2 = [0.99, 0.1, 0.0]  # Very similar
        cache.put("original query", "answer", embedding=emb1)

        entry = cache.get_semantic("similar query", emb2)
        assert entry is not None
        assert entry.answer == "answer"

    def test_semantic_no_match(self) -> None:
        cache = SemanticCache(ttl_seconds=60, similarity_threshold=0.9)
        emb1 = [1.0, 0.0, 0.0]
        emb2 = [0.0, 1.0, 0.0]  # Orthogonal
        cache.put("original query", "answer", embedding=emb1)

        entry = cache.get_semantic("different query", emb2)
        assert entry is None

    def test_persistent_cache(self, tmp_path: Path) -> None:
        db = tmp_path / "cache.db"

        cache1 = SemanticCache(ttl_seconds=3600, storage_path=db)
        cache1.put("persistent query", "persistent answer", confidence="high")

        cache2 = SemanticCache(ttl_seconds=3600, storage_path=db)
        loaded = cache2.load_from_storage()
        assert loaded == 1

    def test_put_with_metadata(self) -> None:
        cache = SemanticCache(ttl_seconds=60)
        cache.put(
            "q1",
            "a1",
            sources=[{"doc": "test.pdf"}],
            confidence="strongly_supported",
            metadata={"latency_ms": 150},
        )
        entry = cache.get("q1")
        assert entry is not None
        assert entry.confidence == "strongly_supported"
        assert len(entry.sources) == 1


class TestCosineSimlarity:
    def test_identical_vectors(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_empty_vectors(self) -> None:
        assert _cosine_similarity([], []) == 0.0

    def test_zero_vector(self) -> None:
        assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


# --- TraceStore ---


class TestTraceStore:
    def test_store_and_get(self, tmp_path: Path) -> None:
        store = TraceStore(tmp_path / "traces.db")
        trace = TraceRecord(
            query="What is RAG?",
            answer="RAG is...",
            confidence="strongly_supported",
            complexity="simple",
            total_latency_ms=150.0,
        )
        store.store(trace)

        retrieved = store.get(trace.trace_id)
        assert retrieved is not None
        assert retrieved.query == "What is RAG?"
        assert retrieved.confidence == "strongly_supported"

    def test_get_nonexistent(self, tmp_path: Path) -> None:
        store = TraceStore(tmp_path / "traces.db")
        assert store.get("nonexistent") is None

    def test_list_traces(self, tmp_path: Path) -> None:
        store = TraceStore(tmp_path / "traces.db")
        for i in range(5):
            store.store(
                TraceRecord(
                    query=f"Query {i}",
                    answer=f"Answer {i}",
                    timestamp=time.time() + i,
                )
            )

        traces = store.list_traces(limit=3)
        assert len(traces) == 3

    def test_stats(self, tmp_path: Path) -> None:
        store = TraceStore(tmp_path / "traces.db")
        for i in range(10):
            store.store(
                TraceRecord(
                    query=f"Q{i}",
                    total_latency_ms=100.0 + i * 10,
                    tokens_in=100,
                    tokens_out=50,
                    estimated_cost=0.001,
                )
            )

        stats = store.get_stats()
        assert stats["total_queries"] == 10
        assert stats["avg_latency_ms"] > 0
        assert stats["total_tokens_in"] == 1000
        assert stats["total_cost"] > 0

    def test_cleanup(self, tmp_path: Path) -> None:
        store = TraceStore(tmp_path / "traces.db")
        old_time = time.time() - 3600
        store.store(TraceRecord(query="old", timestamp=old_time))
        store.store(TraceRecord(query="new", timestamp=time.time()))

        removed = store.cleanup(older_than=time.time() - 1800)
        assert removed == 1

        remaining = store.list_traces()
        assert len(remaining) == 1


# --- CostTracker ---


class TestCostTracker:
    def test_record_and_summary(self) -> None:
        tracker = CostTracker()
        tracker.record(tokens_in=100, tokens_out=50, cost=0.001)
        tracker.record(tokens_in=200, tokens_out=100, cost=0.002)

        summary = tracker.summary()
        assert summary["total_cost"] == 0.003
        assert summary["total_tokens_in"] == 300
        assert summary["query_count"] == 2
        assert abs(summary["avg_cost_per_query"] - 0.0015) < 1e-6

    def test_budget_tracking(self) -> None:
        tracker = CostTracker()
        tracker.set_budget(0.01)
        tracker.record(cost=0.005)
        assert not tracker.is_over_budget

        tracker.record(cost=0.006)
        assert tracker.is_over_budget

    def test_reset(self) -> None:
        tracker = CostTracker()
        tracker.record(tokens_in=100, cost=0.001)
        tracker.reset()

        summary = tracker.summary()
        assert summary["total_cost"] == 0.0
        assert summary["query_count"] == 0


class TestCacheEntry:
    def test_expiration(self) -> None:
        entry = CacheEntry(
            query="test",
            query_hash="abc",
            answer="answer",
            created_at=time.time() - 100,
            ttl_seconds=50,
        )
        assert entry.is_expired

    def test_not_expired(self) -> None:
        entry = CacheEntry(
            query="test",
            query_hash="abc",
            answer="answer",
            created_at=time.time(),
            ttl_seconds=3600,
        )
        assert not entry.is_expired
