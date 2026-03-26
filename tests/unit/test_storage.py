"""Tests for storage layer (SQLite DocumentStore)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantumrag.core.models import Chunk, Document, DocumentMetadata, SourceType
from quantumrag.core.storage.backends.sqlite import SQLiteDocumentStore


@pytest.fixture
def store(tmp_path: Path) -> SQLiteDocumentStore:
    db = SQLiteDocumentStore(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def sample_document() -> Document:
    return Document(
        id="doc1",
        content="This is test content about machine learning.",
        metadata=DocumentMetadata(
            source_type=SourceType.FILE,
            source_id="test_source_1",
            title="ML Guide",
            language="en",
            quality_score=0.95,
            custom={"department": "engineering"},
        ),
    )


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    return [
        Chunk(
            id="chunk1",
            content="Machine learning is a subset of AI.",
            document_id="doc1",
            chunk_index=0,
            metadata={"page": 1},
            context_prefix="From ML Guide:",
        ),
        Chunk(
            id="chunk2",
            content="Deep learning uses neural networks.",
            document_id="doc1",
            chunk_index=1,
            metadata={"page": 2},
            hype_questions=["What is deep learning?", "How does deep learning work?"],
        ),
        Chunk(
            id="chunk3",
            content="Transformers revolutionized NLP.",
            document_id="doc1",
            chunk_index=2,
        ),
    ]


class TestSQLiteDocumentStore:
    @pytest.mark.asyncio
    async def test_add_and_get_document(
        self, store: SQLiteDocumentStore, sample_document: Document
    ) -> None:
        doc_id = await store.add_document(sample_document)
        assert doc_id == "doc1"

        retrieved = await store.get_document("doc1")
        assert retrieved is not None
        assert retrieved.content == sample_document.content
        assert retrieved.metadata.title == "ML Guide"
        assert retrieved.metadata.language == "en"

    @pytest.mark.asyncio
    async def test_get_nonexistent_document(self, store: SQLiteDocumentStore) -> None:
        result = await store.get_document("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_document(
        self, store: SQLiteDocumentStore, sample_document: Document
    ) -> None:
        await store.add_document(sample_document)
        deleted = await store.delete_document("doc1")
        assert deleted is True

        result = await store.get_document("doc1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store: SQLiteDocumentStore) -> None:
        deleted = await store.delete_document("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_update_document(
        self, store: SQLiteDocumentStore, sample_document: Document
    ) -> None:
        await store.add_document(sample_document)
        sample_document.content = "Updated content"
        updated = await store.update_document(sample_document)
        assert updated is True

        retrieved = await store.get_document("doc1")
        assert retrieved is not None
        assert retrieved.content == "Updated content"

    @pytest.mark.asyncio
    async def test_list_documents(self, store: SQLiteDocumentStore) -> None:
        for i in range(5):
            doc = Document(
                id=f"doc{i}",
                content=f"Content {i}",
                metadata=DocumentMetadata(source_id=f"src_{i}", title=f"Doc {i}"),
            )
            await store.add_document(doc)

        docs = await store.list_documents(limit=3)
        assert len(docs) == 3

        all_docs = await store.list_documents(limit=100)
        assert len(all_docs) == 5

    @pytest.mark.asyncio
    async def test_list_documents_with_offset(self, store: SQLiteDocumentStore) -> None:
        for i in range(5):
            doc = Document(
                id=f"doc{i}", content=f"Content {i}", metadata=DocumentMetadata(source_id=f"s{i}")
            )
            await store.add_document(doc)

        page1 = await store.list_documents(limit=2, offset=0)
        page2 = await store.list_documents(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0].id != page2[0].id

    @pytest.mark.asyncio
    async def test_list_documents_with_filter(self, store: SQLiteDocumentStore) -> None:
        doc1 = Document(
            id="d1",
            content="English doc",
            metadata=DocumentMetadata(source_id="s1", language="en"),
        )
        doc2 = Document(
            id="d2",
            content="Korean doc",
            metadata=DocumentMetadata(source_id="s2", language="ko"),
        )
        await store.add_document(doc1)
        await store.add_document(doc2)

        korean_docs = await store.list_documents(filters={"language": "ko"})
        assert len(korean_docs) == 1
        assert korean_docs[0].id == "d2"

    @pytest.mark.asyncio
    async def test_count_documents(self, store: SQLiteDocumentStore) -> None:
        assert await store.count_documents() == 0
        await store.add_document(
            Document(id="d1", content="C1", metadata=DocumentMetadata(source_id="s1"))
        )
        assert await store.count_documents() == 1

    @pytest.mark.asyncio
    async def test_document_exists(
        self, store: SQLiteDocumentStore, sample_document: Document
    ) -> None:
        assert await store.document_exists("test_source_1") is False
        await store.add_document(sample_document)
        assert await store.document_exists("test_source_1") is True


class TestSQLiteChunkStore:
    @pytest.mark.asyncio
    async def test_add_and_get_chunks(
        self,
        store: SQLiteDocumentStore,
        sample_document: Document,
        sample_chunks: list[Chunk],
    ) -> None:
        await store.add_document(sample_document)
        ids = await store.add_chunks(sample_chunks)
        assert len(ids) == 3

        chunks = await store.get_chunks("doc1")
        assert len(chunks) == 3
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1
        assert chunks[2].chunk_index == 2

    @pytest.mark.asyncio
    async def test_get_chunk_by_id(
        self,
        store: SQLiteDocumentStore,
        sample_document: Document,
        sample_chunks: list[Chunk],
    ) -> None:
        await store.add_document(sample_document)
        await store.add_chunks(sample_chunks)

        chunk = await store.get_chunk("chunk2")
        assert chunk is not None
        assert chunk.content == "Deep learning uses neural networks."
        assert chunk.hype_questions == ["What is deep learning?", "How does deep learning work?"]

    @pytest.mark.asyncio
    async def test_chunk_metadata_preserved(
        self,
        store: SQLiteDocumentStore,
        sample_document: Document,
        sample_chunks: list[Chunk],
    ) -> None:
        await store.add_document(sample_document)
        await store.add_chunks(sample_chunks)

        chunk = await store.get_chunk("chunk1")
        assert chunk is not None
        assert chunk.metadata["page"] == 1
        assert chunk.context_prefix == "From ML Guide:"

    @pytest.mark.asyncio
    async def test_count_chunks(
        self,
        store: SQLiteDocumentStore,
        sample_document: Document,
        sample_chunks: list[Chunk],
    ) -> None:
        await store.add_document(sample_document)
        assert await store.count_chunks() == 0
        await store.add_chunks(sample_chunks)
        assert await store.count_chunks() == 3

    @pytest.mark.asyncio
    async def test_cascade_delete(
        self,
        store: SQLiteDocumentStore,
        sample_document: Document,
        sample_chunks: list[Chunk],
    ) -> None:
        await store.add_document(sample_document)
        await store.add_chunks(sample_chunks)
        assert await store.count_chunks() == 3

        await store.delete_document("doc1")
        assert await store.count_chunks() == 0

    @pytest.mark.asyncio
    async def test_get_nonexistent_chunk(self, store: SQLiteDocumentStore) -> None:
        result = await store.get_chunk("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_chunks_for_nonexistent_doc(self, store: SQLiteDocumentStore) -> None:
        chunks = await store.get_chunks("nonexistent")
        assert chunks == []


class TestSQLiteBulkOperations:
    @pytest.mark.asyncio
    async def test_bulk_insert(self, store: SQLiteDocumentStore) -> None:
        doc = Document(id="bulk_doc", content="Bulk", metadata=DocumentMetadata(source_id="bulk"))
        await store.add_document(doc)

        chunks = [
            Chunk(id=f"bc{i}", content=f"Chunk {i}", document_id="bulk_doc", chunk_index=i)
            for i in range(100)
        ]
        ids = await store.add_chunks(chunks)
        assert len(ids) == 100
        assert await store.count_chunks() == 100

    @pytest.mark.asyncio
    async def test_persistence(self, tmp_path: Path) -> None:
        db_path = tmp_path / "persist.db"

        # Write
        store1 = SQLiteDocumentStore(db_path)
        doc = Document(
            id="persist_doc", content="Persistent", metadata=DocumentMetadata(source_id="ps")
        )
        await store1.add_document(doc)
        store1.close()

        # Read in new connection
        store2 = SQLiteDocumentStore(db_path)
        retrieved = await store2.get_document("persist_doc")
        assert retrieved is not None
        assert retrieved.content == "Persistent"
        store2.close()


class TestFilterKeyValidation:
    """Tests for filter key validation to prevent SQL injection."""

    def test_valid_keys(self) -> None:
        from quantumrag.core.storage.backends.sqlite import _validate_filter_key

        assert _validate_filter_key("language") == "language"
        assert _validate_filter_key("source_id") == "source_id"
        assert _validate_filter_key("page123") == "page123"
        assert _validate_filter_key("A_Z_0") == "A_Z_0"

    def test_rejects_sql_injection(self) -> None:
        from quantumrag.core.storage.backends.sqlite import _validate_filter_key

        with pytest.raises(ValueError, match="Invalid filter key"):
            _validate_filter_key("key'); DROP TABLE documents;--")

    def test_rejects_dots(self) -> None:
        from quantumrag.core.storage.backends.sqlite import _validate_filter_key

        with pytest.raises(ValueError, match="Invalid filter key"):
            _validate_filter_key("nested.key")

    def test_rejects_spaces(self) -> None:
        from quantumrag.core.storage.backends.sqlite import _validate_filter_key

        with pytest.raises(ValueError, match="Invalid filter key"):
            _validate_filter_key("has space")

    def test_rejects_special_chars(self) -> None:
        from quantumrag.core.storage.backends.sqlite import _validate_filter_key

        for char in ["$", "'", '"', ";", "-", "/", "\\", "(", ")", "*"]:
            with pytest.raises(ValueError, match="Invalid filter key"):
                _validate_filter_key(f"key{char}val")

    def test_rejects_empty_string(self) -> None:
        from quantumrag.core.storage.backends.sqlite import _validate_filter_key

        with pytest.raises(ValueError, match="Invalid filter key"):
            _validate_filter_key("")

    @pytest.mark.asyncio
    async def test_list_documents_rejects_bad_filter_key(
        self, store: SQLiteDocumentStore
    ) -> None:
        with pytest.raises(ValueError, match="Invalid filter key"):
            await store.list_documents(filters={"bad;key": "value"})
