"""Pydantic request/response models for the QuantumRAG HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# --- Request models ---


class IngestRequest(BaseModel):
    """Request body for POST /v1/ingest."""

    path: str = Field(..., min_length=1)
    recursive: bool = True
    metadata: dict[str, Any] | None = None
    chunking_strategy: str | None = Field(default=None, max_length=100)
    mode: str | None = Field(default=None, description="Ingest mode: full, fast, or minimal")


class QueryRequest(BaseModel):
    """Request body for POST /v1/query and /v1/query/stream."""

    query: str = Field(..., min_length=1, max_length=10000)
    top_k: int | None = Field(default=None, ge=1, le=100)
    filters: dict[str, Any] | None = None
    rerank: bool | None = None


class FeedbackRequest(BaseModel):
    """Request body for POST /v1/feedback."""

    query: str = Field(..., min_length=1, max_length=10000)
    answer: str = Field(..., min_length=1, max_length=100000)
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(default="", max_length=10000)


class EvaluateRequest(BaseModel):
    """Request body for POST /v1/evaluate."""

    metrics: list[str] | None = None


# --- Response models ---


class IngestResponse(BaseModel):
    """Response for POST /v1/ingest."""

    documents: int
    chunks: int
    elapsed_seconds: float
    errors: list[str] = Field(default_factory=list)


class SourceResponse(BaseModel):
    """A source reference in a query response."""

    chunk_id: str
    document_title: str = ""
    page: int | None = None
    section: str | None = None
    excerpt: str = ""
    relevance_score: float = 0.0


class QueryResponse(BaseModel):
    """Response for POST /v1/query."""

    answer: str
    sources: list[SourceResponse] = Field(default_factory=list)
    confidence: str = "insufficient_evidence"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentInfo(BaseModel):
    """Summary info about a stored document."""

    id: str
    title: str = ""
    source_type: str = "file"
    chunk_count: int = 0


class DocumentListResponse(BaseModel):
    """Response for GET /v1/documents."""

    documents: list[DocumentInfo] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 20


class StatusResponse(BaseModel):
    """Response for GET /v1/status."""

    project_name: str = ""
    documents: int = 0
    chunks: int = 0
    data_dir: str = ""
    embedding_model: str = ""
    language: str = ""


class EvalMetricResponse(BaseModel):
    """Single evaluation metric."""

    name: str
    score: float
    details: dict[str, Any] = Field(default_factory=dict)


class EvaluateResponse(BaseModel):
    """Response for POST /v1/evaluate."""

    metrics: list[EvalMetricResponse] = Field(default_factory=list)
    summary: str = ""
    suggestions: list[str] = Field(default_factory=list)
