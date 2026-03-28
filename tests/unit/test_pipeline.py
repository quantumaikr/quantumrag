"""Tests for the pipeline context and signal system."""

from __future__ import annotations

import pytest

from quantumrag.core.models import Chunk, Document, DocumentMetadata
from quantumrag.core.pipeline.context import (
    BoundaryType,
    ChunkSignal,
    DocumentProfile,
    DomainType,
    InformationType,
    PipelineContext,
    QueryIntent,
    QuerySignal,
    RetrievalHints,
)
from quantumrag.core.pipeline.profiler import DocumentProfiler
from quantumrag.core.pipeline.signals import (
    build_query_signal,
    chunk_needs_expansion,
    chunk_should_skip_compression,
    emit_chunk_signals,
    read_chunk_signal,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(content: str, title: str = "Test Doc") -> Document:
    return Document(content=content, metadata=DocumentMetadata(title=title))


def _make_chunk(content: str, doc_id: str = "doc1", index: int = 0, **meta: object) -> Chunk:
    return Chunk(content=content, document_id=doc_id, chunk_index=index, metadata=dict(meta))


# ===========================================================================
# PipelineContext Tests
# ===========================================================================


class TestPipelineContext:
    def test_creation(self) -> None:
        ctx = PipelineContext()
        assert ctx.pipeline_id
        assert ctx.created_at > 0
        assert ctx.active_domain == DomainType.GENERAL

    def test_log_signal(self) -> None:
        ctx = PipelineContext()
        ctx.log_signal("test_stage", "test_signal", key="value")
        assert len(ctx.signal_log) == 1
        assert ctx.signal_log[0]["stage"] == "test_stage"
        assert ctx.signal_log[0]["key"] == "value"

    def test_merge_retrieval_hints_boolean_flags(self) -> None:
        ctx = PipelineContext()
        assert not ctx.retrieval_hints.skip_compression

        hints = RetrievalHints(skip_compression=True, prefer_bm25=True)
        ctx.merge_retrieval_hints(hints)
        assert ctx.retrieval_hints.skip_compression
        assert ctx.retrieval_hints.prefer_bm25

    def test_merge_retrieval_hints_top_k_multiplier(self) -> None:
        ctx = PipelineContext()
        ctx.merge_retrieval_hints(RetrievalHints(top_k_multiplier=1.5))
        ctx.merge_retrieval_hints(RetrievalHints(top_k_multiplier=2.0))
        assert ctx.retrieval_hints.top_k_multiplier == 2.0

    def test_merge_retrieval_hints_fusion_weights(self) -> None:
        ctx = PipelineContext()
        ctx.merge_retrieval_hints(RetrievalHints(fusion_weights={"original": 0.6, "bm25": 0.4}))
        assert ctx.retrieval_hints.fusion_weights == {"original": 0.6, "bm25": 0.4}

        # Merge another set — averages
        ctx.merge_retrieval_hints(RetrievalHints(fusion_weights={"original": 0.2, "bm25": 0.8}))
        assert ctx.retrieval_hints.fusion_weights["original"] == pytest.approx(0.4)
        assert ctx.retrieval_hints.fusion_weights["bm25"] == pytest.approx(0.6)

    def test_get_effective_fusion_weights_default(self) -> None:
        ctx = PipelineContext()
        weights = ctx.get_effective_fusion_weights()
        assert weights == {"original": 0.4, "hype": 0.35, "bm25": 0.25}

    def test_get_effective_fusion_weights_override(self) -> None:
        ctx = PipelineContext()
        ctx.merge_retrieval_hints(
            RetrievalHints(fusion_weights={"original": 0.1, "hype": 0.1, "bm25": 0.8})
        )
        weights = ctx.get_effective_fusion_weights()
        assert weights["bm25"] == 0.8

    def test_get_effective_top_k(self) -> None:
        ctx = PipelineContext()
        assert ctx.get_effective_top_k(5) == 5

        ctx.merge_retrieval_hints(RetrievalHints(top_k_multiplier=2.0))
        assert ctx.get_effective_top_k(5) == 10

    def test_get_effective_top_k_never_zero(self) -> None:
        ctx = PipelineContext()
        ctx.merge_retrieval_hints(RetrievalHints(top_k_multiplier=0.0))
        assert ctx.get_effective_top_k(5) >= 1


# ===========================================================================
# ChunkSignal Tests
# ===========================================================================


class TestChunkSignal:
    def test_to_metadata_roundtrip(self) -> None:
        signal = ChunkSignal(
            completeness=0.7,
            boundary_type=BoundaryType.TOPIC_SHIFT,
            information_type=InformationType.TABULAR,
            requires_context=True,
            has_table=True,
            numeric_density=0.15,
            domain=DomainType.FINANCIAL,
            language="ko",
        )
        meta = signal.to_metadata()
        restored = ChunkSignal.from_metadata(meta)
        assert restored is not None
        assert restored.completeness == 0.7
        assert restored.boundary_type == BoundaryType.TOPIC_SHIFT
        assert restored.information_type == InformationType.TABULAR
        assert restored.requires_context is True
        assert restored.has_table is True
        assert restored.domain == DomainType.FINANCIAL
        assert restored.language == "ko"

    def test_from_metadata_returns_none_for_empty(self) -> None:
        assert ChunkSignal.from_metadata({}) is None
        assert ChunkSignal.from_metadata({"some_key": "value"}) is None

    def test_defaults(self) -> None:
        signal = ChunkSignal()
        assert signal.completeness == 1.0
        assert signal.boundary_type == BoundaryType.SIZE_LIMIT
        assert signal.information_type == InformationType.NARRATIVE
        assert not signal.requires_context
        assert not signal.has_table


# ===========================================================================
# DocumentProfile Tests
# ===========================================================================


class TestDocumentProfile:
    def test_to_metadata(self) -> None:
        profile = DocumentProfile(
            domain=DomainType.LEGAL,
            domain_confidence=0.85,
            structure_type="legal_hierarchical",
            information_type=InformationType.LEGAL,
            primary_language="ko",
        )
        meta = profile.to_metadata()
        assert meta["profile_domain"] == "legal"
        assert meta["profile_structure"] == "legal_hierarchical"
        assert meta["profile_language"] == "ko"

    def test_defaults(self) -> None:
        profile = DocumentProfile()
        assert profile.domain == DomainType.GENERAL
        assert profile.structure_type == "flat"
        assert profile.primary_language == "unknown"


# ===========================================================================
# DocumentProfiler Tests
# ===========================================================================


class TestDocumentProfiler:
    def test_empty_document(self) -> None:
        profiler = DocumentProfiler()
        doc = _make_doc("")
        profile = profiler.profile(doc)
        assert profile.structure_type == "flat"

    def test_korean_legal_document(self) -> None:
        content = """제1조 (목적)
이 계약은 갑과 을 사이의 소프트웨어 개발 용역에 관한 사항을 규정함을 목적으로 한다.

제2조 (계약 기간)
본 계약의 기간은 2024년 1월 1일부터 2024년 12월 31일까지로 한다.

제3조 (손해배상)
당사자가 본 계약을 위반하여 상대방에게 손해를 발생시킨 경우, 위약금으로 계약금의 30%를 배상하여야 한다.

제4조 (해지)
양 당사자는 상대방이 본 계약의 중대한 조항을 위반한 경우 서면 통지로 본 계약을 해지할 수 있다."""
        profiler = DocumentProfiler()
        doc = _make_doc(content)
        profile = profiler.profile(doc)

        assert profile.domain == DomainType.LEGAL
        assert profile.domain_confidence > 0.3
        assert profile.structure_type == "legal_hierarchical"
        assert profile.primary_language == "ko"
        assert profile.recommended_chunking == "structural"
        assert profile.recommended_fusion_weights["bm25"] > 0.4

    def test_financial_document(self) -> None:
        content = """2024년 3분기 실적 보고서

매출: 150억원 (전년대비 +25%)
영업이익: 30억원 (영업이익률 20%)
당기순이익: 22억원

| 항목 | 3Q 2024 | 3Q 2023 | 증감률 |
|------|---------|---------|--------|
| 매출 | 150억  | 120억  | +25%   |
| 영업이익 | 30억 | 20억 | +50%  |

투자 현황:
- Series B 투자 유치: 100억원
- CAGR 35% 성장 목표
- ROI 15% 달성"""
        profiler = DocumentProfiler()
        doc = _make_doc(content)
        profile = profiler.profile(doc)

        assert profile.domain == DomainType.FINANCIAL
        assert profile.numeric_density > 0.05
        assert profile.table_count >= 1
        assert profile.recommended_fusion_weights.get("bm25", 0) >= 0.25

    def test_technical_document(self) -> None:
        content = """# API Reference

## Authentication

All endpoints require an API key passed in the `Authorization` header.

```python
import requests

response = requests.get(
    "https://api.example.com/v1/users",
    headers={"Authorization": "Bearer sk-..."}
)
```

## Endpoints

### GET /users
Returns a list of all users.

### POST /users
Creates a new user. Requires `name` and `email` fields.

```json
{
  "name": "John",
  "email": "john@example.com"
}
```"""
        profiler = DocumentProfiler()
        doc = _make_doc(content)
        profile = profiler.profile(doc)

        assert profile.domain == DomainType.TECHNICAL
        assert profile.structure_type == "hierarchical"
        assert profile.heading_depth >= 2
        assert profile.code_block_count >= 1
        assert profile.recommended_chunking == "structural"

    def test_support_document(self) -> None:
        content = """자주 묻는 질문 (FAQ)

Q: 환불은 어떻게 하나요?
A: 고객센터에 문의하시면 접수 후 3일 이내 처리됩니다.

Q: 배송 기간은 얼마나 걸리나요?
A: 결제 완료 후 2-3일 이내 배송됩니다.

Q: 교환/반품 기간은?
A: 상품 수령 후 7일 이내 교환 및 반품이 가능합니다."""
        profiler = DocumentProfiler()
        doc = _make_doc(content)
        profile = profiler.profile(doc)

        assert profile.domain == DomainType.SUPPORT
        assert profile.recommended_fusion_weights.get("hype", 0) > 0.3

    def test_language_detection_korean(self) -> None:
        content = "이것은 한국어로 작성된 문서입니다. 다양한 주제를 다루고 있습니다."
        profiler = DocumentProfiler()
        doc = _make_doc(content)
        profile = profiler.profile(doc)
        assert profile.primary_language == "ko"

    def test_language_detection_english(self) -> None:
        content = "This is a document written in English covering various topics."
        profiler = DocumentProfiler()
        doc = _make_doc(content)
        profile = profiler.profile(doc)
        assert profile.primary_language == "en"

    def test_mixed_language(self) -> None:
        content = "이 문서는 Korean과 English가 혼합된 mixed language document입니다."
        profiler = DocumentProfiler()
        doc = _make_doc(content)
        profile = profiler.profile(doc)
        assert "ko" in profile.language_mix
        assert "en" in profile.language_mix

    def test_profile_stored_in_document_metadata(self) -> None:
        content = "제1조 (목적) 이 계약은 갑과 을 사이의 용역에 관한 사항을 규정한다."
        profiler = DocumentProfiler()
        doc = _make_doc(content)
        profiler.profile(doc)
        assert "profile" in doc.metadata.custom
        assert doc.metadata.custom["profile"]["profile_domain"] == "legal"

    def test_information_type_tabular(self) -> None:
        content = """| Name | Age | City |
| Alice | 30 | Seoul |
| Bob | 25 | Tokyo |
| Carol | 28 | NYC |
| Dave | 32 | London |
| Eve | 27 | Paris |"""
        profiler = DocumentProfiler()
        doc = _make_doc(content)
        profile = profiler.profile(doc)
        assert profile.information_type in (InformationType.TABULAR, InformationType.MIXED)

    def test_information_type_code(self) -> None:
        content = """```python
def hello():
    print("world")
```

```javascript
function greet() {
    console.log("hello");
}
```

More code follows."""
        profiler = DocumentProfiler()
        doc = _make_doc(content)
        profile = profiler.profile(doc)
        assert profile.code_block_count >= 2

    def test_vocabulary_richness(self) -> None:
        # Repetitive content should have low richness
        low_richness = "the the the the the the the the the the"
        profiler = DocumentProfiler()
        doc = _make_doc(low_richness)
        profile = profiler.profile(doc)
        assert profile.vocabulary_richness < 0.3

    def test_general_domain_for_generic_content(self) -> None:
        content = "오늘 날씨가 좋습니다. 산책을 하면 기분이 좋아질 것 같습니다."
        profiler = DocumentProfiler()
        doc = _make_doc(content)
        profile = profiler.profile(doc)
        # Could be general or any domain with low confidence
        assert profile.domain_confidence < 0.5 or profile.domain == DomainType.GENERAL


# ===========================================================================
# Chunk Signal Emission Tests
# ===========================================================================


class TestEmitChunkSignals:
    def test_basic_signal_emission(self) -> None:
        chunks = [
            _make_chunk("This is a complete sentence about a topic.", index=0),
            _make_chunk("Another complete paragraph with details.", index=1),
        ]
        result = emit_chunk_signals(chunks)
        assert len(result) == 2
        signal = read_chunk_signal(result[0])
        assert signal is not None
        assert signal.completeness > 0
        assert signal.information_type == InformationType.NARRATIVE

    def test_tabular_chunk_detection(self) -> None:
        chunks = [
            _make_chunk("| Name | Value |\n| Alice | 100 |\n| Bob | 200 |", index=0),
        ]
        result = emit_chunk_signals(chunks)
        signal = read_chunk_signal(result[0])
        assert signal is not None
        assert signal.has_table
        assert signal.information_type == InformationType.TABULAR

    def test_code_chunk_detection(self) -> None:
        chunks = [
            _make_chunk("```python\ndef hello():\n    print('world')\n```", index=0),
        ]
        result = emit_chunk_signals(chunks)
        signal = read_chunk_signal(result[0])
        assert signal is not None
        assert signal.has_code
        assert signal.information_type == InformationType.CODE

    def test_list_chunk_detection(self) -> None:
        chunks = [
            _make_chunk("- Item one\n- Item two\n- Item three\n- Item four", index=0),
        ]
        result = emit_chunk_signals(chunks)
        signal = read_chunk_signal(result[0])
        assert signal is not None
        assert signal.has_list

    def test_continuation_detection(self) -> None:
        chunks = [
            _make_chunk("This is a sentence that does not end properly", index=0),
            _make_chunk("and continues here with more information.", index=1),
        ]
        result = emit_chunk_signals(chunks)

        signal_0 = read_chunk_signal(result[0])
        signal_1 = read_chunk_signal(result[1])

        assert signal_0 is not None
        assert signal_1 is not None
        assert signal_0.has_continuation
        assert signal_1.continues_previous
        assert signal_1.requires_context

    def test_completeness_full_sentence(self) -> None:
        chunks = [
            _make_chunk(
                "This is a well-formed paragraph with multiple sentences. "
                "It covers the topic thoroughly. The conclusion is clear.",
                index=0,
            ),
        ]
        result = emit_chunk_signals(chunks)
        signal = read_chunk_signal(result[0])
        assert signal is not None
        assert signal.completeness >= 0.8

    def test_completeness_fragment(self) -> None:
        chunks = [_make_chunk("and also the", index=0)]
        result = emit_chunk_signals(chunks)
        signal = read_chunk_signal(result[0])
        assert signal is not None
        assert signal.completeness < 0.7

    def test_domain_inheritance(self) -> None:
        profile = DocumentProfile(domain=DomainType.LEGAL, primary_language="ko")
        chunks = [
            _make_chunk("제1조 이 계약은 갑과 을 사이의 합의사항이다.", index=0),
        ]
        result = emit_chunk_signals(chunks, document_profile=profile)
        signal = read_chunk_signal(result[0])
        assert signal is not None
        assert signal.domain == DomainType.LEGAL
        assert signal.language == "ko"

    def test_numeric_density(self) -> None:
        chunks = [
            _make_chunk("매출 150억원 영업이익 30억원 성장률 25% 인원 300명", index=0),
        ]
        result = emit_chunk_signals(chunks)
        signal = read_chunk_signal(result[0])
        assert signal is not None
        assert signal.numeric_density > 0.2

    def test_empty_chunks(self) -> None:
        result = emit_chunk_signals([])
        assert result == []

    def test_legal_info_type_detection(self) -> None:
        chunks = [
            _make_chunk(
                "제3조 (손해배상) 당사자가 본 계약을 위반한 경우 위약금을 지급한다.", index=0
            ),
        ]
        result = emit_chunk_signals(chunks)
        signal = read_chunk_signal(result[0])
        assert signal is not None
        assert signal.information_type == InformationType.LEGAL


# ===========================================================================
# Signal Reading Utility Tests
# ===========================================================================


class TestSignalReadingUtilities:
    def test_chunk_needs_expansion_true(self) -> None:
        chunk = _make_chunk("some content", index=0)
        signal = ChunkSignal(requires_context=True, completeness=0.4)
        chunk.metadata.update(signal.to_metadata())
        assert chunk_needs_expansion(chunk)

    def test_chunk_needs_expansion_false(self) -> None:
        chunk = _make_chunk("some content", index=0)
        signal = ChunkSignal(completeness=0.9)
        chunk.metadata.update(signal.to_metadata())
        assert not chunk_needs_expansion(chunk)

    def test_chunk_needs_expansion_no_signal(self) -> None:
        chunk = _make_chunk("some content", index=0)
        assert not chunk_needs_expansion(chunk)

    def test_chunk_should_skip_compression_tabular(self) -> None:
        chunk = _make_chunk("| A | B |", index=0)
        signal = ChunkSignal(information_type=InformationType.TABULAR, has_table=True)
        chunk.metadata.update(signal.to_metadata())
        assert chunk_should_skip_compression(chunk)

    def test_chunk_should_skip_compression_legal(self) -> None:
        chunk = _make_chunk("제1조", index=0)
        signal = ChunkSignal(information_type=InformationType.LEGAL)
        chunk.metadata.update(signal.to_metadata())
        assert chunk_should_skip_compression(chunk)

    def test_chunk_should_skip_compression_code(self) -> None:
        chunk = _make_chunk("def hello():", index=0)
        signal = ChunkSignal(information_type=InformationType.CODE)
        chunk.metadata.update(signal.to_metadata())
        assert chunk_should_skip_compression(chunk)

    def test_chunk_should_not_skip_compression_narrative(self) -> None:
        chunk = _make_chunk("A regular paragraph.", index=0)
        signal = ChunkSignal(information_type=InformationType.NARRATIVE)
        chunk.metadata.update(signal.to_metadata())
        assert not chunk_should_skip_compression(chunk)

    def test_chunk_should_not_skip_no_signal(self) -> None:
        chunk = _make_chunk("content", index=0)
        assert not chunk_should_skip_compression(chunk)


# ===========================================================================
# Query Signal Tests
# ===========================================================================


class TestQuerySignal:
    def test_defaults(self) -> None:
        signal = QuerySignal()
        assert signal.complexity == "simple"
        assert signal.intent == QueryIntent.FACTUAL
        assert signal.domain == DomainType.GENERAL

    def test_retrieval_hints_embedded(self) -> None:
        signal = QuerySignal(retrieval_hints=RetrievalHints(skip_compression=True))
        assert signal.retrieval_hints.skip_compression


class TestBuildQuerySignal:
    def test_simple_korean_query(self) -> None:
        signal = build_query_signal(
            query="매출은 얼마인가요?",
            complexity="simple",
            query_type="factual",
        )
        assert signal.is_korean
        assert signal.language == "ko"
        assert signal.intent == QueryIntent.FACTUAL

    def test_comparative_query(self) -> None:
        signal = build_query_signal(
            query="A와 B의 차이점을 비교해줘",
            complexity="complex",
            query_type="comparative",
        )
        assert signal.intent == QueryIntent.COMPARATIVE
        assert signal.output_format == "table"
        assert signal.requires_comparison
        assert signal.retrieval_hints.top_k_multiplier >= 1.5

    def test_aggregation_query(self) -> None:
        signal = build_query_signal(
            query="모든 프로젝트를 나열해주세요",
            complexity="complex",
            query_type="aggregation",
        )
        assert signal.intent == QueryIntent.AGGREGATION
        assert signal.output_format == "list"
        assert signal.retrieval_hints.top_k_multiplier >= 2.0
        assert signal.retrieval_hints.force_map_reduce

    def test_procedural_query(self) -> None:
        signal = build_query_signal(
            query="환불 방법을 알려주세요",
            complexity="medium",
            query_type="procedural",
        )
        assert signal.intent == QueryIntent.PROCEDURAL
        assert signal.output_format == "step_by_step"

    def test_temporal_query(self) -> None:
        signal = build_query_signal(
            query="분기별 매출 추이를 알려줘",
            complexity="complex",
            query_type="aggregation",
        )
        assert signal.intent == QueryIntent.TEMPORAL

    def test_verification_query(self) -> None:
        signal = build_query_signal(
            query="이 내용이 맞나요?",
            complexity="simple",
            query_type="factual",
        )
        assert signal.intent == QueryIntent.VERIFICATION

    def test_calculation_detection(self) -> None:
        signal = build_query_signal(
            query="총 매출 합계를 계산해주세요",
            complexity="complex",
            query_type="aggregation",
        )
        assert signal.requires_calculation

    def test_domain_from_profiles(self) -> None:
        profiles = [
            DocumentProfile(domain=DomainType.LEGAL, domain_confidence=0.8),
            DocumentProfile(domain=DomainType.LEGAL, domain_confidence=0.7),
        ]
        signal = build_query_signal(
            query="이 조항의 의미는?",
            complexity="medium",
            query_type="factual",
            active_profiles=profiles,
        )
        assert signal.domain == DomainType.LEGAL
        assert signal.domain_confidence > 0

    def test_legal_domain_hints(self) -> None:
        profiles = [
            DocumentProfile(domain=DomainType.LEGAL, domain_confidence=0.9),
        ]
        signal = build_query_signal(
            query="손해배상 조항의 범위는?",
            complexity="medium",
            query_type="factual",
            active_profiles=profiles,
        )
        assert signal.retrieval_hints.prefer_bm25
        assert signal.retrieval_hints.skip_compression
        assert signal.retrieval_hints.fusion_weights is not None
        assert signal.retrieval_hints.fusion_weights["bm25"] >= 0.5

    def test_simple_query_hints(self) -> None:
        signal = build_query_signal(
            query="What is X?",
            complexity="simple",
            query_type="factual",
        )
        assert signal.retrieval_hints.skip_rerank
        assert signal.retrieval_hints.skip_compression

    def test_english_query(self) -> None:
        signal = build_query_signal(
            query="What is the revenue for Q3?",
            complexity="simple",
        )
        assert not signal.is_korean
        assert signal.language == "en"


# ===========================================================================
# Integration: AutoChunker with Profile
# ===========================================================================


class TestAutoChunkerWithProfile:
    def test_profile_guides_chunking_strategy(self) -> None:
        from quantumrag.core.ingest.chunker.auto import AutoChunker

        # Create a legal document that would normally be "semantic" (has paragraphs)
        content = """제1조 (목적)
이 계약은 갑과 을 사이의 합의사항이다.

제2조 (기간)
계약 기간은 1년으로 한다.

제3조 (비용)
비용은 월 100만원으로 한다."""
        doc = _make_doc(content)
        profile = DocumentProfile(recommended_chunking="structural")

        chunker = AutoChunker(chunk_size=512)
        chunks = chunker.chunk(doc, document_profile=profile)
        assert len(chunks) >= 1
        # Chunks should have signal metadata
        signal = read_chunk_signal(chunks[0])
        assert signal is not None

    def test_chunker_without_profile_still_works(self) -> None:
        from quantumrag.core.ingest.chunker.auto import AutoChunker

        content = "A simple document with enough words to form a chunk."
        doc = _make_doc(content)
        chunker = AutoChunker(chunk_size=512)
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 1


# ===========================================================================
# Integration: SemanticChunker boundary types
# ===========================================================================


class TestSemanticChunkerBoundaryTypes:
    def test_topic_shift_boundary_recorded(self) -> None:
        from quantumrag.core.ingest.chunker.semantic import SemanticChunker

        # Two clearly different topics with enough content
        topic_a = "Python is a programming language used for web development. " * 20
        topic_b = "법률 계약서는 갑과 을 사이의 합의사항을 규정합니다. " * 20
        content = topic_a + "\n\n" + topic_b

        chunker = SemanticChunker(min_chunk_size=30, max_chunk_size=500)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)

        # Should have multiple chunks, some with topic_shift boundary
        assert len(chunks) >= 2
        boundaries = [c.metadata.get("boundary_type") for c in chunks]
        # At least one chunk should have a boundary type set
        assert any(b is not None for b in boundaries)


# ===========================================================================
# Pipeline Context with Document Profiles
# ===========================================================================


class TestPipelineContextWithProfiles:
    def test_profile_propagation(self) -> None:
        """Test that document profiles are accessible in pipeline context."""
        profiler = DocumentProfiler()
        doc = _make_doc("제1조 갑과 을의 계약. 제2조 손해배상 조항.")
        profile = profiler.profile(doc)

        ctx = PipelineContext()
        ctx.document_profiles[doc.id] = profile

        # Later, query signal can use these profiles
        signal = build_query_signal(
            query="손해배상 범위는?",
            complexity="medium",
            query_type="factual",
            active_profiles=list(ctx.document_profiles.values()),
        )
        assert signal.domain == DomainType.LEGAL

    def test_full_pipeline_flow(self) -> None:
        """Simulate the full pipeline signal flow."""
        # 1. Ingest: profile document
        profiler = DocumentProfiler()
        doc = _make_doc(
            "매출 150억원, 영업이익 30억원, 투자금 100억원. " "전년대비 매출 25% 성장. CAGR 35%."
        )
        profile = profiler.profile(doc)
        assert profile.domain == DomainType.FINANCIAL

        # 2. Chunk with profile
        from quantumrag.core.ingest.chunker.auto import AutoChunker

        chunker = AutoChunker(chunk_size=512)
        chunks = chunker.chunk(doc, document_profile=profile)
        assert len(chunks) >= 1

        # Verify signal on chunk
        signal = read_chunk_signal(chunks[0])
        assert signal is not None
        assert signal.domain == DomainType.FINANCIAL

        # 3. Query: build pipeline context
        ctx = PipelineContext()
        ctx.document_profiles[doc.id] = profile

        query_sig = build_query_signal(
            query="매출 성장률은?",
            complexity="simple",
            query_type="factual",
            active_profiles=[profile],
        )
        ctx.query_signal = query_sig
        ctx.merge_retrieval_hints(query_sig.retrieval_hints)

        # 4. Verify pipeline context has correct hints
        assert ctx.retrieval_hints.fusion_weights is not None
        assert ctx.retrieval_hints.fusion_weights.get("bm25", 0) >= 0.25
