"""Storage factory -- create storage backends from configuration."""

from __future__ import annotations

from typing import Any, ClassVar

from quantumrag.core.errors import ConfigError


class StorageFactory:
    """Factory for creating storage backend instances.

    Backends are registered by name and lazily imported to avoid
    pulling in heavy dependencies (lancedb, tantivy) until actually needed.
    """

    _document_store_registry: ClassVar[dict[str, type]] = {}
    _vector_store_registry: ClassVar[dict[str, type]] = {}
    _bm25_store_registry: ClassVar[dict[str, type]] = {}

    # -- registration --------------------------------------------------

    @classmethod
    def register_document_store(cls, name: str, store_class: type) -> None:
        """Register a document store backend under *name*."""
        cls._document_store_registry[name] = store_class

    @classmethod
    def register_vector_store(cls, name: str, store_class: type) -> None:
        """Register a vector store backend under *name*."""
        cls._vector_store_registry[name] = store_class

    @classmethod
    def register_bm25_store(cls, name: str, store_class: type) -> None:
        """Register a BM25 store backend under *name*."""
        cls._bm25_store_registry[name] = store_class

    # -- creation ------------------------------------------------------

    @classmethod
    def create_document_store(cls, backend: str = "sqlite", **kwargs: Any) -> Any:
        """Create a document store instance for *backend*."""
        cls._ensure_defaults_registered()
        if backend not in cls._document_store_registry:
            raise ConfigError(
                f"Unknown document store backend: {backend!r}. "
                f"Available: {sorted(cls._document_store_registry)}"
            )
        return cls._document_store_registry[backend](**kwargs)

    @classmethod
    def create_vector_store(cls, backend: str = "lancedb", **kwargs: Any) -> Any:
        """Create a vector store instance for *backend*."""
        cls._ensure_defaults_registered()
        if backend not in cls._vector_store_registry:
            raise ConfigError(
                f"Unknown vector store backend: {backend!r}. "
                f"Available: {sorted(cls._vector_store_registry)}"
            )
        return cls._vector_store_registry[backend](**kwargs)

    @classmethod
    def create_bm25_store(cls, backend: str = "tantivy", **kwargs: Any) -> Any:
        """Create a BM25 store instance for *backend*."""
        cls._ensure_defaults_registered()
        if backend not in cls._bm25_store_registry:
            raise ConfigError(
                f"Unknown BM25 store backend: {backend!r}. "
                f"Available: {sorted(cls._bm25_store_registry)}"
            )
        return cls._bm25_store_registry[backend](**kwargs)

    # -- internal helpers ----------------------------------------------

    _defaults_registered: bool = False

    @classmethod
    def _ensure_defaults_registered(cls) -> None:
        """Lazily register the built-in backends on first use."""
        if cls._defaults_registered:
            return

        # Lazy imports so heavy deps are only loaded when actually requested.
        from quantumrag.core.storage.backends.bm25_store import TantivyBM25Store
        from quantumrag.core.storage.backends.lancedb_store import LanceDBVectorStore
        from quantumrag.core.storage.backends.sqlite import SQLiteDocumentStore

        cls._document_store_registry.setdefault("sqlite", SQLiteDocumentStore)
        cls._vector_store_registry.setdefault("lancedb", LanceDBVectorStore)
        cls._bm25_store_registry.setdefault("tantivy", TantivyBM25Store)
        cls._defaults_registered = True

    @classmethod
    def _reset(cls) -> None:
        """Reset all registries -- useful for testing."""
        cls._document_store_registry.clear()
        cls._vector_store_registry.clear()
        cls._bm25_store_registry.clear()
        cls._defaults_registered = False
