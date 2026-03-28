"""Tests for vector store backends (ChromaDB, FAISS).

Tests the VectorStore protocol compliance and basic CRUD + search operations
for each backend. Backends that are not installed are skipped gracefully.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest


def _has_chromadb() -> bool:
    try:
        import chromadb  # noqa: F401

        return True
    except ImportError:
        return False


def _has_faiss() -> bool:
    try:
        import faiss  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_vector(dim: int, val: float) -> list[float]:
    """Create a normalized vector filled with *val*."""
    raw = [val] * dim
    norm = math.sqrt(sum(v * v for v in raw))
    return [v / norm for v in raw] if norm > 0 else raw


def _similar_vectors(dim: int = 8) -> tuple[list[list[float]], list[list[float]]]:
    """Return (base_vectors, query_vector) where vec[0] is most similar to query."""
    v1 = _make_vector(dim, 1.0)  # most similar to query
    v2 = _make_vector(dim, -1.0)  # least similar
    # Mix: partially similar
    v3 = [0.5 if i < dim // 2 else -0.5 for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in v3))
    v3 = [v / norm for v in v3]
    return [v1, v2, v3], [v1]  # query = same as v1


# ---------------------------------------------------------------------------
# ChromaDB Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_chromadb(), reason="chromadb not installed")
class TestChromaVectorStore:
    @pytest.fixture
    def store(self, tmp_path: Path):
        from quantumrag.core.storage.backends.chroma_store import ChromaVectorStore

        return ChromaVectorStore(db_path=tmp_path / "chroma", collection_name="test")

    @pytest.mark.asyncio
    async def test_add_and_count(self, store):
        vecs = [_make_vector(8, 1.0), _make_vector(8, 0.5)]
        await store.add_vectors(
            ids=["a", "b"],
            vectors=vecs,
            metadata=[{"document_id": "d1"}, {"document_id": "d1"}],
        )
        assert await store.count() == 2

    @pytest.mark.asyncio
    async def test_add_empty(self, store):
        await store.add_vectors(ids=[], vectors=[])
        assert await store.count() == 0

    @pytest.mark.asyncio
    async def test_search_returns_sorted_results(self, store):
        vecs, query = _similar_vectors(8)
        ids = ["most_similar", "least_similar", "partial"]
        meta = [{"document_id": f"d{i}"} for i in range(3)]
        await store.add_vectors(ids=ids, vectors=vecs, metadata=meta)

        results = await store.search(query_vector=query[0], top_k=3)
        assert len(results) >= 1
        # Most similar should be first
        assert results[0].id == "most_similar"
        assert results[0].score > 0.5

    @pytest.mark.asyncio
    async def test_search_with_document_filter(self, store):
        v1 = _make_vector(8, 1.0)
        v2 = _make_vector(8, 0.9)
        await store.add_vectors(
            ids=["a", "b"],
            vectors=[v1, v2],
            metadata=[{"document_id": "doc_x"}, {"document_id": "doc_y"}],
        )
        results = await store.search(query_vector=v1, top_k=10, filters={"document_id": "doc_x"})
        assert all(r.id == "a" for r in results)

    @pytest.mark.asyncio
    async def test_delete_by_id(self, store):
        vecs = [_make_vector(8, 1.0), _make_vector(8, 0.5)]
        await store.add_vectors(ids=["a", "b"], vectors=vecs)
        await store.delete(ids=["a"])
        assert await store.count() == 1

    @pytest.mark.asyncio
    async def test_delete_by_document(self, store):
        vecs = [_make_vector(8, 1.0), _make_vector(8, 0.5)]
        await store.add_vectors(
            ids=["a", "b"],
            vectors=vecs,
            metadata=[{"document_id": "d1"}, {"document_id": "d2"}],
        )
        await store.delete_by_document("d1")
        assert await store.count() == 1

    @pytest.mark.asyncio
    async def test_upsert_overwrites(self, store):
        v1 = _make_vector(8, 1.0)
        await store.add_vectors(ids=["a"], vectors=[v1], metadata=[{"document_id": "d1"}])
        v2 = _make_vector(8, -1.0)
        await store.add_vectors(ids=["a"], vectors=[v2], metadata=[{"document_id": "d1"}])
        assert await store.count() == 1


# ---------------------------------------------------------------------------
# FAISS Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_faiss(), reason="faiss-cpu not installed")
class TestFAISSVectorStore:
    @pytest.fixture
    def store(self, tmp_path: Path):
        from quantumrag.core.storage.backends.faiss_store import FAISSVectorStore

        return FAISSVectorStore(db_path=tmp_path / "faiss")

    @pytest.mark.asyncio
    async def test_add_and_count(self, store):
        vecs = [_make_vector(8, 1.0), _make_vector(8, 0.5)]
        await store.add_vectors(
            ids=["a", "b"],
            vectors=vecs,
            metadata=[{"document_id": "d1"}, {"document_id": "d1"}],
        )
        assert await store.count() == 2

    @pytest.mark.asyncio
    async def test_add_empty(self, store):
        await store.add_vectors(ids=[], vectors=[])
        assert await store.count() == 0

    @pytest.mark.asyncio
    async def test_search_returns_sorted_results(self, store):
        vecs, query = _similar_vectors(8)
        ids = ["most_similar", "least_similar", "partial"]
        meta = [{"document_id": f"d{i}"} for i in range(3)]
        await store.add_vectors(ids=ids, vectors=vecs, metadata=meta)

        results = await store.search(query_vector=query[0], top_k=3)
        assert len(results) >= 1
        assert results[0].id == "most_similar"
        assert results[0].score > 0.5

    @pytest.mark.asyncio
    async def test_search_with_document_filter(self, store):
        v1 = _make_vector(8, 1.0)
        v2 = _make_vector(8, 0.9)
        await store.add_vectors(
            ids=["a", "b"],
            vectors=[v1, v2],
            metadata=[{"document_id": "doc_x"}, {"document_id": "doc_y"}],
        )
        results = await store.search(query_vector=v1, top_k=10, filters={"document_id": "doc_x"})
        assert all(r.id == "a" for r in results)

    @pytest.mark.asyncio
    async def test_delete_by_id(self, store):
        vecs = [_make_vector(8, 1.0), _make_vector(8, 0.5)]
        await store.add_vectors(
            ids=["a", "b"],
            vectors=vecs,
            metadata=[{"document_id": "d1"}, {"document_id": "d2"}],
        )
        await store.delete(ids=["a"])
        assert await store.count() == 1

    @pytest.mark.asyncio
    async def test_delete_by_document(self, store):
        vecs = [_make_vector(8, 1.0), _make_vector(8, 0.5)]
        await store.add_vectors(
            ids=["a", "b"],
            vectors=vecs,
            metadata=[{"document_id": "d1"}, {"document_id": "d2"}],
        )
        await store.delete_by_document("d1")
        assert await store.count() == 1

    @pytest.mark.asyncio
    async def test_persistence(self, tmp_path: Path):
        """Test that FAISS index survives reload."""
        from quantumrag.core.storage.backends.faiss_store import FAISSVectorStore

        db_path = tmp_path / "faiss_persist"
        store1 = FAISSVectorStore(db_path=db_path)
        v1 = _make_vector(8, 1.0)
        await store1.add_vectors(ids=["a"], vectors=[v1], metadata=[{"document_id": "d1"}])
        assert await store1.count() == 1

        # Create new store pointing at same path
        store2 = FAISSVectorStore(db_path=db_path)
        assert await store2.count() == 1
        results = await store2.search(query_vector=v1, top_k=1)
        assert len(results) == 1
        assert results[0].id == "a"

    @pytest.mark.asyncio
    async def test_search_empty_index(self, store):
        results = await store.search(query_vector=_make_vector(8, 1.0), top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_upsert_overwrites(self, store):
        v1 = _make_vector(8, 1.0)
        await store.add_vectors(ids=["a"], vectors=[v1], metadata=[{"document_id": "d1"}])
        v2 = _make_vector(8, -1.0)
        await store.add_vectors(ids=["a"], vectors=[v2], metadata=[{"document_id": "d1"}])
        assert await store.count() == 1


# ---------------------------------------------------------------------------
# StorageFactory integration
# ---------------------------------------------------------------------------


class TestFactoryRegistration:
    """Verify new backends are registered in the factory."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        from quantumrag.core.storage.factory import StorageFactory

        StorageFactory._reset()
        yield
        StorageFactory._reset()

    def test_chroma_in_registry(self):
        from quantumrag.core.storage.factory import StorageFactory

        StorageFactory._ensure_defaults_registered()
        assert "chroma" in StorageFactory._vector_store_registry

    def test_faiss_in_registry(self):
        from quantumrag.core.storage.factory import StorageFactory

        StorageFactory._ensure_defaults_registered()
        assert "faiss" in StorageFactory._vector_store_registry

    def test_lancedb_still_default(self):
        from quantumrag.core.storage.factory import StorageFactory

        StorageFactory._ensure_defaults_registered()
        assert "lancedb" in StorageFactory._vector_store_registry
