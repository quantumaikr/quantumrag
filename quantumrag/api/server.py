"""QuantumRAG HTTP API server."""

from __future__ import annotations

import sqlite3
import time
import urllib.parse
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from quantumrag._version import __version__
from quantumrag.api.middleware import (
    setup_api_key_auth,
    setup_cors,
    setup_rate_limiting,
    setup_request_id,
    setup_request_logging,
)
from quantumrag.api.models import (
    DocumentInfo,
    DocumentListResponse,
    EvalMetricResponse,
    EvaluateRequest,
    EvaluateResponse,
    FeedbackRequest,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    SourceResponse,
    StatusResponse,
)
from quantumrag.api.sse import sse_stream

logger = structlog.get_logger("quantumrag.api")


def validate_path(raw_path: str, base_dir: Path) -> Path:
    """Validate and resolve *raw_path* ensuring it stays within *base_dir*.

    Protections applied:
    1. URL-encoded sequences are decoded before validation.
    2. The path is resolved to an absolute path (``Path.resolve()``).
    3. ``relative_to(base_dir)`` is used to guarantee containment — this is
       immune to string-prefix tricks like ``/allowed_dirX/`` matching
       ``/allowed_dir``.
    4. If the resolved path is a symlink whose real target escapes *base_dir*,
       the request is also rejected.

    Raises ``HTTPException`` (403) on any violation.
    """
    # Decode percent-encoded characters (e.g. %2e%2e for "..")
    decoded = urllib.parse.unquote(raw_path)

    resolved = Path(decoded).resolve()
    base_resolved = base_dir.resolve()

    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Path is outside the allowed base directory",
        )

    # Extra symlink guard: even if the logical path is inside base_dir the
    # *real* target after symlink resolution could point elsewhere.
    if resolved.is_symlink():
        real_target = Path(resolved).resolve(strict=False)
        try:
            real_target.relative_to(base_resolved)
        except ValueError:
            raise HTTPException(
                status_code=403,
                detail="Symlink target is outside the allowed base directory",
            )

    return resolved


def validate_path_no_traversal(raw_path: str) -> Path:
    """Resolve *raw_path* and reject any ``..`` traversal components.

    Used when no explicit ``allowed_base_dir`` is configured.  The resolved
    path is returned for further checks (e.g. existence).

    Raises ``HTTPException`` (400) if the decoded path contains ``..``.
    """
    decoded = urllib.parse.unquote(raw_path)

    # Reject any ".." component regardless of platform separator
    parts = Path(decoded).parts
    if ".." in parts:
        raise HTTPException(
            status_code=400,
            detail="Relative path traversal is not allowed",
        )

    return Path(decoded).resolve()


def _get_engine(request: Request) -> Any:
    """Retrieve the Engine instance from app state."""
    return request.app.state.engine


def _get_feedback_db(request: Request) -> sqlite3.Connection:
    """Open (or create) the feedback SQLite database."""
    db_path: Path = request.app.state.feedback_db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            answer TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


def create_app(config_path: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    from quantumrag.core.config import QuantumRAGConfig
    from quantumrag.core.engine import Engine

    # Load configuration
    if config_path:
        cfg = QuantumRAGConfig.from_yaml(config_path)
    else:
        cfg = QuantumRAGConfig.default()

    engine = Engine(config=cfg)

    app = FastAPI(
        title="QuantumRAG API",
        version=__version__,
        description="QuantumRAG HTTP API — Index-Heavy, Query-Light RAG Engine",
    )

    # Store engine on app state so route handlers can access it via request
    app.state.engine = engine
    app.state.config = cfg
    app.state.feedback_db_path = Path(cfg.storage.data_dir) / "feedback.db"
    app.state.start_time = time.monotonic()

    # Middleware (order matters: last added runs first)
    setup_cors(app)
    setup_request_logging(app)
    setup_request_id(app)
    setup_rate_limiting(app)
    setup_api_key_auth(app)

    # Request body size limit (10 MB default)
    max_body_bytes = int(
        __import__("os").environ.get("QUANTUMRAG_MAX_BODY_BYTES", 100 * 1024 * 1024)
    )

    @app.middleware("http")
    async def _body_size_limit_middleware(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > max_body_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )
        return await call_next(request)

    # --- Routes ---

    @app.get("/health")
    async def health_endpoint(request: Request) -> dict[str, Any]:
        """Lightweight health check endpoint."""
        uptime = time.monotonic() - request.app.state.start_time
        storage: dict[str, int] = {"documents": 0, "chunks": 0}
        try:
            eng = _get_engine(request)
            info = eng.status()
            storage["documents"] = info.get("documents", 0)
            storage["chunks"] = info.get("chunks", 0)
        except Exception:
            pass  # health endpoint should not fail due to engine errors
        return {
            "status": "healthy",
            "version": __version__,
            "uptime_seconds": round(uptime, 2),
            "storage": storage,
        }

    @app.post("/v1/ingest", response_model=IngestResponse)
    async def ingest_endpoint(request: Request, req: IngestRequest) -> IngestResponse:
        """Ingest a file or directory."""
        allowed_base_raw = getattr(cfg, "allowed_base_dir", None)
        if allowed_base_raw is not None:
            # Strict containment check when an allowed base is configured
            target = validate_path(req.path, Path(allowed_base_raw))
        else:
            # No base configured — still decode and resolve, but only block
            # obvious traversal attempts (paths containing ".." components).
            target = validate_path_no_traversal(req.path)

        if not target.exists():
            raise HTTPException(status_code=400, detail=f"Path not found: {req.path}")
        try:
            eng = _get_engine(request)
            result = await eng.aingest(
                target,
                chunking_strategy=req.chunking_strategy,
                metadata=req.metadata,
                recursive=req.recursive,
            )
            return IngestResponse(
                documents=result.documents,
                chunks=result.chunks,
                elapsed_seconds=result.elapsed_seconds,
                errors=result.errors,
            )
        except Exception as e:
            logger.error("ingest_failed", error=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/v1/query", response_model=QueryResponse)
    async def query_endpoint(request: Request, req: QueryRequest) -> QueryResponse:
        """Query the knowledge base."""
        try:
            eng = _get_engine(request)
            result = await eng.aquery(
                req.query,
                top_k=req.top_k,
                filters=req.filters,
                rerank=req.rerank,
            )
            sources = [
                SourceResponse(
                    chunk_id=s.chunk_id,
                    document_title=s.document_title,
                    page=s.page,
                    section=s.section,
                    excerpt=s.excerpt,
                    relevance_score=s.relevance_score,
                )
                for s in result.sources
            ]
            return QueryResponse(
                answer=result.answer,
                sources=sources,
                confidence=result.confidence.value,
                metadata=result.metadata,
            )
        except Exception as e:
            logger.error("query_failed", error=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/v1/query/stream")
    async def query_stream_endpoint(
        request: Request, req: QueryRequest,
    ) -> StreamingResponse:
        """Stream query results via SSE."""
        try:
            eng = _get_engine(request)
            token_iter = eng.query_stream(
                req.query,
                top_k=req.top_k,
                filters=req.filters,
            )
            # query_stream is an async generator — no await needed,
            # but we pass it directly to sse_stream which iterates it.
            return StreamingResponse(
                sse_stream(token_iter),
                media_type="text/event-stream",
            )
        except Exception as e:
            logger.error("query_stream_failed", error=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/v1/documents", response_model=DocumentListResponse)
    async def list_documents(
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ) -> DocumentListResponse:
        """List ingested documents with pagination."""
        try:
            eng = _get_engine(request)
            eng._ensure_initialized()
            doc_store = eng._get_document_store()
            total = await doc_store.count_documents()

            docs: list[DocumentInfo] = []
            if hasattr(doc_store, "list_documents"):
                raw_docs = await doc_store.list_documents(offset=offset, limit=limit)
                for d in raw_docs:
                    # Handle both Document model objects and dicts
                    if hasattr(d, "id"):
                        doc_id = d.id
                        title = getattr(d.metadata, "title", "") or "" if hasattr(d, "metadata") else ""
                        source_type = getattr(d.metadata, "source_type", "file").value if hasattr(d, "metadata") and hasattr(getattr(d.metadata, "source_type", None), "value") else "file"
                    else:
                        doc_id = d.get("id", "")
                        title = d.get("title", "")
                        source_type = d.get("source_type", "file")
                    docs.append(
                        DocumentInfo(
                            id=doc_id,
                            title=title,
                            source_type=source_type,
                            chunk_count=0,
                        )
                    )

            return DocumentListResponse(
                documents=docs,
                total=total,
                offset=offset,
                limit=limit,
            )
        except Exception as e:
            logger.error("list_documents_failed", error=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.delete("/v1/documents/{doc_id}")
    async def delete_document(request: Request, doc_id: str) -> dict[str, Any]:
        """Delete a document by ID."""
        try:
            eng = _get_engine(request)
            eng._ensure_initialized()
            doc_store = eng._get_document_store()
            if hasattr(doc_store, "delete_document"):
                await doc_store.delete_document(doc_id)
            return {"status": "deleted", "document_id": doc_id}
        except Exception as e:
            logger.error("delete_document_failed", error=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/v1/status", response_model=StatusResponse)
    async def status_endpoint(request: Request) -> StatusResponse:
        """Get engine status."""
        try:
            eng = _get_engine(request)
            info = eng.status()
            return StatusResponse(
                project_name=info.get("project_name", ""),
                documents=info.get("documents", 0),
                chunks=info.get("chunks", 0),
                data_dir=str(info.get("data_dir", "")),
                embedding_model=str(info.get("embedding_model", "")),
                language=str(info.get("language", "")),
            )
        except Exception as e:
            logger.error("status_failed", error=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/v1/evaluate", response_model=EvaluateResponse)
    async def evaluate_endpoint(request: Request, req: EvaluateRequest) -> EvaluateResponse:
        """Run evaluation."""
        try:
            eng = _get_engine(request)
            result = eng.evaluate()
            metrics = [
                EvalMetricResponse(
                    name=m.name, score=m.score, details=m.details
                )
                for m in result.metrics
            ]
            return EvaluateResponse(
                metrics=metrics,
                summary=result.summary,
                suggestions=result.suggestions,
            )
        except Exception as e:
            logger.error("evaluate_failed", error=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/v1/feedback")
    async def feedback_endpoint(request: Request, req: FeedbackRequest) -> dict[str, str]:
        """Submit user feedback on a query result."""
        try:
            conn = _get_feedback_db(request)
            conn.execute(
                "INSERT INTO feedback (query, answer, rating, comment) VALUES (?, ?, ?, ?)",
                (req.query, req.answer, req.rating, req.comment),
            )
            conn.commit()
            conn.close()
            return {"status": "ok"}
        except Exception as e:
            logger.error("feedback_failed", error=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    # --- Playground endpoints (text ingest + file upload) ---

    @app.post("/v1/ingest/text", response_model=IngestResponse)
    async def ingest_text_endpoint(request: Request, req: dict[str, Any]) -> IngestResponse:
        """Ingest raw text content directly (for playground)."""
        content = req.get("content", "").strip()
        title = req.get("title", "Untitled")
        if not content:
            raise HTTPException(status_code=400, detail="Content is empty")
        try:
            import tempfile

            eng = _get_engine(request)
            # Write text to a temp file and ingest it
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, prefix="qrag_"
            ) as f:
                f.write(content)
                tmp_path = Path(f.name)
            try:
                result = await eng.aingest(tmp_path, metadata={"title": title})
            finally:
                tmp_path.unlink(missing_ok=True)
            return IngestResponse(
                documents=result.documents,
                chunks=result.chunks,
                elapsed_seconds=result.elapsed_seconds,
                errors=result.errors,
            )
        except Exception as e:
            logger.error("ingest_text_failed", error=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/v1/ingest/upload", response_model=IngestResponse)
    async def ingest_upload_endpoint(
        request: Request, file: UploadFile = File(...),
    ) -> IngestResponse:
        """Ingest an uploaded file (for playground)."""
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        try:
            import tempfile

            eng = _get_engine(request)
            suffix = Path(file.filename).suffix or ".txt"
            with tempfile.NamedTemporaryFile(
                suffix=suffix, delete=False, prefix="qrag_"
            ) as f:
                data = await file.read()
                f.write(data)
                tmp_path = Path(f.name)
            try:
                result = await eng.aingest(
                    tmp_path, metadata={"title": file.filename}
                )
            finally:
                tmp_path.unlink(missing_ok=True)
            return IngestResponse(
                documents=result.documents,
                chunks=result.chunks,
                elapsed_seconds=result.elapsed_seconds,
                errors=result.errors,
            )
        except Exception as e:
            logger.error("ingest_upload_failed", error=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    # Mount web playground UI
    from quantumrag.api.playground import mount_playground

    mount_playground(app)

    return app
