# QA Datasets Status

Updated: 2026-03-29

## Individual Dataset Results

| Dataset | Name | Status | Runs | Best | Latest | Threshold | Questions |
|---------|------|--------|------|------|--------|-----------|-----------|
| ds-001 | Python 표준라이브러리 + K-반도체 산업 | graduated | 4/3 | 100% | 85% | 85% | 20 |
| ds-002 | Python 타입시스템 + 한국 전기차/스타트업 산업 | graduated | 4/3 | 88% | 88% | 80% | 25 |
| ds-003 | 트랜스포머 아키텍처 + MLOps 생태계 + 디자인패턴 | graduated | 3/3 | 87% | 83% | 75% | 30 |
| ds-004 | LLM 벤치마크 + K-반도체 슈퍼사이클 + AI 규제 | graduated | 3/3 | 90% | 77% | 75% | 30 |

## Combined QA Results (Retrieval Precision Test)

All 4 datasets merged into single corpus: 23 sources, ~300 chunks, 105 questions.
Individual QA tests retrieval in isolation (top_k covers 15% of corpus).
Combined QA tests retrieval under noise (top_k covers 3% — closer to production).

| Dataset | Individual | Combined | Degradation | Retrieval Recall |
|---------|-----------|----------|-------------|-----------------|
| ds-001 | 85% | 70% | -15% | 10% |
| ds-002 | 88% | 40% | -48% | 12% |
| ds-003 | 83% | 13% | -70% | 7% |
| ds-004 | 77% | 7% | -70% | 7% |
| **Total** | **83%** | **29%** | **-54%** | **9%** |

**Key Finding**: 68 of 75 failures are retrieval-caused (recall < 50%).
Generation quality is not the bottleneck — retrieval precision is.

### Failure Diagnosis

| Category | Count | Implication |
|----------|-------|-------------|
| Retrieval failures (recall < 50%) | 68 | Embedding/BM25 fusion cannot distinguish relevant docs in noisy corpus |
| Generation failures (recall >= 50%) | 0 | Generation works fine when retrieval succeeds |
| Timeout (> 60s) | 7 | Map-reduce + post-correction on complex queries |

### Next Actions

1. Improve retrieval precision: domain-aware embedding, query-source matching
2. Tune fusion weights for larger corpora
3. Consider document-level pre-filtering before chunk-level retrieval

## Recent Individual Failures

**ds-001** (latest: 85%)
- q004 [easy] deque의 maxlen 속성은 무엇을 의미하나요? → keyword mismatch
- q006 [hard] asyncio.gather()와 asyncio.TaskGroup의 차이점은? → keyword mismatch
- q014 [extreme] HBM 점유율 수치 교차 비교 → keyword mismatch

**ds-002** (latest: 88%)
- q006 [hard] TypeVar covariant/contravariant → keyword mismatch
- q007 [hard] Protocol vs dataclass → keyword mismatch
- q011 [hard] 벤처 투자 성장률 → keyword mismatch

**ds-003** (latest: 83%)
- q009 [hard] Decorator vs Adapter 패턴 → keyword mismatch
- q011 [hard] Semantic vs LLM-Based Chunking → keyword mismatch
- q013 [hard] Naive RAG 한계점 → keyword mismatch
- q022 [extreme] Memento vs Command 패턴 → keyword mismatch
- q029 [extreme] CRAG vs Self-RAG → keyword mismatch

**ds-004** (latest: 77%)
- q007 [hard] 비용효율 1위 LLM → keyword mismatch
- q012 [hard] AI 50 투자유치 1위 → keyword mismatch
- q013-015 [hard] 테이블 파싱 → timeout (120s)
- q025 [extreme] 오픈소스 vs 상용 LLM 점수 차이 → keyword mismatch
