# 설정 가이드

> QuantumRAG 전체 설정 옵션 레퍼런스.

---

## 설정 병합 순서

```
기본값 ← YAML 파일 ← 환경 변수 ← 코드 인자
```

각 계층은 이전 계층을 오버라이드합니다. 환경 변수는 `QUANTUMRAG_` 접두사와 `__` 구분자를 사용합니다:

```bash
export QUANTUMRAG_LANGUAGE=ko
export QUANTUMRAG_MODELS__EMBEDDING__PROVIDER=gemini
export QUANTUMRAG_RETRIEVAL__TOP_K=10
```

---

## 전체 레퍼런스

### 프로젝트 설정

```yaml
project_name: "my-knowledge-base"   # 프로젝트 식별자
language: "ko"                       # 기본 언어: ko, en, auto
domain: "general"                    # 도메인 힌트: general, legal, medical, financial, technical, support
```

### 모델

#### 임베딩

```yaml
models:
  embedding:
    provider: "openai"               # openai, gemini, ollama, local
    model: "text-embedding-3-small"  # 모델명
    dimensions: 1536                 # 임베딩 차원
    api_key: null                    # null → SDK 기본 환경 변수 사용
    base_url: null                   # 커스텀 엔드포인트 (Azure 등)
```

**프로바이더 옵션:**

| 프로바이더 | 모델 | 차원 | API 키 환경 변수 |
|-----------|------|-----|-----------------|
| openai | text-embedding-3-small | 1536 | `OPENAI_API_KEY` |
| openai | text-embedding-3-large | 3072 | `OPENAI_API_KEY` |
| gemini | (Google Embedding API) | 다양 | `GOOGLE_API_KEY` |
| ollama | nomic-embed-text | 768 | (불필요) |
| local | BAAI/bge-m3 | 1024 | (불필요) |

#### 생성

비용 최적화를 위한 3단계 티어. 단순 쿼리(~70%)는 저렴한 모델, 복잡한 쿼리(~10%)는 강력한 모델 사용.

```yaml
models:
  generation:
    simple:
      provider: "openai"
      model: "gpt-5.4-nano"
      api_key: null
      base_url: null
    medium:
      provider: "openai"
      model: "gpt-5.4-mini"
      api_key: null
      base_url: null
    complex:
      provider: "anthropic"
      model: "claude-sonnet-4-20250514"
      api_key: null
      base_url: null
```

**지원 프로바이더:** `openai`, `anthropic`, `gemini`, `ollama`

#### 리랭커

```yaml
models:
  reranker:
    provider: "flashrank"            # flashrank, bge, cohere, jina, noop
    model: null                      # 프로바이더별 모델 오버라이드
```

| 프로바이더 | 비용 | GPU | 비고 |
|-----------|------|-----|------|
| flashrank | 무료 | CPU | 기본값. ms-marco-MiniLM-L-12-v2 |
| bge | 무료 | CPU | 다국어 지원 |
| cohere | 유료 API | N/A | rerank-v3.5. `COHERE_API_KEY` 필요 |
| jina | 유료 API | N/A | jina-reranker-v2-base-multilingual. `JINA_API_KEY` 필요 |
| noop | 무료 | N/A | 리랭킹 건너뛰기 (top_k만 적용) |

#### HyPE (Hypothetical Prompt Embedding)

```yaml
models:
  hype:
    provider: "openai"
    model: "gpt-5.4-nano"
    questions_per_chunk: 3           # 청크당 가상 질문 수
    api_key: null
    base_url: null
```

### 인제스트 설정

```yaml
ingest:
  chunking:
    strategy: "auto"                 # auto, semantic, fixed, custom
    chunk_size: 512                  # 청크당 토큰 수
    overlap: 50                      # 청크 간 중복 토큰
  quality_check: true                # 청킹 후 파싱 품질 검증
  contextual_preamble: true          # 청크별 LLM 생성 컨텍스트 접두사
```

| 전략 | 설명 |
|------|------|
| auto | 문서 구조에 따라 자동 선택 (제목 → structural, 단락 → semantic, 그 외 → fixed) |
| structural | Markdown/HTML 제목 기준 분할, 계층 구조 유지 |
| semantic | 의미 유사도 기반 그룹핑, 자연스러운 경계 존중 |
| fixed | 토큰 기반 분할, 문장 경계 존중 |

### 검색 설정

```yaml
retrieval:
  top_k: 7                          # 검색 청크 수
  fusion_candidate_multiplier: 3    # 인덱스당 후보 = top_k × multiplier
  fusion_weights:
    original: 0.4                   # RRF에서 Original 임베딩 가중치
    hype: 0.35                      # RRF에서 HyPE 임베딩 가중치
    bm25: 0.25                      # RRF에서 BM25 키워드 가중치
  rerank: true                      # 크로스 인코더 리랭킹 활성화
  compression: true                 # 컨텍스트 압축 활성화
  slow_retrieval_threshold_ms: 2000 # 느린 쿼리 경고 임계값
```

### 생성 설정

```yaml
generation:
  streaming: true                    # 토큰 단위 스트리밍
  max_tokens: 2048                   # 생성 답변 최대 토큰 수
  temperature: 0.1                   # 생성 온도 (0 = 결정론적)
  citation_style: "inline"          # inline ([1], [2]) 또는 footnote
  confidence_signal: true            # 신뢰도 평가 포함
  high_confidence_threshold: 0.8     # 이 점수 이상 = STRONGLY_SUPPORTED
  low_confidence_threshold: 0.5      # 이 점수 이상 = PARTIALLY_SUPPORTED
  no_answer_penalty: 0.3            # INSUFFICIENT_EVIDENCE 시 신뢰도 승수
  max_context_chars: 12000           # 컨텍스트 윈도우 최대 문자 수
```

### 평가 설정

```yaml
evaluation:
  auto_synthetic: true               # 벤치마크 미제공 시 QA 쌍 자동 생성
  metrics:
    - "retrieval_recall"
    - "faithfulness"
    - "answer_relevancy"
    - "completeness"
    - "latency"
    - "cost"
```

### 스토리지 설정

```yaml
storage:
  backend: "local"                   # local, server, cluster
  vector_db: "lancedb"              # lancedb, qdrant, pgvector
  document_store: "sqlite"          # sqlite, postgresql
  data_dir: "./quantumrag_data"     # 데이터 디렉토리 경로
```

### 비용 설정

```yaml
cost:
  budget_daily: null                 # 일일 예산 한도 USD (null = 무제한)
  budget_monthly: null               # 월간 예산 한도 USD
  semantic_cache: false              # 시맨틱 결과 캐싱 활성화
  prompt_caching: true               # 프로바이더 수준 프롬프트 캐싱
```

### 한국어 설정

```yaml
korean:
  morphology: "kiwi"                # kiwi (권장) 또는 mecab
  hwp_parser: "auto"                # auto, pyhwp, libreoffice
  mixed_script: true                # 한영 혼합 텍스트 처리
```

---

## API 키 설정

API 키 설정 방법 3가지 (우선순위 순):

### 1. YAML 설정 (모델별)

```yaml
models:
  embedding:
    api_key: "sk-..."
  generation:
    complex:
      api_key: "sk-ant-..."
```

### 2. QuantumRAG 환경 변수

```bash
export QUANTUMRAG_MODELS__EMBEDDING__API_KEY=sk-...
export QUANTUMRAG_MODELS__GENERATION__COMPLEX__API_KEY=sk-ant-...
```

### 3. SDK 기본 환경 변수

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=AIza...
export COHERE_API_KEY=...
export JINA_API_KEY=...
```

---

## 설정 예시

### 최소 설정 (OpenAI만)

```yaml
project_name: "my-project"
language: "auto"
```

`OPENAI_API_KEY`만 설정하면 모든 기능이 OpenAI 기본값으로 동작.

### 한국어 최적화

```yaml
project_name: "korean-docs"
language: "ko"
domain: "financial"

models:
  embedding:
    provider: "openai"
    model: "text-embedding-3-small"
  generation:
    simple:
      provider: "openai"
      model: "gpt-5.4-nano"
    complex:
      provider: "anthropic"
      model: "claude-sonnet-4-20250514"

korean:
  morphology: "kiwi"
  hwp_parser: "auto"
  mixed_script: true
```

### 완전 로컬 (API 키 불필요)

```yaml
project_name: "offline-project"
language: "auto"

models:
  embedding:
    provider: "local"
    model: "BAAI/bge-m3"
    dimensions: 1024
  generation:
    simple:
      provider: "ollama"
      model: "llama3.2"
    medium:
      provider: "ollama"
      model: "llama3.2"
    complex:
      provider: "ollama"
      model: "llama3.2"
  reranker:
    provider: "flashrank"
  hype:
    provider: "ollama"
    model: "llama3.2"
    questions_per_chunk: 2
```

### 비용 최적화

```yaml
project_name: "budget-project"

models:
  generation:
    simple:
      provider: "openai"
      model: "gpt-5.4-nano"
    medium:
      provider: "openai"
      model: "gpt-5.4-nano"
    complex:
      provider: "openai"
      model: "gpt-5.4-mini"

retrieval:
  top_k: 5
  rerank: false
  compression: true

cost:
  budget_monthly: 50.0
  prompt_caching: true

ingest:
  contextual_preamble: false
```

---

## 프로그래밍 방식 설정

```python
from quantumrag import Engine
from quantumrag.core.config import QuantumRAGConfig

# YAML에서 오버라이드 포함 로드
config = QuantumRAGConfig.from_yaml("quantumrag.yaml", language="en")

# 순수 코드
config = QuantumRAGConfig.default(
    language="ko",
    domain="financial",
)

# YAML로 내보내기
config.to_yaml("output.yaml")

# Engine에서 사용
engine = Engine(config=config)
```
