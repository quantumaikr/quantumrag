# 트러블슈팅

QuantumRAG 사용 시 자주 발생하는 문제와 해결 방법입니다.

## 설치

### `uv sync` 의존성 충돌

```bash
# 클린 설치
rm -rf .venv uv.lock
uv sync --dev
```

### Apple Silicon에서 `kiwipiepy` 설치 실패

```bash
softwareupdate --install-rosetta
uv sync --dev
```

## API 키

### "insufficient_quota" 또는 429 에러

OpenAI/Anthropic API 쿼터 초과:

- 빌링 확인: https://platform.openai.com/account/billing
- 저렴한 모델로 전환:
  ```yaml
  models:
    generation:
      simple: { provider: openai, model: gpt-4.1-mini }
  ```
- 로컬 모델 사용 (무료):
  ```bash
  ollama pull gemma3
  quantumrag init --local
  ```

### Ingest 시 "Invalid API key"

Ingest는 임베딩 모델을 사용합니다:
```bash
echo $OPENAI_API_KEY        # OpenAI 임베딩
echo $GEMINI_API_KEY        # Gemini 임베딩 사용 시
```

## 인제스트

### "No documents ingested"

1. 지원 포맷 확인: PDF, DOCX, PPTX, XLSX, HWP, HWPX, MD, CSV, TXT, HTML
2. 파일이 비어있거나 손상되지 않았는지 확인
3. 상세 로그: `quantumrag ingest ./docs --verbose`

### HWP 파일 미파싱

```bash
uv pip install pyhwpx
```

### 인제스트가 느림

- 대용량 PDF: `mode: fast`로 HyPE 건너뛰기:
  ```python
  engine.ingest("./docs", mode="fast")     # HyPE + 프리앰블 생략
  engine.ingest("./docs", mode="minimal")  # 최소: 파싱 + 청킹 + 임베딩만
  ```
- API rate limit: `ingest.max_concurrency` 줄이기

## 쿼리

### 모든 답변이 "INSUFFICIENT_EVIDENCE"

1. 인제스트 확인: `quantumrag status`
2. `retrieval.top_k` 증가 (기본: 10)
3. 쿼리 언어와 문서 언어 일치 확인
4. 압축 비활성화: `retrieval.compression: false`

### 환각 (없는 사실을 지어냄)

fact_verifier가 감지해야 합니다. 그래도 발생하면:
1. `ingest.mode: full` 사용 확인 (fact 추출은 full 모드 필요)
2. `generation.temperature: 0.0` 확인 (반드시 0)
3. trace 확인: `result.trace`에서 각 파이프라인 단계 확인

### 쿼리가 느림 (>30초)

주요 원인:
- **Map-Reduce 발동**: 집계 쿼리("모두 알려줘", "총 합계")는 전체 청크 스캔. 정상 동작이지만 느림
- **Post-correction**: 복잡한 쿼리 시 retry → self-correct → fact verify → completeness. trace로 어느 단계가 느린지 확인
- **Reranker**: FlashRank는 CPU 기반. 느린 머신에서는 `retrieval.rerank: false`

### QA 러너에서 120초 타임아웃

QA 러너는 쿼리당 120초 제한. 이 경우:
- 다수 소스 비교 쿼리
- 20+ 청크 map_reduce 집계 쿼리
- 타임아웃 증가가 아닌 파이프라인 최적화 필요

## 테스트

### `make check` 실패

```bash
make fix       # 린트 자동 수정
make check     # 재시도
```

### 시나리오 테스트 실패

시나리오 테스트는 실제 LLM API 호출이 필요합니다:
```bash
export OPENAI_API_KEY=sk-...
export GEMINI_API_KEY=AI...
make scenario-test
```

### QA 데이터셋 러너

```bash
# 데이터셋 확인
ls datasets/ds-001/qa.yaml

# 실행
.venv/bin/python datasets/run_qa.py ds-001

# 전체 소스 합산 검증
.venv/bin/python datasets/run_qa_combined.py
```

## 서버

### 포트 충돌

```bash
quantumrag serve --port 8001
# 또는 기존 프로세스 종료:
lsof -ti:8000 | xargs kill
```

### 프론트엔드 CORS 에러

```yaml
api:
  cors_origins: ["http://localhost:3000"]
```

## 성능 튜닝

### 속도 우선 (낮은 지연시간)

```yaml
ingest:
  mode: fast
retrieval:
  top_k: 5
  rerank: false
  compression: false
generation:
  max_tokens: 512
```

### 정확도 우선 (높은 품질)

```yaml
ingest:
  mode: full
  chunking:
    strategy: semantic
retrieval:
  top_k: 15
  rerank: true
  retrieval_retry: true
generation:
  max_tokens: 2048
  max_context_chars: 16000
```

### 비용 우선 (API 호출 최소화)

```yaml
models:
  generation:
    simple: { provider: openai, model: gpt-4.1-mini }
    medium: { provider: openai, model: gpt-4.1-mini }
    complex: { provider: openai, model: gpt-4.1 }
  embedding:
    provider: gemini
cost:
  semantic_cache: true
  prompt_caching: true
```

## 디버그 모드

```python
from quantumrag.core.engine import Engine
engine = Engine(verbose=True)

result = engine.query("질문")
for step in result.trace:
    print(f"{step.step}: {step.result[:100]}")
```

CLI:
```bash
quantumrag query "질문" --verbose
```
