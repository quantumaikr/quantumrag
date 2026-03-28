# 평가 시스템

> RAG 품질을 측정하고 개선하기 위한 내장 평가 시스템.

---

## 개요

QuantumRAG는 6개 메트릭으로 검색 및 생성 품질을 측정하는 종합 평가 시스템을 내장하고 있습니다. 합성 QA 생성과 커스텀 벤치마크 파일 모두 지원합니다.

---

## 빠른 시작

```python
from quantumrag import Engine

engine = Engine()
engine.ingest("./docs")

result = engine.evaluate()
print(result.summary)
for metric in result.metrics:
    print(f"  {metric.name}: {metric.score:.2f}")
for suggestion in result.suggestions:
    print(f"  - {suggestion}")
```

---

## 메트릭

| 메트릭 | 설명 | 범위 |
|--------|------|------|
| **retrieval_recall** | 관련 청크가 검색된 비율 | 0.0 - 1.0 |
| **faithfulness** | 답변이 출처에 의해 뒷받침되는 비율 | 0.0 - 1.0 |
| **answer_relevancy** | 답변이 질문에 직접 대답하는 비율 | 0.0 - 1.0 |
| **completeness** | 질문의 모든 측면이 답변에 포함된 비율 | 0.0 - 1.0 |
| **latency** | 평균 쿼리 처리 시간 | 초 |
| **cost** | 쿼리당 평균 비용 | USD |

### 메트릭 상세

**Retrieval Recall**: 검색 파이프라인이 올바른 청크를 찾는지 측정합니다. 높은 리콜은 관련 정보가 누락되지 않음을 의미합니다.

**Faithfulness**: 환각 위험을 측정합니다. 답변의 모든 주장은 검색된 출처에 의해 뒷받침되어야 합니다. 낮은 충실도는 모델이 근거 없는 주장을 생성하고 있음을 나타냅니다.

**Answer Relevancy**: 답변이 질문에 얼마나 직접적으로 대답하는지 측정합니다. 낮은 관련성은 주제에서 벗어나거나 지나치게 넓은 답변을 나타냅니다.

**Completeness**: 복합 질문의 모든 측면이 다루어졌는지 측정합니다. 낮은 완전성은 부분적인 답변을 나타냅니다.

---

## 합성 QA 생성

벤치마크 파일이 제공되지 않으면 인덱싱된 문서에서 QA 쌍을 자동 생성합니다:

```python
result = engine.evaluate(sample_count=20)
```

합성 QA 생성기:
1. 대표적인 문서 섹션 선택
2. LLM으로 섹션별 질문 생성
3. 청크 내용에서 예상 답변 추출
4. 난이도 분류 (simple / medium / hard)

---

## 커스텀 벤치마크

JSON으로 자체 QA 벤치마크 제공:

```json
[
  {
    "question": "QuantumRAG가 지원하는 청킹 전략은 무엇인가요?",
    "expected_answer": "auto, structural, semantic, fixed",
    "reference_chunks": ["chunk_id_1", "chunk_id_2"]
  },
  {
    "question": "CTO가 누구인가요?",
    "expected_answer": "홍길동",
    "reference_chunks": ["chunk_id_3"]
  }
]
```

```python
result = engine.evaluate(benchmark_file="benchmark.json")
```

CLI:

```bash
quantumrag evaluate --benchmark benchmark.json
```

API:

```bash
curl -X POST http://localhost:8000/v1/evaluate \
  -H "Content-Type: application/json" \
  -d '{"benchmark_file": "benchmark.json", "sample_count": 50}'
```

---

## A/B 비교

두 설정을 나란히 비교:

```python
from quantumrag.core.evaluate.evaluator import Evaluator

evaluator = Evaluator(engine)
comparison = await evaluator.compare(
    config_a={"retrieval": {"top_k": 5}},
    config_b={"retrieval": {"top_k": 10}},
    sample_count=20,
)
```

---

## 시나리오 테스트 스위트

QuantumRAG는 16개 카테고리, 4단계 난이도, 87개 테스트 케이스의 종합 E2E 시나리오 테스트 스위트를 포함합니다.

### 카테고리

| # | 카테고리 | 테스트 수 | 설명 |
|---|----------|:--------:|------|
| S1 | 사실 확인 | 7 | 기본 사실 검색, 인물, 날짜 |
| S2 | 멀티홉 추론 | 6 | 교차 문서 정보 결합 |
| S3 | 수치 계산 | 6 | 수학, 백분율, 비교 |
| S4 | 시간/버전 추론 | 6 | 타임라인, 변경 이력, 버전 추적 |
| S5 | 부정/제외 | 5 | 미지원, 미완성 기능 |
| S6 | 교차 문서 종합 | 5 | 다중 출처 데이터 통합 |
| S7 | 패러프레이즈 견고성 | 6 | 구어체, 다양한 표현 방식 |
| S8 | 멀티턴 대화 | 5 | 대명사 해소, 엔티티 추적 |
| S9 | 엣지 케이스 | 7 | 경계 입력, 적대적 쿼리 |
| S10 | 정밀 검색 | 6 | 세부 정보 추출 |
| S11 | 암묵적 추론 | 5 | 직접 명시되지 않은 정보 |
| S12 | 경쟁 분석 | 3 | 시장 포지셔닝, 경쟁사 비교 |
| S13 | 조건부 추론 | 5 | IF/THEN 시나리오, 충분성 판단 |
| S14 | 다중 조건 필터링 | 5 | 복수 기준 교차 필터 |
| S15 | 파생 정량 | 5 | 다중 출처 기반 계산 |
| S16 | 교차 검증 | 4 | 문서 간 일관성 확인 |

### 난이도 분포

| 레벨 | 수량 | 설명 |
|------|:----:|------|
| Easy | 18 | 단일 홉 사실 쿼리 |
| Medium | 37 | 다단계 추론 |
| Hard | 21 | 교차 문서 종합 |
| Extreme | 6 | 복잡 조건 + 집계 |

### 시나리오 테스트 실행

```bash
uv run python tests/run_scenario_tests.py
```

시나리오별 pass/fail 결과와 지연 시간, 신뢰도 상세 정보를 출력합니다.

---

## QA 데이터세트 프레임워크

실제 웹 콘텐츠를 사용한 체계적 RAG 검증 방법론.

### 개별 QA (데이터셋별)

각 데이터셋은 특정 RAG 능력을 격리 환경에서 테스트합니다:

```bash
.venv/bin/python datasets/run_qa.py ds-001    # 특정 데이터셋
.venv/bin/python datasets/run_qa.py            # 최신 자동 선택
```

주요 기능:
- **인제스트 캐시**: 소스 미변경 시 재인덱싱 생략 (SHA256 해시)
- **쿼리별 타임아웃**: 120초 제한
- **병렬 실행**: 동시 3개 쿼리
- **자동 졸업**: pass_rate >= threshold × min_runs 충족 시 자동 status 변경

| 데이터셋 | 검증 초점 | 소스 | 질문 | 졸업 기준 |
|----------|----------|:----:|:----:|:--------:|
| ds-001 | 다국어 + 수치 정확성 | 4 | 20 | 85% |
| ds-002 | 타입시스템 + 교차 주제 혼동 | 6 | 25 | 80% |
| ds-003 | 밀집 기술문서 + 교차 문서 | 7 | 30 | 75% |
| ds-004 | 테이블 추출 + 모순 검출 | 6 | 30 | 75% |

### Combined QA (retrieval 정밀도)

전체 데이터셋을 하나의 corpus로 합산하여 노이즈 환경에서의 retrieval을 테스트합니다. 개별 테스트로는 감지할 수 없는 문제를 발견합니다.

```bash
.venv/bin/python datasets/run_qa_combined.py
```

핵심 지표:
- **Retrieval Recall**: 정답 소스의 청크가 검색 결과에 포함되었는가?
- **Noise Ratio**: 검색된 청크 중 무관한 소스의 비율
- **Degradation**: 개별 대비 합산 시 pass rate 하락폭

기준선 결과 (23 소스, ~300 청크, 105 질문):
- 개별: 평균 83% → 합산: 29% (54% 하락)
- Retrieval Recall: 9% — 대규모 corpus에서 retrieval이 핵심 병목
- 75건 실패 중 68건이 retrieval 원인 (generation 아님)

### QA 라이프사이클

```
/qa-create → /qa-run → /qa-analyze → /qa-improve → /qa-run (검증) → graduated
```

전체 현황: `datasets/STATUS.md`

---

## 설정

```yaml
evaluation:
  auto_synthetic: true       # 벤치마크 미제공 시 QA 쌍 자동 생성
  metrics:
    - "retrieval_recall"
    - "faithfulness"
    - "answer_relevancy"
    - "completeness"
    - "latency"
    - "cost"
```
