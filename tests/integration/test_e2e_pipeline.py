"""End-to-end integration tests for the ingest -> query pipeline (E5.1).

Uses mock LLM/Embedding providers to avoid external API dependencies.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantumrag.core.config import QuantumRAGConfig
from quantumrag.core.engine import Engine
from quantumrag.core.models import Chunk

# ---------------------------------------------------------------------------
# Mock providers
# ---------------------------------------------------------------------------


def _mock_embedding_provider() -> MagicMock:
    """Create a mock embedding provider returning deterministic vectors."""
    provider = AsyncMock()
    provider.dimensions = 8

    async def embed_query(text: str) -> list[float]:
        # Deterministic vector based on text hash
        h = hash(text) % 1000
        return [float(h % (i + 1)) / 100.0 for i in range(8)]

    async def embed_batch(texts: list[str]) -> list[list[float]]:
        return [await embed_query(t) for t in texts]

    provider.embed_query = embed_query
    provider.embed_batch = embed_batch
    return provider


def _mock_llm_provider() -> MagicMock:
    """Create a mock LLM that returns canned answers."""
    provider = AsyncMock()

    async def generate(prompt: str, **kwargs):
        resp = MagicMock()
        resp.text = "The revenue was $10 million in Q4 2025."
        resp.tokens_in = 50
        resp.tokens_out = 20
        resp.model = "mock-model"
        resp.estimated_cost = 0.001
        resp.latency_ms = 10.0
        return resp

    async def generate_structured(prompt: str, **kwargs):
        if "hypothetical" in prompt.lower() or "question" in prompt.lower():
            return {"questions": ["What was the revenue?", "How much was Q4?"]}
        if "classify" in prompt.lower() or "complexity" in prompt.lower():
            return {"classification": "simple", "confidence": 0.9}
        return {"answer": "The revenue was $10 million.", "confidence": 0.85}

    provider.generate = generate
    provider.generate_structured = generate_structured
    return provider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture()
def engine(data_dir: Path) -> Engine:
    config = QuantumRAGConfig.default(storage={"data_dir": str(data_dir)})
    mock_doc_store = AsyncMock()
    mock_doc_store.count_documents = AsyncMock(return_value=0)
    mock_doc_store.count_chunks = AsyncMock(return_value=0)
    mock_doc_store.document_exists = AsyncMock(return_value=False)
    mock_doc_store.add_document = AsyncMock(return_value="doc-1")
    mock_doc_store.add_chunks = AsyncMock(return_value=["c-1", "c-2"])

    eng = Engine(config=config, document_store=mock_doc_store)
    return eng


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestE2EPipeline:
    def test_engine_creates_with_config(self, data_dir: Path) -> None:
        """Engine initializes successfully with default config."""
        config = QuantumRAGConfig.default(storage={"data_dir": str(data_dir)})
        engine = Engine(config=config)
        status = engine.status()
        assert "documents" in status

    def test_engine_status_with_injected_store(self, engine: Engine) -> None:
        """Engine.status() works with injected mock store."""
        status = engine.status()
        assert status["documents"] == 0
        assert status["chunks"] == 0

    def test_engine_with_empty_index_returns_no_results(self, data_dir: Path) -> None:
        """Query against empty index returns appropriate response."""
        config = QuantumRAGConfig.default(storage={"data_dir": str(data_dir)})
        mock_doc_store = AsyncMock()
        mock_doc_store.count_documents = AsyncMock(return_value=0)
        mock_doc_store.count_chunks = AsyncMock(return_value=0)

        engine = Engine(config=config, document_store=mock_doc_store)
        status = engine.status()
        assert status["documents"] == 0


class TestDocumentStoreIntegration:
    @pytest.mark.asyncio
    async def test_sqlite_store_roundtrip(self, data_dir: Path) -> None:
        """SQLite store can add and retrieve documents."""
        from quantumrag.core.models import Document, DocumentMetadata
        from quantumrag.core.storage.backends.sqlite import SQLiteDocumentStore

        store = SQLiteDocumentStore(db_path=data_dir / "test.db")

        doc = Document(
            id="test-doc-1",
            content="The Q4 2025 revenue was $10 million, an increase of 15% YoY.",
            metadata=DocumentMetadata(source="test", source_id="test-1"),
        )
        await store.add_document(doc)

        chunks = [
            Chunk(
                id="c-1",
                document_id="test-doc-1",
                chunk_index=0,
                content="The Q4 2025 revenue was $10 million.",
                metadata={"title": "Financial Report"},
            ),
            Chunk(
                id="c-2",
                document_id="test-doc-1",
                chunk_index=1,
                content="An increase of 15% year-over-year.",
                metadata={"title": "Financial Report"},
            ),
        ]
        await store.add_chunks(chunks)

        # Verify roundtrip
        retrieved = await store.get_document("test-doc-1")
        assert retrieved is not None
        assert "revenue" in retrieved.content

        retrieved_chunks = await store.get_chunks("test-doc-1")
        assert len(retrieved_chunks) == 2

        # Batch retrieval
        batch = await store.get_chunks_batch(["c-1", "c-2", "c-missing"])
        assert len(batch) == 2
        assert "c-1" in batch
        assert "c-2" in batch

        assert await store.count_documents() == 1
        assert await store.count_chunks() == 2

        store.close()
