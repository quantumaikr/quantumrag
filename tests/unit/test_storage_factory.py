"""Tests for StorageFactory and Engine DI integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from quantumrag.core.config import QuantumRAGConfig
from quantumrag.core.engine import Engine
from quantumrag.core.errors import ConfigError
from quantumrag.core.storage.factory import StorageFactory


def _has_lancedb() -> bool:
    try:
        import lancedb  # noqa: F401

        return True
    except ImportError:
        return False


def _has_tantivy() -> bool:
    try:
        import tantivy  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_factory():
    """Ensure every test starts with a clean factory state."""
    StorageFactory._reset()
    yield
    StorageFactory._reset()


class _DummyDocumentStore:
    """Minimal stand-in for a document store."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _DummyVectorStore:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _DummyBM25Store:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_and_create_document_store(self):
        StorageFactory.register_document_store("dummy", _DummyDocumentStore)
        store = StorageFactory.create_document_store(backend="dummy", foo="bar")
        assert isinstance(store, _DummyDocumentStore)
        assert store.kwargs == {"foo": "bar"}

    def test_register_and_create_vector_store(self):
        StorageFactory.register_vector_store("dummy", _DummyVectorStore)
        store = StorageFactory.create_vector_store(backend="dummy", dim=128)
        assert isinstance(store, _DummyVectorStore)
        assert store.kwargs == {"dim": 128}

    def test_register_and_create_bm25_store(self):
        StorageFactory.register_bm25_store("dummy", _DummyBM25Store)
        store = StorageFactory.create_bm25_store(backend="dummy")
        assert isinstance(store, _DummyBM25Store)

    def test_register_overwrites_existing(self):
        StorageFactory.register_document_store("dummy", _DummyDocumentStore)
        StorageFactory.register_document_store("dummy", _DummyVectorStore)  # overwrite
        store = StorageFactory.create_document_store(backend="dummy")
        assert isinstance(store, _DummyVectorStore)


# ---------------------------------------------------------------------------
# Unknown backend tests
# ---------------------------------------------------------------------------


class TestUnknownBackend:
    def test_unknown_document_store_raises(self):
        with pytest.raises(ConfigError, match="Unknown document store backend"):
            StorageFactory.create_document_store(backend="nosql_9000")

    def test_unknown_vector_store_raises(self):
        with pytest.raises(ConfigError, match="Unknown vector store backend"):
            StorageFactory.create_vector_store(backend="nosql_9000")

    def test_unknown_bm25_store_raises(self):
        with pytest.raises(ConfigError, match="Unknown BM25 store backend"):
            StorageFactory.create_bm25_store(backend="nosql_9000")


# ---------------------------------------------------------------------------
# Default backend tests
# ---------------------------------------------------------------------------


class TestDefaultBackends:
    def test_default_document_store_is_sqlite(self, tmp_path: Path):
        store = StorageFactory.create_document_store(backend="sqlite", db_path=tmp_path / "docs.db")
        from quantumrag.core.storage.backends.sqlite import SQLiteDocumentStore

        assert isinstance(store, SQLiteDocumentStore)

    @pytest.mark.skipif(not _has_lancedb(), reason="lancedb not installed")
    def test_default_vector_store_is_lancedb(self, tmp_path: Path):
        store = StorageFactory.create_vector_store(
            backend="lancedb", db_path=tmp_path / "vecs", table_name="t"
        )
        from quantumrag.core.storage.backends.lancedb_store import LanceDBVectorStore

        assert isinstance(store, LanceDBVectorStore)

    @pytest.mark.skipif(not _has_tantivy(), reason="tantivy not installed")
    def test_default_bm25_store_is_tantivy(self, tmp_path: Path):
        store = StorageFactory.create_bm25_store(backend="tantivy", index_path=tmp_path / "idx")
        from quantumrag.core.storage.backends.bm25_store import TantivyBM25Store

        assert isinstance(store, TantivyBM25Store)


# ---------------------------------------------------------------------------
# Reset tests
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_registries(self):
        StorageFactory.register_document_store("dummy", _DummyDocumentStore)
        StorageFactory._reset()
        # After reset, "dummy" should be gone and defaults not yet loaded
        with pytest.raises(ConfigError):
            StorageFactory.create_document_store(backend="dummy")

    def test_reset_allows_reregistration_of_defaults(self, tmp_path: Path):
        # Trigger default registration
        StorageFactory.create_document_store(backend="sqlite", db_path=tmp_path / "a.db")
        StorageFactory._reset()
        # Defaults should re-register lazily
        store = StorageFactory.create_document_store(backend="sqlite", db_path=tmp_path / "b.db")
        from quantumrag.core.storage.backends.sqlite import SQLiteDocumentStore

        assert isinstance(store, SQLiteDocumentStore)


# ---------------------------------------------------------------------------
# Engine DI tests
# ---------------------------------------------------------------------------


class TestEngineDI:
    def test_engine_uses_injected_document_store(self, tmp_path: Path):
        mock_store = AsyncMock()
        mock_store.count_documents = AsyncMock(return_value=42)
        mock_store.count_chunks = AsyncMock(return_value=100)

        config = QuantumRAGConfig.default(storage={"data_dir": str(tmp_path / "data")})
        engine = Engine(config=config, document_store=mock_store)

        # The injected store should be used instead of creating one via factory
        assert engine._components["document_store"] is mock_store

        # status() triggers _ensure_initialized and uses the document store
        status = engine.status()
        assert status["documents"] == 42
        mock_store.count_documents.assert_called()

    def test_engine_uses_injected_vector_store(self, tmp_path: Path):
        mock_vs = AsyncMock()

        config = QuantumRAGConfig.default(storage={"data_dir": str(tmp_path / "data")})
        engine = Engine(config=config, vector_store=mock_vs)

        assert engine._components["vector_store_original"] is mock_vs
        assert engine._get_vector_store("original") is mock_vs

    def test_engine_uses_injected_bm25_store(self, tmp_path: Path):
        mock_bm25 = AsyncMock()

        config = QuantumRAGConfig.default(storage={"data_dir": str(tmp_path / "data")})
        engine = Engine(config=config, bm25_store=mock_bm25)

        assert engine._components["bm25_store"] is mock_bm25
        assert engine._get_bm25_store() is mock_bm25

    def test_engine_falls_back_to_factory_when_no_stores_given(self, tmp_path: Path):
        config = QuantumRAGConfig.default(storage={"data_dir": str(tmp_path / "data")})
        engine = Engine(config=config)

        # Trigger lazy init
        doc_store = engine._get_document_store()
        from quantumrag.core.storage.backends.sqlite import SQLiteDocumentStore

        assert isinstance(doc_store, SQLiteDocumentStore)
