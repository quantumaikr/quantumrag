# API 레퍼런스

> HTTP API 및 Python SDK 레퍼런스.

---

## Python SDK

### Engine

`Engine` 클래스는 모든 QuantumRAG 기능의 단일 진입점입니다.

```python
from quantumrag import Engine
```

#### 생성자

```python
Engine(
    config: str | Path | QuantumRAGConfig | None = None,
    *,
    document_store: Any | None = None,    # 커스텀 스토어 주입
    vector_store: Any | None = None,      # 커스텀 스토어 주입
    bm25_store: Any | None = None,        # 커스텀 스토어 주입
    embedding_model: str | None = None,   # 빠른 오버라이드
    generation_model: str | None = None,  # 빠른 오버라이드
    data_dir: str | None = None,          # 빠른 오버라이드
)
```

#### 메서드

**`ingest(path, *, chunking_strategy=None, metadata=None, recursive=True, enable_hype=True) → IngestResult`**

파일 또는 디렉토리에서 문서를 인제스트합니다.

```python
result = engine.ingest("./docs", recursive=True)
print(result.documents)       # 처리된 문서 수
print(result.chunks)          # 생성된 청크 수
print(result.elapsed_seconds) # 소요 시간
print(result.errors)          # 에러 메시지 목록
```

매개변수:
- `path` — 파일 또는 디렉토리 경로
- `chunking_strategy` — 오버라이드: `"auto"`, `"structural"`, `"semantic"`, `"fixed"`
- `metadata` — 모든 문서에 첨부할 커스텀 메타데이터 딕셔너리
- `recursive` — 하위 디렉토리 재귀 탐색 (기본값: `True`)
- `enable_hype` — HyPE 임베딩 생성 (기본값: `True`)

**`query(query, *, filters=None, top_k=None, rerank=None, conversation_history=None) → QueryResult`**

인덱싱된 문서에 질의합니다.

```python
result = engine.query("매출이 얼마인가요?")
print(result.answer)      # 인라인 인용이 포함된 답변
print(result.confidence)  # 신뢰도 열거형
print(result.sources)     # List[Source] 발췌문 포함
print(result.trace)       # List[TraceStep] 파이프라인 추적
print(result.metadata)    # tokens_used, cost, latency_ms 등
```

매개변수:
- `query` — 자연어 질문
- `filters` — 메타데이터 필터 (dict)
- `top_k` — 검색 수 오버라이드
- `rerank` — 리랭킹 오버라이드 (bool)
- `conversation_history` — 멀티턴용 `ConversationTurn` 목록

**`query_stream(query, *, filters=None, top_k=None) → AsyncIterator[str]`**

답변 토큰을 스트리밍합니다.

```python
async for token in engine.query_stream("매출이 얼마인가요?"):
    print(token, end="", flush=True)
```

**`evaluate(**kwargs) → EvalResult`**

평가 파이프라인을 실행합니다.

```python
result = engine.evaluate()
print(result.summary)
for metric in result.metrics:
    print(f"{metric.name}: {metric.score:.2f}")
for suggestion in result.suggestions:
    print(f"- {suggestion}")
```

**`status() → dict`**

엔진 상태를 조회합니다.

```python
status = engine.status()
# {'documents': 15, 'chunks': 234, 'config': {...}, 'data_dir': '...'}
```

### 데이터 모델

**QueryResult**

```python
@dataclass
class QueryResult:
    answer: str                    # 인용 포함 생성 답변
    sources: list[Source]          # 출처 참조
    confidence: Confidence         # STRONGLY_SUPPORTED | PARTIALLY_SUPPORTED | INSUFFICIENT_EVIDENCE
    trace: list[TraceStep]         # 파이프라인 실행 추적
    metadata: dict[str, Any]       # tokens_used, cost, latency_ms, path 등
```

**Source**

```python
@dataclass
class Source:
    chunk_id: str
    document_title: str
    page: int | None
    section: str | None
    excerpt: str                   # 관련 텍스트 발췌
    relevance_score: float
```

**Confidence**

```python
class Confidence(Enum):
    STRONGLY_SUPPORTED = "STRONGLY_SUPPORTED"         # 강력히 뒷받침됨
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"       # 부분적으로 뒷받침됨
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"   # 근거 불충분
```

**TraceStep**

```python
@dataclass
class TraceStep:
    step: str            # "rewrite", "classify", "retrieve", "generate" 등
    result: str          # 단계 출력 요약
    latency_ms: float
    details: dict        # 단계별 상세 정보
```

**IngestResult**

```python
@dataclass
class IngestResult:
    documents: int
    chunks: int
    elapsed_seconds: float
    errors: list[str]
```

---

## HTTP API

서버 시작:

```bash
quantumrag serve --host 0.0.0.0 --port 8000
```

인터랙티브 문서: `http://localhost:8000/docs` (Swagger UI)

### 인증

`QUANTUMRAG_API_KEY`가 설정된 경우, 모든 `/v1/*` 엔드포인트에 헤더 필요:

```
Authorization: Bearer <api-key>
```

### 엔드포인트

#### `GET /health`

헬스체크 (인증 불필요).

```json
{
  "status": "ok",
  "version": "0.1.0",
  "uptime_seconds": 123.4
}
```

#### `POST /v1/ingest`

파일 시스템 경로에서 문서 인제스트.

**요청:**

```json
{
  "path": "./docs",
  "chunking_strategy": "auto",
  "metadata": {"project": "alpha"},
  "recursive": true,
  "enable_hype": true
}
```

**응답:**

```json
{
  "documents": 15,
  "chunks": 234,
  "elapsed_seconds": 45.2,
  "errors": []
}
```

#### `POST /v1/ingest/upload`

파일 업로드 인제스트 (멀티파트 폼 데이터).

```bash
curl -X POST http://localhost:8000/v1/ingest/upload \
  -H "Authorization: Bearer $API_KEY" \
  -F "files=@report.pdf" \
  -F "files=@data.xlsx"
```

#### `POST /v1/ingest/text`

원시 텍스트 직접 인제스트.

**요청:**

```json
{
  "text": "분기 매출이 500억에 도달했습니다...",
  "title": "Q3 보고서",
  "metadata": {"type": "report"}
}
```

#### `POST /v1/query`

동기 질의.

**요청:**

```json
{
  "query": "분기별 매출이 얼마인가요?",
  "filters": null,
  "top_k": 7,
  "rerank": true,
  "conversation_history": []
}
```

**응답:**

```json
{
  "answer": "분기 매출은 500억원입니다 [1].",
  "sources": [
    {
      "chunk_id": "abc123",
      "document_title": "Q3 보고서",
      "page": 3,
      "section": "재무 요약",
      "excerpt": "Q3 매출이 500억에 도달...",
      "relevance_score": 0.92
    }
  ],
  "confidence": "STRONGLY_SUPPORTED",
  "trace": [...],
  "metadata": {
    "tokens_used": 1250,
    "estimated_cost": 0.003,
    "latency_ms": 1450,
    "path": "MEDIUM"
  }
}
```

#### `POST /v1/query/stream`

SSE 스트리밍 질의.

**요청:**

```json
{
  "query": "주요 발견 사항을 요약해주세요",
  "top_k": 7
}
```

**응답:** Server-Sent Events 스트림:

```
data: 주요
data: 발견
data: 사항은
data: ...
data: [DONE]
```

#### `GET /v1/documents`

인덱싱된 문서 목록 조회.

**쿼리 파라미터:**
- `limit` (기본값: 50)
- `offset` (기본값: 0)

**응답:**

```json
{
  "documents": [
    {
      "id": "doc-uuid",
      "title": "Q3 보고서",
      "source_type": "FILE",
      "chunks": 15,
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 15
}
```

#### `DELETE /v1/documents/{document_id}`

문서 및 관련 청크 삭제.

#### `GET /v1/status`

엔진 상태 조회.

```json
{
  "documents": 15,
  "chunks": 234,
  "config": {
    "language": "ko",
    "domain": "general"
  }
}
```

#### `POST /v1/evaluate`

평가 메트릭 실행.

**요청:**

```json
{
  "benchmark_file": null,
  "sample_count": 20
}
```

**응답:**

```json
{
  "metrics": [
    {"name": "retrieval_recall", "score": 0.92},
    {"name": "faithfulness", "score": 0.95},
    {"name": "answer_relevancy", "score": 0.88}
  ],
  "summary": "전체 품질: 양호",
  "suggestions": ["복잡한 쿼리에 대해 top_k 증가를 권장합니다"]
}
```

#### `POST /v1/feedback`

쿼리 결과에 대한 사용자 피드백 제출.

**요청:**

```json
{
  "query": "매출이 얼마인가요?",
  "answer": "매출은 500억원입니다 [1].",
  "rating": 5,
  "comment": "정확하고 인용이 잘 되어 있습니다"
}
```

---

## CLI 레퍼런스

```bash
quantumrag [OPTIONS] COMMAND [ARGS]
```

### 전역 옵션

| 옵션 | 설명 |
|------|------|
| `--verbose`, `-v` | 디버그 로깅 활성화 |
| `--json-log` | JSON 형식 로그 출력 |
| `--version` | 버전 표시 후 종료 |

### 명령어

**`init`** — 기본 설정 파일 생성

```bash
quantumrag init [--config quantumrag.yaml]
```

**`ingest`** — 문서 인제스트

```bash
quantumrag ingest <PATH> [OPTIONS]
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--config`, `-c` | 설정 파일 경로 | `quantumrag.yaml` |
| `--strategy`, `-s` | 청킹 전략 | `auto` |
| `--metadata`, `-m` | Key=value 쌍 | (없음) |
| `--watch`, `-w` | 파일 변경 감시 | `false` |
| `--recursive` / `--no-recursive` | 하위 디렉토리 재귀 | `true` |

**`query`** — 질문하기

```bash
quantumrag query "매출이 얼마인가요?" [OPTIONS]
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--config`, `-c` | 설정 파일 경로 | `quantumrag.yaml` |
| `--top-k` | 검색 청크 수 | 설정값 |

**`serve`** — HTTP API 서버 시작

```bash
quantumrag serve [OPTIONS]
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--config`, `-c` | 설정 파일 경로 | `quantumrag.yaml` |
| `--host` | 바인드 주소 | `127.0.0.1` |
| `--port` | 바인드 포트 | `8000` |

**`status`** — 엔진 상태 표시

```bash
quantumrag status [--config quantumrag.yaml]
```

**`evaluate`** — 평가 실행

```bash
quantumrag evaluate [--benchmark benchmark.json]
```
