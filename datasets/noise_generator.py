"""Generate synthetic noise documents for scale testing.

Creates diverse domain documents that serve as noise in retrieval tests.
These documents are realistic but unrelated to QA questions, forcing
the retriever to discriminate signal from noise at scale.

Usage:
    .venv/bin/python datasets/noise_generator.py [count]
"""

import sys
from pathlib import Path

DOMAINS = [
    (
        "climate",
        "기후변화와 탄소중립",
        [
            "## 파리기후협약 이행 현황\n\n2015년 파리기후협약은 지구 평균 기온 상승을 산업화 이전 대비 1.5°C 이내로 제한하는 것을 목표로 합니다. 2026년 현재 전 세계 196개국이 참여하고 있으며, 각국은 NDC(국가결정기여)를 통해 온실가스 감축 목표를 제출합니다.\n\n주요 감축 수단:\n- 재생에너지 전환: 태양광, 풍력, 수소\n- 탄소 포집 저장(CCS) 기술\n- 산림 복원 및 탄소 흡수원 확대\n- 탄소세 및 배출권 거래제\n\n한국은 2030년까지 2018년 대비 40% 감축을 목표로 하고 있으나, 석탄발전 비중이 여전히 35%를 차지하고 있어 달성이 쉽지 않은 상황입니다.",
            "## 글로벌 탄소시장 동향\n\nEU ETS(배출권거래제)는 세계 최대 탄소시장으로, 2025년 기준 탄소 가격이 톤당 €85에 달합니다. 한국의 K-ETS는 톤당 ₩25,000 수준으로 EU 대비 현저히 낮습니다.\n\n| 시장 | 가격 (2025) | 거래량 |\n|------|-----------|-------|\n| EU ETS | €85/톤 | 16억톤 |\n| K-ETS | ₩25,000/톤 | 5.9억톤 |\n| 중국 ETS | ¥72/톤 | 23억톤 |\n\n탄소국경조정제도(CBAM)는 2026년 본격 시행되며, 수출 기업의 탄소 비용 부담이 크게 증가할 전망입니다.",
        ],
    ),
    (
        "biotech",
        "바이오테크놀로지 산업 동향",
        [
            "## mRNA 백신 기술의 진화\n\n코로나19 팬데믹을 계기로 mRNA 기술 플랫폼이 급성장했습니다. 모더나와 화이자-바이오엔텍은 mRNA 기반 암 백신, 독감 백신, RSV 백신을 개발 중입니다.\n\nmRNA 기술의 장점:\n- 빠른 개발 속도 (수주 내 설계 가능)\n- 높은 면역 반응 유도\n- 대량 생산 용이\n- 변이 대응 유연성\n\n2026년 글로벌 mRNA 치료제 시장은 $280억 규모로 전망되며, 연평균 12.3% 성장하고 있습니다.",
            "## CRISPR 유전자 편집 상용화\n\nCRISPR-Cas9 기반 유전자 치료제가 2023년 최초로 FDA 승인을 받았습니다. 겸상적혈구병 치료제 Casgevy(Vertex/CRISPR Therapeutics)가 그 주인공입니다.\n\n현재 개발 중인 CRISPR 치료제:\n1. 베타-지중해빈혈 (임상 3상)\n2. 선천성 혈관부종 (임상 2상)\n3. HIV 잠복감염 제거 (임상 1상)\n4. 근이영양증 (전임상)\n\n윤리적 쟁점: 생식세포 편집은 대부분의 국가에서 금지되어 있으나, 체세포 편집은 허용되는 추세입니다.",
        ],
    ),
    (
        "space",
        "우주산업과 위성통신",
        [
            "## 뉴스페이스 산업의 성장\n\n2025년 글로벌 우주 경제 규모는 $5,460억에 달합니다. SpaceX의 재사용 로켓 기술이 발사 비용을 1/10로 낮추면서 상업 우주 시대가 열렸습니다.\n\n주요 플레이어:\n- SpaceX: Starship 개발, Starlink 위성통신 (6,000기 운용)\n- Blue Origin: New Glenn 대형 로켓\n- Rocket Lab: 소형위성 전문 발사체\n- 한화에어로스페이스: 누리호 고체연료 엔진\n\n한국은 2027년까지 독자 위성항법시스템(KPS) 7기 발사를 목표로 하고 있습니다.",
            "## LEO 위성 인터넷 경쟁\n\n저궤도(LEO) 위성 인터넷이 기존 통신 인프라를 보완하고 있습니다.\n\n| 서비스 | 위성 수 | 대역폭 | 지연시간 |\n|--------|---------|--------|--------|\n| Starlink | 6,000+ | 220Mbps | 25ms |\n| OneWeb | 648 | 150Mbps | 32ms |\n| Project Kuiper | 3,236(계획) | 400Mbps | 30ms |\n\nStarlink은 2025년 기준 전 세계 300만 가입자를 확보했으며, 한국에서는 2026년 서비스 개시를 준비 중입니다.",
        ],
    ),
    (
        "quantum",
        "양자컴퓨팅 기술 현황",
        [
            "## 양자 우위 달성 현황\n\nGoogle의 Willow 칩(105큐비트)은 2024년 양자 오류 정정에서 획기적 성과를 거뒀습니다. IBM은 1,121큐비트 Condor 프로세서를 발표했으며, 2025년에는 100,000큐비트 시스템을 목표로 합니다.\n\n양자컴퓨팅 적용 분야:\n- 신약 개발: 분자 시뮬레이션\n- 금융: 포트폴리오 최적화, 리스크 분석\n- 물류: 경로 최적화\n- 암호: 양자내성암호(PQC) 전환\n\n한국은 양자기술 R&D에 2030년까지 3조원을 투자하는 계획을 발표했습니다.",
            "## 양자내성암호(PQC) 표준화\n\nNIST는 2024년 양자내성암호 표준 4종을 최종 발표했습니다:\n\n1. **ML-KEM** (CRYSTALS-Kyber): 키 캡슐화\n2. **ML-DSA** (CRYSTALS-Dilithium): 전자서명\n3. **SLH-DSA** (SPHINCS+): 해시 기반 서명\n4. **FN-DSA** (FALCON): 격자 기반 서명\n\n미국 연방정부는 2035년까지 모든 시스템을 PQC로 전환해야 하며, 한국도 KISA 주도로 전환 로드맵을 수립 중입니다. 금융권은 2028년까지 1차 전환을 완료할 계획입니다.",
        ],
    ),
    (
        "food",
        "식품산업과 대체단백질",
        [
            "## 배양육 산업화 현황\n\n싱가포르에 이어 미국이 2023년 배양육 판매를 승인했습니다. Upside Foods와 GOOD Meat가 레스토랑 납품을 시작했으며, 2026년에는 소매 판매를 목표로 합니다.\n\n배양육 생산 비용 추이:\n- 2013년: $330,000/버거\n- 2020년: $50/버거\n- 2025년: $9/버거\n- 2030년(목표): $2/버거\n\n한국은 식약처에서 배양육 안전성 평가 기준을 마련 중이며, CJ제일제당, 셀미트 등이 연구개발에 참여하고 있습니다.",
            "## 대체단백질 시장 전망\n\n글로벌 대체단백질 시장은 2025년 $142억 규모이며, 2030년 $290억으로 성장할 전망입니다.\n\n| 분류 | 시장규모(2025) | 성장률 |\n|------|-------------|-------|\n| 식물성 단백질 | $98억 | 11.2% |\n| 발효 단백질 | $32억 | 18.5% |\n| 배양육 | $12억 | 25.3% |\n\n한국 시장에서는 비건 라면, 식물성 만두, 대체 참치 등이 편의점과 마트에서 판매되고 있으며, 2025년 국내 대체식품 시장은 2,800억원 규모입니다.",
        ],
    ),
    (
        "edu",
        "교육 기술과 에듀테크",
        [
            "## AI 기반 맞춤형 교육\n\n에듀테크 시장은 2025년 글로벌 $4,040억 규모입니다. AI 튜터, 적응형 학습 플랫폼, VR/AR 교육 콘텐츠가 주요 성장 동력입니다.\n\n한국 에듀테크 기업:\n- 매스프레소(콴다): AI 수학 풀이, MAU 1,200만\n- 뤼이드(산타토익): 적응형 학습, 누적 사용자 500만\n- 클래스101: 온라인 클래스 플랫폼\n- 엘리스: AI 코딩 교육\n\n정부는 2025년부터 초등 3~4학년에 AI 디지털 교과서를 도입하며, 2028년까지 전 학년으로 확대할 계획입니다.",
            "## 마이크로 자격증과 평생학습\n\n전통적 학위 대신 마이크로 자격증(Micro-credential)이 직무 역량 인증 수단으로 부상하고 있습니다.\n\n주요 플랫폼:\n1. Coursera Professional Certificates\n2. Google Career Certificates\n3. AWS Certified Solutions Architect\n4. 한국형 K-MOOC 이수증\n\n2025년 조사에 따르면, 기업 채용 담당자의 68%가 마이크로 자격증을 학위와 동등하게 평가한다고 응답했습니다. 특히 IT, 데이터 분석, 디지털 마케팅 분야에서 인정도가 높습니다.",
        ],
    ),
]


def generate_noise_docs(output_dir: Path, count: int = 50) -> int:
    """Generate diverse noise documents for scale testing."""
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = 0

    for i in range(count):
        domain_idx = i % len(DOMAINS)
        section_idx = i % 2
        domain_key, title, sections = DOMAINS[domain_idx]

        # Vary the content slightly for each document
        suffix = f" (분석 {i + 1})" if i >= len(DOMAINS) * 2 else ""
        doc_title = f"{title}{suffix}"

        content = f"""---
title: "{doc_title}"
lang: ko
domain: noise_{domain_key}
---

# {doc_title}

{sections[section_idx]}

## 추가 분석

이 보고서는 {domain_key} 분야의 최신 동향을 분석한 자료입니다.
주요 데이터는 2025-2026년 기준이며, 향후 전망을 포함합니다.
세부 수치는 각 기관의 공식 발표를 기반으로 합니다.
"""
        filename = f"noise_{i + 1:03d}.md"
        (output_dir / filename).write_text(content, encoding="utf-8")
        generated += 1

    return generated


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    out = Path(__file__).resolve().parent / ".combined" / "noise"
    n = generate_noise_docs(out, count)
    print(f"Generated {n} noise documents in {out}")
