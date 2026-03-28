"""Fact Index — in-memory structured data index for Fact-First retrieval.

At ingest time, fact_extractor extracts structured facts (customer contracts,
financial metrics, security issues, etc.) from each chunk.  This module
collects those facts into a queryable in-memory index so that structured
questions can be answered directly from verified data, bypassing the
inherent ambiguity of text-chunk-based retrieval.

Usage in the pipeline:
1. After ingest, call ``build_from_chunks(all_chunks)`` to populate.
2. At query time, call ``query()`` with type and optional filters.
3. The engine can inject fact query results into the generation context
   *before* text chunks, giving the LLM authoritative data to anchor on.

This is the foundation of the "Fact-First RAG" paradigm: structured facts
are the primary answer source, text chunks are supplementary context.
"""

from __future__ import annotations

from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk

logger = get_logger("quantumrag.fact_index")


class FactIndex:
    """In-memory index of structured facts extracted at ingest time."""

    def __init__(self) -> None:
        self._facts: list[dict[str, Any]] = []
        self._by_type: dict[str, list[dict[str, Any]]] = {}
        self._by_entity: dict[str, list[dict[str, Any]]] = {}
        self._by_chunk: dict[str, list[dict[str, Any]]] = {}

    @property
    def total_facts(self) -> int:
        return len(self._facts)

    @property
    def fact_types(self) -> list[str]:
        return sorted(self._by_type.keys())

    def build_from_chunks(self, chunks: list[Chunk]) -> None:
        """Populate the index from chunks that have metadata["facts"]."""
        self._facts.clear()
        self._by_type.clear()
        self._by_entity.clear()
        self._by_chunk.clear()

        for chunk in chunks:
            facts = chunk.metadata.get("facts")
            if not facts:
                continue
            for f in facts:
                record = {**f, "_chunk_id": chunk.id, "_document_id": chunk.document_id}
                self._facts.append(record)

                ft = f.get("type", "unknown")
                self._by_type.setdefault(ft, []).append(record)

                entity = f.get("entity") or f.get("customer") or f.get("team")
                if entity:
                    self._by_entity.setdefault(entity, []).append(record)

                self._by_chunk.setdefault(chunk.id, []).append(record)

        if self._facts:
            logger.info(
                "fact_index_built",
                total_facts=len(self._facts),
                types=list(self._by_type.keys()),
                entities=len(self._by_entity),
            )

    def query(self, fact_type: str, **filters: Any) -> list[dict[str, Any]]:
        """Query facts by type with optional attribute filters.

        Examples:
            query("customer_contract", deployment="온프레미스")
            query("security_issue", severity="Critical")
            query("finance_metric", metric="ARR")
        """
        candidates = self._by_type.get(fact_type, [])
        if not filters:
            return list(candidates)
        return [f for f in candidates if all(f.get(k) == v for k, v in filters.items())]

    def query_entity(self, entity: str) -> list[dict[str, Any]]:
        """Look up all facts related to a specific entity."""
        return list(self._by_entity.get(entity, []))

    def get_all_of_type(self, fact_type: str) -> list[dict[str, Any]]:
        """Return all facts of a given type (unfiltered)."""
        return list(self._by_type.get(fact_type, []))

    def get_chunk_facts(self, chunk_id: str) -> list[dict[str, Any]]:
        """Return facts associated with a specific chunk."""
        return list(self._by_chunk.get(chunk_id, []))

    def format_facts_as_context(
        self,
        facts: list[dict[str, Any]],
        label: str = "검증된 구조화 데이터",
    ) -> str:
        """Format a list of facts into a text block for LLM context injection.

        This produces a structured, unambiguous representation that the LLM
        can rely on without needing to parse raw text.
        """
        if not facts:
            return ""

        lines = [f"[{label}]"]
        for f in facts:
            ft = f.get("type", "")
            if ft == "customer_contract":
                line = f"  | 고객: {f.get('customer', 'N/A')}"
                line += f" | 등급: {f.get('tier', 'N/A')}"
                if f.get("deployment"):
                    line += f" | 배포: {f['deployment']}"
                lines.append(line)
            elif ft == "finance_metric":
                lines.append(f"  | {f.get('metric', 'N/A')}: {f.get('value', 'N/A')}")
            elif ft == "fund_allocation":
                lines.append(f"  | {f.get('item', 'N/A')}: {f.get('value', 'N/A')}원")
            elif ft == "security_issue":
                lines.append(
                    f"  | {f.get('entity', 'N/A')}: "
                    f"심각도={f.get('severity', 'N/A')}, "
                    f"상태={f.get('status', 'N/A')}"
                )
            elif ft == "team_info":
                lines.append(f"  | {f.get('team', 'N/A')}: {f.get('headcount', 'N/A')}명")
            elif ft == "team_leader":
                lines.append(f"  | {f.get('team', 'N/A')} 팀장: {f.get('leader', 'N/A')}")
            elif ft == "patent":
                lines.append(f"  | {f.get('entity', 'N/A')}: 상태={f.get('status', 'N/A')}")
            elif ft == "product_version":
                lines.append(f"  | {f.get('version', 'N/A')} ({f.get('release_date', 'N/A')})")
            else:
                # Generic fallback
                display = {k: v for k, v in f.items() if not k.startswith("_")}
                lines.append(f"  | {display}")

        if len(lines) <= 1:
            return ""
        return "\n".join(lines)
