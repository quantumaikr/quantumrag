"""QuantumRAG Custom Plugin Example.

Shows how to create a plugin that extends QuantumRAG with
custom parsers, hooks, and processing logic.

Requirements:
    pip install quantumrag
"""

from __future__ import annotations

from typing import Any

from quantumrag.plugins.registry import PluginRegistry, hookimpl


class LoggingPlugin:
    """Example plugin that logs all ingest and query events."""

    name = "logging-plugin"
    version = "1.0.0"

    def __init__(self) -> None:
        self.event_log: list[str] = []

    def initialize(self, config: dict[str, Any]) -> None:
        print(f"[{self.name}] Initialized with config: {config}")

    def cleanup(self) -> None:
        print(f"[{self.name}] Cleanup complete. Total events: {len(self.event_log)}")

    @hookimpl
    def on_ingest_start(self, path: str, config: dict[str, Any]) -> None:
        self.event_log.append(f"ingest_start: {path}")
        print(f"[{self.name}] Starting ingest: {path}")

    @hookimpl
    def on_ingest_complete(self, result: Any) -> None:
        self.event_log.append("ingest_complete")
        print(f"[{self.name}] Ingest complete: {result}")

    @hookimpl
    def on_query_start(self, query: str, config: dict[str, Any]) -> None:
        self.event_log.append(f"query_start: {query}")
        print(f"[{self.name}] Query: {query}")

    @hookimpl
    def on_query_complete(self, result: Any) -> None:
        self.event_log.append("query_complete")
        print(f"[{self.name}] Query complete")


# Usage
if __name__ == "__main__":
    registry = PluginRegistry()

    # Register the plugin
    plugin = LoggingPlugin()
    registry.register(plugin, config={"log_level": "debug"})

    # Simulate hook calls
    registry.call_hook("on_ingest_start", path="./docs", config={})
    registry.call_hook("on_ingest_complete", result={"docs": 5, "chunks": 50})
    registry.call_hook("on_query_start", query="What is RAG?", config={})
    registry.call_hook("on_query_complete", result={"answer": "RAG is..."})

    # Show registered plugins
    for info in registry.list_plugins():
        print(f"\nPlugin: {info.name} v{info.version}")
        print(f"  Hooks: {info.hooks}")
        print(f"  Enabled: {info.enabled}")

    # Cleanup
    registry.unregister("logging-plugin")
    print(f"\nTotal events logged: {len(plugin.event_log)}")
