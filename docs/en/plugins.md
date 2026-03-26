# Plugin System

> Extend QuantumRAG with custom parsers, chunkers, retrievers, and generators.

---

## Overview

QuantumRAG's plugin system allows you to extend or replace any pipeline component without modifying the core engine. Plugins hook into specific lifecycle events and pipeline stages.

---

## Creating a Plugin

### Basic Plugin

```python
from quantumrag.plugins.registry import PluginRegistry, hookimpl

class MyPlugin:
    name = "my-plugin"
    version = "1.0.0"

    def initialize(self, config):
        """Called when the plugin is registered."""
        self.config = config

    def cleanup(self):
        """Called when the plugin is unregistered."""
        pass

    @hookimpl
    def on_query_complete(self, result):
        """Called after every query."""
        print(f"Query answered with confidence: {result.confidence}")
        return result
```

### Registering a Plugin

```python
from quantumrag import Engine
from quantumrag.plugins.registry import PluginRegistry

registry = PluginRegistry()
registry.register(MyPlugin(), config={"key": "value"})

engine = Engine()
# Plugins are called automatically during pipeline execution
```

---

## Available Hooks

### Pipeline Hooks

| Hook | Phase | Description | Return |
|------|-------|-------------|--------|
| `on_ingest_start(path, config)` | Before ingest | Called before document processing begins | None |
| `on_ingest_complete(result)` | After ingest | Called after all documents are indexed | None |
| `on_query_start(query, config)` | Before query | Called before query processing begins | None |
| `on_query_complete(result)` | After query | Called after answer is generated | QueryResult |

### Transformation Hooks

| Hook | Phase | Description | Return |
|------|-------|-------------|--------|
| `on_chunk_created(chunk)` | During ingest | Modify or filter chunks after creation | Chunk |
| `post_retrieve(query, results)` | After retrieval | Modify retrieval results before generation | list[ScoredChunk] |
| `post_generate(query, result)` | After generation | Modify the generated answer | QueryResult |

### Registration Hooks

| Hook | Phase | Description |
|------|-------|-------------|
| `register_parsers(registry)` | Initialization | Register custom document parsers |
| `register_chunkers(registry)` | Initialization | Register custom chunking strategies |
| `register_retrievers(registry)` | Initialization | Register custom retrieval logic |
| `register_generators(registry)` | Initialization | Register custom generation logic |
| `register_connectors(registry)` | Initialization | Register custom data source connectors |

---

## Plugin Examples

### Custom Parser Plugin

```python
class JSONParser:
    name = "json-parser"
    version = "1.0.0"

    def initialize(self, config):
        pass

    def cleanup(self):
        pass

    @hookimpl
    def register_parsers(self, registry):
        registry.register_parser(".json", self.parse_json)
        registry.register_parser(".jsonl", self.parse_jsonl)

    def parse_json(self, path):
        import json
        with open(path) as f:
            data = json.load(f)
        return str(data)

    def parse_jsonl(self, path):
        import json
        lines = []
        with open(path) as f:
            for line in f:
                lines.append(str(json.loads(line)))
        return "\n".join(lines)
```

### Retrieval Filter Plugin

```python
class ConfidenceFilter:
    name = "confidence-filter"
    version = "1.0.0"

    def initialize(self, config):
        self.min_score = config.get("min_score", 0.3)

    def cleanup(self):
        pass

    @hookimpl
    def post_retrieve(self, query, results):
        """Filter out low-confidence retrieval results."""
        return [r for r in results if r.score >= self.min_score]
```

### Logging Plugin

```python
class QueryLogger:
    name = "query-logger"
    version = "1.0.0"

    def initialize(self, config):
        self.log_file = config.get("log_file", "queries.log")

    def cleanup(self):
        pass

    @hookimpl
    def on_query_complete(self, result):
        with open(self.log_file, "a") as f:
            f.write(f"{result.metadata.get('latency_ms')}ms | {result.confidence} | {result.answer[:100]}\n")
        return result
```

---

## Plugin Discovery

Plugins can be loaded in three ways:

### 1. Programmatic Registration

```python
registry.register(MyPlugin(), config={...})
```

### 2. Entry Point Discovery (setuptools)

In your plugin's `pyproject.toml`:

```toml
[project.entry-points."quantumrag.plugins"]
my-plugin = "my_package.plugin:MyPlugin"
```

### 3. Module Path Loading

```python
registry.load_module("path/to/my_plugin.py")
```

---

## Plugin Lifecycle

```
1. register(plugin, config)
   └─ plugin.initialize(config)

2. Pipeline execution
   └─ Hooks called at relevant stages

3. unregister(plugin)
   └─ plugin.cleanup()
```

Plugins are called in registration order. If a transformation hook returns a modified value, that value is passed to subsequent plugins.
