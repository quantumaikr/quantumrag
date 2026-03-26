"""Tests for error handling."""

from quantumrag.core.errors import (
    ConfigError,
    ConnectorError,
    GenerationError,
    ParseError,
    QuantumRAGError,
    RetrievalError,
    StorageError,
)


class TestQuantumRAGError:
    def test_base_error(self) -> None:
        err = QuantumRAGError("something went wrong")
        assert "something went wrong" in str(err)
        assert err.suggestion == ""

    def test_with_suggestion(self) -> None:
        err = QuantumRAGError("failed", suggestion="try again")
        assert "try again" in str(err)
        assert err.suggestion == "try again"


class TestConfigError:
    def test_default_suggestion(self) -> None:
        err = ConfigError("invalid config")
        assert "quantumrag.yaml" in str(err)

    def test_custom_suggestion(self) -> None:
        err = ConfigError("bad key", suggestion="Remove the unknown key")
        assert "Remove the unknown key" in str(err)


class TestParseError:
    def test_with_file_path(self) -> None:
        err = ParseError("cannot parse", file_path="test.pdf")
        assert err.file_path == "test.pdf"
        assert "test.pdf" in str(err)


class TestGenerationError:
    def test_with_provider(self) -> None:
        err = GenerationError("API error", provider="openai")
        assert err.provider == "openai"
        assert "openai" in str(err)


class TestRetrievalError:
    def test_default_suggestion(self) -> None:
        err = RetrievalError("no results")
        assert "ingested" in str(err)


class TestStorageError:
    def test_default_suggestion(self) -> None:
        err = StorageError("disk full")
        assert "disk space" in str(err)


class TestConnectorError:
    def test_with_source(self) -> None:
        err = ConnectorError("auth failed", source="google_drive")
        assert err.source == "google_drive"
        assert "google_drive" in str(err)


class TestExceptionHierarchy:
    def test_all_inherit_from_base(self) -> None:
        errors = [
            ConfigError("x"),
            ParseError("x"),
            RetrievalError("x"),
            GenerationError("x"),
            StorageError("x"),
            ConnectorError("x"),
        ]
        for err in errors:
            assert isinstance(err, QuantumRAGError)
            assert isinstance(err, Exception)
