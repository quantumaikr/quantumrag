"""Tests for core data models."""

from datetime import datetime

from quantumrag.core.models import (
    Chunk,
    Confidence,
    Document,
    DocumentMetadata,
    EvalMetric,
    EvalResult,
    Image,
    QueryComplexity,
    QueryResult,
    Source,
    SourceType,
    Table,
    TraceStep,
)


class TestDocumentMetadata:
    def test_defaults(self) -> None:
        meta = DocumentMetadata()
        assert meta.source_type == SourceType.FILE
        assert meta.language == "auto"
        assert meta.quality_score == 0.0
        assert meta.access_control == []
        assert meta.custom == {}

    def test_custom_values(self) -> None:
        now = datetime.now()
        meta = DocumentMetadata(
            source_type=SourceType.URL,
            source_id="abc123",
            title="Test Doc",
            author="Author",
            created_at=now,
            language="ko",
            quality_score=0.95,
            custom={"department": "legal"},
        )
        assert meta.source_type == SourceType.URL
        assert meta.title == "Test Doc"
        assert meta.quality_score == 0.95
        assert meta.custom["department"] == "legal"

    def test_serialization_roundtrip(self) -> None:
        meta = DocumentMetadata(title="Test", language="ko")
        data = meta.model_dump()
        restored = DocumentMetadata.model_validate(data)
        assert restored.title == meta.title
        assert restored.language == meta.language

    def test_json_roundtrip(self) -> None:
        meta = DocumentMetadata(title="JSON Test")
        json_str = meta.model_dump_json()
        restored = DocumentMetadata.model_validate_json(json_str)
        assert restored.title == "JSON Test"


class TestDocument:
    def test_minimal(self) -> None:
        doc = Document(content="Hello world")
        assert doc.content == "Hello world"
        assert doc.id  # auto-generated
        assert doc.tables == []
        assert doc.images == []
        assert doc.raw_bytes is None

    def test_with_tables_and_images(self) -> None:
        doc = Document(
            content="Report",
            tables=[Table(headers=["A", "B"], rows=[["1", "2"]])],
            images=[Image(caption="Figure 1")],
        )
        assert len(doc.tables) == 1
        assert doc.tables[0].headers == ["A", "B"]
        assert len(doc.images) == 1

    def test_serialization_roundtrip(self) -> None:
        doc = Document(content="Test content", metadata=DocumentMetadata(title="Test"))
        data = doc.model_dump()
        restored = Document.model_validate(data)
        assert restored.content == doc.content
        assert restored.metadata.title == "Test"


class TestChunk:
    def test_creation(self) -> None:
        chunk = Chunk(content="chunk text", document_id="doc1", chunk_index=0)
        assert chunk.content == "chunk text"
        assert chunk.document_id == "doc1"
        assert chunk.chunk_index == 0
        assert chunk.hype_questions == []
        assert chunk.context_prefix == ""

    def test_with_hype_questions(self) -> None:
        chunk = Chunk(
            content="Revenue was $1B",
            document_id="doc1",
            chunk_index=3,
            hype_questions=["What was the revenue?", "How much money was made?"],
        )
        assert len(chunk.hype_questions) == 2

    def test_serialization_roundtrip(self) -> None:
        chunk = Chunk(content="Test", document_id="d1", chunk_index=0, metadata={"page": 5})
        data = chunk.model_dump()
        restored = Chunk.model_validate(data)
        assert restored.metadata["page"] == 5


class TestQueryResult:
    def test_minimal(self) -> None:
        result = QueryResult(answer="The revenue is $1B")
        assert result.answer == "The revenue is $1B"
        assert result.confidence == Confidence.INSUFFICIENT_EVIDENCE
        assert result.sources == []
        assert result.trace == []

    def test_full_result(self) -> None:
        result = QueryResult(
            answer="Answer here",
            sources=[
                Source(
                    chunk_id="c1",
                    document_title="Report",
                    page=15,
                    excerpt="relevant text",
                    relevance_score=0.94,
                )
            ],
            confidence=Confidence.STRONGLY_SUPPORTED,
            trace=[
                TraceStep(step="retrieve", result="5 chunks", latency_ms=120.5),
                TraceStep(step="generate", result="answer", latency_ms=350.0),
            ],
            metadata={"path": "simple", "tokens_used": 1250},
        )
        assert result.confidence == Confidence.STRONGLY_SUPPORTED
        assert len(result.sources) == 1
        assert result.sources[0].relevance_score == 0.94
        assert len(result.trace) == 2
        assert result.metadata["path"] == "simple"

    def test_json_roundtrip(self) -> None:
        result = QueryResult(
            answer="Test",
            sources=[Source(chunk_id="c1", relevance_score=0.9)],
            confidence=Confidence.PARTIALLY_SUPPORTED,
        )
        json_str = result.model_dump_json()
        restored = QueryResult.model_validate_json(json_str)
        assert restored.answer == "Test"
        assert restored.confidence == Confidence.PARTIALLY_SUPPORTED


class TestSource:
    def test_creation(self) -> None:
        src = Source(chunk_id="c1", document_title="Doc", relevance_score=0.85)
        assert src.chunk_id == "c1"
        assert src.relevance_score == 0.85


class TestTraceStep:
    def test_creation(self) -> None:
        step = TraceStep(step="classify", result="simple", latency_ms=5.2)
        assert step.step == "classify"
        assert step.latency_ms == 5.2


class TestEvalResult:
    def test_creation(self) -> None:
        result = EvalResult(
            metrics=[EvalMetric(name="faithfulness", score=0.92)],
            summary="Good performance",
            suggestions=["Add more training data"],
        )
        assert result.metrics[0].score == 0.92
        assert len(result.suggestions) == 1


class TestEnums:
    def test_source_type_values(self) -> None:
        assert SourceType.FILE.value == "file"
        assert SourceType.URL.value == "url"

    def test_confidence_values(self) -> None:
        assert Confidence.STRONGLY_SUPPORTED.value == "strongly_supported"

    def test_query_complexity(self) -> None:
        assert QueryComplexity.SIMPLE.value == "simple"
        assert QueryComplexity.COMPLEX.value == "complex"
