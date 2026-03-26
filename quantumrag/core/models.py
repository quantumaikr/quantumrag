"""Core data models for QuantumRAG."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Document source types."""

    FILE = "file"
    URL = "url"
    GOOGLE_DRIVE = "google_drive"
    NOTION = "notion"
    CONFLUENCE = "confluence"
    SLACK = "slack"
    SHAREPOINT = "sharepoint"
    DATABASE = "database"
    GITHUB = "github"
    EMAIL = "email"


class Confidence(str, Enum):
    """Answer confidence levels."""

    STRONGLY_SUPPORTED = "strongly_supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class QueryComplexity(str, Enum):
    """Query complexity levels for adaptive routing."""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class DocumentMetadata(BaseModel):
    """Metadata associated with a document."""

    source_type: SourceType = SourceType.FILE
    source_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    title: str = ""
    author: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    language: str = "auto"
    access_control: list[str] = Field(default_factory=list)
    version: str | None = None
    quality_score: float = 0.0
    custom: dict[str, Any] = Field(default_factory=dict)


class Table(BaseModel):
    """Extracted table from a document."""

    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    caption: str = ""
    page: int | None = None


class Image(BaseModel):
    """Extracted image from a document."""

    data: bytes = b""
    mime_type: str = "image/png"
    caption: str = ""
    page: int | None = None


class Document(BaseModel):
    """A parsed document ready for ingestion."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    content: str
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    tables: list[Table] = Field(default_factory=list)
    images: list[Image] = Field(default_factory=list)
    raw_bytes: bytes | None = None


class Chunk(BaseModel):
    """A chunk of a document for indexing and retrieval."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    content: str
    document_id: str
    chunk_index: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    parent_chunk_id: str | None = None

    # Populated during indexing
    context_prefix: str = ""  # Contextual prefix for BM25
    hype_questions: list[str] = Field(default_factory=list)  # HyPE generated questions


class Source(BaseModel):
    """A source reference in a query result."""

    chunk_id: str
    document_title: str = ""
    page: int | None = None
    section: str | None = None
    excerpt: str = ""
    relevance_score: float = 0.0


class TraceStep(BaseModel):
    """A step in the query execution trace."""

    step: str
    result: str = ""
    latency_ms: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)


class QueryResult(BaseModel):
    """Result of a RAG query."""

    answer: str
    sources: list[Source] = Field(default_factory=list)
    confidence: Confidence = Confidence.INSUFFICIENT_EVIDENCE
    trace: list[TraceStep] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalMetric(BaseModel):
    """A single evaluation metric result."""

    name: str
    score: float
    details: dict[str, Any] = Field(default_factory=dict)


class EvalResult(BaseModel):
    """Result of an evaluation run."""

    metrics: list[EvalMetric] = Field(default_factory=list)
    summary: str = ""
    suggestions: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
