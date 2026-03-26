"""Tests for batch chunk retrieval (E2.3 N+1 query fix)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantumrag.core.models import Chunk, Document, DocumentMetadata
from quantumrag.core.storage.backends.sqlite import SQLiteDocumentStore


@pytest.fixture()
async def store(tmp_path: Path) -> SQLiteDocumentStore:
    s = SQLiteDocumentStore(db_path=tmp_path / "test.db")
    doc = Document(
        id="doc-1",
        content="Test document",
        metadata=DocumentMetadata(source="test", source_id="t1"),
    )
    await s.add_document(doc)
    return s


def _make_chunk(chunk_id: str, doc_id: str = "doc-1", index: int = 0) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=doc_id,
        chunk_index=index,
        content=f"Content of {chunk_id}",
        metadata={"title": "Test"},
    )


class TestGetChunksBatch:
    @pytest.mark.asyncio
    async def test_batch_returns_all_found(self, store: SQLiteDocumentStore) -> None:
        chunks = [_make_chunk(f"c-{i}", index=i) for i in range(5)]
        await store.add_chunks(chunks)

        result = await store.get_chunks_batch([f"c-{i}" for i in range(5)])
        assert len(result) == 5
        for i in range(5):
            assert f"c-{i}" in result
            assert result[f"c-{i}"].content == f"Content of c-{i}"

    @pytest.mark.asyncio
    async def test_batch_skips_missing(self, store: SQLiteDocumentStore) -> None:
        chunks = [_make_chunk("c-0"), _make_chunk("c-1", index=1)]
        await store.add_chunks(chunks)

        result = await store.get_chunks_batch(["c-0", "c-missing", "c-1"])
        assert len(result) == 2
        assert "c-0" in result
        assert "c-1" in result
        assert "c-missing" not in result

    @pytest.mark.asyncio
    async def test_batch_empty_list(self, store: SQLiteDocumentStore) -> None:
        result = await store.get_chunks_batch([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_batch_single_chunk(self, store: SQLiteDocumentStore) -> None:
        await store.add_chunks([_make_chunk("c-only")])
        result = await store.get_chunks_batch(["c-only"])
        assert len(result) == 1
        assert result["c-only"].content == "Content of c-only"
