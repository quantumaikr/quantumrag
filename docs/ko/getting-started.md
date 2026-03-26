# 시작하기

> 설치부터 첫 번째 질문까지 5분 이내.

---

## 설치

### 기본 설치

```bash
pip install quantumrag
```

### 권장 (전체 기능)

```bash
pip install quantumrag[all]
```

OpenAI, Anthropic, LanceDB, Tantivy, Kiwi, FastAPI 등 모든 선택적 의존성 포함.

### 선택적 설치

```bash
# 한국어 지원
pip install quantumrag[korean]

# API 서버만
pip install quantumrag[api]

# Gemini 프로바이더
pip install quantumrag[gemini]

# 리랭킹 모델
pip install quantumrag[rerank]
```

### 개발 환경

```bash
git clone https://github.com/quantumrag/quantumrag.git
cd quantumrag
pip install -e ".[dev,all]"
```

---

## 시스템 요구사항

| 요구사항 | 최소 | 권장 |
|---------|------|------|
| Python | 3.10 | 3.11 또는 3.12 |
| RAM | 2 GB | 4 GB+ |
| GPU | 불필요 | 불필요 |
| 저장소 | SQLite + LanceDB + Tantivy (로컬) | 동일 |
| OS | Linux, macOS, Windows (WSL2) | 모두 |

---

## API 키 설정

QuantumRAG는 LLM 프로바이더 API 키가 필요합니다. 환경 변수로 설정:

```bash
# OpenAI (기본 프로바이더)
export OPENAI_API_KEY=sk-...

# 또는 Anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# 또는 Google Gemini
export GOOGLE_API_KEY=AIza...
```

Ollama를 통한 로컬 모델 사용 시 API 키 불필요.

---

## 빠른 시작

### 1. 프로젝트 초기화

```bash
quantumrag init
```

기본값으로 `quantumrag.yaml` 설정 파일 생성.

### 2. 문서 인제스트

**CLI:**

```bash
quantumrag ingest ./docs --recursive
```

**Python:**

```python
from quantumrag import Engine

engine = Engine()
result = engine.ingest("./docs")
print(f"{result.documents}개 문서, {result.chunks}개 청크 인덱싱 완료")
```

### 3. 질문하기

**CLI:**

```bash
quantumrag query "분기별 매출이 얼마인가요?"
```

**Python:**

```python
result = engine.query("분기별 매출이 얼마인가요?")
print(result.answer)       # [1], [2] 인라인 인용이 포함된 답변
print(result.confidence)   # STRONGLY_SUPPORTED / PARTIALLY_SUPPORTED / INSUFFICIENT_EVIDENCE
print(result.sources)      # 출처 참조 목록
```

### 4. API 서버 시작 (선택)

```bash
quantumrag serve --port 8000
```

HTTP로 질의:

```bash
curl -X POST http://localhost:8000/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "분기별 매출이 얼마인가요?"}'
```

---

## 로컬 모델 사용 (API 키 불필요)

[Ollama](https://ollama.com/)를 설치하고 모델 다운로드:

```bash
ollama pull nomic-embed-text
ollama pull llama3.2
```

QuantumRAG 설정:

```python
from quantumrag import Engine

engine = Engine(
    embedding_model="nomic-embed-text",
    generation_model="llama3.2",
)
engine.ingest("./docs")
result = engine.query("문서를 요약해주세요")
```

또는 YAML 설정:

```yaml
# quantumrag.yaml
models:
  embedding:
    provider: "ollama"
    model: "nomic-embed-text"
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
```

---

## 한국어 최적화 로컬 임베딩

API 키 없이 한국어 문서 처리:

```yaml
models:
  embedding:
    provider: "local"
    model: "BAAI/bge-m3"
    dimensions: 1024
```

BGE-M3 모델을 로컬에서 다운로드하여 실행 (CPU 기반, 다국어 지원).

---

## 설정

QuantumRAG는 계층형 설정 시스템을 사용합니다:

```
기본값 ← quantumrag.yaml ← 환경 변수 ← 코드 인자
```

### 설정 파일

```bash
quantumrag init  # 기본값으로 quantumrag.yaml 생성
```

### 환경 변수

`QUANTUMRAG_` 접두사로 모든 설정 키 오버라이드 가능:

```bash
export QUANTUMRAG_LANGUAGE=ko
export QUANTUMRAG_RETRIEVAL__TOP_K=10
export QUANTUMRAG_MODELS__EMBEDDING__PROVIDER=gemini
```

### 코드 인자

```python
from quantumrag import Engine
from quantumrag.core.config import QuantumRAGConfig

# YAML에서 로드
engine = Engine(config="./quantumrag.yaml")

# 오버라이드 포함
config = QuantumRAGConfig.from_yaml("./quantumrag.yaml", language="en")
engine = Engine(config=config)

# 빠른 오버라이드
engine = Engine(embedding_model="text-embedding-3-large", data_dir="./my_data")
```

---

## 설치 확인

```python
from quantumrag import Engine

engine = Engine()
status = engine.status()
print(status)
# {'documents': 0, 'chunks': 0, 'config': {...}, 'data_dir': './quantumrag_data'}
```

---

## 다음 단계

- [설정 가이드](configuration.md) — 전체 설정 레퍼런스
- [아키텍처](architecture.md) — 엔진 내부 동작 원리
- [API 레퍼런스](api-reference.md) — HTTP API 엔드포인트
- [한국어 가이드](korean-support.md) — 한국어 최적화
