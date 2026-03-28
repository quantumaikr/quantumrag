"""Tests for CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from quantumrag.cli.main import app

ENGINE_PATCH = "quantumrag.core.engine.Engine"

runner = CliRunner()


class TestCLIVersion:
    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "QuantumRAG v" in result.output

    def test_short_version_flag(self) -> None:
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "QuantumRAG v" in result.output


class TestCLIInit:
    def test_init_creates_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quantumrag.yaml"
        result = runner.invoke(app, ["init", "--config", str(config_path)])
        assert result.exit_code == 0
        assert config_path.exists()
        content = config_path.read_text()
        assert "project_name" in content
        assert "models:" in content

    def test_init_warns_existing(self, tmp_path: Path) -> None:
        config_path = tmp_path / "quantumrag.yaml"
        config_path.write_text("existing content")
        result = runner.invoke(app, ["init", "--config", str(config_path)], input="n\n")
        assert "already exists" in result.output


class TestCLIHelp:
    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "QuantumRAG" in result.output

    def test_init_help(self) -> None:
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0

    def test_ingest_help(self) -> None:
        result = runner.invoke(app, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "Ingest" in result.output

    def test_query_help(self) -> None:
        result = runner.invoke(app, ["query", "--help"])
        assert result.exit_code == 0
        assert "Query" in result.output

    def test_status_help(self) -> None:
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0


def _make_ingest_result(
    documents: int = 3, chunks: int = 15, elapsed: float = 1.5, errors: list[str] | None = None
):
    """Create a mock IngestResult."""
    from quantumrag.core.engine import IngestResult

    return IngestResult(documents=documents, chunks=chunks, elapsed_seconds=elapsed, errors=errors)


def _make_query_result(answer: str = "The answer is 42.", confidence: str = "strongly_supported"):
    """Create a mock QueryResult."""
    from quantumrag.core.models import Confidence, QueryResult, Source, TraceStep

    conf_map = {
        "strongly_supported": Confidence.STRONGLY_SUPPORTED,
        "partially_supported": Confidence.PARTIALLY_SUPPORTED,
        "insufficient_evidence": Confidence.INSUFFICIENT_EVIDENCE,
    }
    return QueryResult(
        answer=answer,
        confidence=conf_map[confidence],
        sources=[
            Source(
                chunk_id="abc123",
                document_title="test.pdf",
                excerpt="Some relevant text from the document.",
                relevance_score=0.95,
            ),
        ],
        trace=[
            TraceStep(step="classify", result="medium/factual", latency_ms=5.0),
            TraceStep(step="retrieve", result="5 chunks", latency_ms=120.0),
            TraceStep(step="generate", result="answer generated", latency_ms=800.0),
        ],
    )


class TestCLIIngest:
    @patch(ENGINE_PATCH)
    def test_ingest_success(self, mock_engine_cls: MagicMock, tmp_path: Path) -> None:
        # Create a file to ingest
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world")

        mock_engine = MagicMock()
        mock_engine.ingest.return_value = _make_ingest_result()
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["ingest", str(test_file)])
        assert result.exit_code == 0
        assert "Documents parsed" in result.output
        assert "Chunks created" in result.output
        assert "3" in result.output  # documents
        assert "15" in result.output  # chunks
        assert "Successfully ingested" in result.output

    @patch(ENGINE_PATCH)
    def test_ingest_directory(self, mock_engine_cls: MagicMock, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("doc a")
        (tmp_path / "b.txt").write_text("doc b")

        mock_engine = MagicMock()
        mock_engine.ingest.return_value = _make_ingest_result(documents=2, chunks=8)
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["ingest", str(tmp_path)])
        assert result.exit_code == 0
        assert "2" in result.output
        mock_engine.ingest.assert_called_once()

    def test_ingest_nonexistent_path(self) -> None:
        result = runner.invoke(app, ["ingest", "/nonexistent/path/file.txt"])
        assert result.exit_code == 1
        assert "Path not found" in result.output

    @patch(ENGINE_PATCH)
    def test_ingest_with_strategy(self, mock_engine_cls: MagicMock, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello")

        mock_engine = MagicMock()
        mock_engine.ingest.return_value = _make_ingest_result()
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["ingest", str(test_file), "--strategy", "semantic"])
        assert result.exit_code == 0
        mock_engine.ingest.assert_called_once()
        call_kwargs = mock_engine.ingest.call_args[1]
        assert call_kwargs["chunking_strategy"] == "semantic"

    @patch(ENGINE_PATCH)
    def test_ingest_with_metadata(self, mock_engine_cls: MagicMock, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello")

        mock_engine = MagicMock()
        mock_engine.ingest.return_value = _make_ingest_result()
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(
            app, ["ingest", str(test_file), "--metadata", "author=Alice", "--metadata", "dept=eng"]
        )
        assert result.exit_code == 0
        call_kwargs = mock_engine.ingest.call_args[1]
        assert call_kwargs["metadata"] == {"author": "Alice", "dept": "eng"}

    @patch(ENGINE_PATCH)
    def test_ingest_no_recursive(self, mock_engine_cls: MagicMock, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello")

        mock_engine = MagicMock()
        mock_engine.ingest.return_value = _make_ingest_result()
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["ingest", str(test_file), "--no-recursive"])
        assert result.exit_code == 0
        call_kwargs = mock_engine.ingest.call_args[1]
        assert call_kwargs["recursive"] is False

    @patch(ENGINE_PATCH)
    def test_ingest_zero_documents(self, mock_engine_cls: MagicMock, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello")

        mock_engine = MagicMock()
        mock_engine.ingest.return_value = _make_ingest_result(documents=0, chunks=0)
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["ingest", str(test_file)])
        assert result.exit_code == 0
        assert "No documents were ingested" in result.output

    @patch(ENGINE_PATCH)
    def test_ingest_with_errors(self, mock_engine_cls: MagicMock, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello")

        mock_engine = MagicMock()
        mock_engine.ingest.return_value = _make_ingest_result(errors=["Failed to parse foo.bin"])
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["ingest", str(test_file)])
        assert result.exit_code == 0
        assert "Errors" in result.output
        assert "Failed to parse foo.bin" in result.output

    @patch(ENGINE_PATCH)
    def test_ingest_engine_exception(self, mock_engine_cls: MagicMock, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello")

        mock_engine = MagicMock()
        mock_engine.ingest.side_effect = RuntimeError("Database locked")
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["ingest", str(test_file)])
        assert result.exit_code == 1
        assert "Error during ingestion" in result.output

    def test_ingest_invalid_metadata_format(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello")

        result = runner.invoke(app, ["ingest", str(test_file), "--metadata", "badformat"])
        assert result.exit_code == 1
        assert "Invalid metadata format" in result.output


class TestCLIQuery:
    @patch(ENGINE_PATCH)
    def test_query_text_format(self, mock_engine_cls: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_engine.query.return_value = _make_query_result()
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["query", "What is the answer?"])
        assert result.exit_code == 0
        assert "The answer is 42." in result.output
        assert "strongly_supported" in result.output
        assert "Sources" in result.output

    @patch(ENGINE_PATCH)
    def test_query_json_format(self, mock_engine_cls: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_engine.query.return_value = _make_query_result()
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["query", "What is the answer?", "--format", "json"])
        assert result.exit_code == 0
        assert "The answer is 42." in result.output
        assert "strongly_supported" in result.output

    @patch(ENGINE_PATCH)
    def test_query_verbose(self, mock_engine_cls: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_engine.query.return_value = _make_query_result()
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["query", "What is the answer?", "--verbose"])
        assert result.exit_code == 0
        assert "Processing Trace" in result.output
        assert "classify" in result.output
        assert "retrieve" in result.output

    @patch(ENGINE_PATCH)
    def test_query_no_rerank(self, mock_engine_cls: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_engine.query.return_value = _make_query_result()
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["query", "test question", "--no-rerank"])
        assert result.exit_code == 0
        call_kwargs = mock_engine.query.call_args[1]
        assert call_kwargs["rerank"] is False

    @patch(ENGINE_PATCH)
    def test_query_top_k(self, mock_engine_cls: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_engine.query.return_value = _make_query_result()
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["query", "test question", "--top-k", "10"])
        assert result.exit_code == 0
        call_kwargs = mock_engine.query.call_args[1]
        assert call_kwargs["top_k"] == 10

    @patch(ENGINE_PATCH)
    def test_query_engine_exception(self, mock_engine_cls: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_engine.query.side_effect = RuntimeError("API key missing")
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["query", "test question"])
        assert result.exit_code == 1
        assert "Error during query" in result.output

    @patch(ENGINE_PATCH)
    def test_query_insufficient_evidence(self, mock_engine_cls: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_engine.query.return_value = _make_query_result(
            answer="I don't have enough information.",
            confidence="insufficient_evidence",
        )
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["query", "some question"])
        assert result.exit_code == 0
        assert "insufficient_evidence" in result.output


class TestCLIStatus:
    @patch(ENGINE_PATCH)
    def test_status_with_engine(self, mock_engine_cls: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_engine.status.return_value = {
            "project_name": "test-project",
            "documents": 42,
            "chunks": 256,
            "data_dir": "./quantumrag_data",
            "embedding_model": "text-embedding-3-small",
            "language": "ko",
        }
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "test-project" in result.output
        assert "42" in result.output
        assert "256" in result.output
        assert "text-embedding-3-small" in result.output

    @patch(ENGINE_PATCH)
    def test_status_engine_error(self, mock_engine_cls: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_engine.status.side_effect = RuntimeError("No database")
        mock_engine_cls.return_value = mock_engine

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "No index found" in result.output or "Error getting status" in result.output
