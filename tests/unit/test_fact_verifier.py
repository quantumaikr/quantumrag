"""Tests for fact_verifier — hallucination detection via fact cross-checking."""

from __future__ import annotations

from unittest.mock import MagicMock

from quantumrag.core.generate.fact_verifier import (
    VerificationResult,
    _extract_companies_from_answer,
    _is_customer_context,
    build_correction_hint,
    verify_against_facts,
)


# --- Helper to create mock ScoredChunk ---
def _make_chunk(content: str, facts: list[dict] | None = None) -> MagicMock:
    chunk = MagicMock()
    chunk.chunk.content = content
    chunk.chunk.metadata = {"facts": facts} if facts else {}
    return chunk


# --- Company extraction ---
class TestExtractCompanies:
    def test_suffix_patterns(self) -> None:
        text = "삼성전자와 SK텔레콤이 공동으로 개발했습니다."
        result = _extract_companies_from_answer(text)
        assert "삼성전자" in result
        assert "SK텔레콤" in result

    def test_wellknown_names(self) -> None:
        text = "네이버와 카카오의 매출을 비교하면"
        result = _extract_companies_from_answer(text)
        assert "네이버" in result
        assert "카카오" in result

    def test_no_companies(self) -> None:
        text = "Python asyncio에서 코루틴을 실행하는 방법"
        result = _extract_companies_from_answer(text)
        assert result == []

    def test_no_duplicates(self) -> None:
        text = "삼성전자가 삼성전자의 실적을 발표했다"
        result = _extract_companies_from_answer(text)
        assert result.count("삼성전자") == 1


# --- Customer context detection ---
class TestCustomerContext:
    def test_customer_context_detected(self) -> None:
        answer = "삼성전자는 주요 고객사로 계약을 체결했습니다."
        assert _is_customer_context(answer, "삼성전자") is True

    def test_no_customer_context(self) -> None:
        answer = "삼성전자는 반도체를 생산합니다."
        assert _is_customer_context(answer, "삼성전자") is False

    def test_company_not_in_text(self) -> None:
        answer = "트랜스포머 아키텍처에 대한 설명입니다."
        assert _is_customer_context(answer, "삼성전자") is False


# --- Verification against facts ---
class TestVerifyAgainstFacts:
    def test_no_facts_returns_valid(self) -> None:
        chunks = [_make_chunk("some text")]
        result = verify_against_facts("답변입니다", chunks)
        assert result.is_valid is True
        assert result.warnings == []

    def test_known_customer_passes(self) -> None:
        facts = [{"type": "customer_contract", "customer": "삼성전자"}]
        chunks = [_make_chunk("삼성전자 관련 내용", facts)]
        answer = "삼성전자는 주요 고객사입니다."
        result = verify_against_facts(answer, chunks)
        assert result.is_valid is True

    def test_hallucinated_customer_detected(self) -> None:
        facts = [{"type": "customer_contract", "customer": "삼성전자"}]
        chunks = [_make_chunk("삼성전자 관련", facts)]
        # LG화학 is not in facts and not in chunk text
        answer = "LG화학은 신규 고객사로 계약을 체결했습니다. 또한 현대자동차도 고객입니다."
        result = verify_against_facts(answer, chunks)
        # Two hallucinated entities → is_valid should be False
        assert result.is_valid is False
        assert len(result.hallucinated_entities) >= 2

    def test_company_in_chunk_text_not_flagged(self) -> None:
        facts = [{"type": "customer_contract", "customer": "삼성전자"}]
        chunks = [_make_chunk("LG에너지 관련 정보가 있습니다", facts)]
        answer = "LG에너지는 고객사로 등록되어 있습니다."
        result = verify_against_facts(answer, chunks)
        # LG에너지 is in chunk text, so should not be flagged
        assert result.is_valid is True

    def test_empty_answer(self) -> None:
        facts = [{"type": "customer_contract", "customer": "삼성전자"}]
        chunks = [_make_chunk("text", facts)]
        result = verify_against_facts("", chunks)
        assert result.is_valid is True

    def test_single_hallucination_still_valid(self) -> None:
        """Conservative threshold: single unknown entity is tolerated."""
        facts = [{"type": "customer_contract", "customer": "삼성전자"}]
        chunks = [_make_chunk("삼성전자 관련", facts)]
        answer = "현대자동차는 신규 고객사입니다."
        result = verify_against_facts(answer, chunks)
        # Single hallucination → still valid (conservative)
        assert result.is_valid is True
        assert len(result.hallucinated_entities) == 1


# --- VerificationResult ---
class TestVerificationResult:
    def test_default_valid(self) -> None:
        r = VerificationResult()
        assert r.is_valid is True
        assert r.warnings == []
        assert r.hallucinated_entities == []

    def test_repr(self) -> None:
        r = VerificationResult(is_valid=False, warnings=["w1", "w2"])
        assert "valid=False" in repr(r)
        assert "warnings=2" in repr(r)


# --- Correction hint ---
class TestCorrectionHint:
    def test_valid_returns_empty(self) -> None:
        r = VerificationResult(is_valid=True)
        assert build_correction_hint(r) == ""

    def test_invalid_returns_hint(self) -> None:
        r = VerificationResult(
            is_valid=False,
            warnings=["'LG화학' 검증되지 않음"],
        )
        hint = build_correction_hint(r)
        assert "사실 검증 경고" in hint
        assert "LG화학" in hint
        assert "INSUFFICIENT_EVIDENCE" in hint
