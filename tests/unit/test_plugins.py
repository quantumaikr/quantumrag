"""Tests for plugin system."""

from __future__ import annotations

from typing import Any

from quantumrag.plugins.registry import PluginRegistry, hookimpl

# --- Plugin System ---


class DummyPlugin:
    name = "test-plugin"
    version = "1.0.0"

    def __init__(self) -> None:
        self.initialized = False
        self.cleaned = False

    def initialize(self, config: dict[str, Any]) -> None:
        self.initialized = True
        self.config = config

    def cleanup(self) -> None:
        self.cleaned = True

    @hookimpl
    def on_ingest_start(self, path: str, config: dict[str, Any]) -> str:
        return f"ingest:{path}"

    @hookimpl
    def on_query_start(self, query: str, config: dict[str, Any]) -> str:
        return f"query:{query}"


class AnotherPlugin:
    name = "another-plugin"
    version = "2.0.0"

    def initialize(self, config: dict[str, Any]) -> None:
        pass

    def cleanup(self) -> None:
        pass

    @hookimpl
    def on_ingest_start(self, path: str, config: dict[str, Any]) -> str:
        return f"another:{path}"


class TestPluginRegistry:
    def test_register_plugin(self) -> None:
        registry = PluginRegistry()
        plugin = DummyPlugin()
        registry.register(plugin)

        assert len(registry.list_plugins()) == 1
        info = registry.get_plugin("test-plugin")
        assert info is not None
        assert info.version == "1.0.0"
        assert plugin.initialized

    def test_register_with_config(self) -> None:
        registry = PluginRegistry()
        plugin = DummyPlugin()
        registry.register(plugin, config={"key": "value"})

        assert plugin.config == {"key": "value"}

    def test_unregister_plugin(self) -> None:
        registry = PluginRegistry()
        plugin = DummyPlugin()
        registry.register(plugin)
        result = registry.unregister("test-plugin")

        assert result is True
        assert plugin.cleaned
        assert len(registry.list_plugins()) == 0

    def test_unregister_nonexistent(self) -> None:
        registry = PluginRegistry()
        assert registry.unregister("nonexistent") is False

    def test_duplicate_registration(self) -> None:
        registry = PluginRegistry()
        plugin = DummyPlugin()
        registry.register(plugin)
        registry.register(plugin)  # Should warn but not duplicate
        assert len(registry.list_plugins()) == 1

    def test_call_hook(self) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())

        results = registry.call_hook("on_ingest_start", path="/docs", config={})
        assert len(results) == 1
        assert results[0] == "ingest:/docs"

    def test_call_hook_multiple_plugins(self) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        registry.register(AnotherPlugin())

        results = registry.call_hook("on_ingest_start", path="/docs", config={})
        assert len(results) == 2

    def test_call_nonexistent_hook(self) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        results = registry.call_hook("nonexistent_hook")
        assert results == []

    def test_disabled_plugin(self) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        info = registry.get_plugin("test-plugin")
        assert info is not None
        info.enabled = False

        results = registry.call_hook("on_ingest_start", path="/docs", config={})
        assert len(results) == 0

    def test_hook_discovery(self) -> None:
        registry = PluginRegistry()
        plugin = DummyPlugin()
        registry.register(plugin)

        info = registry.get_plugin("test-plugin")
        assert info is not None
        assert "on_ingest_start" in info.hooks
        assert "on_query_start" in info.hooks
