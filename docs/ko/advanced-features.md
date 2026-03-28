# 고급 기능

> 생성 후 교정 파이프라인, 환각 방지, 시맨틱 캐시, 관측성, 보안, 배치 처리.

---

## 생성 후 교정 파이프라인 (Post-Generation Correction)

답변 생성 후 자동으로 모듈형 교정 체인이 실행됩니다:

```
Generate → Retrieval Retry → Self-Correct → Fact Verify → Completeness
```

각 단계는 선행 조건을 체크하고, 불필요하면 건너뜁니다 (정상 경로에서 오버헤드 없음).

| 단계 | 트리거 | 동작 |
|------|--------|------|
| **Retrieval Retry** | confidence = insufficient_evidence | BM25 위주로 재검색 |
| **Self-Correct** | 낮은 신뢰도 패턴 감지 | 교정 힌트와 함께 재생성 |
| **Fact Verify** | 고객/재무 사실이 답변에 포함 | 추출된 fact과 교차 검증 |
| **Completeness** | 다중 항목 쿼리 감지 | 모든 기대 항목이 포함되었는지 확인 |

### Fact Verifier (환각 방지)

LLM 비용 없이 규칙 기반으로 검증:

```python
result = engine.query("주요 고객사를 알려주세요")
# 답변에 "SK텔레콤"이 있지만 fact index에는 "삼성전자", "LG전자"만 있으면
# → fact_verifier가 잠재적 환각으로 플래그
# → 교정 힌트와 함께 재생성
```

설계 원칙: 정밀도 우선 — 명확한 모순만 플래그, 모호한 경우 허용.

### 완전성 검사 (Completeness Checker)

다중 항목 쿼리를 감지하고 커버리지를 확인:

```python
# "3건의 계약을 알려주세요" → 3개 항목 기대
# "매출과 비용 및 이익을 비교해줘" → 3개 항목: 매출, 비용, 이익
# 답변이 2/3만 커버하면 → 누락 항목에 대해 타겟 재검색
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
result = engine.query("적응형 쿼리 라우팅은 어떻게 동작하나요?")
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
    "Triple Index Fusion은 어떻게 동작하나요?",
    "지원되는 청킹 전략은 무엇인가요?",
    "모든 데이터 커넥터를 나열해주세요",
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
