"""Tests for plugin system and multi-tenancy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from quantumrag.core.multitenancy.tenant import TenantConfig, TenantManager
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

        results = registry.call_hook(
            "on_ingest_start", path="/docs", config={}
        )
        assert len(results) == 1
        assert results[0] == "ingest:/docs"

    def test_call_hook_multiple_plugins(self) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        registry.register(AnotherPlugin())

        results = registry.call_hook(
            "on_ingest_start", path="/docs", config={}
        )
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

        results = registry.call_hook(
            "on_ingest_start", path="/docs", config={}
        )
        assert len(results) == 0

    def test_hook_discovery(self) -> None:
        registry = PluginRegistry()
        plugin = DummyPlugin()
        registry.register(plugin)

        info = registry.get_plugin("test-plugin")
        assert info is not None
        assert "on_ingest_start" in info.hooks
        assert "on_query_start" in info.hooks


# --- Multi-tenancy ---


class TestTenantConfig:
    def test_valid_tenant_id(self) -> None:
        config = TenantConfig(tenant_id="acme-corp")
        assert config.tenant_id == "acme-corp"
        assert config.display_name == "acme-corp"

    def test_custom_display_name(self) -> None:
        config = TenantConfig(tenant_id="acme", display_name="Acme Corp")
        assert config.display_name == "Acme Corp"

    def test_invalid_tenant_id(self) -> None:
        with pytest.raises(ValueError, match="Invalid tenant ID"):
            TenantConfig(tenant_id="")

    def test_invalid_tenant_id_special_chars(self) -> None:
        with pytest.raises(ValueError, match="Invalid tenant ID"):
            TenantConfig(tenant_id="tenant with spaces")

    def test_valid_tenant_id_patterns(self) -> None:
        TenantConfig(tenant_id="tenant-1")
        TenantConfig(tenant_id="tenant_2")
        TenantConfig(tenant_id="Tenant3")
        TenantConfig(tenant_id="a")


class TestTenantManager:
    def test_create_tenant(self, tmp_path: Path) -> None:
        manager = TenantManager(tmp_path / "quantumrag")
        config = manager.create_tenant("test-tenant", display_name="Test")

        assert config.tenant_id == "test-tenant"
        assert config.display_name == "Test"
        assert Path(config.data_dir).exists()

    def test_create_duplicate_tenant(self, tmp_path: Path) -> None:
        manager = TenantManager(tmp_path / "quantumrag")
        manager.create_tenant("test-tenant")

        with pytest.raises(ValueError, match="already exists"):
            manager.create_tenant("test-tenant")

    def test_list_tenants(self, tmp_path: Path) -> None:
        manager = TenantManager(tmp_path / "quantumrag")
        manager.create_tenant("t1")
        manager.create_tenant("t2")
        manager.create_tenant("t3")

        tenants = manager.list_tenants()
        assert len(tenants) == 3

    def test_get_tenant(self, tmp_path: Path) -> None:
        manager = TenantManager(tmp_path / "quantumrag")
        manager.create_tenant("my-tenant", display_name="My Tenant")

        config = manager.get_tenant("my-tenant")
        assert config is not None
        assert config.display_name == "My Tenant"

    def test_get_nonexistent_tenant(self, tmp_path: Path) -> None:
        manager = TenantManager(tmp_path / "quantumrag")
        assert manager.get_tenant("nonexistent") is None

    def test_delete_tenant(self, tmp_path: Path) -> None:
        manager = TenantManager(tmp_path / "quantumrag")
        manager.create_tenant("to-delete")
        assert manager.delete_tenant("to-delete") is True
        assert manager.get_tenant("to-delete") is None

    def test_delete_nonexistent_tenant(self, tmp_path: Path) -> None:
        manager = TenantManager(tmp_path / "quantumrag")
        assert manager.delete_tenant("nonexistent") is False

    def test_tenant_persistence(self, tmp_path: Path) -> None:
        base_dir = tmp_path / "quantumrag"
        manager1 = TenantManager(base_dir)
        manager1.create_tenant("persistent", display_name="Persistent Tenant")

        # Reload from disk
        manager2 = TenantManager(base_dir)
        config = manager2.get_tenant("persistent")
        assert config is not None
        assert config.display_name == "Persistent Tenant"

    def test_tenant_status(self, tmp_path: Path) -> None:
        manager = TenantManager(tmp_path / "quantumrag")
        manager.create_tenant("status-test")

        status = manager.tenant_status("status-test")
        assert status["tenant_id"] == "status-test"
        assert "storage_bytes" in status

    def test_tenant_status_unknown(self, tmp_path: Path) -> None:
        manager = TenantManager(tmp_path / "quantumrag")
        status = manager.tenant_status("unknown")
        assert "error" in status

    def test_get_engine_unknown_tenant(self, tmp_path: Path) -> None:
        manager = TenantManager(tmp_path / "quantumrag")
        with pytest.raises(ValueError, match="Unknown tenant"):
            manager.get_engine("nonexistent")

    def test_create_tenant_with_limits(self, tmp_path: Path) -> None:
        manager = TenantManager(tmp_path / "quantumrag")
        config = manager.create_tenant(
            "limited",
            max_documents=100,
            max_queries_per_day=1000,
            allowed_file_types=[".pdf", ".txt"],
        )
        assert config.max_documents == 100
        assert config.max_queries_per_day == 1000
        assert ".pdf" in config.allowed_file_types
