"""Abstract storage interfaces for QuantumRAG."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from quantumrag.core.models import Chunk, Document


@runtime_checkable
class DocumentStore(Protocol):
    """Protocol for document and chunk storage."""

    async def add_document(self, document: Document) -> str:
        """Store a document and return its ID."""
        ...

    async def get_document(self, document_id: str) -> Document | None:
        """Retrieve a document by ID."""
        ...

    async def list_documents(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Document]:
        """List documents with optional filtering."""
        ...

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and its chunks. Returns True if found."""
        ...

    async def update_document(self, document: Document) -> bool:
        """Update an existing document. Returns True if found."""
        ...

    async def add_chunks(self, chunks: list[Chunk]) -> list[str]:
        """Store chunks and return their IDs."""
        ...

    async def get_chunks(self, document_id: str) -> list[Chunk]:
        """Retrieve all chunks for a document."""
        ...

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Retrieve a single chunk by ID."""
        ...

    async def get_chunks_batch(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        """Retrieve multiple chunks by ID in a single query.

        Returns a mapping of chunk_id → Chunk for all found chunks.
        """
        ...

    async def count_documents(self) -> int:
        """Return total document count."""
        ...

    async def count_chunks(self) -> int:
        """Return total chunk count."""
        ...

    async def document_exists(self, source_id: str) -> bool:
        """Check if a document with given source_id already exists."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for vector similarity search."""

    async def add_vectors(
        self,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add vectors with IDs and optional metadata."""
        ...

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        """Search for similar vectors."""
        ...

    async def delete(self, ids: list[str]) -> None:
        """Delete vectors by IDs."""
        ...

    async def delete_by_document(self, document_id: str) -> None:
        """Delete all vectors associated with a document."""
        ...

    async def count(self) -> int:
        """Return total vector count."""
        ...


class VectorSearchResult:
    """Result from a vector search."""

    __slots__ = ("id", "metadata", "score")

    def __init__(
        self,
        id: str,
        score: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.score = score
        self.metadata = metadata or {}


@runtime_checkable
class BM25Store(Protocol):
    """Protocol for BM25 full-text search."""

    async def add_documents(
        self,
        ids: list[str],
        texts: list[str],
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add documents to the BM25 index."""
        ...

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[BM25SearchResult]:
        """Search using BM25 scoring."""
        ...

    async def delete(self, ids: list[str]) -> None:
        """Delete documents by IDs."""
        ...

    async def delete_by_document(self, document_id: str) -> None:
        """Delete all entries associated with a document."""
        ...

    async def count(self) -> int:
        """Return total indexed document count."""
        ...


class BM25SearchResult:
    """Result from a BM25 search."""

    __slots__ = ("id", "metadata", "score")

    def __init__(
        self,
        id: str,
        score: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.score = score
        self.metadata = metadata or {}
