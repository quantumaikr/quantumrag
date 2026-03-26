"""Plugin registry — discover, load, and manage plugins.

Plugins can extend QuantumRAG with custom parsers, chunkers, retrievers,
generators, and more.

Example plugin structure::

    # my_plugin.py
    from quantumrag.plugins.registry import Plugin, hookimpl

    class MyParserPlugin(Plugin):
        name = "my-parser"
        version = "1.0.0"

        @hookimpl
        def register_parsers(self, registry):
            registry.register(MyCustomParser())
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from quantumrag.core.logging import get_logger

logger = get_logger(__name__)


# --- Plugin Protocol ---


@runtime_checkable
class Plugin(Protocol):
    """Base protocol for all QuantumRAG plugins."""

    name: str
    version: str

    def initialize(self, config: dict[str, Any]) -> None:
        """Called when the plugin is loaded."""
        ...

    def cleanup(self) -> None:
        """Called when the plugin is unloaded."""
        ...


# --- Hook Specifications ---


class HookSpec:
    """Defines available plugin hooks."""

    def register_parsers(self, registry: Any) -> None:
        """Register custom document parsers."""

    def register_chunkers(self, registry: Any) -> None:
        """Register custom chunking strategies."""

    def register_retrievers(self, registry: Any) -> None:
        """Register custom retrieval strategies."""

    def register_generators(self, registry: Any) -> None:
        """Register custom generation strategies."""

    def register_connectors(self, registry: Any) -> None:
        """Register custom document source connectors."""

    def on_ingest_start(self, path: str, config: dict[str, Any]) -> None:
        """Called before ingestion starts."""

    def on_ingest_complete(self, result: Any) -> None:
        """Called after ingestion completes."""

    def on_query_start(self, query: str, config: dict[str, Any]) -> None:
        """Called before query processing starts."""

    def on_query_complete(self, result: Any) -> None:
        """Called after query processing completes."""

    def on_chunk_created(self, chunk: Any) -> Any:
        """Called when a chunk is created. Can modify the chunk."""

    def post_retrieve(self, query: str, results: list[Any]) -> list[Any]:
        """Called after retrieval. Can filter/modify results."""

    def post_generate(self, query: str, result: Any) -> Any:
        """Called after generation. Can modify the result."""


def hookimpl(func: Any) -> Any:
    """Decorator to mark a method as a hook implementation."""
    func._is_hookimpl = True
    return func


# --- Plugin Registry ---


@dataclass
class PluginInfo:
    """Metadata about a loaded plugin."""

    name: str
    version: str
    plugin: Plugin
    hooks: list[str] = field(default_factory=list)
    enabled: bool = True


class PluginRegistry:
    """Central registry for discovering, loading, and managing plugins.

    Supports three plugin discovery methods:
    1. Programmatic registration via `register()`
    2. Entry point discovery via `discover_entrypoints()`
    3. Module path loading via `load_module()`
    """

    def __init__(self) -> None:
        self._plugins: dict[str, PluginInfo] = {}
        self._hook_implementations: dict[str, list[tuple[str, Any]]] = {}

    def register(
        self, plugin: Plugin, config: dict[str, Any] | None = None
    ) -> None:
        """Register and initialize a plugin."""
        name = plugin.name
        if name in self._plugins:
            logger.warning("plugin_already_registered", name=name)
            return

        # Initialize the plugin
        try:
            if hasattr(plugin, "initialize"):
                plugin.initialize(config or {})
        except Exception as e:
            logger.error("plugin_init_failed", name=name, error=str(e))
            return

        # Discover hook implementations
        hooks: list[str] = []
        for attr_name in dir(plugin):
            attr = getattr(plugin, attr_name, None)
            if callable(attr) and getattr(attr, "_is_hookimpl", False):
                hooks.append(attr_name)
                if attr_name not in self._hook_implementations:
                    self._hook_implementations[attr_name] = []
                self._hook_implementations[attr_name].append((name, attr))

        info = PluginInfo(
            name=name,
            version=getattr(plugin, "version", "0.0.0"),
            plugin=plugin,
            hooks=hooks,
        )
        self._plugins[name] = info
        logger.info(
            "plugin_registered",
            name=name,
            version=info.version,
            hooks=hooks,
        )

    def unregister(self, name: str) -> bool:
        """Unregister and cleanup a plugin."""
        info = self._plugins.pop(name, None)
        if not info:
            return False

        # Remove hook implementations
        for hook_name in info.hooks:
            if hook_name in self._hook_implementations:
                self._hook_implementations[hook_name] = [
                    (n, h)
                    for n, h in self._hook_implementations[hook_name]
                    if n != name
                ]

        # Cleanup
        try:
            if hasattr(info.plugin, "cleanup"):
                info.plugin.cleanup()
        except Exception as e:
            logger.warning("plugin_cleanup_failed", name=name, error=str(e))

        logger.info("plugin_unregistered", name=name)
        return True

    def get_plugin(self, name: str) -> PluginInfo | None:
        """Get plugin info by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[PluginInfo]:
        """List all registered plugins."""
        return list(self._plugins.values())

    def call_hook(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """Call all implementations of a hook.

        Returns list of results from each plugin's implementation.
        """
        implementations = self._hook_implementations.get(hook_name, [])
        results: list[Any] = []

        for plugin_name, hook_fn in implementations:
            info = self._plugins.get(plugin_name)
            if not info or not info.enabled:
                continue

            try:
                result = hook_fn(**kwargs)
                results.append(result)
            except Exception as e:
                logger.warning(
                    "hook_call_failed",
                    hook=hook_name,
                    plugin=plugin_name,
                    error=str(e),
                )

        return results

    def call_hook_chain(self, hook_name: str, value: Any, **kwargs: Any) -> Any:
        """Call hook implementations as a chain, passing result of each to next.

        Used for hooks that transform data (like post_retrieve, post_generate).
        """
        implementations = self._hook_implementations.get(hook_name, [])

        for plugin_name, hook_fn in implementations:
            info = self._plugins.get(plugin_name)
            if not info or not info.enabled:
                continue

            try:
                value = hook_fn(value=value, **kwargs)
            except Exception as e:
                logger.warning(
                    "hook_chain_failed",
                    hook=hook_name,
                    plugin=plugin_name,
                    error=str(e),
                )

        return value

    def discover_entrypoints(self, group: str = "quantumrag.plugins") -> int:
        """Discover plugins from Python entry points.

        Looks for entry points in the 'quantumrag.plugins' group.
        Returns the number of plugins discovered.
        """
        count = 0
        if sys.version_info >= (3, 12):
            from importlib.metadata import entry_points

            eps = entry_points(group=group)
        else:
            from importlib.metadata import entry_points

            all_eps = entry_points()
            eps = all_eps.get(group, [])

        for ep in eps:
            try:
                plugin_class = ep.load()
                plugin = plugin_class()
                self.register(plugin)
                count += 1
            except Exception as e:
                logger.warning(
                    "plugin_entrypoint_failed",
                    name=ep.name,
                    error=str(e),
                )

        return count

    def load_module(self, module_path: str) -> bool:
        """Load a plugin from a Python module path.

        Args:
            module_path: Dotted module path (e.g., 'mypackage.plugins.custom')
        """
        try:
            module = importlib.import_module(module_path)
            # Look for Plugin subclasses in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and attr_name != "Plugin"
                    and isinstance(attr, type)
                    and hasattr(attr, "name")
                    and hasattr(attr, "version")
                ):
                    try:
                        plugin = attr()
                        if isinstance(plugin, Plugin):
                            self.register(plugin)
                            return True
                    except Exception:
                        continue
            return False
        except ImportError as e:
            logger.error("plugin_module_load_failed", path=module_path, error=str(e))
            return False
