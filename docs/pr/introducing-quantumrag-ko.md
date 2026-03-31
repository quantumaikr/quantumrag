# QuantumRAG — 문서를 넣으면 정확한 답이 나오는 오픈소스 RAG 엔진

> 2026년 3월 31일 | v0.4.4 | Apache 2.0

## 한 줄 요약

문서를 넣으세요. 질문하세요. 출처가 달린 정확한 답변을 받으세요. **설정 없이 바로 동작합니다.**

```python
from quantumrag import Engine

engine = Engine()
engine.ingest("./docs")
result = engine.query("주요 발견사항은?")
print(result.answer)   # ... [1][2] + Confidence: STRONGLY_SUPPORTED
```

## 왜 만들었나

RAG를 직접 구축해 보면, 생각보다 많은 것이 안 됩니다.

- 질문 표현을 살짝 바꾸면 답을 못 찾음
- 여러 문서에 걸친 답변을 종합하지 못함
- 정확한 수치나 엔티티를 요구하면 조용히 실패
- 한국어 문서(HWP 등)는 제대로 파싱조차 안 됨

대부분의 RAG는 문서를 벡터로 변환한 뒤, 적절한 청크가 돌아오기를 기도합니다. QuantumRAG는 다른 접근을 합니다.

**인덱싱 시점에 문서를 깊이 이해해서, 쿼리가 기본적으로 정확하게 작동합니다.**

## 핵심 기술

### Triple Index Fusion

하나의 검색 방식으로는 한계가 있습니다. 세 가지를 동시에 돌리고 Score-Weighted RRF로 융합합니다:

| 인덱스 | 역할 | 왜 필요한가 |
|--------|------|------------|
| **Original Embedding** | 의미적 유사성 | 패러프레이즈 처리 |
| **HyPE Embedding** | "이 문서로 답할 수 있는 질문" 매칭 | 질문↔문서 격차 해소 |
| **Contextual BM25** | 정확한 키워드/엔티티 매칭 | 수치, 이름 등 정밀 검색 |

### 환각 방지 이중 방벽

1. **Fact Verifier** (Hard Gate): 인제스트 시 추출한 facts와 답변을 교차 검증. LLM 비용 제로.
2. **시스템 프롬프트** (Soft Gate): 11개 한국어 생성 규칙으로 출처 없는 주장을 원천 차단.

### 적응형 후처리 파이프라인

답변 생성 후 자동 교정:
- Retrieval Retry → Self-Correction → Fact Verification → Completeness Check
- 시간 예산(20초) 내에서 동작, 단순 쿼리는 자동 스킵

## 한국어를 모국어로

| 기능 | 설명 |
|------|------|
| HWP/HWPX 파싱 | 정부/관공서 문서 직접 파싱 |
| Kiwi 형태소 분석 | BM25 인덱싱 정확도 향상 |
| EUC-KR 자동 감지 | 레거시 인코딩 자동 변환 |
| 혼합 스크립트 | 한영 혼합 텍스트 최적 토크나이징 |
| 언어 자동 감지 | 영어 질문 → 영어 답변, 한국어 질문 → 한국어 답변 |

## 측정된 성능

105개 QA 질문, 73개 소스 문서(50개 노이즈 포함)에서:

- **Combined QA: 75% pass rate** (29%에서 6회 반복 개선)
- **Timeout: 0%**
- 176개 시나리오 테스트, 831개 유닛 테스트, mypy 0 에러

## 비용: 제로에서 시작

- **임베딩**: Microsoft Harrier 270M (로컬, 무료, MTEB 66.5)
- **LLM**: Gemini 무료 티어 (gemini-3.1-flash-lite-preview)
- **Reranker**: FlashRank (CPU, 무료)
- **GPU 불필요**: CPU만으로 동작

## 30초 체험

```bash
pip install quantumrag
quantumrag demo
# 브라우저에서 http://localhost:8000 접속
```

또는 Docker:

```bash
docker run -e GOOGLE_API_KEY=AIza... -p 8000:8000 quantumrag
```

## 지원 포맷

PDF, DOCX, PPTX, XLSX, HWP/HWPX, HTML, Markdown, CSV, TXT

## 프로젝트 구조

```
quantumrag/
├── core/engine.py          # 단일 진입점
├── core/retrieve/fusion.py # Triple Index 퓨전 검색
├── core/generate/          # 생성 + 환각 방지 + 완전성 검사
├── core/pipeline/          # 적응형 후처리 교정
├── api/                    # FastAPI + 웹 플레이그라운드
├── cli/                    # init, ingest, query, serve, demo
└── korean/                 # Kiwi 형태소, EUC-KR 인코딩
```

## 링크

- **GitHub**: https://github.com/quantumaikr/quantumrag
- **PyPI**: `pip install quantumrag`
- **문서**: [한국어](../../docs/ko/index.md) | [English](../../docs/en/index.md)
- **라이선스**: Apache 2.0

---

*QuantumAI Inc. — hi@quantumai.kr*
