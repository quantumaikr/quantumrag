"""Structured Fact Extraction — extract key-value facts from chunks at ingest.

For each chunk, extracts structured facts (entities, attributes, relationships)
and stores them in chunk.metadata["facts"]. These facts enable:
1. Metadata-filtered retrieval (severity=Critical AND status=완료)
2. Entity-based reverse indexing (Level 4)
3. Derived term generation boost

Uses lightweight rule-based extraction (no LLM cost) with domain-specific
patterns for security, finance, HR, product, patent, and contract domains.
"""

from __future__ import annotations

import re
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk

logger = get_logger("quantumrag.fact_extractor")

# ── Domain detection ────────────────────────────────────────────────────────

_DOMAIN_PATTERNS: dict[str, re.Pattern[str]] = {
    "security": re.compile(
        r"SEC-\d{3}|보안\s*감사|취약점|보안\s*이슈|CORS|SQL\s*Injection|CVE-",
        re.IGNORECASE,
    ),
    "finance": re.compile(
        r"매출|비용|예산|투자|ARR|런웨이|소진율|현금|파이프라인|Series\s*[A-D]",
    ),
    "hr": re.compile(
        r"인원|팀장|부서|채용|조직|헤드카운트|직급",
    ),
    "product": re.compile(
        r"v\d+\.\d+|릴리스|버전|변경\s*이력|changelog|신기능|버그\s*수정",
        re.IGNORECASE,
    ),
    "patent": re.compile(
        r"PAT-\d{3}|특허|발명자|출원|등록|PCT|IP\s*현황",
    ),
    "contract": re.compile(
        r"고객사|계약|PoC|Enterprise|Pro|온프레미스|클라우드|월\s*매출",
    ),
}


def detect_domains(text: str) -> list[str]:
    """Detect which domains are present in the text."""
    return [
        domain
        for domain, pattern in _DOMAIN_PATTERNS.items()
        if pattern.search(text)
    ]


# ── Security fact extraction ────────────────────────────────────────────────

_SEC_ID_PATTERN = re.compile(r"\[?(SEC-\d{3})\]?")
_SEVERITY_PATTERN = re.compile(
    r"(Critical|High|Medium|Low|심각|높음|중간|낮음|보통)",
    re.IGNORECASE,
)
_STATUS_EXTRACT = re.compile(
    r"(?:조치\s*상태|상태)\s*[:：]?\s*"
    r"(?:(\d{4}[-./]\d{1,2}[-./]\d{1,2})\s*)?"
    r"(완료|미조치|진행\s*중|진행중|예정|보류)",
)

_SEVERITY_MAP = {
    "critical": "Critical",
    "심각": "Critical",
    "high": "High",
    "높음": "High",
    "medium": "Medium",
    "중간": "Medium",
    "보통": "Medium",
    "low": "Low",
    "낮음": "Low",
}


def _extract_security_facts(text: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    issue_ids = _SEC_ID_PATTERN.findall(text)
    severities = _SEVERITY_PATTERN.findall(text)
    status_matches = _STATUS_EXTRACT.findall(text)

    # Normalize severity
    norm_severities = []
    for s in severities:
        norm = _SEVERITY_MAP.get(s.lower(), s)
        if norm not in norm_severities:
            norm_severities.append(norm)

    # Extract individual issue facts
    for issue_id in issue_ids:
        fact: dict[str, Any] = {
            "type": "security_issue",
            "entity": issue_id,
        }
        if norm_severities:
            fact["severity"] = norm_severities[0]
        if status_matches:
            date, status = status_matches[0]
            fact["status"] = status.replace(" ", "")
            if date:
                fact["action_date"] = date
        facts.append(fact)

    # If we found severity but no specific IDs, still record
    if not issue_ids and norm_severities:
        facts.append({
            "type": "security_summary",
            "severities": norm_severities,
        })

    return facts


# ── Finance fact extraction ─────────────────────────────────────────────────

_FINANCE_METRIC = re.compile(
    r"(매출|ARR|비용|예산|투자|런웨이|소진율|현금|파이프라인|인건비|인프라|마케팅)"
    r"\s*[:：]?\s*"
    r"(?:약\s*)?(\d+(?:\.\d+)?)\s*(억|천만|백만|만|개월)?\s*(?:원)?"
)

# Fund allocation pattern: "- X: N억원" or "- X: N억원" in lists
_FUND_ALLOCATION = re.compile(
    r"[-·•]\s*(.{2,20}?)\s*[:：]\s*(\d+(?:\.\d+)?)\s*(억|천만|백만|만)\s*(?:원)?",
)

# Section header for fund allocation context
_FUND_SECTION = re.compile(
    r"(?:자금|투자금?|예산)\s*(?:용도|사용|배분|활용|계획)",
)


def _extract_finance_facts(text: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for m in _FINANCE_METRIC.finditer(text):
        metric = m.group(1)
        value = m.group(2)
        unit = m.group(3) or ""
        facts.append({
            "type": "finance_metric",
            "metric": metric,
            "value": f"{value}{unit}",
        })

    # Extract fund allocation items if chunk has allocation section
    if _FUND_SECTION.search(text):
        allocations = _FUND_ALLOCATION.findall(text)
        for item_name, value, unit in allocations:
            facts.append({
                "type": "fund_allocation",
                "item": item_name.strip(),
                "value": f"{value}{unit}",
                "context": "자금 용도",
            })

    return facts


# ── HR fact extraction ──────────────────────────────────────────────────────

_TEAM_PATTERN = re.compile(
    r"([\w가-힣]+팀)\s*[:：|]?\s*"
    r"(?:.*?인원\s*[:：]?\s*)?(\d+)\s*명"
)
_LEADER_PATTERN = re.compile(
    r"([\w가-힣]+팀)\s*.*?팀장\s*[:：]?\s*([\w가-힣]{2,4})"
)


def _extract_hr_facts(text: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for m in _TEAM_PATTERN.finditer(text):
        facts.append({
            "type": "team_info",
            "team": m.group(1),
            "headcount": int(m.group(2)),
        })
    for m in _LEADER_PATTERN.finditer(text):
        facts.append({
            "type": "team_leader",
            "team": m.group(1),
            "leader": m.group(2),
        })
    return facts


# ── Product fact extraction ─────────────────────────────────────────────────

_VERSION_BLOCK = re.compile(
    r"v?(\d+\.\d+(?:\.\d+)?)\s*\((\d{4}[-./]\d{1,2}[-./]\d{1,2})\)"
)


def _extract_product_facts(text: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for m in _VERSION_BLOCK.finditer(text):
        facts.append({
            "type": "product_version",
            "version": f"v{m.group(1)}",
            "release_date": m.group(2),
        })
    return facts


# ── Patent fact extraction ──────────────────────────────────────────────────

_PAT_ID = re.compile(r"\[?(PAT-\d{3})\]?")
_INVENTOR = re.compile(r"발명자\s*[:：]?\s*([\w가-힣,\s]+?)(?:\n|$)")
_PAT_STATUS = re.compile(r"(등록\s*완료|출원\s*완료|출원\s*중|PCT\s*완료|심사\s*중)")


def _extract_patent_facts(text: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    pat_ids = _PAT_ID.findall(text)
    inventors = _INVENTOR.findall(text)
    statuses = _PAT_STATUS.findall(text)

    for pat_id in pat_ids:
        fact: dict[str, Any] = {
            "type": "patent",
            "entity": pat_id,
        }
        if inventors:
            fact["inventors"] = [
                inv.strip() for inv in inventors[0].split(",") if inv.strip()
            ]
        if statuses:
            fact["status"] = statuses[0].replace(" ", "")
        facts.append(fact)
    return facts


# ── Contract/customer fact extraction ───────────────────────────────────────

_CUSTOMER_PATTERN = re.compile(
    r"([\w가-힣]+(?:전자|은행|클라우드|자동차|법무법인\s*[\w가-힣]+|대학교?))\s*"
    r".*?(Enterprise|Pro|Basic|Free)\s*"
    r".*?(온프레미스|클라우드|하이브리드)?"
)


def _extract_contract_facts(text: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for m in _CUSTOMER_PATTERN.finditer(text):
        fact: dict[str, Any] = {
            "type": "customer_contract",
            "customer": m.group(1),
            "tier": m.group(2),
        }
        if m.group(3):
            fact["deployment"] = m.group(3)
        facts.append(fact)
    return facts


# ── Public API ──────────────────────────────────────────────────────────────

_DOMAIN_EXTRACTORS = {
    "security": _extract_security_facts,
    "finance": _extract_finance_facts,
    "hr": _extract_hr_facts,
    "product": _extract_product_facts,
    "patent": _extract_patent_facts,
    "contract": _extract_contract_facts,
}


def extract_facts(chunk: Chunk) -> list[dict[str, Any]]:
    """Extract structured facts from a chunk using rule-based patterns.

    Results are stored in chunk.metadata["facts"].
    """
    text = chunk.content
    domains = detect_domains(text)
    all_facts: list[dict[str, Any]] = []

    for domain in domains:
        extractor = _DOMAIN_EXTRACTORS.get(domain)
        if extractor:
            facts = extractor(text)
            all_facts.extend(facts)

    return all_facts


def extract_facts_for_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Extract and store structured facts for all chunks.

    Facts are stored in chunk.metadata["facts"] for each chunk.
    """
    total_facts = 0
    for chunk in chunks:
        facts = extract_facts(chunk)
        if facts:
            chunk.metadata["facts"] = facts
            total_facts += len(facts)

    if total_facts:
        logger.info(
            "facts_extracted",
            total_facts=total_facts,
            chunks_with_facts=sum(1 for c in chunks if c.metadata.get("facts")),
            total_chunks=len(chunks),
        )

    return chunks
