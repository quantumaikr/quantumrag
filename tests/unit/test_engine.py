"""Tests for Engine class."""

from __future__ import annotations

from pathlib import Path

from quantumrag.core.config import QuantumRAGConfig
from quantumrag.core.engine import Engine


class TestEngineInit:
    def test_default_init(self, tmp_path: Path) -> None:
        config = QuantumRAGConfig.default(storage={"data_dir": str(tmp_path / "data")})
        engine = Engine(config=config)
        assert engine._config.project_name == "my-knowledge-base"

    def test_init_with_overrides(self, tmp_path: Path) -> None:
        engine = Engine(
            embedding_model="text-embedding-3-large",
            generation_model="gpt-4.1",
            data_dir=str(tmp_path / "custom"),
        )
        assert engine._config.models.embedding.model == "text-embedding-3-large"
        assert engine._config.models.generation.medium.model == "gpt-4.1"
        assert engine._config.storage.data_dir == str(tmp_path / "custom")

    def test_init_with_yaml(self, tmp_path: Path) -> None:
        yaml_content = 'project_name: "test"\nlanguage: "en"\n'
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        engine = Engine(config=yaml_file)
        assert engine._config.project_name == "test"
        assert engine._config.language == "en"

    def test_status(self, tmp_path: Path) -> None:
        config = QuantumRAGConfig.default(storage={"data_dir": str(tmp_path / "data")})
        engine = Engine(config=config)
        status = engine.status()
        assert "documents" in status
        assert status["documents"] == 0
        assert "project_name" in status
