# QuantumRAG

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)]()
[![Scenario Tests](https://img.shields.io/badge/scenario_tests-86%2F87_passed-brightgreen.svg)]()
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

[English](README.md) | [한국어](README.ko.md)

**Index-Heavy, Query-Light RAG 엔진** — 문서를 넣고, 질문하세요. 그냥 됩니다.

QuantumRAG는 인덱싱 시점에 문서를 깊이 이해하는 오픈소스 RAG 엔진입니다 — 엔티티 추출, 팩트 인덱스 구축, 검색 가능한 동의어 생성, 청크 간 관계 사전 계산을 수행하여, 모든 쿼리가 빠르고 정밀하며 근거에 기반합니다. **Triple Index Fusion** (Original Embedding + HyPE + Contextual BM25)과 **4-Level Indexing** (Multi-Resolution 요약, Structured Fact 추출, Derived Index 보강, Entity-Centric 역인덱스)을 결합하여, 멀티홉 추론, 엔티티 필터링, 교차 문서 검증 등 기존 임베딩 기반 RAG가 처리하지 못하는 87개 실전 시나리오 테스트에서 98.9% 정확도를 달성합니다.

> **[왜 QuantumRAG인가?](docs/ko/introduction.md)** — 현재 RAG 시스템의 문제점과 QuantumRAG의 해결 방식.

---

## 핵심 특징

### 검색 (Retrieval)

- **Triple Index Fusion** — Original Embedding + [HyPE](https://arxiv.org/abs/2404.01765) (가상 프롬프트 임베딩) + Contextual BM25를 RRF(Reciprocal Rank Fusion)로 결합
- **4-Level Indexing** — Multi-Resolution 요약, Structured Fact 추출, Derived 동의어/계층 용어, Entity-Centric 역인덱스
- **적응형 쿼리 라우팅** — 단순/중간/복잡 쿼리를 자동 분류하여 모델 티어별 최적 경로 배정
- **Entity-Centric 역인덱스** — 엔티티 ID(`SEC-001`, `PAT-003`), 속성 필터(`severity:Critical`), 범위 쿼리(`severity >= High`) 에 대한 완전 재현율 보장

### 생성 (Generation)

- **출처 기반 답변 생성** — 모든 답변에 `[1]`, `[2]` 인라인 출처 인용 포함
- **Map-Reduce RAG** — 열거형/교차 문서 쿼리를 위한 병렬 추출 + 집계
- **쿼리 분해** — 복합 질문을 서브 쿼리로 분리하여 독립 검색
- **신뢰도 평가** — `STRONGLY_SUPPORTED`, `PARTIALLY_SUPPORTED`, `INSUFFICIENT_EVIDENCE` 3단계 평가

### 인프라

- **한국어 네이티브** — HWP/HWPX 파싱, Kiwi 형태소 분석, EUC-KR 인코딩, 이중 언어 프롬프트
- **다양한 문서 형식** — PDF, DOCX, PPTX, XLSX, HTML, Markdown, CSV, HWP/HWPX, 텍스트
- **멀티 LLM 프로바이더** — OpenAI, Anthropic, Google Gemini, Ollama (로컬) + 티어별 개별 설정
- **HTTP API** — FastAPI 서버, SSE 스트리밍, API 키 인증, 레이트 리미팅
- **내장 평가 시스템** — 합성 QA 생성, Recall@K, Faithfulness, Answer Relevancy, Completeness
- **플러그인 시스템** — 커스텀 파서, 청커, 리트리버, 제너레이터 확장
- **멀티 테넌트** — 테넌트별 격리 스토리지
- **데이터 커넥터** — 로컬 파일, Google Drive, Notion, AWS S3, 웹 URL

## 동작 원리

### 인덱싱 파이프라인 (인제스트 시점 — 무거운 연산)

```
문서 (PDF, DOCX, HWP, ...)
  ├─ 파싱 & 청킹 (auto/semantic/fixed/structural 전략)
  ├─ Multi-Resolution 요약 (문서 → 섹션 → 청크)
  ├─ Structured Fact 추출 (엔티티, 속성, 관계)
  ├─ Derived Index 보강 (동의어, 계층 용어 → BM25)
  ├─ Entity-Centric 역인덱스 (entity → chunk_id 매핑)
  └─ Triple Index 빌드
       ├─ Original Embedding (text-embedding-3-small)
       ├─ HyPE Embedding (가상 질문 → 임베딩)
       └─ Contextual BM25 (Kiwi 형태소 분석 토큰)
```

### 쿼리 파이프라인 (쿼리 시점 — 가벼운 연산)

```
사용자 쿼리
  ├─ 쿼리 리라이트 / 분해
  ├─ 엔티티 감지 (ID, 등급 필터, 상태 필터)
  ├─ 적응형 라우팅 (simple → nano, medium → mini, complex → full)
  ├─ Triple Index Fusion 검색 (RRF: 0.4 / 0.35 / 0.25)
  ├─ Entity Index 주입 (정확 매칭 청크 결과에 병합)
  ├─ 리랭킹 (FlashRank / BGE / Cohere / Jina)
  ├─ 컨텍스트 압축 (추출형, 쿼리 인식)
  ├─ 출처 기반 답변 생성 (인용 포함)
  └─ 신뢰도 평가 → 답변 [1][2]
```

## 빠른 시작

### 설치

```bash
pip install quantumrag

# 전체 의존성 설치 (권장)
pip install quantumrag[all]

# 한국어 지원만 추가
pip install quantumrag[korean]
```

### Python SDK

```python
from quantumrag import Engine

engine = Engine()
engine.ingest("./docs")
result = engine.query("Triple Index Fusion은 어떻게 동작하나요?")
print(result.answer)
# 출처: [1] architecture.md (§Triple Index), [2] configuration.md (§검색 설정)
```

### CLI

```bash
# 프로젝트 초기화
quantumrag init

# 문서 인제스트
quantumrag ingest ./docs --recursive

# 질문하기
quantumrag query "지원되는 청킹 전략은 무엇인가요?"

# 파일 변경 감시 모드
quantumrag ingest ./docs --watch

# API 서버 시작
quantumrag serve --port 8000
```

### 로컬 모델 (API 키 불필요)

```python
from quantumrag import Engine

engine = Engine(
    embedding_model="nomic-embed-text",
    generation_model="llama3.2",
)
engine.ingest("./docs")
result = engine.query("문서를 요약해주세요")
```

## 설정

```yaml
# quantumrag.yaml
project_name: "my-knowledge-base"
language: "ko"                          # ko, en, auto
domain: "general"                       # general, legal, medical, financial, technical

models:
  embedding:
    provider: "openai"                  # openai, gemini, ollama, local
    model: "text-embedding-3-small"
  generation:
    simple:
      provider: "openai"
      model: "gpt-5.4-nano"            # 단순 쿼리용 저비용 모델 (~70%)
    medium:
      provider: "openai"
      model: "gpt-5.4-mini"            # 중간 쿼리용 (~20%)
    complex:
      provider: "anthropic"
      model: "claude-sonnet-4-20250514" # 복잡한 쿼리용 풀 모델 (~10%)
  reranker:
    provider: "flashrank"               # flashrank (무료/CPU), bge, cohere, jina
  hype:
    provider: "openai"
    model: "gpt-5.4-nano"
    questions_per_chunk: 3

retrieval:
  top_k: 7
  fusion_weights:
    original: 0.4
    hype: 0.35
    bm25: 0.25
  rerank: true
  compression: true

storage:
  vector_db: "lancedb"
  document_store: "sqlite"
  data_dir: "./quantumrag_data"
```

환경 변수로 설정 오버라이드 (접두사: `QUANTUMRAG_`):

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export QUANTUMRAG_LANGUAGE=ko
# 중첩 설정: QUANTUMRAG_MODELS__EMBEDDING__PROVIDER=gemini
```

## 한국어 지원

QuantumRAG는 한국어를 1등 시민(first-class citizen)으로 지원합니다:

| 기능 | 설명 |
|------|------|
| **HWP/HWPX 파싱** | 한글 문서 직접 파싱 (정부/관공서 문서 지원) |
| **Kiwi 형태소 분석** | BM25 인덱싱에 한국어 형태소 분석 적용 |
| **EUC-KR 자동 감지** | 레거시 인코딩 자동 감지 및 변환 |
| **혼합 스크립트** | 한영 혼합 텍스트에서 각각 최적 토크나이저 적용 |
| **이중 언어 프롬프트** | 쿼리 언어에 따라 한국어/영어 시스템 프롬프트 자동 전환 |
| **한국어 쿼리 패턴** | 교착어 형태론 인식 쿼리 라우팅 및 분해 |

```bash
pip install kiwipiepy  # 한국어 형태소 분석 필수
```

## HTTP API

```bash
quantumrag serve --port 8000
```

| 메서드 | 엔드포인트 | 설명 |
|--------|----------|------|
| `POST` | `/v1/ingest` | 경로에서 문서 인제스트 |
| `POST` | `/v1/ingest/upload` | 파일 업로드 인제스트 |
| `POST` | `/v1/ingest/text` | 원시 텍스트 인제스트 |
| `POST` | `/v1/query` | 질의 (동기) |
| `POST` | `/v1/query/stream` | 질의 (SSE 스트리밍) |
| `GET` | `/v1/documents` | 문서 목록 조회 |
| `DELETE` | `/v1/documents/{id}` | 문서 삭제 |
| `GET` | `/v1/status` | 시스템 상태 |
| `POST` | `/v1/evaluate` | 평가 실행 |
| `POST` | `/v1/feedback` | 피드백 제출 |
| `GET` | `/health` | 헬스체크 |

인터랙티브 API 문서: `http://localhost:8000/docs`

## 평가 시스템

6개 메트릭을 포함하는 내장 평가 시스템:

```python
engine = Engine()
result = engine.evaluate()
print(result.summary)
# retrieval_recall: 0.92
# faithfulness: 0.95
# answer_relevancy: 0.88
# completeness: 0.85
# latency: 1.2s avg
# cost: $0.003/query avg
```

### 시나리오 테스트

16개 카테고리, 4단계 난이도, 87개 E2E 시나리오 테스트:

| 카테고리 | 테스트 수 | 설명 |
|----------|:--------:|------|
| 사실 확인 | 7 | 기본 사실 검색, 인물, 날짜 |
| 멀티홉 추론 | 6 | 교차 문서 정보 결합 |
| 수치 계산 | 6 | 수학, 백분율, 비교 |
| 시간/버전 추론 | 6 | 타임라인, 변경 이력, 버전 추적 |
| 부정/제외 | 5 | 미지원, 미완성 기능 |
| 교차 문서 종합 | 5 | 다중 출처 데이터 통합 |
| 패러프레이즈 견고성 | 6 | 구어체, 다양한 표현 방식 |
| 멀티턴 대화 | 5 | 대명사 해소, 엔티티 추적 |
| 엣지 케이스 | 7 | 경계 입력, 적대적 쿼리 |
| 정밀 검색 | 6 | 세부 정보 추출 |
| 암묵적 추론 | 5 | 직접 명시되지 않은 정보 |
| 경쟁 분석 | 3 | 시장 포지셔닝, 경쟁사 비교 |
| 조건부 추론 | 5 | IF/THEN 시나리오, 충분성 판단 |
| 다중 조건 필터링 | 5 | 복수 기준 교차 필터 |
| 파생 정량 | 5 | 다중 출처 기반 계산 |
| 교차 검증 | 4 | 문서 간 일관성 확인 |

```bash
uv run python tests/run_scenario_tests.py
```

## 프로젝트 구조

```
quantumrag/
├── core/
│   ├── engine.py              # 단일 진입점
│   ├── config.py              # 설정 (Pydantic + YAML)
│   ├── models.py              # 데이터 모델 (Chunk, QueryResult, ...)
│   ├── ingest/
│   │   ├── parser/            # 다중 문서 형식 파싱
│   │   ├── chunker/           # 6가지 청킹 전략
│   │   └── indexer/           # Triple Index + 4-Level Indexing
│   │       ├── triple_index_builder.py
│   │       ├── multi_resolution.py
│   │       ├── fact_extractor.py
│   │       ├── derived_index.py
│   │       └── entity_index.py
│   ├── retrieve/
│   │   ├── fusion.py          # RRF 트리플 인덱스 퓨전
│   │   ├── reranker.py        # 멀티 프로바이더 리랭킹
│   │   ├── compressor.py      # 컨텍스트 압축
│   │   ├── entity_detector.py # 엔티티 쿼리 감지
│   │   └── constellation.py   # 청크 관계 그래프
│   ├── generate/
│   │   ├── generator.py       # 출처 기반 답변 생성
│   │   ├── router.py          # 쿼리 복잡도 라우팅
│   │   ├── rewriter.py        # 쿼리 리라이팅
│   │   ├── map_reduce.py      # Map-Reduce 집계
│   │   └── decomposer.py      # 쿼리 분해
│   ├── storage/               # SQLite + LanceDB + Tantivy
│   ├── llm/                   # 프로바이더 추상화 레이어
│   │   └── providers/         # OpenAI, Anthropic, Gemini, Ollama
│   ├── evaluate/              # 평가 메트릭 & 합성 QA
│   ├── cache/                 # 시맨틱 캐시
│   ├── security/              # 입력 검증, API 인증
│   ├── observability/         # 구조화 로깅, 트레이싱
│   └── multitenancy/          # 테넌트 격리
├── api/                       # FastAPI HTTP 서버
├── cli/                       # Typer CLI
├── connectors/                # File, GDrive, Notion, S3, URL
├── korean/                    # Kiwi 형태소 분석, 인코딩
└── plugins/                   # 플러그인 레지스트리 & 훅
```

## 경쟁 비교

| 기능 | QuantumRAG | LangChain | LlamaIndex | OpenAI file_search |
|------|:----------:|:---------:|:----------:|:------------------:|
| Triple Index (Embedding + HyPE + BM25) | O | X | X | X |
| 4-Level Indexing | O | X | X | X |
| Entity-Centric 역인덱스 | O | X | X | X |
| Index-Heavy 아키텍처 | O | X | 부분 | X |
| 한국어 (HWP, Kiwi) | 네이티브 | 플러그인 | 플러그인 | X |
| 적응형 쿼리 라우팅 | O | 수동 | X | X |
| Map-Reduce RAG | O | O | O | X |
| 로컬 LLM (Ollama) | O | O | O | X |
| 내장 평가 | O | LangSmith | O | X |
| GPU 불필요 | O | 상황별 | 상황별 | N/A |

## 개발

```bash
git clone https://github.com/quantumrag/quantumrag.git
cd quantumrag
pip install -e ".[dev,all]"

# 유닛 테스트 실행
pytest tests/ -q

# 시나리오 테스트 실행
uv run python tests/run_scenario_tests.py

# 린트
ruff check quantumrag/ tests/
```

## 시스템 요구사항

- **Python**: 3.10, 3.11, 3.12
- **RAM**: 최소 2GB, 4GB 이상 권장
- **GPU**: 불필요 (CPU만으로 동작)
- **저장소**: SQLite + LanceDB + Tantivy (모두 로컬, 외부 서비스 불필요)
- **OS**: Linux, macOS, Windows (WSL2)

## 라이선스

Apache License 2.0 - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.
