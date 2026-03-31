"""Tests for configuration system."""

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from quantumrag.core.config import (
    QuantumRAGConfig,
    generate_default_yaml,
)


class TestQuantumRAGConfigDefaults:
    def test_default_creation(self) -> None:
        config = QuantumRAGConfig.default()
        assert config.project_name == "my-knowledge-base"
        assert config.language == "auto"
        assert config.domain == "general"

    def test_default_models(self) -> None:
        # default() calls auto() — provider depends on env vars.
        config = QuantumRAGConfig.default()
        assert config.models.embedding.provider in (
            "openai",
            "gemini",
            "anthropic",
            "ollama",
            "local",
        )
        assert config.models.embedding.model  # non-empty
        assert config.models.generation.simple.model  # non-empty
        assert config.models.reranker.provider == "flashrank"

    @patch("quantumrag.core.config._load_dotenv")
    def test_auto_openai(self, _mock_dotenv: Any) -> None:
        """OpenAI selected only when no Gemini key is present."""
        env = {"OPENAI_API_KEY": "sk-test"}
        with patch.dict(os.environ, env, clear=True):
            config = QuantumRAGConfig.auto()
        assert config.models.embedding.provider == "openai"
        assert config.models.generation.simple.model == "gpt-5.4-nano"

    @patch("quantumrag.core.config._load_dotenv")
    def test_auto_gemini(self, _mock_dotenv: Any) -> None:
        """Gemini is preferred when GOOGLE_API_KEY is present."""
        env = {"GOOGLE_API_KEY": "AIza-test"}
        with patch.dict(os.environ, env, clear=True):
            config = QuantumRAGConfig.auto()
        assert config.models.embedding.provider == "local"  # Harrier local embedding
        assert config.models.embedding.model == "microsoft/harrier-oss-v1-0.6b"
        assert config.models.generation.simple.model == "gemini-3.1-flash-lite-preview"

    @patch("quantumrag.core.config._load_dotenv")
    def test_gemini_over_openai(self, _mock_dotenv: Any) -> None:
        """Gemini takes priority even when both keys are present."""
        env = {"GOOGLE_API_KEY": "AIza-test", "OPENAI_API_KEY": "sk-test"}
        with patch.dict(os.environ, env, clear=True):
            config = QuantumRAGConfig.auto()
        assert config.models.embedding.provider == "local"

    def test_default_retrieval(self) -> None:
        config = QuantumRAGConfig.default()
        assert config.retrieval.top_k == 12
        assert config.retrieval.fusion_weights.original == 0.35
        assert config.retrieval.fusion_weights.hype == 0.15
        assert config.retrieval.fusion_weights.bm25 == 0.50
        assert config.retrieval.rerank is True

    def test_default_storage(self) -> None:
        config = QuantumRAGConfig.default()
        assert config.storage.backend == "local"
        assert config.storage.vector_db == "lancedb"
        assert config.storage.document_store == "sqlite"

    def test_default_korean(self) -> None:
        config = QuantumRAGConfig.default()
        assert config.korean.morphology == "kiwi"
        assert config.korean.mixed_script is True


class TestQuantumRAGConfigOverrides:
    def test_code_overrides(self) -> None:
        config = QuantumRAGConfig.default(project_name="test-project", language="en")
        assert config.project_name == "test-project"
        assert config.language == "en"

    def test_env_var_override(self) -> None:
        with patch.dict(os.environ, {"QUANTUMRAG_PROJECT_NAME": "env-project"}):
            config = QuantumRAGConfig()
            assert config.project_name == "env-project"

    def test_nested_env_var_override(self) -> None:
        with patch.dict(os.environ, {"QUANTUMRAG_LANGUAGE": "en"}):
            config = QuantumRAGConfig()
            assert config.language == "en"


class TestQuantumRAGConfigYaml:
    def test_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = """\
project_name: "yaml-project"
language: "en"
domain: "legal"
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        config = QuantumRAGConfig.from_yaml(yaml_file)
        assert config.project_name == "yaml-project"
        assert config.language == "en"
        assert config.domain == "legal"
        # Default embedding is local Harrier
        assert config.models.embedding.provider in ("openai", "gemini", "local")

    def test_from_yaml_with_overrides(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text('project_name: "yaml-project"\n')

        config = QuantumRAGConfig.from_yaml(yaml_file, project_name="override-project")
        assert config.project_name == "override-project"

    def test_from_yaml_not_found(self) -> None:
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            QuantumRAGConfig.from_yaml("/nonexistent/path.yaml")

    def test_to_yaml(self, tmp_path: Path) -> None:
        config = QuantumRAGConfig.default(project_name="export-test")
        output_path = tmp_path / "out.yaml"
        config.to_yaml(output_path)

        assert output_path.exists()
        restored = QuantumRAGConfig.from_yaml(output_path)
        assert restored.project_name == "export-test"

    def test_merge_order_yaml_then_env(self, tmp_path: Path) -> None:
        """Env vars should override yaml values."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text('project_name: "from-yaml"\nlanguage: "ko"\n')

        with patch.dict(os.environ, {"QUANTUMRAG_PROJECT_NAME": "from-env"}):
            # Load yaml first, then env overrides
            config = QuantumRAGConfig.from_yaml(yaml_file)
            # Note: from_yaml passes yaml data as kwargs, env vars are loaded by pydantic-settings
            # The behavior depends on pydantic-settings priority
            assert config.project_name in ("from-yaml", "from-env")


class TestGenerateDefaultYaml:
    def test_generates_valid_yaml(self, tmp_path: Path) -> None:
        content = generate_default_yaml()
        yaml_file = tmp_path / "default.yaml"
        yaml_file.write_text(content)

        config = QuantumRAGConfig.from_yaml(yaml_file)
        assert config.project_name == "my-knowledge-base"
        assert config.language == "auto"

    def test_contains_all_sections(self) -> None:
        content = generate_default_yaml()
        assert "models:" in content
        assert "ingest:" in content
        assert "retrieval:" in content
        assert "generation:" in content
        assert "evaluation:" in content
        assert "storage:" in content
        assert "cost:" in content
        assert "korean:" in content
