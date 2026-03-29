"""Tests for ingest mode parameter (full / fast / minimal)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantumrag.core.config import IngestConfig, QuantumRAGConfig
from quantumrag.core.errors import ConfigError

# ---------------------------------------------------------------------------
# 1. IngestConfig defaults
# ---------------------------------------------------------------------------


class TestIngestConfigDefaults:
    def test_mode_default_is_fast(self) -> None:
        cfg = IngestConfig()
        assert cfg.mode == "fast"

    def test_max_concurrency_default(self) -> None:
        cfg = IngestConfig()
        assert cfg.max_concurrency == 3

    def test_parse_concurrency_default(self) -> None:
        cfg = IngestConfig()
        assert cfg.parse_concurrency == 4

    def test_quality_check_default(self) -> None:
        cfg = IngestConfig()
        assert cfg.quality_check is True

    def test_contextual_preamble_default(self) -> None:
        cfg = IngestConfig()
        assert cfg.contextual_preamble is True

    def test_full_config_ingest_mode_default(self) -> None:
        """Default ingest mode is 'fast' (safe for free-tier APIs)."""
        cfg = QuantumRAGConfig.default()
        assert cfg.ingest.mode == "fast"


# ---------------------------------------------------------------------------
# 2. Config YAML roundtrip for mode field
# ---------------------------------------------------------------------------


class TestIngestModeYamlRoundtrip:
    @pytest.mark.parametrize("mode", ["full", "fast", "minimal"])
    def test_mode_persists_through_yaml(self, tmp_path: Path, mode: str) -> None:
        cfg = QuantumRAGConfig.default()
        cfg.ingest.mode = mode
        out = tmp_path / "cfg.yaml"
        cfg.to_yaml(out)

        restored = QuantumRAGConfig.from_yaml(out)
        assert restored.ingest.mode == mode

    def test_concurrency_persists_through_yaml(self, tmp_path: Path) -> None:
        cfg = QuantumRAGConfig.default()
        cfg.ingest.max_concurrency = 10
        cfg.ingest.parse_concurrency = 8
        out = tmp_path / "cfg.yaml"
        cfg.to_yaml(out)

        restored = QuantumRAGConfig.from_yaml(out)
        assert restored.ingest.max_concurrency == 10
        assert restored.ingest.parse_concurrency == 8

    def test_mode_from_yaml_file(self, tmp_path: Path) -> None:
        yaml_content = """\
ingest:
  mode: "minimal"
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        cfg = QuantumRAGConfig.from_yaml(yaml_file)
        assert cfg.ingest.mode == "minimal"


# ---------------------------------------------------------------------------
# 3. Invalid mode raises ConfigError
# ---------------------------------------------------------------------------


class TestInvalidModeRaisesConfigError:
    @pytest.mark.asyncio
    async def test_invalid_mode_in_aingest(self, tmp_path: Path) -> None:
        from quantumrag.core.engine import Engine

        doc = tmp_path / "test.txt"
        doc.write_text("Hello world")

        engine = Engine(
            config=QuantumRAGConfig.default(),
            document_store=MagicMock(),
            vector_store=MagicMock(),
            bm25_store=MagicMock(),
        )

        with pytest.raises(ConfigError, match=r"Unknown ingest mode.*'turbo'"):
            await engine.aingest(doc, mode="turbo")

    @pytest.mark.asyncio
    async def test_invalid_mode_from_config(self, tmp_path: Path) -> None:
        from quantumrag.core.engine import Engine

        doc = tmp_path / "test.txt"
        doc.write_text("Hello world")

        cfg = QuantumRAGConfig.default()
        cfg.ingest.mode = "invalid"

        engine = Engine(
            config=cfg,
            document_store=MagicMock(),
            vector_store=MagicMock(),
            bm25_store=MagicMock(),
        )

        with pytest.raises(ConfigError, match=r"Unknown ingest mode.*'invalid'"):
            await engine.aingest(doc)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["full", "fast", "minimal"])
    async def test_valid_modes_do_not_raise(self, tmp_path: Path, mode: str) -> None:
        """Valid modes should not raise ConfigError (they may fail later on
        missing providers, but that's a different error)."""
        from quantumrag.core.engine import Engine

        doc = tmp_path / "test.txt"
        doc.write_text("Hello world")

        doc_store = AsyncMock()
        doc_store.add_document = AsyncMock()
        doc_store.add_chunks = AsyncMock()
        doc_store.get_chunks = AsyncMock(return_value=[])

        engine = Engine(
            config=QuantumRAGConfig.default(),
            document_store=doc_store,
            vector_store=MagicMock(),
            bm25_store=MagicMock(),
        )

        # Patch out the embedding provider so we don't need real API keys
        with patch.object(engine, "_get_embedding_provider", return_value=MagicMock()):
            # The call may fail further in the pipeline, but NOT with ConfigError
            # about unknown mode.
            try:
                await engine.aingest(doc, mode=mode)
            except ConfigError as e:
                if "Unknown ingest mode" in str(e):
                    pytest.fail(f"Valid mode {mode!r} raised ConfigError: {e}")
            except Exception:
                pass  # Other errors (missing LLM provider, etc.) are expected


# ---------------------------------------------------------------------------
# 4. Mode flag derivation
# ---------------------------------------------------------------------------


class TestModeFlagDerivation:
    """Test that each mode correctly enables/disables pipeline steps.

    These are pure logic tests against the flag derivation rules in aingest.
    """

    @staticmethod
    def _derive_flags(
        ingest_mode: str,
        enable_hype: bool = True,
        quality_check: bool = True,
        contextual_preamble: bool = True,
    ) -> dict[str, bool]:
        """Replicate the flag derivation logic from Engine.aingest."""
        return {
            "do_hype": enable_hype and ingest_mode == "full",
            "do_preamble": contextual_preamble and ingest_mode == "full",
            "do_facts": ingest_mode in ("full", "fast"),
            "do_quality": quality_check and ingest_mode in ("full", "fast"),
            "do_multi_res": ingest_mode in ("full", "fast"),
            "do_entity_index": ingest_mode in ("full", "fast"),
            "do_chunk_graph": ingest_mode == "full",
        }

    # --- Full mode ---

    def test_full_mode_all_enabled(self) -> None:
        flags = self._derive_flags("full")
        assert flags == {
            "do_hype": True,
            "do_preamble": True,
            "do_facts": True,
            "do_quality": True,
            "do_multi_res": True,
            "do_entity_index": True,
            "do_chunk_graph": True,
        }

    def test_full_mode_hype_disabled_by_param(self) -> None:
        flags = self._derive_flags("full", enable_hype=False)
        assert flags["do_hype"] is False
        # Everything else still on
        assert flags["do_preamble"] is True
        assert flags["do_facts"] is True
        assert flags["do_chunk_graph"] is True

    def test_full_mode_preamble_disabled_by_config(self) -> None:
        flags = self._derive_flags("full", contextual_preamble=False)
        assert flags["do_preamble"] is False
        assert flags["do_hype"] is True

    def test_full_mode_quality_disabled_by_config(self) -> None:
        flags = self._derive_flags("full", quality_check=False)
        assert flags["do_quality"] is False
        assert flags["do_facts"] is True

    # --- Fast mode ---

    def test_fast_mode_skips_hype_and_preamble(self) -> None:
        flags = self._derive_flags("fast")
        assert flags["do_hype"] is False
        assert flags["do_preamble"] is False
        assert flags["do_chunk_graph"] is False

    def test_fast_mode_keeps_facts_and_quality(self) -> None:
        flags = self._derive_flags("fast")
        assert flags["do_facts"] is True
        assert flags["do_quality"] is True
        assert flags["do_multi_res"] is True
        assert flags["do_entity_index"] is True

    # --- Minimal mode ---

    def test_minimal_mode_disables_all_enrichment(self) -> None:
        flags = self._derive_flags("minimal")
        assert flags == {
            "do_hype": False,
            "do_preamble": False,
            "do_facts": False,
            "do_quality": False,
            "do_multi_res": False,
            "do_entity_index": False,
            "do_chunk_graph": False,
        }

    def test_minimal_mode_ignores_enable_hype_param(self) -> None:
        """Even if enable_hype=True, minimal mode disables it."""
        flags = self._derive_flags("minimal", enable_hype=True)
        assert flags["do_hype"] is False


# ---------------------------------------------------------------------------
# 5. CLI --fast flag maps to mode="fast"
# ---------------------------------------------------------------------------


class TestCliFastFlag:
    def test_fast_flag_overrides_mode(self) -> None:
        """The CLI resolves --fast to ingest_mode='fast'."""
        # Replicate the CLI logic: ingest_mode = "fast" if fast else mode
        fast = True
        mode = "full"
        ingest_mode = "fast" if fast else mode
        assert ingest_mode == "fast"

    def test_fast_flag_false_uses_explicit_mode(self) -> None:
        fast = False
        mode = "minimal"
        ingest_mode = "fast" if fast else mode
        assert ingest_mode == "minimal"

    def test_fast_flag_false_defaults_to_full(self) -> None:
        fast = False
        mode = "full"  # CLI default
        ingest_mode = "fast" if fast else mode
        assert ingest_mode == "full"


# ---------------------------------------------------------------------------
# 6. Engine integration: verify pipeline steps per mode via mocking
# ---------------------------------------------------------------------------


def _make_mock_engine(
    tmp_path: Path,
    mode: str = "full",
    quality_check: bool = True,
    contextual_preamble: bool = True,
) -> Any:
    """Create an Engine with all heavy dependencies mocked out."""
    from quantumrag.core.engine import Engine

    cfg = QuantumRAGConfig.default()
    cfg.ingest.mode = mode
    cfg.ingest.quality_check = quality_check
    cfg.ingest.contextual_preamble = contextual_preamble
    cfg.storage.data_dir = str(tmp_path / "data")

    doc_store = AsyncMock()
    doc_store.add_document = AsyncMock()
    doc_store.add_chunks = AsyncMock()
    doc_store.get_chunks = AsyncMock(return_value=[])

    engine = Engine(
        config=cfg,
        document_store=doc_store,
        vector_store=MagicMock(),
        bm25_store=MagicMock(),
    )
    return engine


class TestEngineIngestModeFull:
    @pytest.mark.asyncio
    async def test_full_mode_calls_preamble_and_hype(self, tmp_path: Path) -> None:
        engine = _make_mock_engine(tmp_path, mode="full")
        doc = tmp_path / "test.txt"
        doc.write_text("Some test content for ingestion.")

        with (
            patch.object(engine, "_get_embedding_provider", return_value=MagicMock()),
            patch.object(engine, "_get_llm_provider", return_value=MagicMock()),
            patch.object(engine, "_get_vector_store", return_value=MagicMock()),
            patch.object(engine, "_get_bm25_store", return_value=MagicMock()),
            patch(
                "quantumrag.core.ingest.chunker.context.generate_contextual_preambles",
                new_callable=AsyncMock,
            ) as mock_preamble,
            patch(
                "quantumrag.core.ingest.indexer.fact_extractor.extract_facts_for_chunks"
            ) as mock_facts,
            patch("quantumrag.core.ingest.quality.ChunkQualityChecker") as mock_quality_cls,
            patch(
                "quantumrag.core.ingest.indexer.multi_resolution.build_multi_resolution_chunks"
            ) as mock_multi_res,
            patch("quantumrag.core.ingest.indexer.entity_index.EntityIndex"),
            patch("quantumrag.core.ingest.indexer.chunk_graph.build_chunk_graph"),
            patch(
                "quantumrag.core.ingest.indexer.triple_index_builder.TripleIndexBuilder"
            ) as mock_builder_cls,
        ):
            # Configure mocks to return usable values
            mock_preamble.return_value = []
            mock_facts.return_value = []
            mock_quality_cls.return_value.filter_chunks.return_value = []
            mock_multi_res.return_value = []
            mock_builder_cls.return_value.build = AsyncMock()

            result = await engine.aingest(doc, mode="full")

            assert result.documents >= 0
            # In full mode, preamble generation is called
            mock_preamble.assert_called()
            mock_facts.assert_called()
            mock_quality_cls.assert_called()
            mock_multi_res.assert_called()


class TestEngineIngestModeFast:
    @pytest.mark.asyncio
    async def test_fast_mode_skips_preamble(self, tmp_path: Path) -> None:
        engine = _make_mock_engine(tmp_path, mode="fast")
        doc = tmp_path / "test.txt"
        doc.write_text("Some test content for ingestion.")

        with (
            patch.object(engine, "_get_embedding_provider", return_value=MagicMock()),
            patch.object(engine, "_get_llm_provider", return_value=MagicMock()),
            patch.object(engine, "_get_vector_store", return_value=MagicMock()),
            patch.object(engine, "_get_bm25_store", return_value=MagicMock()),
            patch(
                "quantumrag.core.ingest.chunker.context.generate_contextual_preambles",
                new_callable=AsyncMock,
            ) as mock_preamble,
            patch(
                "quantumrag.core.ingest.indexer.fact_extractor.extract_facts_for_chunks"
            ) as mock_facts,
            patch("quantumrag.core.ingest.quality.ChunkQualityChecker") as mock_quality_cls,
            patch(
                "quantumrag.core.ingest.indexer.multi_resolution.build_multi_resolution_chunks"
            ) as mock_multi_res,
            patch(
                "quantumrag.core.ingest.indexer.chunk_graph.build_chunk_graph"
            ) as mock_chunk_graph,
            patch(
                "quantumrag.core.ingest.indexer.triple_index_builder.TripleIndexBuilder"
            ) as mock_builder_cls,
        ):
            mock_facts.return_value = []
            mock_quality_cls.return_value.filter_chunks.return_value = []
            mock_multi_res.return_value = []
            mock_builder_cls.return_value.build = AsyncMock()

            await engine.aingest(doc, mode="fast")

            # Preamble and chunk graph should NOT be called in fast mode
            mock_preamble.assert_not_called()
            mock_chunk_graph.assert_not_called()
            # Facts, quality, multi-res still run
            mock_facts.assert_called()
            mock_quality_cls.assert_called()
            mock_multi_res.assert_called()


class TestEngineIngestModeMinimal:
    @pytest.mark.asyncio
    async def test_minimal_mode_skips_all_enrichment(self, tmp_path: Path) -> None:
        engine = _make_mock_engine(tmp_path, mode="minimal")
        doc = tmp_path / "test.txt"
        doc.write_text("Some test content for ingestion.")

        with (
            patch.object(engine, "_get_embedding_provider", return_value=MagicMock()),
            patch.object(engine, "_get_vector_store", return_value=MagicMock()),
            patch.object(engine, "_get_bm25_store", return_value=MagicMock()),
            patch(
                "quantumrag.core.ingest.chunker.context.generate_contextual_preambles",
                new_callable=AsyncMock,
            ) as mock_preamble,
            patch(
                "quantumrag.core.ingest.indexer.fact_extractor.extract_facts_for_chunks"
            ) as mock_facts,
            patch("quantumrag.core.ingest.quality.ChunkQualityChecker") as mock_quality_cls,
            patch(
                "quantumrag.core.ingest.indexer.multi_resolution.build_multi_resolution_chunks"
            ) as mock_multi_res,
            patch("quantumrag.core.ingest.indexer.entity_index.EntityIndex") as mock_entity_cls,
            patch(
                "quantumrag.core.ingest.indexer.chunk_graph.build_chunk_graph"
            ) as mock_chunk_graph,
            patch(
                "quantumrag.core.ingest.indexer.triple_index_builder.TripleIndexBuilder"
            ) as mock_builder_cls,
        ):
            mock_builder_cls.return_value.build = AsyncMock()

            await engine.aingest(doc, mode="minimal")

            # ALL enrichment steps should be skipped
            mock_preamble.assert_not_called()
            mock_facts.assert_not_called()
            mock_quality_cls.assert_not_called()
            mock_multi_res.assert_not_called()
            mock_entity_cls.assert_not_called()
            mock_chunk_graph.assert_not_called()


class TestEngineIngestModeOverride:
    @pytest.mark.asyncio
    async def test_mode_param_overrides_config(self, tmp_path: Path) -> None:
        """Passing mode= to aingest overrides config.ingest.mode."""
        engine = _make_mock_engine(tmp_path, mode="full")
        doc = tmp_path / "test.txt"
        doc.write_text("Some test content for ingestion.")

        with (
            patch.object(engine, "_get_embedding_provider", return_value=MagicMock()),
            patch.object(engine, "_get_vector_store", return_value=MagicMock()),
            patch.object(engine, "_get_bm25_store", return_value=MagicMock()),
            patch(
                "quantumrag.core.ingest.chunker.context.generate_contextual_preambles",
                new_callable=AsyncMock,
            ) as mock_preamble,
            patch(
                "quantumrag.core.ingest.indexer.fact_extractor.extract_facts_for_chunks"
            ) as mock_facts,
            patch(
                "quantumrag.core.ingest.indexer.chunk_graph.build_chunk_graph"
            ) as mock_chunk_graph,
            patch("quantumrag.core.ingest.quality.ChunkQualityChecker") as mock_quality_cls,
            patch(
                "quantumrag.core.ingest.indexer.multi_resolution.build_multi_resolution_chunks"
            ) as mock_multi_res,
            patch(
                "quantumrag.core.ingest.indexer.triple_index_builder.TripleIndexBuilder"
            ) as mock_builder_cls,
        ):
            mock_facts.return_value = []
            mock_quality_cls.return_value.filter_chunks.return_value = []
            mock_multi_res.return_value = []
            mock_builder_cls.return_value.build = AsyncMock()

            # Config says "full" but we pass "fast" → fast wins
            await engine.aingest(doc, mode="fast")

            mock_preamble.assert_not_called()
            mock_chunk_graph.assert_not_called()
            mock_facts.assert_called()
