"""Tantivy-based BM25 full-text search storage."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any, Protocol

from quantumrag.core.errors import StorageError
from quantumrag.core.logging import get_logger
from quantumrag.core.storage.base import BM25SearchResult

logger = get_logger(__name__)


class Tokenizer(Protocol):
    """Minimal tokenizer interface for pre-tokenizing text before BM25 indexing."""

    def tokenize(self, text: str) -> list[str]: ...


class TantivyBM25Store:
    """Tantivy-based implementation of BM25Store."""

    def __init__(self, index_path: str | Path, tokenizer: Tokenizer | None = None) -> None:
        self._index_path = Path(index_path)
        self._index: Any = None
        self._writer: Any = None
        self._tokenizer = tokenizer
        self._initialize()

    def _initialize(self) -> None:
        try:
            import tantivy
        except ImportError:
            raise StorageError(
                "tantivy is not installed",
                suggestion="Install with: pip install quantumrag[all] or pip install tantivy",
            ) from None

        self._index_path.mkdir(parents=True, exist_ok=True)

        schema_builder = tantivy.SchemaBuilder()
        schema_builder.add_text_field("id", stored=True)
        schema_builder.add_text_field("document_id", stored=True)
        schema_builder.add_text_field("content", stored=True, tokenizer_name="default")
        schema_builder.add_text_field("metadata_json", stored=True)
        schema = schema_builder.build()

        self._index = tantivy.Index(schema, path=str(self._index_path))
        logger.debug("Tantivy BM25 store initialized", path=str(self._index_path))

    def _preprocess(self, text: str) -> str:
        """Pre-tokenize text using the configured tokenizer.

        When a tokenizer (e.g. KoreanTokenizer with Kiwi) is set, morphemes
        are joined by spaces so Tantivy's default whitespace tokenizer indexes
        each morpheme as a separate term.  Without a tokenizer the text is
        passed through unchanged.
        """
        if self._tokenizer is None:
            return text
        tokens = self._tokenizer.tokenize(text)
        return " ".join(tokens) if tokens else text

    def _get_writer(self) -> Any:
        if self._writer is None:
            self._writer = self._index.writer(heap_size=50_000_000)
        return self._writer

    async def add_documents(
        self,
        ids: list[str],
        texts: list[str],
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        if not ids:
            return

        metadata = metadata or [{}] * len(ids)
        writer = self._get_writer()

        try:
            import tantivy

            for id_, text, meta in zip(ids, texts, metadata, strict=True):
                writer.add_document(
                    tantivy.Document(
                        id=id_,
                        document_id=meta.get("document_id", ""),
                        content=self._preprocess(text),
                        metadata_json=json.dumps(meta, ensure_ascii=False),
                    )
                )
            writer.commit()
            self._index.reload()
            logger.debug("BM25 documents added", count=len(ids))
        except Exception as e:
            raise StorageError(f"Failed to add BM25 documents: {e}") from e

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[BM25SearchResult]:
        if not query.strip():
            return []

        try:
            searcher = self._index.searcher()
            # Pre-tokenize query (e.g. Korean morphemes) before parsing
            parsed_query = self._index.parse_query(self._preprocess(query), ["content"])

            results = searcher.search(parsed_query, limit=top_k).hits

            search_results = []
            for score, doc_address in results:
                doc = searcher.doc(doc_address)
                doc_id = doc["id"][0] if doc["id"] else ""

                # Apply document_id filter if specified
                if filters and "document_id" in filters:
                    doc_document_id = doc["document_id"][0] if doc["document_id"] else ""
                    if doc_document_id != filters["document_id"]:
                        continue

                meta_str = doc["metadata_json"][0] if doc["metadata_json"] else "{}"
                search_results.append(
                    BM25SearchResult(
                        id=doc_id,
                        score=score,
                        metadata=json.loads(meta_str),
                    )
                )

            return search_results
        except Exception as e:
            logger.warning("BM25 search failed", error=str(e))
            return []

    async def delete(self, ids: list[str]) -> None:
        writer = self._get_writer()
        try:
            for id_ in ids:
                writer.delete_documents("id", id_)
            writer.commit()
            self._index.reload()
        except Exception as e:
            logger.warning("Failed to delete BM25 documents", error=str(e))

    async def delete_by_document(self, document_id: str) -> None:
        writer = self._get_writer()
        try:
            writer.delete_documents("document_id", document_id)
            writer.commit()
            self._index.reload()
        except Exception as e:
            logger.warning("Failed to delete BM25 documents by document", error=str(e))

    async def count(self) -> int:
        try:
            searcher = self._index.searcher()
            return searcher.num_docs
        except Exception:
            return 0

    def close(self) -> None:
        if self._writer:
            with contextlib.suppress(Exception):
                self._writer.commit()
            self._writer = None
