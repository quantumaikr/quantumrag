"""Pipeline context and signal definitions.

Provides the signal infrastructure for cross-module communication.
Each signal type captures domain-specific knowledge that would otherwise
be lost at module boundaries.

Design principles:
- All signals are optional: if absent, modules fall back to current behavior.
- Signals are additive: each stage can read upstream signals and add its own.
- Signals are serializable: stored in chunk/document metadata for persistence.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class InformationType(str, Enum):
    """The dominant information type within a chunk or document."""

    NARRATIVE = "narrative"  # Prose, paragraphs, flowing text
    TABULAR = "tabular"  # Tables, key-value pairs, structured data
    ENUMERATION = "enumeration"  # Lists, bullet points, numbered items
    CODE = "code"  # Source code, config files, CLI output
    MIXED = "mixed"  # Combination of the above
    LEGAL = "legal"  # Clauses, articles, statutory language
    CONVERSATIONAL = "conversational"  # Dialog, Q&A, chat logs


class BoundaryType(str, Enum):
    """Why a chunk boundary was placed here."""

    TOPIC_SHIFT = "topic_shift"  # Vocabulary overlap dropped
    SIZE_LIMIT = "size_limit"  # Hit max chunk size
    STRUCTURAL = "structural"  # Heading / section boundary
    SENTENCE = "sentence"  # Sentence-level split (fallback)
    PARAGRAPH = "paragraph"  # Paragraph boundary
    TABLE = "table"  # Table unit boundary
    MANUAL = "manual"  # Explicit user-defined boundary


class DomainType(str, Enum):
    """Document / query domain classification."""

    GENERAL = "general"
    LEGAL = "legal"
    FINANCIAL = "financial"
    MEDICAL = "medical"
    TECHNICAL = "technical"
    SUPPORT = "support"  # Customer support / FAQ
    ACADEMIC = "academic"  # Research papers, theses


class QueryIntent(str, Enum):
    """Fine-grained query intent classification."""

    FACTUAL = "factual"  # Simple fact lookup
    COMPARATIVE = "comparative"  # Compare two or more items
    PROCEDURAL = "procedural"  # How-to, step-by-step
    AGGREGATION = "aggregation"  # Count, sum, list all
    ANALYTICAL = "analytical"  # Why, reason, cause-effect
    CONDITIONAL = "conditional"  # What-if, hypothetical
    TEMPORAL = "temporal"  # Time-based, chronological
    VERIFICATION = "verification"  # Fact-check, confirm/deny


# ---------------------------------------------------------------------------
# Document Profile — produced at ingest time
# ---------------------------------------------------------------------------


class DocumentProfile(BaseModel):
    """Structural and semantic profile of a document.

    Produced by DocumentProfiler at ingest time. Stored in document metadata
    and propagated to all chunks from that document.

    This is the "Index-Heavy" investment: spend compute once at ingest to
    avoid repeated analysis at query time.
    """

    # Structure
    structure_type: str = "flat"  # hierarchical, flat, tabular, mixed
    heading_depth: int = 0  # Max heading level found (0 = no headings)
    paragraph_count: int = 0
    table_count: int = 0
    list_count: int = 0  # Bullet/numbered lists
    code_block_count: int = 0

    # Content characteristics
    information_type: InformationType = InformationType.NARRATIVE
    avg_sentence_length: float = 0.0
    vocabulary_richness: float = 0.0  # Unique words / total words

    # Domain signals
    domain: DomainType = DomainType.GENERAL
    domain_confidence: float = 0.0  # 0.0-1.0
    domain_vocabulary: list[str] = Field(default_factory=list)  # Top domain terms

    # Language
    primary_language: str = "unknown"  # ko, en, ja, etc.
    language_mix: dict[str, float] = Field(default_factory=dict)  # e.g. {"ko": 0.7, "en": 0.3}

    # Density metrics
    information_density: float = 0.0  # Non-whitespace ratio
    numeric_density: float = 0.0  # Ratio of tokens that are numbers

    # Recommended strategies (hints, not mandates)
    recommended_chunking: str = "auto"
    recommended_fusion_weights: dict[str, float] = Field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        """Serialize to a flat dict suitable for chunk/document metadata."""
        return {
            "profile_structure": self.structure_type,
            "profile_domain": self.domain.value,
            "profile_domain_confidence": self.domain_confidence,
            "profile_info_type": self.information_type.value,
            "profile_language": self.primary_language,
            "profile_numeric_density": self.numeric_density,
            "profile_heading_depth": self.heading_depth,
            "profile_table_count": self.table_count,
        }


# ---------------------------------------------------------------------------
# Chunk Signal — produced per chunk by chunkers
# ---------------------------------------------------------------------------


class ChunkSignal(BaseModel):
    """Per-chunk signal metadata produced by chunkers.

    Describes characteristics of the chunk that downstream modules
    (retriever, compressor, generator) can use to make better decisions.

    Stored in chunk.metadata["signal"] for persistence.
    """

    # Chunk quality signals
    completeness: float = 1.0  # 0.0 = fragment, 1.0 = self-contained
    boundary_type: BoundaryType = BoundaryType.SIZE_LIMIT
    information_type: InformationType = InformationType.NARRATIVE

    # Relationship signals
    requires_context: bool = False  # Needs adjacent chunks for full meaning
    continues_previous: bool = False  # Starts mid-thought from previous chunk
    has_continuation: bool = False  # Continues into next chunk

    # Content signals
    has_table: bool = False
    has_code: bool = False
    has_list: bool = False
    numeric_density: float = 0.0  # Ratio of numeric tokens

    # Domain from parent document
    domain: DomainType = DomainType.GENERAL
    language: str = "unknown"

    def to_metadata(self) -> dict[str, Any]:
        """Serialize to a flat dict for chunk.metadata."""
        return {
            "signal_completeness": self.completeness,
            "signal_boundary": self.boundary_type.value,
            "signal_info_type": self.information_type.value,
            "signal_requires_context": self.requires_context,
            "signal_continues_previous": self.continues_previous,
            "signal_has_continuation": self.has_continuation,
            "signal_has_table": self.has_table,
            "signal_has_code": self.has_code,
            "signal_has_list": self.has_list,
            "signal_numeric_density": self.numeric_density,
            "signal_domain": self.domain.value,
            "signal_language": self.language,
        }

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> ChunkSignal | None:
        """Reconstruct from chunk.metadata, or None if no signal data."""
        if "signal_completeness" not in metadata:
            return None
        return cls(
            completeness=metadata.get("signal_completeness", 1.0),
            boundary_type=BoundaryType(metadata.get("signal_boundary", "size_limit")),
            information_type=InformationType(metadata.get("signal_info_type", "narrative")),
            requires_context=metadata.get("signal_requires_context", False),
            continues_previous=metadata.get("signal_continues_previous", False),
            has_continuation=metadata.get("signal_has_continuation", False),
            has_table=metadata.get("signal_has_table", False),
            has_code=metadata.get("signal_has_code", False),
            has_list=metadata.get("signal_has_list", False),
            numeric_density=metadata.get("signal_numeric_density", 0.0),
            domain=DomainType(metadata.get("signal_domain", "general")),
            language=metadata.get("signal_language", "unknown"),
        )


# ---------------------------------------------------------------------------
# Retrieval Hints — strategy recommendations for the retriever
# ---------------------------------------------------------------------------


class RetrievalHints(BaseModel):
    """Strategy hints that influence retrieval behavior.

    Produced by QuerySignal or DocumentProfile. The retriever reads these
    to adjust fusion weights, top_k, compression, etc.
    """

    fusion_weights: dict[str, float] | None = None  # Override default weights
    top_k_multiplier: float = 1.0  # Scale the base top_k
    skip_compression: bool = False  # Don't compress (e.g., legal docs)
    skip_rerank: bool = False  # Skip reranking (e.g., simple queries)
    prefer_bm25: bool = False  # Keyword-exact matching priority
    prefer_semantic: bool = False  # Embedding similarity priority
    force_sibling_expansion: bool = False  # Always expand siblings
    force_map_reduce: bool = False  # Use map-reduce pipeline


# ---------------------------------------------------------------------------
# Query Signal — enriched query classification
# ---------------------------------------------------------------------------


class QuerySignal(BaseModel):
    """Enriched query classification with domain awareness.

    Extends the basic SIMPLE/MEDIUM/COMPLEX classification with intent,
    domain, and retrieval strategy hints.
    """

    # Basic classification (compatible with existing QueryClassification)
    complexity: str = "simple"  # simple, medium, complex
    confidence: float = 0.9
    needs_retrieval: bool = True

    # Enriched classification
    intent: QueryIntent = QueryIntent.FACTUAL
    domain: DomainType = DomainType.GENERAL
    domain_confidence: float = 0.0

    # Language detection
    language: str = "auto"
    is_korean: bool = False

    # Retrieval hints derived from query analysis
    retrieval_hints: RetrievalHints = Field(default_factory=RetrievalHints)

    # Generation hints
    output_format: str = "prose"  # prose, table, list, step_by_step
    requires_calculation: bool = False
    requires_comparison: bool = False


# ---------------------------------------------------------------------------
# Pipeline Context — the shared bus flowing through all stages
# ---------------------------------------------------------------------------


class PipelineContext(BaseModel):
    """Shared context that flows through the entire RAG pipeline.

    Created at the start of each query (or ingest). Each pipeline stage
    can read context from upstream stages and write its own signals.

    The PipelineContext acts as a "signal bus" — it doesn't control execution,
    but carries rich metadata that enables better decisions at each stage.
    """

    # Identity
    pipeline_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = Field(default_factory=time.time)

    # Document profile (set during ingest, available during query if cached)
    document_profiles: dict[str, DocumentProfile] = Field(default_factory=dict)

    # Query signal (set during query preprocessing)
    query_signal: QuerySignal | None = None

    # Active signals from current pipeline run
    active_domain: DomainType = DomainType.GENERAL
    active_language: str = "auto"

    # Accumulated hints (merged from document profiles + query signal)
    retrieval_hints: RetrievalHints = Field(default_factory=RetrievalHints)

    # Signal log for observability
    signal_log: list[dict[str, Any]] = Field(default_factory=list)

    def log_signal(self, stage: str, signal_type: str, **data: Any) -> None:
        """Record a signal emission for tracing."""
        self.signal_log.append(
            {
                "stage": stage,
                "type": signal_type,
                "timestamp": time.time(),
                **data,
            }
        )

    def merge_retrieval_hints(self, hints: RetrievalHints) -> None:
        """Merge additional hints into the accumulated retrieval hints.

        Later hints override earlier ones for scalar values.
        Fusion weights are averaged if both present.
        """
        current = self.retrieval_hints

        if hints.fusion_weights:
            if current.fusion_weights:
                # Average the weights
                merged: dict[str, float] = {}
                all_keys = set(current.fusion_weights) | set(hints.fusion_weights)
                for key in all_keys:
                    v1 = current.fusion_weights.get(key, 0.0)
                    v2 = hints.fusion_weights.get(key, 0.0)
                    merged[key] = (v1 + v2) / 2
                current.fusion_weights = merged
            else:
                current.fusion_weights = dict(hints.fusion_weights)

        # Take the larger multiplier (more conservative)
        if hints.top_k_multiplier > current.top_k_multiplier:
            current.top_k_multiplier = hints.top_k_multiplier

        # Boolean flags: True wins (additive)
        if hints.skip_compression:
            current.skip_compression = True
        if hints.skip_rerank:
            current.skip_rerank = True
        if hints.prefer_bm25:
            current.prefer_bm25 = True
        if hints.prefer_semantic:
            current.prefer_semantic = True
        if hints.force_sibling_expansion:
            current.force_sibling_expansion = True
        if hints.force_map_reduce:
            current.force_map_reduce = True

    def get_effective_fusion_weights(
        self, default: dict[str, float] | None = None
    ) -> dict[str, float]:
        """Get the effective fusion weights considering all hints.

        Falls back to default if no hints override.
        """
        if self.retrieval_hints.fusion_weights:
            return self.retrieval_hints.fusion_weights

        if default:
            return dict(default)

        return {"original": 0.4, "hype": 0.35, "bm25": 0.25}

    def get_effective_top_k(self, base_top_k: int) -> int:
        """Get the effective top_k considering multiplier hints."""
        return max(1, int(base_top_k * self.retrieval_hints.top_k_multiplier))
