"""Semantic cache — cache query results by embedding similarity.

Avoids redundant LLM calls for semantically similar questions.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantumrag.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """A cached query result."""

    query: str
    query_hash: str
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    confidence: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    ttl_seconds: float = 3600.0
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_seconds


class SemanticCache:
    """Cache query results with semantic similarity matching.

    Uses exact hash matching for identical queries, and optionally
    embedding similarity for semantically equivalent queries.

    Args:
        ttl_seconds: Time-to-live for cache entries.
        max_entries: Maximum cache entries (LRU eviction).
        similarity_threshold: Cosine similarity threshold for cache hits.
        storage_path: Optional path for persistent cache (SQLite).
    """

    def __init__(
        self,
        ttl_seconds: float = 3600.0,
        max_entries: int = 1000,
        similarity_threshold: float = 0.95,
        storage_path: str | Path | None = None,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._similarity_threshold = similarity_threshold
        self._storage_path = Path(storage_path) if storage_path else None

        # In-memory cache: hash -> CacheEntry
        self._cache: dict[str, CacheEntry] = {}

        # Embedding cache for semantic matching: hash -> embedding vector
        self._embeddings: dict[str, list[float]] = {}

        # Stats
        self._hits = 0
        self._misses = 0

        if self._storage_path:
            self._init_persistent_storage()

    def _init_persistent_storage(self) -> None:
        """Initialize SQLite-based persistent cache."""
        import sqlite3

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._storage_path))
        conn.execute(
            """CREATE TABLE IF NOT EXISTS cache (
                query_hash TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources TEXT NOT NULL DEFAULT '[]',
                confidence TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                ttl_seconds REAL NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.commit()
        conn.close()
        logger.debug("cache_storage_initialized", path=str(self._storage_path))

    @staticmethod
    def _hash_query(query: str) -> str:
        """Create a deterministic hash for a query."""
        normalized = query.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def get(self, query: str) -> CacheEntry | None:
        """Look up a cached result for the given query.

        First tries exact hash match, then semantic similarity if embeddings
        are available.
        """
        query_hash = self._hash_query(query)

        # Exact match
        entry = self._cache.get(query_hash)
        if entry and not entry.is_expired:
            entry.hit_count += 1
            self._hits += 1
            logger.debug("cache_hit", query_hash=query_hash, hit_type="exact")
            return entry

        # Remove expired entry
        if entry and entry.is_expired:
            del self._cache[query_hash]
            self._embeddings.pop(query_hash, None)

        self._misses += 1
        return None

    def get_semantic(
        self, query: str, query_embedding: list[float]
    ) -> CacheEntry | None:
        """Look up cached result using embedding similarity."""
        # First try exact match
        exact = self.get(query)
        if exact:
            return exact

        # Semantic search across cached embeddings
        best_score = 0.0
        best_hash = None

        for cached_hash, cached_emb in self._embeddings.items():
            score = _cosine_similarity(query_embedding, cached_emb)
            if score > best_score:
                best_score = score
                best_hash = cached_hash

        if best_hash and best_score >= self._similarity_threshold:
            entry = self._cache.get(best_hash)
            if entry and not entry.is_expired:
                entry.hit_count += 1
                self._hits += 1
                logger.debug(
                    "cache_hit",
                    query_hash=best_hash,
                    hit_type="semantic",
                    similarity=f"{best_score:.3f}",
                )
                return entry

        self._misses += 1
        return None

    def put(
        self,
        query: str,
        answer: str,
        sources: list[dict[str, Any]] | None = None,
        confidence: str = "",
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> None:
        """Store a query result in the cache."""
        # Evict if at capacity
        if len(self._cache) >= self._max_entries:
            self._evict_lru()

        query_hash = self._hash_query(query)
        entry = CacheEntry(
            query=query,
            query_hash=query_hash,
            answer=answer,
            sources=sources or [],
            confidence=confidence,
            metadata=metadata or {},
            created_at=time.time(),
            ttl_seconds=self._ttl,
        )

        self._cache[query_hash] = entry

        if embedding:
            self._embeddings[query_hash] = embedding

        # Persist if storage configured
        if self._storage_path:
            self._persist_entry(entry)

        logger.debug("cache_put", query_hash=query_hash)

    def invalidate(self, query: str | None = None) -> int:
        """Invalidate cache entries.

        If query is given, invalidate that specific entry.
        If query is None, invalidate all entries.
        Returns the number of entries invalidated.
        """
        if query:
            query_hash = self._hash_query(query)
            if query_hash in self._cache:
                del self._cache[query_hash]
                self._embeddings.pop(query_hash, None)
                return 1
            return 0

        count = len(self._cache)
        self._cache.clear()
        self._embeddings.clear()
        logger.info("cache_invalidated_all", count=count)
        return count

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        return {
            "entries": len(self._cache),
            "max_entries": self._max_entries,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "ttl_seconds": self._ttl,
        }

    def _evict_lru(self) -> None:
        """Evict the least recently used (oldest, least hit) entry."""
        if not self._cache:
            return

        # Evict entry with oldest creation time and fewest hits
        worst_hash = min(
            self._cache,
            key=lambda h: (self._cache[h].hit_count, -self._cache[h].created_at),
        )
        del self._cache[worst_hash]
        self._embeddings.pop(worst_hash, None)

    def _persist_entry(self, entry: CacheEntry) -> None:
        """Save entry to SQLite."""
        import sqlite3

        try:
            conn = sqlite3.connect(str(self._storage_path))
            conn.execute(
                """INSERT OR REPLACE INTO cache
                   (query_hash, query, answer, sources, confidence, metadata, created_at, ttl_seconds, hit_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.query_hash,
                    entry.query,
                    entry.answer,
                    json.dumps(entry.sources),
                    entry.confidence,
                    json.dumps(entry.metadata),
                    entry.created_at,
                    entry.ttl_seconds,
                    entry.hit_count,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("cache_persist_failed", error=str(e))

    def load_from_storage(self) -> int:
        """Load cache entries from persistent storage. Returns count loaded."""
        if not self._storage_path or not self._storage_path.exists():
            return 0

        import sqlite3

        try:
            conn = sqlite3.connect(str(self._storage_path))
            rows = conn.execute(
                "SELECT query_hash, query, answer, sources, confidence, metadata, created_at, ttl_seconds, hit_count FROM cache"
            ).fetchall()
            conn.close()

            count = 0
            for row in rows:
                entry = CacheEntry(
                    query_hash=row[0],
                    query=row[1],
                    answer=row[2],
                    sources=json.loads(row[3]),
                    confidence=row[4],
                    metadata=json.loads(row[5]),
                    created_at=row[6],
                    ttl_seconds=row[7],
                    hit_count=row[8],
                )
                if not entry.is_expired:
                    self._cache[entry.query_hash] = entry
                    count += 1

            logger.info("cache_loaded", count=count)
            return count
        except Exception as e:
            logger.warning("cache_load_failed", error=str(e))
            return 0


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)
