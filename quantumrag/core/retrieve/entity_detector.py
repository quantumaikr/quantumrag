"""Entity Query Detector — detect entity patterns and attribute filters in queries.

Parses queries like "조치 완료된 High 등급 이상 보안 이슈의 ID를 모두 나열"
into structured lookups: severity_gte=High, status=완료.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.entity_detector")

_SEVERITY_MAP = {
    "critical": "Critical",
    "심각": "Critical",
    "high": "High",
    "높음": "High",
    "medium": "Medium",
    "중간": "Medium",
    "low": "Low",
    "낮음": "Low",
}

# Pattern: "X 등급 이상/이하"
_SEVERITY_RANGE_PATTERN = re.compile(
    r"(Critical|High|Medium|Low|심각|높음|중간|낮음)\s*(?:등급\s*)?이상",
    re.IGNORECASE,
)

# Pattern: status filtering
_STATUS_PATTERN = re.compile(
    r"(?:조치\s*)?(?:완료|미조치|미해결|진행\s*중|진행중|보류)(?:된|인|의)?",
)

# Pattern: entity IDs in query
_ENTITY_ID_PATTERN = re.compile(
    r"(SEC-\d{3}|PAT-\d{3}|v\d+\.\d+)",
    re.IGNORECASE,
)

# Pattern: domain indicators
_DOMAIN_INDICATORS = {
    "security": re.compile(r"보안\s*(?:이슈|감사|사항|취약점)|SEC-", re.IGNORECASE),
    "patent": re.compile(r"특허|발명|출원|PAT-", re.IGNORECASE),
    "product": re.compile(r"버전|릴리스|변경|v\d+", re.IGNORECASE),
    "contract": re.compile(r"고객|계약|PoC|Enterprise", re.IGNORECASE),
}

_STATUS_NORMALIZE = {
    "완료": "완료",
    "조치완료": "완료",
    "조치 완료": "완료",
    "미조치": "미조치",
    "미해결": "미조치",
    "진행중": "진행중",
    "진행 중": "진행중",
    "보류": "보류",
}


@dataclass
class EntityQuery:
    """Structured representation of entity-related query constraints."""

    entity_ids: list[str] = field(default_factory=list)
    severity_gte: str | None = None
    status: str | None = None
    domain: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    fund_allocation: bool = False

    @property
    def has_constraints(self) -> bool:
        return bool(
            self.entity_ids
            or self.severity_gte
            or self.status
            or self.attributes
            or self.fund_allocation
        )


def detect_entity_query(query: str) -> EntityQuery | None:
    """Detect entity patterns and attribute filters in a query.

    Returns EntityQuery if structured constraints are found, None otherwise.
    """
    result = EntityQuery()

    # Detect specific entity IDs
    result.entity_ids = _ENTITY_ID_PATTERN.findall(query)

    # Detect severity range
    sev_match = _SEVERITY_RANGE_PATTERN.search(query)
    if sev_match:
        raw = sev_match.group(1).lower()
        result.severity_gte = _SEVERITY_MAP.get(raw, raw)

    # Detect status filter
    status_match = _STATUS_PATTERN.search(query)
    if status_match:
        raw = status_match.group(0).replace("된", "").replace("인", "").replace("의", "").strip()
        result.status = _STATUS_NORMALIZE.get(raw, raw)

    # Detect fund allocation queries
    if re.search(r"(?:투자금?|자금|예산)\s*.{0,10}(?:용도|사용|배분|활용)", query):
        result.fund_allocation = True

    # Detect domain
    for domain, pattern in _DOMAIN_INDICATORS.items():
        if pattern.search(query):
            result.domain = domain
            break

    if result.has_constraints:
        logger.debug(
            "entity_query_detected",
            entity_ids=result.entity_ids,
            severity_gte=result.severity_gte,
            status=result.status,
            domain=result.domain,
        )
        return result

    return None
