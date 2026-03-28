# QA Datasets Status
Updated: 2026-03-29 00:04

| Dataset | Name | Status | Runs | Best | Latest | Threshold | Questions |
|---------|------|--------|------|------|--------|-----------|-----------|
| ds-001 | Python 표준라이브러리 + K-반도체 산업 | graduated | 4/3 | 100% | 85% | 85% | 20 |
| ds-002 | Python 타입시스템 + 한국 전기차/스타트업 산업 | graduated | 4/3 | 88% | 88% | 80% | 25 |
| ds-003 | 트랜스포머 아키텍처 + MLOps 생태계 + 디자인패턴 | graduated | 3/3 | 87% | 83% | 75% | 30 |
| ds-004 | LLM 벤치마크 + K-반도체 슈퍼사이클 + AI 규제 | graduated | 3/3 | 90% | 77% | 75% | 30 |

## Recent Failures

**ds-001** (latest: 85%)
- q004 [easy] deque의 maxlen 속성은 무엇을 의미하나요?... → keyword mismatch
- q006 [hard] asyncio.gather()와 asyncio.TaskGroup의 차이점은 무엇인가요?... → keyword mismatch
- q014 [extreme] 두 뉴스 기사에서 삼성전자의 HBM 점유율 수치가 다르게 보도되었는데, 각각 얼마인가요?... → keyword mismatch

**ds-002** (latest: 88%)
- q006 [hard] TypeVar의 covariant와 contravariant의 차이점을 설명하세요.... → keyword mismatch
- q007 [hard] typing.Protocol과 dataclasses.dataclass의 용도 차이는?... → keyword mismatch
- q011 [hard] 2025년 벤처 투자에서 가장 높은 성장률을 보인 업종은?... → keyword mismatch

**ds-003** (latest: 83%)
- q009 [hard] Decorator 패턴과 Adapter 패턴의 차이점은?... → keyword mismatch
- q011 [hard] Semantic Chunking과 LLM-Based Chunking의 복잡도 차이는?... → keyword mismatch
- q013 [hard] Naive RAG의 한계점들을 설명해주세요.... → keyword mismatch
- q022 [extreme] Memento 패턴과 Command 패턴 모두 undo 기능에 사용될 수 있나요? 차이점은... → keyword mismatch
- q029 [extreme] RAG에서 CRAG와 Self-RAG의 공통점과 차이점은?... → keyword mismatch

**ds-004** (latest: 77%)
- q007 [hard] 가장 비용효율이 높은 LLM 모델은 무엇이며 효율 점수는?... → keyword mismatch
- q011 [hard] 한국 AI 기본법에서 고영향 AI로 분류되는 분야 수와 EU AI Act의 고위험 분야 수... → keyword mismatch
- q012 [hard] 대한민국 AI 50에서 투자유치액이 가장 높은 기업은 어디이며 얼마인가요?... → keyword mismatch
- q013 [hard] 대한민국 AI 50 중 AI 반도체(NPU) 분야 기업들을 모두 나열하세요.... → Timeout after 120s
- q014 [hard] 미국이 인텔에 지원한 반도체 보조금은 얼마이며, 한국의 삼성·SK 직접 지원과 비교하면?... → Timeout after 120s
- q015 [hard] Claude Opus 4.6의 벤치마크 종합 점수, 가격, 속도를 알려주세요.... → Timeout after 120s
- q025 [extreme] 오픈소스 LLM의 평균 벤치마크 점수와 상용 LLM의 평균 벤치마크 점수 차이는 약 몇 점... → keyword mismatch
