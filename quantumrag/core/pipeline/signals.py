"""Signal emitters — utilities that produce signals for pipeline stages.

Provides helper functions that chunkers, retrievers, and generators
can use to produce and consume signals without tight coupling to
the signal definitions.
"""

from __future__ import annotations

import re

from quantumrag.core.models import Chunk
from quantumrag.core.pipeline.context import (
    BoundaryType,
    ChunkSignal,
    DocumentProfile,
    DomainType,
    InformationType,
    QueryIntent,
    QuerySignal,
    RetrievalHints,
)
from quantumrag.core.utils.text import (
    detect_korean,
    ends_with_terminator,
    has_code,
    has_legal_structure,
    has_list,
    has_table,
    numeric_density,
    starts_mid_sentence,
)

# ---------------------------------------------------------------------------
# Compiled patterns (module-level, compiled once)
# ---------------------------------------------------------------------------

_LIST_ITEM_START_RE = re.compile(r"^\s*\d+[.)]\s+")
_TEMPORAL_RE = re.compile(r"(?:기간별|월별|분기별|연도별|언제|when|timeline)", re.IGNORECASE)
_VERIFICATION_RE = re.compile(r"(?:맞나요|사실인가|정말|진짜|확인|verify|is it true)", re.IGNORECASE)
_CALCULATION_RE = re.compile(r"계산|합계|총|평균|calculate|sum|total|average", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Chunk Signal Emission
# ---------------------------------------------------------------------------

def emit_chunk_signals(
    chunks: list[Chunk],
    document_profile: DocumentProfile | None = None,
) -> list[Chunk]:
    """Analyze and annotate a list of chunks with signals.

    This is the main entry point for chunkers to emit signals.
    It analyzes each chunk's content and relationship to neighbors,
    then writes signal metadata.

    Args:
        chunks: Chunks to annotate (modified in-place).
        document_profile: Optional profile from parent document.

    Returns:
        The same chunks list with signal metadata added.
    """
    if not chunks:
        return chunks

    for i, chunk in enumerate(chunks):
        signal = _analyze_chunk(chunk)

        # Relationship signals: detect continuations
        if i > 0:
            signal.continues_previous = _detects_continuation(
                chunks[i - 1].content, chunk.content
            )
        if i < len(chunks) - 1:
            signal.has_continuation = _detects_continuation(
                chunk.content, chunks[i + 1].content
            )

        # If chunk continues or is continued, it's incomplete
        if signal.continues_previous or signal.has_continuation:
            signal.requires_context = True
            signal.completeness = min(signal.completeness, 0.6)

        # Inherit domain from document profile
        if document_profile:
            signal.domain = document_profile.domain
            signal.language = document_profile.primary_language

        # Write signal to chunk metadata
        chunk.metadata.update(signal.to_metadata())

    return chunks


def _analyze_chunk(chunk: Chunk) -> ChunkSignal:
    """Analyze a single chunk and produce its signal."""
    content = chunk.content
    words = content.split()
    word_count = len(words)

    # Information type detection
    info_type = _detect_chunk_info_type(content)

    # Completeness heuristic
    completeness = _estimate_completeness(content, word_count)

    # Boundary type from existing metadata
    boundary_type = _infer_boundary_type(chunk)

    return ChunkSignal(
        completeness=completeness,
        boundary_type=boundary_type,
        information_type=info_type,
        has_table=has_table(content),
        has_code=has_code(content),
        has_list=has_list(content),
        numeric_density=numeric_density(words),
    )


def _detect_chunk_info_type(content: str) -> InformationType:
    """Detect the dominant information type in a chunk."""
    if has_legal_structure(content):
        return InformationType.LEGAL
    if has_table(content):
        return InformationType.TABULAR
    if has_code(content):
        return InformationType.CODE
    if has_list(content) and content.count("\n") > 3:
        return InformationType.ENUMERATION
    return InformationType.NARRATIVE


def _estimate_completeness(content: str, word_count: int) -> float:
    """Estimate how self-contained a chunk is.

    A complete chunk:
    - Starts with a capital letter or heading/topic indicator
    - Ends with sentence-ending punctuation
    - Has reasonable length
    - Doesn't start with a conjunction or lowercase continuation
    """
    if word_count == 0:
        return 0.0

    score = 1.0

    # Starts mid-sentence (lowercase letter, conjunction)
    if starts_mid_sentence(content):
        score -= 0.3

    # Doesn't end with sentence-ending punctuation
    if not ends_with_terminator(content):
        score -= 0.15

    # Very short chunks are likely fragments
    if word_count < 20:
        score -= 0.2
    elif word_count < 50:
        score -= 0.1

    return max(0.1, min(1.0, round(score, 2)))


def _infer_boundary_type(chunk: Chunk) -> BoundaryType:
    """Infer boundary type from existing chunk metadata."""
    meta = chunk.metadata

    if meta.get("breadcrumb") or meta.get("section"):
        return BoundaryType.STRUCTURAL
    if meta.get("strategy") == "topic_shift":
        return BoundaryType.TOPIC_SHIFT

    return BoundaryType.SIZE_LIMIT


def _detects_continuation(prev_content: str, next_content: str) -> bool:
    """Detect if next_content continues from prev_content.

    Signs of continuation:
    - prev ends without sentence terminator
    - next starts with lowercase or conjunction
    - prev ends with a list item and next starts with one
    """
    prev_stripped = prev_content.strip()
    next_stripped = next_content.strip()

    if not prev_stripped or not next_stripped:
        return False

    # Previous doesn't end with sentence terminator
    prev_ends_incomplete = not ends_with_terminator(prev_content)

    # Next starts mid-sentence
    next_starts_mid = starts_mid_sentence(next_content)

    if prev_ends_incomplete and next_starts_mid:
        return True

    # List continuation: both end/start with list items
    prev_has_list = bool(_LIST_ITEM_START_RE.search(prev_stripped.split("\n")[-1]))
    next_has_list = bool(_LIST_ITEM_START_RE.match(next_stripped))
    return bool(prev_has_list and next_has_list)


# ---------------------------------------------------------------------------
# Query Signal Emission
# ---------------------------------------------------------------------------

def build_query_signal(
    query: str,
    complexity: str = "simple",
    confidence: float = 0.9,
    needs_retrieval: bool = True,
    query_type: str = "factual",
    active_profiles: list[DocumentProfile] | None = None,
) -> QuerySignal:
    """Build a QuerySignal from query analysis and optional document context.

    Combines the basic classification with domain awareness and
    retrieval strategy hints.

    Args:
        query: The user query.
        complexity: Basic complexity level (simple/medium/complex).
        confidence: Classification confidence.
        needs_retrieval: Whether retrieval is needed.
        query_type: Detected query type from router.
        active_profiles: DocumentProfiles from indexed documents.

    Returns:
        Enriched QuerySignal.
    """
    # Map query_type to QueryIntent
    intent_map = {
        "factual": QueryIntent.FACTUAL,
        "comparative": QueryIntent.COMPARATIVE,
        "procedural": QueryIntent.PROCEDURAL,
        "aggregation": QueryIntent.AGGREGATION,
        "analytical": QueryIntent.ANALYTICAL,
        "conditional": QueryIntent.CONDITIONAL,
    }
    intent = intent_map.get(query_type, QueryIntent.FACTUAL)

    # Detect if temporal
    if _TEMPORAL_RE.search(query):
        intent = QueryIntent.TEMPORAL

    # Detect if verification
    if _VERIFICATION_RE.search(query):
        intent = QueryIntent.VERIFICATION

    # Language detection
    is_korean = detect_korean(query)
    language = "ko" if is_korean else "en"

    # Domain from document profiles
    domain = DomainType.GENERAL
    domain_confidence = 0.0
    if active_profiles:
        domain_counts: dict[DomainType, float] = {}
        for p in active_profiles:
            d = p.domain
            domain_counts[d] = domain_counts.get(d, 0) + p.domain_confidence
        if domain_counts:
            domain = max(domain_counts, key=domain_counts.get)  # type: ignore[arg-type]
            domain_confidence = domain_counts[domain] / len(active_profiles)

    # Build retrieval hints
    hints = _build_retrieval_hints(intent, domain, complexity, active_profiles)

    # Output format
    output_format = "prose"
    if intent == QueryIntent.COMPARATIVE:
        output_format = "table"
    elif intent == QueryIntent.PROCEDURAL:
        output_format = "step_by_step"
    elif intent == QueryIntent.AGGREGATION:
        output_format = "list"

    return QuerySignal(
        complexity=complexity,
        confidence=confidence,
        needs_retrieval=needs_retrieval,
        intent=intent,
        domain=domain,
        domain_confidence=domain_confidence,
        language=language,
        is_korean=is_korean,
        retrieval_hints=hints,
        output_format=output_format,
        requires_calculation=bool(_CALCULATION_RE.search(query)),
        requires_comparison=intent == QueryIntent.COMPARATIVE,
    )


def _build_retrieval_hints(
    intent: QueryIntent,
    domain: DomainType,
    complexity: str,
    profiles: list[DocumentProfile] | None,
) -> RetrievalHints:
    """Build retrieval strategy hints from query and document context."""
    hints = RetrievalHints()

    # Intent-based hints
    if intent == QueryIntent.AGGREGATION:
        hints.top_k_multiplier = 2.5
        hints.force_map_reduce = True
    elif intent == QueryIntent.COMPARATIVE:
        hints.top_k_multiplier = 2.0
        hints.force_sibling_expansion = True
    elif intent == QueryIntent.TEMPORAL:
        hints.top_k_multiplier = 1.5
    elif intent == QueryIntent.VERIFICATION:
        hints.top_k_multiplier = 1.5  # Multiple sources for cross-check

    # Domain-based hints
    if domain == DomainType.LEGAL:
        hints.prefer_bm25 = True
        hints.skip_compression = True  # Never compress legal text
        hints.fusion_weights = {"original": 0.2, "hype": 0.2, "bm25": 0.6}
    elif domain == DomainType.FINANCIAL:
        hints.fusion_weights = {"original": 0.3, "hype": 0.3, "bm25": 0.4}
    elif domain == DomainType.SUPPORT:
        hints.prefer_semantic = False
        hints.fusion_weights = {"original": 0.2, "hype": 0.6, "bm25": 0.2}

    # Complexity-based hints
    if complexity == "simple":
        hints.skip_rerank = True
        hints.skip_compression = True

    # Profile-based fusion weight override
    if profiles:
        profile_weights: dict[str, list[float]] = {}
        for p in profiles:
            for key, val in p.recommended_fusion_weights.items():
                profile_weights.setdefault(key, []).append(val)
        if profile_weights and not hints.fusion_weights:
            hints.fusion_weights = {
                k: round(sum(v) / len(v), 2)
                for k, v in profile_weights.items()
            }

    return hints


# ---------------------------------------------------------------------------
# Signal Reading Utilities
# ---------------------------------------------------------------------------

def read_chunk_signal(chunk: Chunk) -> ChunkSignal | None:
    """Read signal from a chunk's metadata."""
    return ChunkSignal.from_metadata(chunk.metadata)


def chunk_needs_expansion(chunk: Chunk) -> bool:
    """Check if a chunk's signal indicates it needs sibling expansion."""
    signal = read_chunk_signal(chunk)
    if signal is None:
        return False
    return signal.requires_context or signal.completeness < 0.5


def chunk_should_skip_compression(chunk: Chunk) -> bool:
    """Check if a chunk should not be compressed."""
    signal = read_chunk_signal(chunk)
    if signal is None:
        return False
    return (
        signal.information_type in (InformationType.TABULAR, InformationType.LEGAL, InformationType.CODE)
        or signal.has_table
    )
