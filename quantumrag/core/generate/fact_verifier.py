"""Fact-based answer verification — detect hallucination by cross-checking.

Complements self_correct.py (which detects *insufficient* answers) by
detecting *wrong* answers.  The key insight: fact_extractor already
produces structured data (customer names, financial metrics, etc.) at
ingest time.  By comparing entities and numbers in the generated answer
against those verified facts we can flag fabricated content that the LLM
confidently states — something self_correct's pattern-matching can never
catch.

Design principles:
- Zero LLM cost: pure rule-based comparison
- Precision over recall: only flag clear contradictions, not ambiguity
- Minimal overhead: O(facts * answer_entities), typically <1 ms
"""

from __future__ import annotations

import re
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.retrieve.fusion import ScoredChunk

logger = get_logger("quantumrag.fact_verifier")

# ── Entity extraction from answer text ──────────────────────────────────────

# Korean company name patterns (common suffixes)
_COMPANY_NAME_RE = re.compile(
    r"([\w가-힣]{2,}(?:전자|은행|텔레콤|자동차|바이오|소프트|클라우드|증권"
    r"|건설|중공업|화학|제약|에너지|물산|생명|화재|카드|캐피탈))"
    r"|"
    r"((?:법무법인|회계법인)\s*[\w가-힣]+)"
    r"|"
    # Well-known Korean companies that don't follow suffix patterns
    r"(네이버|카카오|쿠팡|토스|당근|배달의민족|김앤장|세종|율촌)"
)

# Patterns indicating the entity is described as a customer/client
_CUSTOMER_CONTEXT_RE = re.compile(
    r"(?:고객(?:사)?|계약|등급|월\s*매출|배포\s*방식|도입|사용|Enterprise|Pro|Basic|PoC"
    r"|온프레미스|클라우드|하이브리드)",
)

# Number extraction (Korean monetary amounts)
_AMOUNT_RE = re.compile(
    r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:만\s*)?(?:원|달러|USD)",
)


# ── Core verification ───────────────────────────────────────────────────────


class VerificationResult:
    """Result of fact verification."""

    __slots__ = ("hallucinated_entities", "is_valid", "warnings")

    def __init__(
        self,
        is_valid: bool = True,
        warnings: list[str] | None = None,
        hallucinated_entities: list[str] | None = None,
    ) -> None:
        self.is_valid = is_valid
        self.warnings = warnings or []
        self.hallucinated_entities = hallucinated_entities or []

    def __repr__(self) -> str:
        return f"VerificationResult(valid={self.is_valid}, warnings={len(self.warnings)})"


def _collect_facts_from_chunks(chunks: list[ScoredChunk]) -> list[dict[str, Any]]:
    """Gather all structured facts from retrieved chunks."""
    all_facts: list[dict[str, Any]] = []
    for sc in chunks:
        facts = sc.chunk.metadata.get("facts")
        if facts:
            all_facts.extend(facts)
    return all_facts


def _extract_companies_from_answer(answer: str) -> list[str]:
    """Extract company names mentioned in the answer."""
    companies: list[str] = []
    for m in _COMPANY_NAME_RE.finditer(answer):
        name = m.group(1) or m.group(2) or m.group(3)
        if name and name not in companies:
            companies.append(name)
    return companies


def _is_customer_context(answer: str, company: str) -> bool:
    """Check if a company is described in a customer/contract context."""
    # Find the company in the answer and check surrounding text
    idx = answer.find(company)
    if idx < 0:
        return False
    # Look at ±100 chars around the mention
    window_start = max(0, idx - 100)
    window_end = min(len(answer), idx + len(company) + 100)
    window = answer[window_start:window_end]
    return bool(_CUSTOMER_CONTEXT_RE.search(window))


def verify_against_facts(
    answer: str,
    chunks: list[ScoredChunk],
    query: str = "",
) -> VerificationResult:
    """Verify answer entities/numbers against structured facts from chunks.

    Detects hallucination by checking if the answer mentions entities
    that don't exist in the verified fact index.  Only flags entities
    that appear in a customer/contract context (to avoid false positives
    on casual mentions).

    Args:
        answer: The generated answer text.
        chunks: Retrieved chunks (with metadata["facts"]).
        query: Original query (for context-aware verification).

    Returns:
        VerificationResult with is_valid=False if hallucination detected.
    """
    all_facts = _collect_facts_from_chunks(chunks)
    if not all_facts:
        return VerificationResult()  # No facts to verify against

    warnings: list[str] = []
    hallucinated: list[str] = []

    # ── Customer verification ───────────────────────────────────────────
    customer_facts = [f for f in all_facts if f.get("type") == "customer_contract"]
    if customer_facts:
        known_customers = {f["customer"] for f in customer_facts}
        mentioned_companies = _extract_companies_from_answer(answer)

        # Also collect company names from chunk text to avoid
        # false positives when Fact Index is incomplete
        chunk_text = " ".join(
            sc.chunk.content for sc in chunks if hasattr(sc.chunk, "content")
        ).lower()

        for company in mentioned_companies:
            # Only flag if described as a customer AND not in verified list
            if company not in known_customers and _is_customer_context(answer, company):
                # Fuzzy check: partial match (e.g., "삼성" in "삼성전자")
                if any(company in kc or kc in company for kc in known_customers):
                    continue
                # Also allow if the company name appears in retrieved chunks
                # (Fact Index may be incomplete but chunks contain the data)
                if company.lower() in chunk_text:
                    continue
                warnings.append(
                    f"'{company}'이(가) 고객으로 언급되었으나 "
                    f"검증된 고객 목록({', '.join(sorted(known_customers))})에 없습니다"
                )
                hallucinated.append(company)

    # ── Finance metric verification ─────────────────────────────────────
    finance_facts = [f for f in all_facts if f.get("type") == "finance_metric"]
    if finance_facts:
        fact_values: dict[str, str] = {}
        for f in finance_facts:
            metric = f.get("metric", "")
            value = f.get("value", "")
            if metric and value:
                fact_values[metric] = value

        # Cross-check: if answer mentions a metric with a different value
        for metric, fact_value in fact_values.items():
            if metric in answer:
                # Extract numbers near the metric mention in the answer
                metric_idx = answer.find(metric)
                window = answer[max(0, metric_idx - 50) : metric_idx + len(metric) + 100]
                answer_amounts = _AMOUNT_RE.findall(window)
                fact_amounts = _AMOUNT_RE.findall(fact_value)
                if answer_amounts and fact_amounts:
                    # Normalize: strip commas for comparison
                    answer_num = answer_amounts[0].replace(",", "")
                    fact_num = fact_amounts[0].replace(",", "")
                    if answer_num != fact_num:
                        warnings.append(
                            f"'{metric}' 수치 불일치: 답변 '{answer_amounts[0]}' vs "
                            f"팩트 '{fact_amounts[0]}'"
                        )
                        hallucinated.append(metric)

    if warnings:
        log_level = "warning" if len(hallucinated) >= 2 else "info"
        getattr(logger, log_level)(
            "fact_verification_issues",
            warnings=warnings,
            hallucinated=hallucinated,
            count=len(hallucinated),
        )

    # Graduated threshold:
    # - 0 hallucinations: valid, no warnings
    # - 1 hallucination: valid but with warnings (logged for monitoring)
    # - 2+ hallucinations: invalid, triggers re-generation
    return VerificationResult(
        is_valid=len(hallucinated) < 2,
        warnings=warnings,
        hallucinated_entities=hallucinated,
    )


def build_correction_hint(verification: VerificationResult) -> str:
    """Build a correction hint to prepend to re-generation prompt.

    When verification fails, this hint is added to the context so the
    LLM can self-correct on the second attempt.
    """
    if verification.is_valid:
        return ""
    lines = ["[사실 검증 경고 — 아래 사항에 유의하여 답변을 수정하세요]"]
    for w in verification.warnings:
        lines.append(f"  ! {w}")
    lines.append(
        "위 경고에 해당하는 정보는 답변에서 제외하거나 INSUFFICIENT_EVIDENCE로 표시하세요."
    )
    return "\n".join(lines)
