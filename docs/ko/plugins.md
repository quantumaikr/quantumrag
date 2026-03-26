# 플러그인 시스템

> 커스텀 파서, 청커, 리트리버, 제너레이터로 QuantumRAG를 확장하세요.

---

## 개요

QuantumRAG의 플러그인 시스템을 사용하면 코어 엔진을 수정하지 않고도 파이프라인 컴포넌트를 확장하거나 교체할 수 있습니다. 플러그인은 특정 라이프사이클 이벤트와 파이프라인 단계에 훅을 걸 수 있습니다.

---

## 플러그인 만들기

### 기본 플러그인

```python
from quantumrag.plugins.registry import PluginRegistry, hookimpl

class MyPlugin:
    name = "my-plugin"
    version = "1.0.0"

    def initialize(self, config):
        """플러그인 등록 시 호출됩니다."""
        self.config = config

    def cleanup(self):
        """플러그인 해제 시 호출됩니다."""
        pass

    @hookimpl
    def on_query_complete(self, result):
        """모든 쿼리 후 호출됩니다."""
        print(f"쿼리 답변 완료 - 신뢰도: {result.confidence}")
        return result
```

### 플러그인 등록

```python
from quantumrag import Engine
from quantumrag.plugins.registry import PluginRegistry

registry = PluginRegistry()
registry.register(MyPlugin(), config={"key": "value"})

engine = Engine()
# 플러그인은 파이프라인 실행 중 자동으로 호출됩니다
```

---

## 사용 가능한 훅

### 파이프라인 훅

| 훅 | 단계 | 설명 | 반환값 |
|----|------|------|--------|
| `on_ingest_start(path, config)` | 인제스트 전 | 문서 처리 시작 전 호출 | None |
| `on_ingest_complete(result)` | 인제스트 후 | 모든 문서 인덱싱 후 호출 | None |
| `on_query_start(query, config)` | 쿼리 전 | 쿼리 처리 시작 전 호출 | None |
| `on_query_complete(result)` | 쿼리 후 | 답변 생성 후 호출 | QueryResult |

### 변환 훅

| 훅 | 단계 | 설명 | 반환값 |
|----|------|------|--------|
| `on_chunk_created(chunk)` | 인제스트 중 | 청크 생성 후 수정 또는 필터링 | Chunk |
| `post_retrieve(query, results)` | 검색 후 | 생성 전 검색 결과 수정 | list[ScoredChunk] |
| `post_generate(query, result)` | 생성 후 | 생성된 답변 수정 | QueryResult |

### 등록 훅

| 훅 | 단계 | 설명 |
|----|------|------|
| `register_parsers(registry)` | 초기화 | 커스텀 문서 파서 등록 |
| `register_chunkers(registry)` | 초기화 | 커스텀 청킹 전략 등록 |
| `register_retrievers(registry)` | 초기화 | 커스텀 검색 로직 등록 |
| `register_generators(registry)` | 초기화 | 커스텀 생성 로직 등록 |
| `register_connectors(registry)` | 초기화 | 커스텀 데이터 소스 커넥터 등록 |

---

## 플러그인 예제

### 커스텀 파서 플러그인

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

### 검색 필터 플러그인

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
        """낮은 신뢰도의 검색 결과를 필터링합니다."""
        return [r for r in results if r.score >= self.min_score]
```

### 로깅 플러그인

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

## 플러그인 검색

플러그인을 로드하는 3가지 방법:

### 1. 프로그래밍 방식 등록

```python
registry.register(MyPlugin(), config={...})
```

### 2. 엔트리 포인트 검색 (setuptools)

플러그인의 `pyproject.toml`:

```toml
[project.entry-points."quantumrag.plugins"]
my-plugin = "my_package.plugin:MyPlugin"
```

### 3. 모듈 경로 로딩

```python
registry.load_module("path/to/my_plugin.py")
```

---

## 플러그인 라이프사이클

```
1. register(plugin, config)
   └─ plugin.initialize(config)

2. 파이프라인 실행
   └─ 관련 단계에서 훅 호출

3. unregister(plugin)
   └─ plugin.cleanup()
```

플러그인은 등록 순서대로 호출됩니다. 변환 훅이 수정된 값을 반환하면 그 값이 후속 플러그인에 전달됩니다.
