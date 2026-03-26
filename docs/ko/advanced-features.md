# 고급 기능

> 멀티 테넌시, 시맨틱 캐시, 관측성, 보안, 배치 처리.

---

## 멀티 테넌시

테넌트별 격리된 스토리지와 커스텀 설정, 쿼터 관리.

### 설정

```python
from quantumrag.core.multitenancy.tenant import TenantManager

manager = TenantManager(base_dir="/data/quantumrag")

# 테넌트 생성
manager.create_tenant(
    "acme-corp",
    display_name="Acme Corporation",
    max_documents=10000,
    max_queries_per_day=50000,
)

manager.create_tenant(
    "beta-inc",
    display_name="Beta Inc",
    embedding_model="text-embedding-3-large",
    max_documents=5000,
)
```

### 사용법

```python
# 테넌트별 엔진 가져오기
engine = manager.get_engine("acme-corp")
engine.ingest("./acme_docs")
result = engine.query("Acme의 정책은 무엇인가요?")
```

### 테넌트 격리

각 테넌트는 다음을 보유합니다:
- **격리된 데이터 디렉토리**: `/base/tenants/{tenant_id}/data`
- **개별 데이터베이스**: 테넌트별 SQLite, LanceDB, Tantivy
- **커스텀 모델**: 테넌트별 임베딩/생성 모델
- **쿼터 적용**: 문서 수, 일일 쿼리 제한
- **설정 영속성**: 테넌트 디렉토리별 `tenant.json`

### 테넌트 설정

```python
@dataclass
class TenantConfig:
    tenant_id: str                     # [a-zA-Z0-9][a-zA-Z0-9_-]{0,62}
    display_name: str
    data_dir: str
    embedding_model: str | None        # 기본값 오버라이드
    generation_model: str | None       # 기본값 오버라이드
    max_documents: int | None          # 쿼터
    max_queries_per_day: int | None    # 쿼터
    allowed_file_types: list[str]      # 형식 제한
    metadata: dict[str, Any]           # 커스텀 필드
```

---

## 시맨틱 캐시

시맨틱 유사도 매칭을 통해 중복 LLM 호출을 방지합니다.

### 설정

```yaml
cost:
  semantic_cache: true
```

### 동작 방식

```
쿼리 → 해시 매칭 → 캐시 결과 반환 (빠른 경로)
         │
         ▼ (정확한 매칭 없음)
쿼리 → 임베딩 → 코사인 유사도 → 0.95 이상이면 캐시 결과 반환
         │
         ▼ (시맨틱 매칭 없음)
전체 파이프라인 → 결과 캐싱 → 답변 반환
```

### 캐시 속성

| 속성 | 기본값 |
|------|--------|
| TTL | 3600초 (1시간) |
| 최대 엔트리 | 1000 |
| 유사도 임계값 | 0.95 |
| 저장소 | SQLite 영속 |
| 퇴거 정책 | LRU (최근 최소 사용) |

### 캐시 API

```python
from quantumrag.core.cache.semantic import SemanticCache

cache = SemanticCache(
    ttl_seconds=3600,
    max_entries=1000,
    similarity_threshold=0.95,
    storage_path="cache.db",
)

# 정확한 매칭
cached = cache.get(query)

# 시맨틱 매칭
cached = cache.get_semantic(query, query_embedding)

# 결과 저장
cache.put(query, answer, sources, confidence, metadata)

# 통계
stats = cache.stats()  # hits, misses, hit_rate
```

---

## 관측성

### 구조화 로깅

QuantumRAG는 `structlog`을 사용하여 구조화된 기계 가독 로그를 생성합니다:

```python
from quantumrag.core.logging import get_logger, setup_logging

setup_logging(level="DEBUG", json_output=True)
logger = get_logger("my_module")
logger.info("query_complete", latency_ms=1450, confidence="STRONGLY_SUPPORTED")
```

출력 (JSON 모드):

```json
{"event": "query_complete", "latency_ms": 1450, "confidence": "STRONGLY_SUPPORTED", "timestamp": "2025-01-15T10:30:00Z"}
```

### 쿼리 트레이싱

모든 쿼리는 파이프라인 단계별 추적을 생성합니다:

```python
result = engine.query("매출이 얼마인가요?")
for step in result.trace:
    print(f"{step.step}: {step.latency_ms:.0f}ms - {step.result}")
```

예시 트레이스:

```
rewrite: 0ms - 리라이트 불필요
classify: 150ms - MEDIUM (type: factual)
retrieve: 450ms - 7개 청크 검색
rerank: 200ms - 최고 점수: 0.92
compress: 50ms - 7개 청크 압축
generate: 800ms - 2개 인용 포함 답변
```

### 트레이스 저장

분석을 위해 SQLite에 트레이스 저장:

```python
from quantumrag.core.observability.tracer import TraceStore

tracer = TraceStore(db_path="traces.db")

# 트레이스 조회
traces = tracer.list_traces(limit=50, since=timestamp)

# 집계 통계
stats = tracer.get_stats(since=timestamp)
# {'total_queries': 1000, 'avg_latency_ms': 1200, 'avg_cost': 0.003}
```

---

## 보안

### API 인증

```bash
export QUANTUMRAG_API_KEY=your-secret-key
quantumrag serve --port 8000
```

모든 `/v1/*` 엔드포인트에 필요:

```
Authorization: Bearer your-secret-key
```

### 경로 탐색 방어

API 서버는 디렉토리 탐색 공격을 방지하기 위해 모든 파일 경로를 검증합니다:

1. 검증 전 URL 디코딩
2. `Path.resolve()`로 절대 경로 정규화
3. `relative_to()`로 포함 관계 확인
4. 심볼릭 링크 해석 가드

### 접근 제어 목록 (ACL)

문서 수준 접근 제어:

```python
# 인제스트 시
engine.ingest("./confidential", metadata={
    "acl_roles": ["admin", "finance"],
    "acl_users": ["user123"],
})

# 쿼리 시 — 사용자 역할에 맞는 문서만 반환
result = engine.query(
    "예산이 얼마인가요?",
    filters={"acl_roles": ["finance"]},
)
```

### 레이트 리미팅

API 키별 토큰 버킷 레이트 리미팅.

### 요청 추적

모든 API 요청에 고유한 `X-Request-ID` 헤더가 부여됩니다.

---

## 배치 처리

제어된 동시성으로 다수의 쿼리를 병렬 처리:

```python
from quantumrag.core.batch import BatchProcessor

processor = BatchProcessor(engine, max_concurrency=5)

queries = [
    "매출이 얼마인가요?",
    "CEO가 누구인가요?",
    "모든 제품을 나열해주세요",
]

results = await processor.process(queries)
for query, result in zip(queries, results):
    print(f"Q: {query}")
    print(f"A: {result.answer}\n")
```

---

## 스트리밍

### Python SDK 스트리밍

```python
async for token in engine.query_stream("보고서를 요약해주세요"):
    print(token, end="", flush=True)
```

### SSE 스트리밍 (API)

```bash
curl -N -X POST http://localhost:8000/v1/query/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "보고서를 요약해주세요"}'
```

응답 (Server-Sent Events):

```
data: 보고서의
data: 주요
data: 내용은
data: ...
data: [DONE]
```

---

## 대화 모드

자동 컨텍스트 추적이 포함된 멀티턴 대화:

```python
from quantumrag.core.models import ConversationTurn

history = []

# 턴 1
result = engine.query("CTO가 누구인가요?")
history.append(ConversationTurn(role="user", content="CTO가 누구인가요?"))
history.append(ConversationTurn(role="assistant", content=result.answer))

# 턴 2 — "그분의"가 CTO로 해소됨
result = engine.query(
    "그분의 이전 경력은?",
    conversation_history=history,
)
```

엔진이 자동으로:
1. 대명사 해소를 통한 쿼리 리라이트
2. 턴 간 활성 토픽 추적
3. 모호한 쿼리를 대화 컨텍스트로 보강
