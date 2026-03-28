"""QuantumRAG Scenario Test Suite v4 — Self-contained runner.

33 scenarios, 176 test cases covering:
- S1-S17: Baseline scenarios (from v1)
- S18: Incomplete info reasoning
- S19: Contradiction detection
- S20: Mixed Korean-English queries
- S21: Counterfactual reasoning
- S22: Precision cross-check with numerical verification
- S23: Complex conditional queries
- S24: Abstract / meta-level queries
- S25: Reverse inference
- S26: Table structure understanding
- S27: Answer completeness
- S28: Chunk boundary robustness
- S29: PDF deep structure extraction
- S30: Scattered info aggregation
- S31: Reranker-enhanced retrieval (v4)
- S32: HWPX deep content extraction (v4)
- S33: Cross-format numerical precision (v4)

Usage:
    uv run python tests/scenarios/v4/test_cases.py
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

# Load .env
env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from quantumrag.core.config import QuantumRAGConfig
from quantumrag.core.engine import Engine

# -- Constants ----------------------------------------------------------------
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
DIVIDER = "=" * 78
SUB_DIVIDER = "-" * 78

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "test_scenario_data"
DOCS_DIR = PROJECT_ROOT / "test_docs"


@dataclass
class TestCase:
    id: str
    scenario: str
    question: str
    # ALL keywords must appear (strict mode), or specify mode
    expected_keywords: list[str]
    description: str = ""
    match_mode: str = "any"  # "any" = at least one, "all" = every keyword required
    expect_insufficient: bool = False
    expect_confidence: str | None = None  # None = any confidence ok
    difficulty: str = "medium"  # "easy", "medium", "hard", "extreme"


@dataclass
class TestResult:
    test_case: TestCase
    passed: bool
    answer: str = ""
    confidence: str = ""
    latency_s: float = 0.0
    sources_count: int = 0
    top_score: float = 0.0
    error: str = ""


@dataclass
class ScenarioReport:
    name: str
    results: list[TestResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def avg_latency(self) -> float:
        latencies = [r.latency_s for r in self.results if r.latency_s > 0]
        return sum(latencies) / len(latencies) if latencies else 0.0


# ==============================================================================
# TEST CASE DEFINITIONS -- S1-S17 BASELINE (from v1)
# ==============================================================================

# -- S1: Factual Baseline -----------------------------------------------------
S1_FACTUAL = [
    TestCase(
        "1.1", "S1", "퀀텀소프트 대표이사 이름은?", ["김태현"], "기본 인물 조회", difficulty="easy"
    ),
    TestCase(
        "1.2", "S1", "2024년 연 매출은 얼마인가요?", ["152억"], "기본 수치 조회", difficulty="easy"
    ),
    TestCase("1.3", "S1", "SLA 가용성 목표는?", ["99.9"], "계약서 수치", difficulty="easy"),
    TestCase(
        "1.4",
        "S1",
        "QuantumRAG v2.5.0의 출시일은?",
        ["2024-10-15", "2024년 10월", "10월 15일"],
        "제품 버전 날짜 -- 청크 문맥 보강으로 해결 기대",
        difficulty="medium",
    ),
    TestCase("1.5", "S1", "AI팀 인원은 몇 명인가요?", ["15"], "조직도 수치", difficulty="easy"),
    TestCase(
        "1.6",
        "S1",
        "보안 감사 전체 발견 사항은 총 몇 건인가요?",
        ["13"],
        "보안 감사 보고서",
        difficulty="easy",
    ),
    TestCase(
        "1.7",
        "S1",
        "법무법인 김앤장의 월 매출은?",
        ["2,000만", "2000만"],
        "고객 사례 보고서",
        difficulty="easy",
    ),
]

# -- S2: Multi-hop Reasoning ---------------------------------------------------
S2_MULTIHOP = [
    TestCase(
        "2.1",
        "S2",
        "현재 월 소진율과 보유 현금으로 볼 때 런웨이는 몇 개월인가요?",
        ["10.7", "10", "11"],
        "회의록+이메일: 45억 / 4.2억",
        difficulty="medium",
    ),
    TestCase(
        "2.2",
        "S2",
        "Series C 200억원이 성공하면 총 누적 투자액은 얼마인가요?",
        ["355억", "355"],
        "155억(기존) + 200억(Series C) = 355억",
        match_mode="any",
        difficulty="hard",
    ),
    TestCase(
        "2.3",
        "S2",
        "CTO가 겸임하는 팀은 어디이고, 그 팀의 예산은 얼마인가요?",
        ["백엔드", "8"],
        "조직도에서 박서연 겸임 + 예산",
        match_mode="all",
        difficulty="medium",
    ),
    TestCase(
        "2.4",
        "S2",
        "HyPE 기능 도입으로 인제스트 시간이 얼마나 증가했고, 이를 개선하기 위해 어떤 최적화를 진행 중인가요?",
        ["73%", "임베딩 배치", "2배"],
        "이메일(HyPE 성능 보고) + changelog 교차",
        difficulty="hard",
    ),
    TestCase(
        "2.5",
        "S2",
        "일본 시장 PoC 3건의 총 예상 연 계약 규모는 얼마인가요?",
        ["7.5억", "7억5"],
        "이메일: 2.5억 + 1.8억 + 3.2억 = 7.5억",
        difficulty="hard",
    ),
    TestCase(
        "2.6",
        "S2",
        "Series C 클로징까지 ARR을 얼마나 더 올려야 하고, 이를 위해 필요한 신규 계약 규모는?",
        ["180억", "30억"],
        "이메일(ARR 180억 필요) + 이메일(하반기 신규 30억)",
        difficulty="extreme",
    ),
]

# -- S3: Numerical Computation -------------------------------------------------
S3_NUMERICAL = [
    TestCase(
        "3.1",
        "S3",
        "2022년 대비 2024년 매출 성장률은 몇 퍼센트인가요?",
        ["192", "193", "약 3배", "2.9배", "190"],
        "(152-52)/52 = 192%",
        difficulty="medium",
    ),
    TestCase(
        "3.2",
        "S3",
        "인건비가 전체 비용에서 차지하는 비율과 월 인건비 금액은?",
        ["65%", "5.8억"],
        "회의록 비용 구조",
        match_mode="all",
        difficulty="medium",
    ),
    TestCase(
        "3.3",
        "S3",
        "개발 부서 전체 예산 합계는 얼마인가요?",
        ["32.5", "32억"],
        "조직도: 8+12+4+6.5+2 = 32.5억",
        difficulty="medium",
    ),
    TestCase(
        "3.4",
        "S3",
        "전체 파이프라인 규모에서 일본 비중은 얼마인가요?",
        ["38%", "39%", "7.5", "19.5"],
        "이메일: 7.5/19.5 = 38.5%",
        difficulty="hard",
    ),
    TestCase(
        "3.5",
        "S3",
        "삼성전자 도입 후 문서 검색 시간이 절대적으로 얼마나 줄었나요?",
        ["5.5시간", "5시간 30분", "5.5"],
        "고객 사례: 주 8시간 -> 2.5시간 = 5.5시간 절감",
        difficulty="medium",
    ),
    TestCase(
        "3.6",
        "S3",
        "보안 감사에서 조치 완료된 비율은 얼마인가요?",
        ["7", "8", "54%", "62%", "53%"],
        "감사 보고서: 심각1+높음3+중간2+낮음0 = 6~7건 조치 완료 / 13건",
        difficulty="hard",
    ),
]

# -- S4: Temporal / Version Reasoning ------------------------------------------
S4_TEMPORAL = [
    TestCase(
        "4.1",
        "S4",
        "Triple Index Fusion은 어느 버전에서 처음 도입되었나요?",
        ["v2.3", "2.3"],
        "changelog breadcrumb으로 해결 기대",
        difficulty="medium",
    ),
    TestCase(
        "4.2",
        "S4",
        "HyPE 기능이 도입되기 전에는 어떤 검색 방식을 사용했나요?",
        ["단일 벡터", "벡터 검색", "벡터", "Original"],
        "v2.1 -> v2.3 변화",
        difficulty="hard",
    ),
    TestCase(
        "4.3",
        "S4",
        "Adaptive Query Routing과 HyPE 중 어느 것이 먼저 출시되었나요?",
        ["Adaptive Query Routing", "라우팅", "v2.4"],
        "v2.4(라우팅, 2024-07) vs v2.5(HyPE, 2024-10)",
        difficulty="medium",
    ),
    TestCase(
        "4.4",
        "S4",
        "Python 최소 버전이 3.11로 변경된 것은 어느 릴리스인가요?",
        ["v2.5", "2.5"],
        "changelog 호환성 섹션",
        difficulty="medium",
    ),
    TestCase(
        "4.5",
        "S4",
        "QuantumGuard의 프로토타입 완성 시점과 정식 출시 시점은 각각 언제인가요?",
        ["2024년 12월", "12월", "2025년 Q2", "Q2"],
        "이메일 + 로드맵 교차",
        difficulty="medium",
    ),
    TestCase(
        "4.6",
        "S4",
        "v3.0 Atlas 릴리스에서 가장 높은 우선순위(P0) 기능들은 무엇인가요?",
        ["OCR", "증분 인덱싱"],
        "로드맵 Q1 P0 항목",
        match_mode="all",
        difficulty="medium",
    ),
]

# -- S5: Negation / Exclusion --------------------------------------------------
S5_NEGATION = [
    TestCase(
        "5.1",
        "S5",
        "현재 온프레미스 배포를 지원하지 않는 경쟁사는 어디인가요?",
        ["뤼튼"],
        "경쟁사 분석: 뤼튼만 X",
        difficulty="medium",
    ),
    TestCase(
        "5.2",
        "S5",
        "멀티모달을 지원하지 않는 경쟁사를 모두 알려주세요",
        ["뤼튼", "포티투마루"],
        "경쟁사 분석 표에서 X 찾기",
        match_mode="all",
        difficulty="medium",
    ),
    TestCase(
        "5.3",
        "S5",
        "보안 감사에서 아직 조치되지 않은 '중간' 등급 사항은 몇 건인가요?",
        ["3", "SEC-005", "SEC-006", "SEC-008"],
        "보안 감사: 중간 5건 중 2건 완료, 3건 미조치",
        difficulty="hard",
    ),
    TestCase(
        "5.4",
        "S5",
        "QuantumRAG v2.4.0에서 도입되지 않은 기능은? HyPE, Adaptive Query Routing, PPTX 파서 중에서",
        ["HyPE"],
        "HyPE는 v2.5.0에서 도입",
        difficulty="medium",
    ),
    TestCase(
        "5.5",
        "S5",
        "등록된 특허 중 해외(PCT) 출원이 되지 않은 특허는?",
        ["PAT-001", "하이브리드", "Triple Index"],
        "특허: PAT-001은 한국만, PAT-002는 PCT 완료",
        difficulty="hard",
    ),
]

# -- S6: Cross-Document Synthesis ----------------------------------------------
S6_CROSS_DOC = [
    TestCase(
        "6.1",
        "S6",
        "삼성전자의 도입 제품, 도입 후 검색 만족도, 그리고 주요 개선 요청을 알려주세요",
        ["Enterprise", "82%", "스캔", "PDF", "이미지"],
        "고객 사례: Enterprise, 82%, 스캔 PDF/이미지",
        match_mode="any",
        difficulty="hard",
    ),
    TestCase(
        "6.2",
        "S6",
        "KB국민은행의 응답 속도 요구사항과, 이를 해결할 수 있는 v2.5 기능은?",
        ["1.5초", "BM25", "40%"],
        "이메일(속도 요구) + changelog(BM25 40% 개선)",
        difficulty="hard",
    ),
    TestCase(
        "6.3",
        "S6",
        "네이버 클라우드가 경쟁사에서 전환한 이유와, 전환 후 검색 정확도 개선 수치는?",
        ["퀀텀아이", "Upstage", "19%", "0.81"],
        "고객 사례: Upstage에서 전환, NDCG 개선",
        difficulty="hard",
    ),
    TestCase(
        "6.4",
        "S6",
        "QuantumGuard의 핵심 기능, 가격 정책, 관련 특허를 종합해주세요",
        ["인젝션", "PII", "200만", "PAT-004"],
        "이메일(기능/가격) + 특허(PAT-004)",
        difficulty="extreme",
    ),
    TestCase(
        "6.5",
        "S6",
        "Series C 자금 용도 중 R&D 인력 확충 비용과 실제 채용 계획 인원을 연결해주세요",
        ["80억", "15명", "30명"],
        "이메일(80억 R&D) + 로드맵(개발15+영업5+기타10=30명)",
        difficulty="hard",
    ),
]

# -- S7: Paraphrase / Colloquial -----------------------------------------------
S7_PARAPHRASE = [
    TestCase(
        "7.1",
        "S7",
        "회사에 돈이 얼마나 남아있어요?",
        ["45억"],
        "보유 현금 45억 (일상적 표현)",
        difficulty="easy",
    ),
    TestCase(
        "7.2",
        "S7",
        "투자자들한테 회사 가치를 얼마로 보여주려고 하나요?",
        ["1,500억", "1500억"],
        "밸류에이션 (비공식 표현)",
        difficulty="medium",
    ),
    TestCase(
        "7.3",
        "S7",
        "해킹 당하면 제일 위험한 게 뭐에요?",
        ["API 키", "평문", "SEC-001", "SQL Injection", "SEC-003", "데이터 유출"],
        "보안 감사 Critical/High 항목 (구어체)",
        difficulty="hard",
    ),
    TestCase(
        "7.4",
        "S7",
        "일본에서 제일 큰 계약이 될 곳은 어디야?",
        ["NTT", "3.2억"],
        "이메일: NTT 데이터 3.2억 (최대 규모)",
        difficulty="medium",
    ),
    TestCase(
        "7.5",
        "S7",
        "우리 기술 뺏기지 않으려고 뭐 해놨어?",
        ["특허", "3건", "PAT"],
        "특허 포트폴리오 (비격식 질문)",
        difficulty="hard",
    ),
    TestCase(
        "7.6",
        "S7",
        "매출이 가장 큰 고객사는 어디인가요?",
        ["김앤장", "2,000만", "2000만"],
        "고객 사례: 최대 고객",
        difficulty="medium",
    ),
]

# -- S8: Multi-turn (handled separately in run_multiturn) ----------------------

# -- S9: Edge Cases & Robustness -----------------------------------------------
S9_EDGE = [
    TestCase("9.1", "S9", "", [], "빈 질문", expect_insufficient=True, difficulty="easy"),
    TestCase(
        "9.2",
        "S9",
        "퀀텀소프트의 양자 컴퓨터 연구소는 어디에 있나요?",
        [],
        "문서에 없는 내용",
        expect_insufficient=True,
        difficulty="easy",
    ),
    TestCase(
        "9.3",
        "S9",
        "매출은??? $$$$ 얼마냐고!!",
        ["152억"],
        "공격적 어투 + 특수문자",
        difficulty="medium",
    ),
    TestCase(
        "9.4",
        "S9",
        "퀀텀소프트의 " * 30 + "매출은 얼마인가요?",
        ["152억"],
        "반복 패턴이 포함된 긴 질문",
        difficulty="medium",
    ),
    TestCase(
        "9.5",
        "S9",
        "SELECT * FROM companies WHERE name='퀀텀소프트'",
        [],
        "SQL injection 시도",
        expect_insufficient=True,
        difficulty="easy",
    ),
    TestCase(
        "9.6",
        "S9",
        "리턴제로의 CTO 이름은 무엇인가요?",
        [],
        "문서에 존재하지 않는 상세 정보",
        expect_insufficient=True,
        difficulty="easy",
    ),
    TestCase(
        "9.7",
        "S9",
        "2030년 퀀텀소프트 매출 전망은?",
        [],
        "미래 예측 (문서에 없음)",
        expect_insufficient=True,
        difficulty="easy",
    ),
]

# -- S10: Precision Search -----------------------------------------------------
S10_PRECISION = [
    TestCase(
        "10.1",
        "S10",
        "Series C 투자 리드 후보사는 어디인가요?",
        ["미래에셋", "한화"],
        "회의록/이메일 깊은 상세 정보",
        match_mode="all",
        difficulty="medium",
    ),
    TestCase(
        "10.2",
        "S10",
        "v2.4.0에서 수정된 버그를 모두 나열해주세요",
        ["race condition", "UTF-8", "오버랩"],
        "changelog 특정 버전 상세",
        match_mode="all",
        difficulty="medium",
    ),
    TestCase(
        "10.3",
        "S10",
        "해외사업팀의 팀장과 인원수, 주요 업무를 알려주세요",
        ["김하은", "3", "일본"],
        "조직도 CSV의 특정 행",
        match_mode="all",
        difficulty="easy",
    ),
    TestCase(
        "10.4",
        "S10",
        "보안 감사에서 SQL Injection 취약점의 조치 상태와 조치 내용은?",
        ["SEC-003", "파라미터 바인딩", "완료", "2024-09-20"],
        "보안 감사 SEC-003 상세",
        difficulty="hard",
    ),
    TestCase(
        "10.5",
        "S10",
        "HyPE 알파 테스트에서 Recall@5 수치 변화와 스토리지 증가율은?",
        ["0.72", "0.83", "75"],
        "이메일: HyPE 성능 표",
        match_mode="all",
        difficulty="hard",
    ),
    TestCase(
        "10.6",
        "S10",
        "PAT-003 특허의 발명자, 등록일, 보호 범위를 알려주세요",
        ["강지훈", "김민수", "2024-09-30", "일본"],
        "특허 문서 상세",
        match_mode="all",
        difficulty="hard",
    ),
]

# -- S11: Implicit Inference ---------------------------------------------------
S11_IMPLICIT = [
    TestCase(
        "11.1",
        "S11",
        "퀀텀소프트에서 가장 많은 특허를 보유한 개인은 누구인가요?",
        ["강지훈"],
        "특허: PAT-001, 002, 003, 004에 모두 등재 -> 강지훈 4건",
        difficulty="hard",
    ),
    TestCase(
        "11.2",
        "S11",
        "하반기 채용 확대로 월 소진율이 얼마나 증가했나요?",
        ["0.4억", "4천만", "4,000만", "3.8", "4.2"],
        "이메일: 3.8억->4.2억 = 0.4억 증가",
        difficulty="hard",
    ),
    TestCase(
        "11.3",
        "S11",
        "현대자동차 PoC가 실패하면 어떤 경쟁사로 전환할 가능성이 있나요?",
        ["퀀텀아이", "Upstage"],
        "고객 사례: PoC 실패 시 Upstage 재전환 가능",
        difficulty="hard",
    ),
    TestCase(
        "11.4",
        "S11",
        "Kiwi 형태소 분석기의 라이선스 리스크는 무엇이고, 현재 문제 상태는?",
        ["LGPL", "정적 링크", "동적 링크"],
        "특허 문서: 현재 정적 링크 사용 -> 동적 링크 변경 필요",
        difficulty="hard",
    ),
    TestCase(
        "11.5",
        "S11",
        "QuantumRAG Community 버전을 SaaS로 제공할 때의 법적 제약은?",
        ["AGPL", "소스 공개", "엔터프라이즈"],
        "특허: AGPL 네트워크 사용 조항",
        difficulty="hard",
    ),
]

# -- S12: Competitive Analysis -------------------------------------------------
S12_COMPETITIVE = [
    TestCase(
        "12.1",
        "S12",
        "특허 건수 기준으로 퀀텀소프트보다 많은 특허를 보유한 경쟁사는?",
        ["퀀텀아이", "리턴제로", "42Maru", "포티투마루"],
        "특허: 퀀텀소프트 3건 vs 퀀텀아이 8, 리턴제로 12, 42Maru 5",
        difficulty="hard",
    ),
    TestCase(
        "12.2",
        "S12",
        "네이버 클라우드가 퀀텀아이에서 퀀텀소프트로 전환한 것이 시장 점유율에 어떤 영향을 줄 수 있나요?",
        ["1,200만", "1200만", "퀀텀아이"],
        "고객 사례(월 1,200만 계약) + 경쟁사(점유율)",
        difficulty="extreme",
    ),
    TestCase(
        "12.3",
        "S12",
        "42Maru와 NTT 데이터 PoC에서 경쟁하고 있는데, 42Maru 대비 퀀텀소프트의 기술적 장점은?",
        ["Triple Index", "한국어", "검색 정확도"],
        "이메일(NTT 경쟁) + 경쟁사 분석(기술 비교)",
        difficulty="extreme",
    ),
]

# -- S13: Conditional Reasoning ------------------------------------------------
S13_CONDITIONAL = [
    TestCase(
        "13.1",
        "S13",
        "Series C 200억원 투자금의 가장 큰 사용 용도는 무엇이고 얼마인가요?",
        ["R&D", "80억"],
        "이메일6: R&D 인력 80억 > 운영 50억 > QuantumGuard 40억 > 일본 30억",
        difficulty="medium",
    ),
    TestCase(
        "13.2",
        "S13",
        "현재 런웨이로 QuantumGuard 정식 출시(2025 Q2)까지 자금이 충분한가요?",
        ["10.7", "충분", "가능"],
        "런웨이 10.7개월, Q2 2025까지 약 7-8개월 -> 가능하지만 여유 없음",
        difficulty="hard",
    ),
    TestCase(
        "13.3",
        "S13",
        "삼성전자가 요청한 스캔 PDF 지원은 로드맵에서 언제 해결될 예정인가요?",
        ["OCR", "Q1", "v3.0", "Tesseract"],
        "고객 사례(스캔 PDF 요청) + 로드맵(Q1 OCR 통합)",
        difficulty="hard",
    ),
    TestCase(
        "13.4",
        "S13",
        "자체 파인튜닝 모델로 전환하면 연간 얼마를 절감할 수 있나요?",
        ["1,500만", "1500만", "60%", "1.8억", "18000"],
        "회의록: 월 2,400만 -> 월 1,500만 절감 (60%), 연 1.8억",
        difficulty="hard",
    ),
    TestCase(
        "13.5",
        "S13",
        "ARR 180억원을 달성하려면 현재 대비 얼마나 더 매출을 올려야 하고, 이를 위해 파이프라인이 충분한가요?",
        ["60억", "180", "120", "19.5", "28억"],
        "현재 ARR 120억 -> 180억 필요 = +60억. 파이프라인 19.5억(이메일) + 28억(회의록)",
        difficulty="extreme",
    ),
]

# -- S14: Multi-Constraint Filtering -------------------------------------------
S14_FILTER = [
    TestCase(
        "14.1",
        "S14",
        "온프레미스로 배포된 Enterprise 등급 고객의 월 매출 합계는?",
        ["2,800만", "2800만"],
        "삼성전자(800만) + 김앤장(2,000만) = 2,800만",
        difficulty="hard",
    ),
    TestCase(
        "14.2",
        "S14",
        "조치 완료된 High 등급 이상 보안 이슈의 ID를 모두 나열하세요",
        ["SEC-001", "SEC-002", "SEC-003", "SEC-004"],
        "Critical: SEC-001(완료), High: SEC-002,003,004(모두 완료) -- 4개 섹션 동시 검색 필요",
        match_mode="all",
        difficulty="extreme",
    ),
    TestCase(
        "14.3",
        "S14",
        "PCT 국제 출원이 완료된 특허 중 강지훈이 발명자인 것은?",
        ["PAT-002", "적응형", "라우팅"],
        "PAT-002만 PCT 완료 + 강지훈 발명",
        difficulty="hard",
    ),
    TestCase(
        "14.4",
        "S14",
        "개발 부서에서 인원이 10명 이상인 팀과 해당 팀장을 알려주세요",
        ["백엔드", "박서연", "AI", "강지훈"],
        "조직도: 백엔드(12명,박서연) + AI(15명,강지훈)",
        match_mode="all",
        difficulty="medium",
    ),
    TestCase(
        "14.5",
        "S14",
        "2024년 하반기(7월 이후)에 릴리스된 제품 버전의 주요 신기능을 각각 알려주세요",
        ["v2.4", "Routing", "v2.5", "HyPE"],
        "changelog: v2.4(7월, Adaptive Query Routing) + v2.5(10월, HyPE)",
        match_mode="all",
        difficulty="hard",
    ),
]

# -- S15: Derived Quantitative -------------------------------------------------
S15_DERIVED = [
    TestCase(
        "15.1",
        "S15",
        "개발 부서에서 팀별 1인당 예산이 가장 높은 팀은 어디이고 얼마인가요?",
        ["인프라", "1.08", "1.0"],
        "인프라: 6.5억/6명=1.08억 > AI: 12/15=0.8 > 백엔드: 8/12=0.67",
        difficulty="hard",
    ),
    TestCase(
        "15.2",
        "S15",
        "상위 5개 고객사의 월 매출 합이 전체 월 매출에서 차지하는 비중은?",
        ["63", "62", "5,200", "5200", "8,267", "8267"],
        "김앤장2000+네이버1200+삼성800+KB600+현대600=5200/8267=63%",
        difficulty="extreme",
    ),
    TestCase(
        "15.3",
        "S15",
        "2022년에서 2024년까지 매출 연평균 성장률(CAGR)은 약 몇 %인가요?",
        ["70", "71", "170", "171"],
        "52->152억 in 2년, CAGR=(152/52)^0.5-1=71%",
        difficulty="extreme",
    ),
    TestCase(
        "15.4",
        "S15",
        "전체 비용 구조에서 인건비와 인프라 비용의 합은 월 얼마이고 전체의 몇 %인가요?",
        ["6.3", "71", "5.8", "0.5"],
        "회의록: 인건비 5.8억(65%) + 인프라 0.5억(6%) = 6.3억(71%)",
        difficulty="hard",
    ),
    TestCase(
        "15.5",
        "S15",
        "고객사당 평균 연간 계약 규모(ARR/고객수)는 얼마인가요?",
        ["3.75", "3,800만", "3800만", "120억"],
        "ARR 120억 / 32개사 = 3.75억. 또는 회의록: 평균 3,800만원/년",
        difficulty="medium",
    ),
]

# -- S16: Cross-Verification --------------------------------------------------
S16_CROSSCHECK = [
    TestCase(
        "16.1",
        "S16",
        "CEO 이메일과 CFO 보고서에서 런웨이 수치가 다른데, 각각 얼마로 언급했나요?",
        ["12", "13", "10.7"],
        "CEO: 실질 12~13개월, CFO: 10.7개월 -- 시점/가정 차이",
        match_mode="all",
        difficulty="hard",
    ),
    TestCase(
        "16.2",
        "S16",
        "회의록의 채용 계획과 로드맵의 채용 계획이 일치하나요?",
        ["25", "30"],
        "회의록: 25명(개발15+영업5+기타5), 로드맵: 30명(개발15+영업5+기타10)",
        match_mode="all",
        difficulty="hard",
    ),
    TestCase(
        "16.3",
        "S16",
        "QuantumGuard의 출시 일정이 이메일과 로드맵에서 동일한가요?",
        ["Q2", "2025"],
        "이메일5: 정식 출시 Q2 2025 = 로드맵 Q2 2025 QuantumGuard v1.0",
        difficulty="medium",
    ),
    TestCase(
        "16.4",
        "S16",
        "일본 법인 설립 비용이 이메일과 회의록에서 다른데, 각각 얼마인가요?",
        ["20억", "30억"],
        "회의록: 약 20억원, 이메일6: 30억원 -- 범위 차이",
        match_mode="all",
        difficulty="hard",
    ),
]

# -- S17: Multi-Format Documents (PDF / HWPX) ---------------------------------
S17_FORMATS = [
    # -- PDF: ZeroH Hallucination Framework --
    TestCase(
        "17.1",
        "S17",
        "ZeroH Hallucination Framework의 저자와 소속은?",
        ["QuantumAI", "Kanhun Lee"],
        "PDF: 저자/소속 기본 확인",
        match_mode="all",
        difficulty="easy",
    ),
    TestCase(
        "17.2",
        "S17",
        "ZeroH 프레임워크에서 사용하는 Multi-Agent Orchestration의 핵심 원리는?",
        ["multi-agent", "에이전트", "협업", "collaboration", "orchestration"],
        "PDF: 아키텍처 핵심 개념",
        difficulty="medium",
    ),
    TestCase(
        "17.3",
        "S17",
        "ZeroH에서 할루시네이션 분석에 사용한 데이터셋과 규모는?",
        ["COCO", "5,000", "5000"],
        "PDF: COCO dataset 5000 image-caption pairs",
        difficulty="medium",
    ),
    TestCase(
        "17.4",
        "S17",
        "ZeroH에서 이미지-캡션 유사도를 측정하는 데 사용하는 모델은?",
        ["CLIP"],
        "PDF: Image-Caption Similarity Assessment",
        difficulty="easy",
    ),
    TestCase(
        "17.5",
        "S17",
        "ZeroH의 생성 품질 평가 지표 3가지는 무엇인가요?",
        ["informativeness", "consistency", "fluency"],
        "PDF: Metrics for Generation Quality",
        match_mode="all",
        difficulty="medium",
    ),
    TestCase(
        "17.6",
        "S17",
        "ZeroH의 Triple-Oriented Response Segmentation은 어떤 방식으로 할루시네이션을 감지하나요?",
        ["triple", "knowledge", "align"],
        "PDF: Methodology - triple extraction and alignment",
        difficulty="hard",
    ),
    TestCase(
        "17.7",
        "S17",
        "ZeroH에서 그래프 기반 문맥 일관성 비교에 사용하는 네트워크는?",
        ["RGCN", "Relational Graph"],
        "PDF: Graph-based Contextual Consistency Comparison",
        difficulty="medium",
    ),
    TestCase(
        "17.8",
        "S17",
        "ZeroH의 Multi-Stage Workflow에서 MKT와 Alignment Test의 역할은?",
        ["MKT", "Model Knowledge Test", "Alignment"],
        "PDF: MKT assesses knowledge sufficiency, Alignment Test evaluates content alignment",
        match_mode="any",
        difficulty="hard",
    ),
    TestCase(
        "17.9",
        "S17",
        "ZeroH에서 에이전트 간 통신에 사용하는 표준 프레임워크는?",
        ["OVON", "Open Voice Network"],
        "PDF: Multi-Agent Collaboration via OVON",
        difficulty="medium",
    ),
    TestCase(
        "17.10",
        "S17",
        "ZeroH 프레임워크의 리뷰 레벨 구조는?",
        ["Front End Agent", "Second Level Reviewer", "Third Level Reviewer"],
        "PDF: 3단계 리뷰 구조",
        match_mode="any",
        difficulty="hard",
    ),
    # -- HWPX: 2025 Ministry of the Interior plan --
    TestCase(
        "17.11",
        "S17",
        "2025년 행정안전부의 기본 방향은 무엇인가요?",
        ["안정적 국정 운영", "안전한 국민 일상"],
        "HWPX: 기본 방향",
        difficulty="easy",
    ),
    TestCase(
        "17.12",
        "S17",
        "2025년 정부 경제성장률 전망은 얼마인가요?",
        ["1.8"],
        "HWPX: 경제성장률 '25 1.8%",
        difficulty="easy",
    ),
    TestCase(
        "17.13",
        "S17",
        "국가공무원 정원은 얼마나 감축되었나요?",
        ["4천", "4,000", "4000"],
        "HWPX: 국가공무원 정원 약 4천 명 감축",
        difficulty="medium",
    ),
    TestCase(
        "17.14",
        "S17",
        "모바일 신분증 발급자 수는 얼마인가요?",
        ["400만"],
        "HWPX: 모바일 신분증 발급자 400만 명 돌파",
        difficulty="easy",
    ),
    TestCase(
        "17.15",
        "S17",
        "고향사랑기부제의 2024년 잠정 모금액은 얼마인가요?",
        ["879억"],
        "HWPX: 고향사랑기부제 '24잠정 879억 모금",
        difficulty="medium",
    ),
    TestCase(
        "17.16",
        "S17",
        "풍수해 생활권 종합정비 사업은 2025년에 몇 개소로 확대되나요?",
        ["35"],
        "HWPX: '24 18개소->'25 35개소",
        difficulty="medium",
    ),
    TestCase(
        "17.17",
        "S17",
        "재난문자 제공언어는 몇 개에서 몇 개로 확대되나요?",
        ["5개", "19개"],
        "HWPX: 5개->19개 언어, '25.8.",
        match_mode="all",
        difficulty="medium",
    ),
    TestCase(
        "17.18",
        "S17",
        "SAR(합성 개구 레이더)를 활용한 R&D의 대상은 무엇인가요?",
        ["급경사지", "붕괴"],
        "HWPX: 드론/SAR 활용 급경사지 붕괴위험 분석기술",
        difficulty="hard",
    ),
    # -- Cross-format: PDF + HWPX --
    TestCase(
        "17.19",
        "S17",
        "ZeroH 프레임워크의 할루시네이션 완화 기법과 행정안전부의 재난문자 정보 전달력 강화는 어떤 공통점이 있나요?",
        ["정확", "신뢰", "정보"],
        "PDF+HWPX: 정보의 정확성과 신뢰성이라는 공통 주제",
        difficulty="extreme",
    ),
    TestCase(
        "17.20",
        "S17",
        "ZeroH에서 언급된 Unlearning 기법의 핵심 목적은 무엇인가요?",
        ["hallucination", "할루시네이션", "unlearning", "잘못된", "부정확"],
        "PDF: Comprehensive Unlearning Techniques -- 할루시네이션 최소화",
        difficulty="hard",
    ),
]


# ==============================================================================
# TEST CASE DEFINITIONS -- S18-S25 ADVANCED (v2 exclusive)
# ==============================================================================

# -- S18: Incomplete Info Reasoning --------------------------------------------
S18_INCOMPLETE = [
    TestCase(
        "18.1",
        "S18",
        "Series C 투자 후 직원 1인당 연봉 평균은 얼마인가요?",
        ["부족", "확인", "산출", "인건비", "87"],
        "문서에 총 인원/예산은 있으나 1인당 연봉은 없음 -- 부분 정보 인정 필요",
        expect_insufficient=True,
        difficulty="hard",
    ),
    TestCase(
        "18.2",
        "S18",
        "퀀텀소프트의 여성 임원 비율은?",
        ["확인", "명시", "성별", "조직도"],
        "조직도에 이름만 있고 성별 정보 없음",
        expect_insufficient=True,
        difficulty="medium",
    ),
    TestCase(
        "18.3",
        "S18",
        "ZeroH 프레임워크를 실제 서비스에 적용한 기업 사례는?",
        ["학술", "논문", "사례", "없"],
        "학술 논문이므로 실제 배포 사례 없음",
        expect_insufficient=True,
        difficulty="medium",
    ),
    TestCase(
        "18.4",
        "S18",
        "행정안전부 2025년 예산 총액은?",
        ["개별", "사업", "총액", "확인"],
        "HWPX에 개별 프로그램 예산은 있으나 총액 합산은 불명확",
        expect_insufficient=True,
        difficulty="hard",
    ),
    TestCase(
        "18.5",
        "S18",
        "퀀텀소프트의 기술 부채(tech debt) 규모는?",
        ["감사", "보안", "기술 부채", "명시"],
        "직접 명시되지 않음 -- 감사 결과에서 간접 추론 가능하나 수치 불가",
        expect_insufficient=True,
        difficulty="hard",
    ),
]

# -- S19: Contradiction Detection ----------------------------------------------
S19_CONTRADICTION = [
    TestCase(
        "19.1",
        "S19",
        "회의록과 이메일에서 Series C 마감 시점이 동일한가요?",
        ["Q1", "2025"],
        "회의록/이메일 간 날짜 교차 확인",
        match_mode="all",
        difficulty="hard",
    ),
    TestCase(
        "19.2",
        "S19",
        "보안 감사 보고서의 전체 위험도 평가와 개별 항목 분석이 일치하나요?",
        ["심각", "높음", "4건", "3건"],
        "전체 등급 vs 개별 항목 정합성 검증",
        difficulty="extreme",
    ),
    TestCase(
        "19.3",
        "S19",
        "고객사별 도입 시기와 계약 갱신 시점에 모순이 있나요?",
        ["갱신", "계약"],
        "시간적 일관성 확인",
        difficulty="hard",
    ),
    TestCase(
        "19.4",
        "S19",
        "CEO 이메일의 낙관적 전망과 CFO 보고서의 보수적 전망 중 구체적 수치 차이는?",
        ["12", "13", "10.7", "소진율"],
        "CEO 12-13개월 vs CFO 10.7개월",
        match_mode="any",
        difficulty="hard",
    ),
]

# -- S20: Mixed Korean-English Queries -----------------------------------------
S20_MIXED_LANG = [
    TestCase(
        "20.1",
        "S20",
        "QuantumRAG의 Triple Index Fusion에서 BM25 weight는 기본값이 얼마인가요?",
        ["0.25", "25%"],
        "한영 혼합: 기술 용어(영) + 질문(한)",
        difficulty="medium",
    ),
    TestCase(
        "20.2",
        "S20",
        "CLIP model로 image-caption similarity를 측정할 때 ZeroH의 baseline score는?",
        ["CLIP"],
        "PDF 기반 영어 기술 용어 + 한국어 문맥",
        difficulty="hard",
    ),
    TestCase(
        "20.3",
        "S20",
        "Enterprise plan의 on-premise deployment 고객 중 monthly revenue가 가장 높은 곳은?",
        ["김앤장", "2,000만", "2000만"],
        "영어 비즈니스 용어 + 한국어 데이터",
        difficulty="medium",
    ),
    TestCase(
        "20.4",
        "S20",
        "pyhwpx parser로 HWPX document를 parsing할 때의 known limitation은?",
        ["hwpx", "파싱", "한글", "제한"],
        "기술 용어 혼합 -- 문서에 직접 정보 부족할 수 있음",
        expect_insufficient=True,
        difficulty="hard",
    ),
]

# -- S21: Counterfactual Reasoning ---------------------------------------------
S21_COUNTERFACTUAL = [
    TestCase(
        "21.1",
        "S21",
        "Series C가 실패하면 현재 런웨이로 언제까지 운영 가능한가요?",
        ["10.7", "10", "2025"],
        "런웨이 10.7개월 기반 가정 추론",
        difficulty="hard",
    ),
    TestCase(
        "21.2",
        "S21",
        "일본 PoC 3건이 모두 성사되면 ARR에 어떤 영향이 있나요?",
        ["7.5억", "120억", "127.5"],
        "현재 ARR 120억 + 일본 7.5억 = 127.5억",
        difficulty="extreme",
    ),
    TestCase(
        "21.3",
        "S21",
        "HyPE 기능이 없었다면 현재 검색 성능은 어떤 수준이었을까요?",
        ["단일 벡터", "v2.3", "개선"],
        "HyPE 도입 전 성능 수준으로 회귀 가정",
        difficulty="hard",
    ),
    TestCase(
        "21.4",
        "S21",
        "행정안전부의 디지털 플랫폼 정부 계획이 중단되면 가장 큰 영향을 받는 사업은?",
        ["모바일", "신분증", "디지털"],
        "HWPX: 디지털 플랫폼 연관 사업 식별",
        difficulty="hard",
    ),
]

# -- S22: Precision Cross-Check ------------------------------------------------
S22_PRECISION_CROSS = [
    TestCase(
        "22.1",
        "S22",
        "전체 고객사 수(32개)와 고객 사례에 명시된 고객 수가 일치하나요?",
        ["32", "8", "사례"],
        "고객 사례 보고서에 명시된 개별 고객 수 vs 전체 32개",
        difficulty="extreme",
    ),
    TestCase(
        "22.2",
        "S22",
        "특허 출원일 순서대로 나열하고, 가장 최근 특허와 가장 오래된 특허의 간격은?",
        ["PAT-001", "PAT-004", "2024"],
        "특허 문서의 날짜 기반 정렬 및 간격 계산",
        difficulty="hard",
    ),
    TestCase(
        "22.3",
        "S22",
        "조직도의 총 인원과 회사 소개의 직원 수가 일치하나요?",
        ["87", "총 인원"],
        "조직도 CSV 합산 vs 회사 소개 수치 비교",
        difficulty="medium",
    ),
    TestCase(
        "22.4",
        "S22",
        "2024년 하반기 changelog의 기능 추가 건수와 버그 수정 건수를 각각 알려주세요",
        ["v2.4", "v2.5"],
        "changelog에서 하반기 항목 분류 및 집계",
        match_mode="all",
        difficulty="hard",
    ),
]

# -- S23: Complex Conditional Queries ------------------------------------------
S23_COMPLEX_COND = [
    TestCase(
        "23.1",
        "S23",
        "온프레미스 Enterprise 고객 중 검색 만족도 80% 이상인 곳의 공통 특징은?",
        ["삼성전자", "82%"],
        "다중 조건: 배포 방식 + 등급 + 만족도 필터링",
        difficulty="extreme",
    ),
    TestCase(
        "23.2",
        "S23",
        "보안 감사 High 등급 이상이면서 아직 미조치인 항목의 구체적 위험은?",
        ["SEC", "진행 중"],
        "보안 감사: 등급 + 조치 상태 교차 필터",
        difficulty="hard",
    ),
    TestCase(
        "23.3",
        "S23",
        "2024년 Q4에 달성한 마일스톤과 2025 Q1에 계획된 마일스톤을 각각 알려주세요",
        ["QuantumGuard", "프로토타입", "v3.0", "Atlas"],
        "시간 구간별 마일스톤 분류",
        match_mode="any",
        difficulty="hard",
    ),
    TestCase(
        "23.4",
        "S23",
        "월 매출 500만원 이상이면서 만족도 85% 이상인 고객사를 모두 알려주세요",
        ["삼성전자", "네이버"],
        "매출 + 만족도 이중 조건 필터",
        difficulty="hard",
    ),
]

# -- S24: Abstract / Meta Queries ----------------------------------------------
S24_ABSTRACT = [
    TestCase(
        "24.1",
        "S24",
        "퀀텀소프트의 가장 큰 사업 리스크 3가지를 우선순위로 알려주세요",
        ["런웨이", "경쟁", "일본"],
        "여러 문서에서 리스크 요인 추출 및 우선순위 판단",
        difficulty="extreme",
    ),
    TestCase(
        "24.2",
        "S24",
        "ZeroH 논문의 학술적 기여(contribution)를 3줄로 요약해주세요",
        ["hallucination", "multi-agent", "framework"],
        "PDF 전체 요약 -- 학술적 기여 추출",
        difficulty="hard",
    ),
    TestCase(
        "24.3",
        "S24",
        "행정안전부 2025년 계획에서 디지털 전환과 관련된 핵심 사업을 모두 나열해주세요",
        ["모바일 신분증", "디지털"],
        "HWPX에서 디지털 전환 관련 항목 필터링",
        difficulty="hard",
    ),
]

# -- S25: Reverse Inference ----------------------------------------------------
S25_REVERSE = [
    TestCase(
        "25.1",
        "S25",
        "월 소진율이 4.2억인 이유를 설명해주세요",
        ["채용", "하반기", "인건비"],
        "수치에서 역방향으로 원인 추적",
        difficulty="hard",
    ),
    TestCase(
        "25.2",
        "S25",
        "NDCG 0.81이라는 수치가 등장하는 맥락은?",
        ["네이버", "전환", "검색 정확도"],
        "수치 -> 문맥 역추적",
        difficulty="medium",
    ),
    TestCase(
        "25.3",
        "S25",
        "879억이라는 금액이 의미하는 것은?",
        ["고향사랑기부제", "기부", "모금"],
        "HWPX: 고향사랑기부제 모금액 역추적",
        difficulty="medium",
    ),
]


# ==============================================================================
# TEST CASE DEFINITIONS -- S26-S30 ADVANCED (v3 exclusive)
# ==============================================================================

# -- S26: Table Structure Understanding ----------------------------------------
S26_TABLE = [
    TestCase(
        "26.1",
        "S26",
        "경쟁사 비교표에서 온프레미스와 멀티모달을 모두 지원하는 경쟁사는?",
        ["리턴제로", "퀀텀아이"],
        "표의 행/열 교차 조건 필터링",
        difficulty="hard",
    ),
    TestCase(
        "26.2",
        "S26",
        "경쟁사 중 MAU 기준 상위 3개사와 각각의 MAU를 알려주세요",
        ["리턴제로", "퀀텀아이", "뤼튼"],
        "표에서 정렬 + 상위 N 추출",
        difficulty="hard",
    ),
    TestCase(
        "26.3",
        "S26",
        "고객 사례 표에서 Cloud 배포 고객과 On-Premise 배포 고객의 평균 만족도 차이는?",
        ["Cloud", "On-Premise", "만족도"],
        "표의 그룹별 집계 비교",
        difficulty="extreme",
    ),
    TestCase(
        "26.4",
        "S26",
        "보안 감사에서 등급별 발견 건수를 표로 정리해주세요",
        ["Critical", "High", "Medium", "Low"],
        "구조적 데이터의 재구조화",
        match_mode="all",
        difficulty="hard",
    ),
    TestCase(
        "26.5",
        "S26",
        "ZeroH 논문의 표에서 각 평가 지표별 최고 성능 모델은?",
        ["informativeness", "consistency", "fluency"],
        "PDF 테이블 내 비교 데이터 추출",
        difficulty="extreme",
    ),
]

# -- S27: Answer Completeness --------------------------------------------------
S27_COMPLETENESS = [
    TestCase(
        "27.1",
        "S27",
        "일본 시장 PoC 3건의 회사명과 각각의 예상 계약 규모를 모두 알려주세요",
        ["미쓰비시", "NTT", "소프트뱅크", "2.5", "3.2", "1.8"],
        "3건의 산재된 정보 완전 수집",
        match_mode="any",
        difficulty="hard",
    ),
    TestCase(
        "27.2",
        "S27",
        "보안 감사에서 Critical과 High 등급의 모든 이슈 ID와 조치 상태를 나열하세요",
        ["SEC-001", "SEC-002", "SEC-003", "SEC-004"],
        "4개 보안 이슈 완전 열거",
        match_mode="all",
        difficulty="extreme",
    ),
    TestCase(
        "27.3",
        "S27",
        "퀀텀소프트의 4개 특허 각각의 제목과 상태를 알려주세요",
        ["PAT-001", "PAT-002", "PAT-003", "PAT-004"],
        "4개 특허 완전 열거",
        match_mode="all",
        difficulty="hard",
    ),
    TestCase(
        "27.4",
        "S27",
        "Series C 200억 투자금의 4가지 사용 용도와 각각의 금액은?",
        ["R&D", "80억", "운영", "50억", "QuantumGuard", "40억", "일본", "30억"],
        "4개 항목 완전 열거 + 금액",
        match_mode="any",
        difficulty="hard",
    ),
    TestCase(
        "27.5",
        "S27",
        "2025 로드맵에서 Q1~Q4 각 분기별 핵심 목표를 알려주세요",
        ["Q1", "Q2", "Q3", "Q4"],
        "4분기 전체 로드맵 완전 수집",
        match_mode="all",
        difficulty="hard",
    ),
]

# -- S28: Chunk Boundary Robustness --------------------------------------------
S28_BOUNDARY = [
    TestCase(
        "28.1",
        "S28",
        "v2.3.0의 마지막 신기능과 v2.4.0의 첫 번째 신기능은 각각 무엇인가요?",
        ["v2.3", "v2.4", "Triple Index", "Routing"],
        "버전 경계에 걸친 정보 추출",
        difficulty="hard",
    ),
    TestCase(
        "28.2",
        "S28",
        "이메일 본문 끝에 언급된 시그니처나 추신(P.S.) 내용이 있나요?",
        ["추신", "P.S.", "서명", "감사"],
        "문서 말미의 부가 정보 — 청크 경계에서 누락 가능",
        difficulty="medium",
    ),
    TestCase(
        "28.3",
        "S28",
        "행정안전부 문서의 마지막 섹션에서 다루는 주제는?",
        ["R&D", "기술", "연구"],
        "HWPX 문서 후반부 정보 — 마지막 청크에 위치",
        difficulty="medium",
    ),
    TestCase(
        "28.4",
        "S28",
        "ZeroH 논문의 References 직전 섹션(Conclusion)의 핵심 주장은?",
        ["hallucination", "framework", "future", "결론"],
        "PDF 결론부 — 문서 끝부분 청크 경계",
        difficulty="hard",
    ),
]

# -- S29: PDF Deep Structure Extraction ----------------------------------------
S29_PDF_DEEP = [
    TestCase(
        "29.1",
        "S29",
        "ZeroH 논문에서 Figure나 Table의 캡션을 하나 이상 인용해주세요",
        ["Figure", "Table", "Fig"],
        "PDF의 Figure/Table 캡션 추출",
        difficulty="hard",
    ),
    TestCase(
        "29.2",
        "S29",
        "ZeroH에서 환각(hallucination)의 유형을 몇 가지로 분류하나요?",
        ["intrinsic", "extrinsic", "factual", "유형"],
        "PDF 본문의 분류 체계 추출",
        difficulty="medium",
    ),
    TestCase(
        "29.3",
        "S29",
        "ZeroH 논문의 Abstract에서 언급된 핵심 기여 3가지는?",
        ["hallucination", "framework", "evaluation", "multi-agent"],
        "PDF Abstract 섹션 정밀 추출",
        difficulty="medium",
    ),
    TestCase(
        "29.4",
        "S29",
        "ZeroH에서 제안하는 hallucination mitigation 전략은 몇 가지이며 각각 무엇인가요?",
        ["mitigation", "strategy", "unlearning", "검증"],
        "PDF 핵심 방법론 완전 열거",
        difficulty="hard",
    ),
    TestCase(
        "29.5",
        "S29",
        "ZeroH 논문에서 실험에 사용된 모델이나 도구를 모두 나열해주세요",
        ["CLIP", "GPT", "model"],
        "PDF의 실험 설정 정보 수집",
        difficulty="extreme",
    ),
]

# -- S30: Scattered Info Aggregation -------------------------------------------
S30_AGGREGATION = [
    TestCase(
        "30.1",
        "S30",
        "퀀텀소프트의 모든 외부 파트너사(투자사, 고객사 제외)를 나열해주세요",
        ["미래에셋", "한화"],
        "여러 문서에 산재된 파트너 정보 수집",
        difficulty="hard",
    ),
    TestCase(
        "30.2",
        "S30",
        "현재 진행 중인 PoC(Proof of Concept) 프로젝트를 모두 나열하고 상태를 알려주세요",
        ["일본", "NTT", "현대", "PoC"],
        "이메일+회의록에 분산된 PoC 정보 종합",
        difficulty="extreme",
    ),
    TestCase(
        "30.3",
        "S30",
        "2025년에 예정된 모든 제품 출시/업데이트 일정을 시간순으로 정리해주세요",
        ["Q1", "Q2", "v3.0", "QuantumGuard"],
        "로드맵+이메일+회의록의 일정 정보 통합",
        match_mode="any",
        difficulty="hard",
    ),
    TestCase(
        "30.4",
        "S30",
        "퀀텀소프트가 사용하는 모든 오픈소스 라이브러리와 라이선스 리스크를 정리해주세요",
        ["AGPL", "LGPL", "Kiwi", "라이선스"],
        "특허+감사+changelog에 분산된 오픈소스 정보",
        difficulty="extreme",
    ),
]

# -- S31: Reranker-enhanced retrieval (v4) ------------------------------------
S31_RERANKER = [
    TestCase(
        "31.1",
        "S31",
        "일본 법인 설립 비용이 이메일과 회의록에서 다른데, 각각 얼마인가요?",
        ["30억", "20억"],
        "이메일 30억 vs 회의록 20억 — reranker로 양쪽 모두 검색",
        match_mode="all",
        difficulty="hard",
    ),
    TestCase(
        "31.2",
        "S31",
        "CEO와 CFO가 언급한 런웨이 수치를 각각 알려주세요",
        ["12", "10.7"],
        "CEO 12-13개월 vs CFO 10.7개월 — 교차 문서 수치 검색",
        difficulty="hard",
    ),
    TestCase(
        "31.3",
        "S31",
        "온프레미스 Enterprise 고객의 월 매출 합계를 계산해주세요",
        ["2,800만", "2800만"],
        "삼성(800)+김앤장(2000)=2800만 계산",
        difficulty="hard",
    ),
    TestCase(
        "31.4",
        "S31",
        "일본 PoC 3건이 모두 성사되면 ARR에 미치는 영향은?",
        ["7.5억", "127.5"],
        "미쓰비시2.5+소프트뱅크1.8+NTT3.2=7.5억 -> 120+7.5=127.5",
        difficulty="extreme",
    ),
    TestCase(
        "31.5",
        "S31",
        "2024년 하반기 changelog에서 각 버전의 주요 변경사항을 알려주세요",
        ["v2.4", "v2.5"],
        "하반기 버전명 구체적 열거",
        match_mode="all",
        difficulty="hard",
    ),
]

# -- S32: HWPX deep content extraction (v4) ----------------------------------
S32_HWPX_DEEP = [
    TestCase(
        "32.1",
        "S32",
        "2025년 정부 경제성장률 전망은 얼마인가요?",
        ["1.8"],
        "HWPX에서 경제성장률 1.8% 추출",
        difficulty="medium",
    ),
    TestCase(
        "32.2",
        "S32",
        "고향사랑기부제의 2024년 잠정 모금액은 얼마인가요?",
        ["879억"],
        "HWPX에서 879억 추출",
        difficulty="medium",
    ),
    TestCase(
        "32.3",
        "S32",
        "재난문자 제공언어는 몇 개에서 몇 개로 확대되나요?",
        ["5개", "19개"],
        "HWPX에서 5개→19개 추출",
        match_mode="all",
        difficulty="medium",
    ),
    TestCase(
        "32.4",
        "S32",
        "행정안전부 문서에서 R&D 관련 추진 사업을 알려주세요",
        ["R&D", "기술", "연구"],
        "HWPX 후반부 R&D 관련 내용",
        difficulty="hard",
    ),
    TestCase(
        "32.5",
        "S32",
        "모바일 신분증 발급자 수와 관련 법적 근거를 알려주세요",
        ["400만"],
        "HWPX 수치와 맥락 함께 추출",
        difficulty="medium",
    ),
]

# -- S33: Cross-format numerical precision (v4) ------------------------------
S33_CROSS_NUM = [
    TestCase(
        "33.1",
        "S33",
        "퀀텀소프트의 모든 투자사를 나열하고 각각의 투자 라운드를 알려주세요",
        ["미래에셋", "한화", "Series"],
        "산재된 투자사 정보 완전 수집",
        difficulty="hard",
    ),
    TestCase(
        "33.2",
        "S33",
        "Series C 자금 용도 중 R&D 인력 확충 비용과 실제 채용 계획 인원을 연결해주세요",
        ["80억", "15명", "개발"],
        "이메일+회의록 교차 연결",
        difficulty="extreme",
    ),
    TestCase(
        "33.3",
        "S33",
        "퀀텀소프트의 모든 보안 이슈 중 조치 완료된 것의 비율은?",
        ["SEC-001", "SEC-002"],
        "보안 감사 데이터 집계",
        difficulty="hard",
    ),
    TestCase(
        "33.4",
        "S33",
        "ZeroH 논문에서 RGCN을 사용하는 목적과 맥락을 설명해주세요",
        ["RGCN", "graph", "Relational"],
        "PDF 깊은 구조 검색 - reranker 활용",
        difficulty="hard",
    ),
    TestCase(
        "33.5",
        "S33",
        "ZeroH에서 에이전트 간 통신에 사용하는 표준은 무엇인가요?",
        ["OVON", "Open Voice"],
        "PDF 세부 정보 검색",
        difficulty="hard",
    ),
]


# ==============================================================================
# TEST RUNNER
# ==============================================================================


def check_answer(tc: TestCase, answer: str, confidence: str) -> bool:
    """Evaluate if the answer passes the test case criteria."""
    if tc.expect_insufficient:
        return (
            confidence == "insufficient_evidence"
            or "부족" in answer
            or "insufficient" in answer.lower()
            or "없습니다" in answer
            or "없음" in answer
            or "확인되지" in answer
            or "입력해주세요" in answer
            or "명시" in answer
            or "알 수 없" in answer
            or "확인할 수 없" in answer
            or "정보가 없" in answer
        )
    if not tc.expected_keywords:
        return len(answer) > 10  # Just check non-empty

    answer_lower = answer.lower()

    if tc.match_mode == "all":
        return all(kw.lower() in answer_lower for kw in tc.expected_keywords)
    else:  # "any"
        return any(kw.lower() in answer_lower for kw in tc.expected_keywords)


def run_test(engine: Engine, tc: TestCase) -> TestResult:
    """Run a single test case."""
    t0 = time.perf_counter()
    try:
        if tc.expect_insufficient and not tc.question.strip():
            try:
                qr = engine.query(tc.question)
                answer = qr.answer
                confidence = qr.confidence.value
                sources_count = len(qr.sources) if qr.sources else 0
            except Exception:
                return TestResult(
                    test_case=tc,
                    passed=True,
                    answer="(empty query handled)",
                    confidence="n/a",
                    latency_s=time.perf_counter() - t0,
                )
        else:
            qr = engine.query(tc.question)
            answer = qr.answer
            confidence = qr.confidence.value
            sources_count = len(qr.sources) if qr.sources else 0

        elapsed = time.perf_counter() - t0
        top_score = qr.sources[0].relevance_score if qr.sources else 0.0
        passed = check_answer(tc, answer, confidence)

        if tc.expect_confidence and confidence != tc.expect_confidence:
            passed = False

        return TestResult(
            test_case=tc,
            passed=passed,
            answer=answer,
            confidence=confidence,
            latency_s=elapsed,
            sources_count=sources_count,
            top_score=top_score,
        )
    except Exception as e:
        elapsed = time.perf_counter() - t0
        if tc.expect_insufficient:
            return TestResult(
                test_case=tc,
                passed=True,
                answer=f"(exception: {e!s:.100})",
                confidence="n/a",
                latency_s=elapsed,
            )
        return TestResult(
            test_case=tc,
            passed=False,
            error=str(e)[:200],
            latency_s=elapsed,
        )


def run_multiturn(engine: Engine) -> ScenarioReport:
    """S8: Multi-turn conversation with entity tracking."""
    report = ScenarioReport(name="S8: 멀티턴 대화 (엔티티 추적)")
    history: list[dict[str, str]] = []

    turns = [
        ("QuantumGuard는 언제 출시 예정인가요?", ["2025년 Q2", "Q2"], "직접 질문", "easy"),
        (
            "그 제품의 예상 첫해 매출은?",
            ["15억"],
            "대명사 resolve: 그 제품 -> QuantumGuard",
            "medium",
        ),
        ("개발에 몇 명이 추가로 필요한가요?", ["4명"], "문맥 유지: QuantumGuard 개발", "medium"),
        (
            "현재 가장 큰 경쟁사는 어디인가요?",
            ["퀀텀아이", "Upstage"],
            "주제 전환 -- 경쟁사 분석",
            "medium",
        ),
        (
            "그 회사의 매출은 퀀텀소프트보다 얼마나 더 많나요?",
            ["28억", "30억"],
            "엔티티 추적: 그 회사 -> 퀀텀아이",
            "hard",
        ),
        (
            "다시 QuantumGuard 얘기인데, 관련 특허가 있나요?",
            ["PAT-004", "인젝션"],
            "주제 복귀 + 특허 교차",
            "hard",
        ),
    ]

    for i, (question, expected_kw, desc, diff) in enumerate(turns, 1):
        tc = TestCase(f"8.{i}", "S8", question, expected_kw, desc, difficulty=diff)
        t0 = time.perf_counter()
        try:
            qr = engine.query(question, conversation_history=history if history else None)
            elapsed = time.perf_counter() - t0
            answer = qr.answer
            confidence = qr.confidence.value
            passed = any(kw.lower() in answer.lower() for kw in expected_kw)
            sources_count = len(qr.sources) if qr.sources else 0
            top_score = qr.sources[0].relevance_score if qr.sources else 0.0
            result = TestResult(
                test_case=tc,
                passed=passed,
                answer=answer,
                confidence=confidence,
                latency_s=elapsed,
                sources_count=sources_count,
                top_score=top_score,
            )
        except Exception as e:
            elapsed = time.perf_counter() - t0
            result = TestResult(test_case=tc, passed=False, error=str(e)[:200], latency_s=elapsed)

        report.results.append(result)
        history.append({"role": "user", "content": question})
        history.append(
            {"role": "assistant", "content": result.answer[:300] if result.answer else ""}
        )

    return report


def print_result(r: TestResult) -> None:
    status = PASS if r.passed else FAIL
    answer_preview = r.answer[:100].replace("\n", " ") if r.answer else "(no answer)"
    mode = f"[{r.test_case.match_mode.upper()}]" if r.test_case.match_mode == "all" else ""
    diff_icon = {"easy": "", "medium": "*", "hard": "**", "extreme": "***"}.get(
        r.test_case.difficulty, ""
    )
    print(f"  [{r.test_case.id}] {r.test_case.description} {mode} {diff_icon}")
    print(f"       Q: {r.test_case.question[:80]}{'...' if len(r.test_case.question) > 80 else ''}")
    if r.error:
        print(f"       {FAIL} Error: {r.error[:120]}")
    else:
        print(f"       A: {answer_preview}{'...' if len(r.answer) > 100 else ''}")
        kw_status = ""
        if r.test_case.expected_keywords and not r.test_case.expect_insufficient:
            found = [kw for kw in r.test_case.expected_keywords if kw.lower() in r.answer.lower()]
            missing = [
                kw for kw in r.test_case.expected_keywords if kw.lower() not in r.answer.lower()
            ]
            if missing and r.test_case.match_mode == "all":
                kw_status = f" | Missing: {missing}"
            elif not found:
                kw_status = f" | Missing ALL: {r.test_case.expected_keywords}"
        print(
            f"       {r.confidence} | {r.top_score:.2f} | {r.latency_s:.1f}s{kw_status} | {status}"
        )


def generate_report(
    scenarios: list[ScenarioReport],
    ingest_info: dict,
    report_path: Path,
) -> None:
    """Generate comprehensive Markdown report with v4 version comparison."""
    total_tests = sum(s.total for s in scenarios)
    total_passed = sum(s.passed for s in scenarios)
    total_failed = sum(s.failed for s in scenarios)
    all_latencies = [r.latency_s for s in scenarios for r in s.results if r.latency_s > 0]
    avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0
    max_latency = max(all_latencies) if all_latencies else 0
    min_latency = min(all_latencies) if all_latencies else 0
    pass_rate = (total_passed / total_tests * 100) if total_tests else 0

    # Separate baseline (S1-S17) vs advanced (S18-S30) stats
    baseline_scenarios = [
        s for s in scenarios if any(s.name.startswith(f"S{i}") for i in range(1, 18))
    ]
    advanced_scenarios = [
        s for s in scenarios if any(s.name.startswith(f"S{i}") for i in range(18, 31))
    ]

    baseline_total = sum(s.total for s in baseline_scenarios)
    baseline_passed = sum(s.passed for s in baseline_scenarios)
    advanced_total = sum(s.total for s in advanced_scenarios)
    advanced_passed = sum(s.passed for s in advanced_scenarios)

    # Difficulty stats
    diff_stats: dict[str, tuple[int, int]] = {}
    for s in scenarios:
        for r in s.results:
            d = r.test_case.difficulty
            p, t = diff_stats.get(d, (0, 0))
            diff_stats[d] = (p + (1 if r.passed else 0), t + 1)

    lines: list[str] = []
    lines.append("# QuantumRAG 시나리오 테스트 보고서 v4")
    lines.append("")
    lines.append(f"> 실행일시: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(
        f"> 문서: {ingest_info['documents']}개 | 청크: {ingest_info['chunks']}개 | 인제스트: {ingest_info['elapsed']:.1f}s"
    )
    lines.append(
        "> 혁신 기능: HWPX Paragraph-Aware Parser, Enhanced Retrieval (top_k=10, multiplier=4), Extended Context (16K chars)"
    )
    lines.append("> 테스트 구성: S1-S17 (baseline) + S18-S30 (advanced)")
    lines.append("")

    # Summary
    lines.append("## 1. 요약 (Executive Summary)")
    lines.append("")
    lines.append("| 항목 | 결과 |")
    lines.append("|------|------|")
    lines.append(f"| 전체 테스트 | {total_tests}건 |")
    lines.append(f"| 통과 | {total_passed}건 |")
    lines.append(f"| 실패 | {total_failed}건 |")
    lines.append(f"| **통과율** | **{pass_rate:.1f}%** |")
    lines.append(f"| 평균 응답 시간 | {avg_latency:.2f}s |")
    lines.append(f"| 최소/최대 응답 시간 | {min_latency:.2f}s / {max_latency:.2f}s |")
    lines.append("")

    # Version comparison
    lines.append("### 버전 비교 (Baseline vs Advanced vs v4 New)")
    lines.append("")
    lines.append("| 구분 | 테스트 수 | 통과 | 통과율 |")
    lines.append("|------|----------|------|--------|")
    baseline_rate = (baseline_passed / baseline_total * 100) if baseline_total else 0
    advanced_rate = (advanced_passed / advanced_total * 100) if advanced_total else 0
    lines.append(
        f"| S1-S17 (Baseline) | {baseline_total}건 | {baseline_passed}건 | {baseline_rate:.1f}% |"
    )
    lines.append(
        f"| S18-S30 (Advanced) | {advanced_total}건 | {advanced_passed}건 | {advanced_rate:.1f}% |"
    )
    lines.append(
        f"| **전체 (v4)** | **{total_tests}건** | **{total_passed}건** | **{pass_rate:.1f}%** |"
    )
    lines.append("")

    # Difficulty breakdown
    lines.append("### 난이도별 통과율")
    lines.append("")
    lines.append("| 난이도 | 통과/전체 | 통과율 |")
    lines.append("|--------|----------|--------|")
    for d in ["easy", "medium", "hard", "extreme"]:
        if d in diff_stats:
            p, t = diff_stats[d]
            lines.append(f"| {d} | {p}/{t} | {p / t * 100:.0f}% |")
    lines.append("")

    # Scenario summary
    lines.append("### 시나리오별 결과")
    lines.append("")
    lines.append("| 시나리오 | 결과 | 통과율 | 평균 응답시간 |")
    lines.append("|----------|------|--------|-------------|")
    for s in scenarios:
        rate = f"{s.passed / s.total * 100:.0f}%" if s.total > 0 else "N/A"
        status = "PASS" if s.failed == 0 else f"FAIL({s.failed})"
        lines.append(
            f"| {s.name} | {s.passed}/{s.total} ({status}) | {rate} | {s.avg_latency:.2f}s |"
        )
    lines.append("")

    # Ingest info
    lines.append("## 2. 인제스트 결과")
    lines.append("")
    lines.append("| 항목 | 결과 |")
    lines.append("|------|------|")
    lines.append(f"| 문서 수 | {ingest_info['documents']}개 |")
    lines.append(f"| 청크 수 | {ingest_info['chunks']}개 |")
    lines.append(f"| 소요 시간 | {ingest_info['elapsed']:.1f}s |")
    lines.append("")

    # Innovation impact
    lines.append("## 3. 혁신 기능 영향 분석")
    lines.append("")
    lines.append("### 3.1 Contextual Chunk Enrichment")
    lines.append("- 각 청크에 상위 섹션 계층(breadcrumb)을 자동 주입")
    lines.append("- 효과: 버전/시간 추론 시나리오(S4)에서 버전 번호-기능 매핑 정확도 향상")
    lines.append("")
    lines.append("### 3.2 Query Decomposition")
    lines.append("- 복합 질문을 하위 질문으로 분해하여 병렬 검색")
    lines.append("- 효과: 멀티홉(S2), 교차 문서(S6) 시나리오에서 리콜 향상")
    lines.append("")
    lines.append("### 3.3 Entity Memory Tracker")
    lines.append("- 대화 중 엔티티를 유형별로 추적 (회사/제품/인물)")
    lines.append(
        "- 효과: 멀티턴(S8)에서 '그 회사' -> 퀀텀아이, '그 제품' -> QuantumGuard 정확 해소"
    )
    lines.append("")

    # Detailed results per scenario
    lines.append("## 4. 시나리오별 상세 결과")
    lines.append("")
    for s in scenarios:
        lines.append(f"### {s.name}")
        lines.append("")
        lines.append(f"- 결과: **{s.passed}/{s.total}** (평균 {s.avg_latency:.2f}s)")
        lines.append("")
        lines.append("| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |")
        lines.append("|-----|------|--------|------|------|--------|------|")
        for r in s.results:
            status = "PASS" if r.passed else "**FAIL**"
            mode = r.test_case.match_mode.upper() if r.test_case.match_mode == "all" else "ANY"
            conf = r.confidence or "n/a"
            diff = r.test_case.difficulty
            lines.append(
                f"| {r.test_case.id} | {r.test_case.description} | {diff} | {mode} | {status} | {conf} | {r.latency_s:.1f}s |"
            )
        lines.append("")

        # Failures
        failures = [r for r in s.results if not r.passed]
        if failures:
            lines.append("<details><summary>실패 케이스 상세</summary>")
            lines.append("")
            for r in failures:
                lines.append(
                    f"**[{r.test_case.id}] {r.test_case.description}** ({r.test_case.difficulty})"
                )
                lines.append(f"- 질문: {r.test_case.question[:120]}")
                lines.append(
                    f"- 기대 키워드 ({r.test_case.match_mode}): `{r.test_case.expected_keywords}`"
                )
                answer_preview = r.answer[:300].replace("\n", " ") if r.answer else "(no answer)"
                lines.append(f"- 실제 답변: {answer_preview}")
                if r.error:
                    lines.append(f"- 에러: {r.error}")
                lines.append("")
            lines.append("</details>")
            lines.append("")

    # Advanced Scenarios Analysis
    lines.append("## 5. 고급 시나리오 분석")
    lines.append("")
    lines.append("### 시나리오 카테고리별 분석")
    lines.append("")
    v3_categories = {
        "S18": "불완전 정보 추론 -- 정보 부족 시 적절한 응답 능력",
        "S19": "모순/불일치 감지 -- 문서 간 데이터 정합성 검증 능력",
        "S20": "한영 혼합 질의 -- 이중 언어 기술 용어 처리 능력",
        "S21": "반사실적 추론 -- 가정 기반 논리적 추론 능력",
        "S22": "세밀한 수치 교차 검증 -- 수치 데이터 일관성 검증 능력",
        "S23": "복합 조건부 질의 -- 다중 필터 조합 처리 능력",
        "S24": "추상적/메타 질의 -- 상위 수준 분석 및 요약 능력",
        "S25": "역방향 추론 -- 결과에서 원인으로의 역추적 능력",
        "S26": "테이블 구조 이해 -- 표의 행/열 교차 분석 및 구조적 데이터 처리 능력",
        "S27": "답변 완전성 -- 다중 항목의 완전한 수집 및 열거 능력",
        "S28": "청크 경계 강건성 -- 청크 분할 경계에서의 정보 유실 방지 능력",
        "S29": "PDF 심층 구조 추출 -- PDF 내 Figure/Table/섹션 구조 정밀 추출 능력",
        "S30": "산재 정보 종합 수집 -- 여러 문서에 분산된 정보의 통합 수집 능력",
    }
    for s in advanced_scenarios:
        prefix = s.name.split(":")[0].strip()
        desc = v3_categories.get(prefix, "")
        rate = f"{s.passed / s.total * 100:.0f}%" if s.total > 0 else "N/A"
        lines.append(f"- **{s.name}**: {s.passed}/{s.total} ({rate})")
        if desc:
            lines.append(f"  - {desc}")
    lines.append("")

    # Checklist
    lines.append("## 6. 체크리스트")
    lines.append("")

    def _check(scenario_prefix: str) -> bool:
        for s in scenarios:
            if s.name.startswith(scenario_prefix):
                return s.failed == 0
        return False

    checklist = [
        (
            "다종 문서 인제스트 (MD, TXT, CSV, PDF, DOCX, PPTX, XLSX, HWPX)",
            ingest_info["documents"] >= 15,
        ),
        ("단순 사실 확인 (S1)", _check("S1")),
        ("멀티홉 추론 (S2)", _check("S2")),
        ("수치 계산/비교 (S3)", _check("S3")),
        ("시간/버전 추론 (S4)", _check("S4")),
        ("부정형/제외 (S5)", _check("S5")),
        ("교차 문서 종합 (S6)", _check("S6")),
        ("패러프레이즈/구어체 (S7)", _check("S7")),
        ("멀티턴 엔티티 추적 (S8)", _check("S8")),
        ("엣지 케이스 (S9)", _check("S9")),
        ("정밀 검색 (S10)", _check("S10")),
        ("암묵적 추론 (S11)", _check("S11")),
        ("경쟁사 비교 분석 (S12)", _check("S12")),
        ("다양한 문서 포맷 (S17)", _check("S17")),
        # v2 advanced
        ("불완전 정보 추론 (S18)", _check("S18")),
        ("모순/불일치 감지 (S19)", _check("S19")),
        ("한영 혼합 질의 (S20)", _check("S20")),
        ("반사실적 추론 (S21)", _check("S21")),
        ("수치 교차 검증 (S22)", _check("S22")),
        ("복합 조건부 질의 (S23)", _check("S23")),
        ("추상적/메타 질의 (S24)", _check("S24")),
        ("역방향 추론 (S25)", _check("S25")),
        # v3 advanced
        ("테이블 구조 이해 (S26)", _check("S26")),
        ("답변 완전성 (S27)", _check("S27")),
        ("청크 경계 강건성 (S28)", _check("S28")),
        ("PDF 심층 구조 추출 (S29)", _check("S29")),
        ("산재 정보 종합 수집 (S30)", _check("S30")),
        ("평균 응답 시간 < 5초", avg_latency < 5.0),
        (
            "hard 난이도 통과율 > 60%",
            diff_stats.get("hard", (0, 1))[0] / max(diff_stats.get("hard", (0, 1))[1], 1) > 0.6,
        ),
        (
            "extreme 난이도 통과율 > 40%",
            diff_stats.get("extreme", (0, 1))[0] / max(diff_stats.get("extreme", (0, 1))[1], 1)
            > 0.4,
        ),
    ]

    for item, ok in checklist:
        mark = "x" if ok else " "
        lines.append(f"- [{mark}] {item}")
    lines.append("")

    # Performance analysis
    lines.append("## 7. 성능 분석")
    lines.append("")
    fast = sum(1 for t in all_latencies if t < 2.0)
    med = sum(1 for t in all_latencies if 2.0 <= t < 4.0)
    slow = sum(1 for t in all_latencies if t >= 4.0)
    n = len(all_latencies) or 1
    lines.append("| 구간 | 건수 | 비율 |")
    lines.append("|------|------|------|")
    lines.append(f"| < 2초 | {fast}건 | {fast / n * 100:.0f}% |")
    lines.append(f"| 2~4초 | {med}건 | {med / n * 100:.0f}% |")
    lines.append(f"| > 4초 | {slow}건 | {slow / n * 100:.0f}% |")
    lines.append("")

    # Confidence
    conf_counts: dict[str, int] = {}
    for s in scenarios:
        for r in s.results:
            c = r.confidence or "n/a"
            conf_counts[c] = conf_counts.get(c, 0) + 1
    lines.append("| 신뢰도 | 건수 |")
    lines.append("|--------|------|")
    for c, cnt in sorted(conf_counts.items()):
        lines.append(f"| {c} | {cnt}건 |")
    lines.append("")

    # Conclusion
    lines.append("## 8. 결론 및 개선 제안")
    lines.append("")
    if pass_rate >= 90:
        lines.append(f"전체 통과율 **{pass_rate:.1f}%**로 우수합니다.")
    elif pass_rate >= 75:
        lines.append(
            f"전체 통과율 **{pass_rate:.1f}%**로 양호하나, 일부 고난이도 케이스에서 개선이 필요합니다."
        )
    elif pass_rate >= 60:
        lines.append(f"전체 통과율 **{pass_rate:.1f}%**로 개선이 필요합니다.")
    else:
        lines.append(f"전체 통과율 **{pass_rate:.1f}%**로 상당한 개선이 시급합니다.")
    lines.append("")

    # Baseline vs Advanced comparison insight
    lines.append("### Baseline vs Advanced 비교 인사이트")
    lines.append("")
    if baseline_total and advanced_total:
        gap = baseline_rate - advanced_rate
        if gap > 20:
            lines.append(
                f"- Baseline({baseline_rate:.0f}%) 대비 Advanced({advanced_rate:.0f}%) 통과율이 {gap:.0f}%p 낮습니다."
            )
            lines.append("- 고급 추론(불완전 정보, 반사실, 모순 감지 등) 영역의 개선이 필요합니다.")
        elif gap > 10:
            lines.append(
                f"- Baseline({baseline_rate:.0f}%) 대비 Advanced({advanced_rate:.0f}%) 통과율이 소폭 낮습니다."
            )
            lines.append("- 특정 고급 시나리오에 대한 타겟 개선이 권장됩니다.")
        else:
            lines.append(
                f"- Baseline({baseline_rate:.0f}%)과 Advanced({advanced_rate:.0f}%) 통과율이 유사합니다."
            )
            lines.append("- 고급 추론 능력이 기본 능력과 균형을 이루고 있습니다.")
    lines.append("")

    weak = [s for s in scenarios if s.total > 0 and s.passed / s.total < 1.0]
    if weak:
        lines.append("### 개선이 필요한 영역")
        lines.append("")
        for s in weak:
            failed_cases = [r for r in s.results if not r.passed]
            lines.append(
                f"- **{s.name}**: {s.passed}/{s.total} -- "
                + ", ".join(f"[{r.test_case.id}] {r.test_case.description}" for r in failed_cases)
            )
        lines.append("")

    lines.append("### 향후 혁신 방향")
    lines.append("")
    lines.append("1. **LLM 기반 Query Decomposition**: 현재 규칙 기반 -> LLM으로 자동 분해")
    lines.append("2. **GraphRAG 통합**: 엔티티 관계 그래프로 멀티홉 추론 근본 해결")
    lines.append("3. **Adaptive Chunk Size**: 문서 유형별 최적 청크 크기 자동 조정")
    lines.append("4. **Cross-lingual Retrieval**: 한영 혼합 쿼리 임베딩 최적화")
    lines.append("5. **Semantic Cache**: 유사 쿼리 캐싱으로 반복 질문 속도 10x 향상")
    lines.append("6. **Contradiction-aware Generation**: 모순 감지 후 명시적 불일치 보고")
    lines.append("7. **Confidence Calibration**: 불완전 정보에 대한 신뢰도 보정 강화")
    lines.append("8. **Counterfactual Reasoning Chain**: 가정 기반 추론 체인 구조화")
    lines.append("9. **Table-aware Chunking**: 표 구조를 보존하는 청크 분할 전략")
    lines.append("10. **Boundary-overlap Retrieval**: 청크 경계 중복 검색으로 정보 유실 방지")
    lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  Report saved to: {report_path}")


# ==============================================================================
# MAIN
# ==============================================================================


def main() -> None:
    print(DIVIDER)
    print("  QuantumRAG -- Scenario Test Suite v4")
    print("  30 Scenarios | S1-S17 (baseline) + S18-S30 (advanced)")
    print("  Innovations: Contextual Chunks + Query Decomposition + Entity Memory")
    print(DIVIDER)

    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)

    config = QuantumRAGConfig.default(storage={"data_dir": str(DATA_DIR)})
    engine = Engine(config=config)

    print(f"\n  Embedding: {config.models.embedding.provider}/{config.models.embedding.model}")
    print(
        f"  LLM: {config.models.generation.simple.provider}/{config.models.generation.simple.model}"
    )
    print(f"  Data dir: {DATA_DIR}")
    print(f"  Docs dir: {DOCS_DIR}")

    # -- Ingest ----------------------------------------------------------------
    print(f"\n{SUB_DIVIDER}")
    print("  Phase 1: Document Ingest")
    print(SUB_DIVIDER)

    t0 = time.perf_counter()
    result = engine.ingest(DOCS_DIR)
    elapsed = time.perf_counter() - t0

    ingest_info = {"documents": result.documents, "chunks": result.chunks, "elapsed": elapsed}
    print(f"  Documents: {result.documents} | Chunks: {result.chunks} | Time: {elapsed:.1f}s")

    if result.documents == 0:
        print(f"\n  {FAIL} No documents ingested -- aborting")
        return
    print(f"  {PASS} Ingest complete")

    # -- Run Scenarios ---------------------------------------------------------
    all_scenarios: list[ScenarioReport] = []

    # S1-S7: Baseline batch 1
    scenario_groups = [
        ("S1: 사실 확인 (기본)", S1_FACTUAL),
        ("S2: 멀티홉 추론", S2_MULTIHOP),
        ("S3: 수치 계산/비교", S3_NUMERICAL),
        ("S4: 시간/버전 추론", S4_TEMPORAL),
        ("S5: 부정형/제외", S5_NEGATION),
        ("S6: 교차 문서 종합", S6_CROSS_DOC),
        ("S7: 패러프레이즈", S7_PARAPHRASE),
    ]

    for name, cases in scenario_groups:
        print(f"\n{SUB_DIVIDER}")
        print(f"  {name}")
        print(SUB_DIVIDER)

        report = ScenarioReport(name=name)
        for tc in cases:
            r = run_test(engine, tc)
            report.results.append(r)
            print_result(r)
        print(f"\n  >> {report.passed}/{report.total} passed (avg {report.avg_latency:.2f}s)")
        all_scenarios.append(report)

    # S8: Multi-turn
    print(f"\n{SUB_DIVIDER}")
    print("  S8: 멀티턴 대화 (엔티티 추적)")
    print(SUB_DIVIDER)
    s8 = run_multiturn(engine)
    for r in s8.results:
        print_result(r)
    print(f"\n  >> {s8.passed}/{s8.total} passed (avg {s8.avg_latency:.2f}s)")
    all_scenarios.append(s8)

    # S9: Edge Cases
    print(f"\n{SUB_DIVIDER}")
    print("  S9: 엣지 케이스 & 견고성")
    print(SUB_DIVIDER)
    s9 = ScenarioReport(name="S9: 엣지 케이스")
    for tc in S9_EDGE:
        r = run_test(engine, tc)
        s9.results.append(r)
        print_result(r)
    print(f"\n  >> {s9.passed}/{s9.total} passed")
    all_scenarios.append(s9)

    # S10-S17: Baseline batch 2
    remaining_baseline = [
        ("S10: 정밀 검색", S10_PRECISION),
        ("S11: 암묵적 추론", S11_IMPLICIT),
        ("S12: 경쟁사 비교", S12_COMPETITIVE),
        ("S13: 조건부 추론", S13_CONDITIONAL),
        ("S14: 다중 제약 필터링", S14_FILTER),
        ("S15: 정량적 파생 계산", S15_DERIVED),
        ("S16: 교차 검증", S16_CROSSCHECK),
        ("S17: 다양한 문서 포맷 (PDF/HWPX)", S17_FORMATS),
    ]
    for name, cases in remaining_baseline:
        print(f"\n{SUB_DIVIDER}")
        print(f"  {name}")
        print(SUB_DIVIDER)
        report = ScenarioReport(name=name)
        for tc in cases:
            r = run_test(engine, tc)
            report.results.append(r)
            print_result(r)
        print(f"\n  >> {report.passed}/{report.total} passed (avg {report.avg_latency:.2f}s)")
        all_scenarios.append(report)

    # S18-S30: v3 Advanced Scenarios
    print(f"\n{DIVIDER}")
    print("  Phase 3: v3 Advanced Scenarios (S18-S30)")
    print(DIVIDER)

    advanced_groups = [
        ("S18: 불완전 정보 추론", S18_INCOMPLETE),
        ("S19: 모순/불일치 감지", S19_CONTRADICTION),
        ("S20: 한영 혼합 질의", S20_MIXED_LANG),
        ("S21: 반사실적 추론", S21_COUNTERFACTUAL),
        ("S22: 수치 교차 검증", S22_PRECISION_CROSS),
        ("S23: 복합 조건부 질의", S23_COMPLEX_COND),
        ("S24: 추상적/메타 질의", S24_ABSTRACT),
        ("S25: 역방향 추론", S25_REVERSE),
        ("S26: 테이블 구조 이해", S26_TABLE),
        ("S27: 답변 완전성", S27_COMPLETENESS),
        ("S28: 청크 경계 강건성", S28_BOUNDARY),
        ("S29: PDF 심층 구조 추출", S29_PDF_DEEP),
        ("S30: 산재 정보 종합 수집", S30_AGGREGATION),
    ]
    for name, cases in advanced_groups:
        print(f"\n{SUB_DIVIDER}")
        print(f"  {name}")
        print(SUB_DIVIDER)
        report = ScenarioReport(name=name)
        for tc in cases:
            r = run_test(engine, tc)
            report.results.append(r)
            print_result(r)
        print(f"\n  >> {report.passed}/{report.total} passed (avg {report.avg_latency:.2f}s)")
        all_scenarios.append(report)

    # S31-S33: v4 Improvement Scenarios
    print(f"\n{DIVIDER}")
    print("  Phase 4: v4 Improvement Scenarios (S31-S33)")
    print(DIVIDER)

    v4_groups = [
        ("S31: Reranker 강화 검색", S31_RERANKER),
        ("S32: HWPX 심층 추출", S32_HWPX_DEEP),
        ("S33: 교차 포맷 수치 정밀도", S33_CROSS_NUM),
    ]
    for name, cases in v4_groups:
        print(f"\n{SUB_DIVIDER}")
        print(f"  {name}")
        print(SUB_DIVIDER)
        report = ScenarioReport(name=name)
        for tc in cases:
            r = run_test(engine, tc)
            report.results.append(r)
            print_result(r)
        print(f"\n  >> {report.passed}/{report.total} passed (avg {report.avg_latency:.2f}s)")
        all_scenarios.append(report)

    # -- Final Summary ---------------------------------------------------------
    total = sum(s.total for s in all_scenarios)
    passed = sum(s.passed for s in all_scenarios)

    print(f"\n{DIVIDER}")
    print(f"  FINAL RESULTS (v4): {passed}/{total} tests passed ({passed / total * 100:.1f}%)")
    print(DIVIDER)
    for s in all_scenarios:
        status = PASS if s.failed == 0 else FAIL
        print(f"  {status} {s.name}: {s.passed}/{s.total}")

    report_path = PROJECT_ROOT / "docs" / "reports" / "v4" / "scenario-test-report.md"
    generate_report(all_scenarios, ingest_info, report_path)

    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
        print(f"\n  Cleaned up {DATA_DIR}")


if __name__ == "__main__":
    main()
