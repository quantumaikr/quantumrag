# QuantumRAG

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)]()
[![Scenario Tests](https://img.shields.io/badge/scenario_tests-86%2F87_passed-brightgreen.svg)]()
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

[English](README.md) | [한국어](README.ko.md)

**문서를 깊이 이해하는 오픈소스 RAG 엔진. 정확하고, 출처가 있고, 빠릅니다.**

```python
from quantumrag import Engine

engine = Engine()
engine.ingest("./docs")
result = engine.query("보안 감사에서 발견된 주요 이슈는?")
print(result.answer)
# 감사에서 3건의 주요 발견사항이 확인되었습니다: ... [1][2]
# 신뢰도: STRONGLY_SUPPORTED
```

문서를 넣으세요. 질문하세요. 나머지는 알아서 합니다.

---

## 왜 QuantumRAG인가

대부분의 RAG 시스템은 문서를 벡터로 변환한 뒤, 적절한 청크가 돌아오기를 기대합니다. 질문 표현이 조금 달라지거나, 답이 여러 문서에 걸쳐 있거나, 정확한 엔티티 매칭이 필요할 때 — 조용히 실패합니다.

QuantumRAG는 다른 접근을 합니다: **인덱싱 시점에 문서를 깊이 이해해서, 쿼리가 기본적으로 빠르고 정확하게 작동합니다.**

모든 문서를 여러 관점에서 이해합니다 — 의미적 유사성, 이 문서로 답할 수 있는 가상 질문, 키워드와 동의어, 구조화된 사실, 엔티티 관계 — 그리고 이 관점들을 쿼리 시점에 융합하여 어떻게 질문하든 정확한 답을 찾습니다.

> **결과:** 멀티홉 추론, 교차 문서 검증, 엔티티 필터링 등 기존 RAG가 처리하지 못하는 [87개 실전 시나리오 테스트](docs/reports/scenario-test-report.md)에서 98.9% 정확도 달성.

## 세 가지 사용 방식

| | 하는 일 | 일어나는 일 |
|---|---------|-----------|
| **그냥 쓰면** | `engine.ingest("./docs")` → `engine.query("...")` | 파서, 청커, 인덱스, 라우팅 — 모두 자동 선택 |
| **좀 더 쓰면** | 퓨전 가중치 조정, 모델 선택, 도메인 설정 | 특정 유스케이스에 더 좋은 결과 |
| **깊이 쓰면** | 커스텀 파서, 청커, 리트리버, 제너레이터 | 모든 레이어를 플러그인으로 교체 가능 |

첫 번째 답까지 설정 제로. 필요하면 모든 것을 제어할 수 있습니다.

## 빠른 시작

### 설치

```bash
pip install quantumrag

# 전체 의존성 설치 (권장)
pip install quantumrag[all]

# 한국어 지원만 추가
pip install quantumrag[korean]
```

### CLI

```bash
# 프로젝트 초기화
quantumrag init

# 문서 인제스트
quantumrag ingest ./docs --recursive

# 질문하기
quantumrag query "지원되는 청킹 전략은 무엇인가요?"

# 웹 플레이그라운드와 함께 API 서버 시작
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

## 한국어 지원

QuantumRAG는 한국어를 번역이 아닌 모국어로 대합니다.

| 기능 | 설명 |
|------|------|
| **HWP/HWPX 파싱** | 한글 문서 직접 파싱 (정부/관공서 문서 지원) |
| **Kiwi 형태소 분석** | BM25 인덱싱에 정확한 한국어 형태소 분석 적용 |
| **EUC-KR 자동 감지** | 레거시 인코딩 자동 감지 및 UTF-8 변환 |
| **혼합 스크립트** | 한영 혼합 텍스트에서 각각 최적 토크나이저 적용 |
| **이중 언어 프롬프트** | 쿼리 언어에 따라 시스템 프롬프트 자동 전환 |
| **한국어 쿼리 패턴** | 교착어 형태론 인식 쿼리 라우팅 및 분해 |

```bash
pip install kiwipiepy  # 한국어 형태소 분석 필수
```

## 동작 원리

### Index-Heavy, Query-Light

핵심 설계: 비용이 큰 연산은 인제스트 시점에 한 번 수행하여, 쿼리를 빠르고 정밀하게 만듭니다.

**인덱싱 파이프라인 (인제스트 시점 — 무거운 연산)**

```
문서 (PDF, DOCX, HWP, PPTX, XLSX, HTML, MD, CSV, TXT)
  ├─ 파서 & 청킹 전략 자동 선택
  ├─ Multi-Resolution 요약 (문서 → 섹션 → 청크)
  ├─ Structured Fact 추출 (엔티티, 속성, 관계)
  ├─ Derived Index 보강 (동의어, 계층 용어)
  ├─ Entity-Centric 역인덱스 (entity → chunk_id 매핑)
  └─ Triple Index 빌드
       ├─ Original Embedding (의미적 유사성)
       ├─ HyPE Embedding (가상 질문 → 임베딩)
       └─ Contextual BM25 (형태소 기반 키워드 인덱스)
```

**쿼리 파이프라인 (쿼리 시점 — 가벼운 연산)**

```
사용자 쿼리
  ├─ 쿼리 리라이트 / 분해
  ├─ 엔티티 감지 & 속성 필터링
  ├─ 적응형 라우팅 (simple → nano, medium → mini, complex → full)
  ├─ Triple Index Fusion 검색 (RRF: 0.4 / 0.35 / 0.25)
  ├─ 리랭킹 (FlashRank / BGE / Cohere / Jina)
  ├─ 컨텍스트 압축
  └─ 출처 기반 답변 생성 → 답변 [1][2] + 신뢰도
```

### Triple Index Fusion

세 가지 검색 방식을 RRF로 결합 — 각각이 다른 것이 놓친 것을 찾습니다:

| 인덱스 | 찾는 것 | 중요한 이유 |
|--------|---------|------------|
| **Original Embedding** | 의미적으로 유사한 콘텐츠 | 패러프레이즈, 개념적 질문 처리 |
| **HyPE Embedding** | 유사한 질문에 답할 수 있는 콘텐츠 | 질문↔문서 간 격차 해소 |
| **Contextual BM25** | 정확한 키워드 및 엔티티 매칭 | 찾으려는 것이 명확할 때 정밀 검색 |

### 4-Level Indexing

모두 룰 기반, 인제스트 시 LLM 비용 제로:

1. **Multi-Resolution 요약** — 문서, 섹션, 청크 수준으로 폭넓은 검색
2. **Structured Fact 추출** — 도메인별 패턴 매칭 (ID, 등급, 버전, 계약)
3. **Derived Index 보강** — 동의어와 계층 용어로 BM25 재현율 향상
4. **Entity-Centric 역인덱스** — 엔티티 쿼리와 속성 필터에 대한 완전 재현율

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

웹 플레이그라운드: `http://localhost:8000/playground`
인터랙티브 API 문서: `http://localhost:8000/docs`

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
```

## 평가 시스템

6개 메트릭과 16개 카테고리 87개 시나리오 테스트를 포함하는 내장 평가 시스템:

```python
engine = Engine()
result = engine.evaluate()
print(result.summary)
# retrieval_recall: 0.92, faithfulness: 0.95
# answer_relevancy: 0.88, completeness: 0.85
# latency: 1.2s avg, cost: $0.003/query avg
```

| 카테고리 | 테스트 수 | 카테고리 | 테스트 수 |
|----------|:--------:|----------|:--------:|
| 사실 확인 | 7 | 정밀 검색 | 6 |
| 멀티홉 추론 | 6 | 암묵적 추론 | 5 |
| 수치 계산 | 6 | 경쟁 분석 | 3 |
| 시간/버전 추론 | 6 | 조건부 추론 | 5 |
| 부정/제외 | 5 | 다중 조건 필터링 | 5 |
| 교차 문서 종합 | 5 | 파생 정량 | 5 |
| 패러프레이즈 견고성 | 6 | 교차 검증 | 4 |
| 멀티턴 대화 | 5 | 엣지 케이스 | 7 |

```bash
uv run python tests/run_scenario_tests.py
```

## 경쟁 비교

LangChain과 LlamaIndex는 부품을 줍니다. OpenAI는 블랙박스를 줍니다. QuantumRAG는 **엔진**을 줍니다 — 바로 작동하는 기본값, 필요할 때 제어할 수 있는 모든 레이어.

| 기능 | QuantumRAG | LangChain | LlamaIndex | OpenAI file_search |
|------|:----------:|:---------:|:----------:|:------------------:|
| Triple Index (Embedding + HyPE + BM25) | O | X | X | X |
| 4-Level Indexing | O | X | X | X |
| Entity-Centric 역인덱스 | O | X | X | X |
| 한국어 (HWP, Kiwi) | 네이티브 | 플러그인 | 플러그인 | X |
| 적응형 쿼리 라우팅 | O | 수동 | X | X |
| 로컬 LLM (Ollama) | O | O | O | X |
| 내장 평가 | O | LangSmith | O | X |
| GPU 불필요 | O | 상황별 | 상황별 | N/A |
| 설정 없이 첫 답변 | O | X | X | 부분적 |

## 프로젝트 구조

```
quantumrag/
├── core/
│   ├── engine.py              # 단일 진입점
│   ├── config.py              # 설정 (Pydantic + YAML)
│   ├── models.py              # 데이터 모델 (Chunk, QueryResult, ...)
│   ├── ingest/
│   │   ├── parser/            # 다중 문서 형식 파싱
│   │   ├── chunker/           # 청킹 전략 (auto/semantic/fixed/structural)
│   │   └── indexer/           # Triple Index + 4-Level Indexing
│   ├── retrieve/
│   │   ├── fusion.py          # RRF 트리플 인덱스 퓨전
│   │   ├── reranker.py        # 멀티 프로바이더 리랭킹
│   │   └── entity_detector.py # 엔티티 쿼리 감지
│   ├── generate/
│   │   ├── generator.py       # 출처 기반 답변 생성
│   │   ├── router.py          # 쿼리 복잡도 라우팅
│   │   └── decomposer.py      # 쿼리 분해
│   ├── storage/               # SQLite + LanceDB + Tantivy
│   ├── llm/                   # 프로바이더 추상화 (OpenAI, Anthropic, Gemini, Ollama)
│   ├── evaluate/              # 평가 메트릭 & 합성 QA
│   └── pipeline/              # 프로파일링, 시그널, 오케스트레이션
├── api/                       # FastAPI HTTP 서버 + 웹 플레이그라운드
├── cli/                       # Typer CLI
├── connectors/                # File, GDrive, Notion, S3, URL
├── korean/                    # Kiwi 형태소 분석, 인코딩
└── plugins/                   # 플러그인 레지스트리 & 훅
```

## 개발

```bash
git clone https://github.com/quantumaikr/quantumrag.git
cd quantumrag
pip install -e ".[dev,all]"

# 테스트 실행
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
