"""Entity-Centric Reverse Index — entity → chunk_ids mapping.

Enables complete recall for entity-based queries by building a reverse
index from entities and attributes to chunk IDs. At query time, detected
entity patterns trigger reverse index lookups that guarantee all relevant
chunks are in the candidate set.

Index types:
    - Pattern entities: SEC-001, PAT-003, v2.5.0
    - Attribute entities: severity:Critical, status:완료, team:AI팀
    - Named entities: company names, person names
"""

from __future__ import annotations

from collections import defaultdict

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk

logger = get_logger("quantumrag.entity_index")

# Severity hierarchy for range queries
_SEVERITY_ORDER = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}


class EntityIndex:
    """In-memory entity → chunk_id reverse index."""

    def __init__(self) -> None:
        # entity_key → set of chunk_ids
        self._index: dict[str, set[str]] = defaultdict(set)
        # chunk_id → document_id (for document-level expansion)
        self._chunk_to_doc: dict[str, str] = {}

    def build(self, chunks: list[Chunk]) -> None:
        """Build the reverse index from a list of chunks."""
        for chunk in chunks:
            self._chunk_to_doc[chunk.id] = chunk.document_id
            facts = chunk.metadata.get("facts", [])

            for fact in facts:
                ftype = fact.get("type", "")
                entity = fact.get("entity", "")

                # Index by entity ID
                if entity:
                    self._index[entity.upper()].add(chunk.id)
                    self._index[f"type:{ftype}"].add(chunk.id)

                # Index by attributes
                for attr_key in ("severity", "status", "tier", "deployment"):
                    attr_val = fact.get(attr_key)
                    if attr_val:
                        norm_val = attr_val.replace(" ", "")
                        self._index[f"{attr_key}:{norm_val}"].add(chunk.id)

                # Index severity hierarchy (Critical → also indexed under High이상)
                severity = fact.get("severity")
                if severity and severity in _SEVERITY_ORDER:
                    level = _SEVERITY_ORDER[severity]
                    for sev_name, sev_level in _SEVERITY_ORDER.items():
                        if sev_level <= level:
                            self._index[f"severity_gte:{sev_name}"].add(chunk.id)

                # Index inventors
                inventors = fact.get("inventors", [])
                for inv in inventors:
                    self._index[f"person:{inv}"].add(chunk.id)

                # Index customer names
                customer = fact.get("customer")
                if customer:
                    self._index[f"customer:{customer}"].add(chunk.id)

                # Index fund allocations
                if ftype == "fund_allocation":
                    self._index["type:fund_allocation"].add(chunk.id)
                    item = fact.get("item", "")
                    if item:
                        self._index[f"fund_item:{item}"].add(chunk.id)

            # Also index resolution-level chunks
            resolution = chunk.metadata.get("resolution")
            if resolution:
                self._index[f"resolution:{resolution}"].add(chunk.id)

        total_entries = sum(len(v) for v in self._index.values())
        logger.info(
            "entity_index_built",
            unique_keys=len(self._index),
            total_entries=total_entries,
            chunks_indexed=len(self._chunk_to_doc),
        )

    def lookup(self, key: str) -> set[str]:
        """Look up chunk IDs by entity key."""
        # Prefixed keys (type:X, severity_gte:X) use mixed case; entity IDs use upper
        if ":" in key:
            return set(self._index.get(key, set()))
        return set(self._index.get(key.upper(), set()))

    def lookup_attribute(self, attr: str, value: str) -> set[str]:
        """Look up chunk IDs by attribute key-value pair."""
        return set(self._index.get(f"{attr}:{value.replace(' ', '')}", set()))

    def lookup_severity_gte(self, min_severity: str) -> set[str]:
        """Look up chunk IDs with severity >= min_severity."""
        return set(self._index.get(f"severity_gte:{min_severity}", set()))

    def lookup_combined(
        self,
        entity_keys: list[str] | None = None,
        attributes: dict[str, str] | None = None,
        severity_gte: str | None = None,
    ) -> set[str]:
        """Look up chunk IDs matching ALL given criteria (intersection)."""
        result_sets: list[set[str]] = []

        if entity_keys:
            for key in entity_keys:
                matches = self.lookup(key)
                if matches:
                    result_sets.append(matches)

        if attributes:
            for attr, val in attributes.items():
                matches = self.lookup_attribute(attr, val)
                if matches:
                    result_sets.append(matches)

        if severity_gte:
            matches = self.lookup_severity_gte(severity_gte)
            if matches:
                result_sets.append(matches)

        if not result_sets:
            return set()

        # Intersection of all criteria
        result = result_sets[0]
        for s in result_sets[1:]:
            result = result & s

        return result

    def get_document_chunks(self, chunk_id: str) -> set[str]:
        """Get all chunk IDs from the same document as the given chunk."""
        doc_id = self._chunk_to_doc.get(chunk_id)
        if not doc_id:
            return set()
        return {cid for cid, did in self._chunk_to_doc.items() if did == doc_id}

    @property
    def size(self) -> int:
        return len(self._index)
