"""Tests for completeness — multi-part answer verification."""

from __future__ import annotations

from quantumrag.core.generate.completeness import (
    ExpectedParts,
    _count_distinct_items,
    _extract_conjunction_items,
    detect_expected_parts,
    verify_completeness,
)


# --- detect_expected_parts ---
class TestDetectExpectedParts:
    def test_explicit_count(self) -> None:
        result = detect_expected_parts("3건의 계약을 알려주세요")
        assert result is not None
        assert result.expected_count == 3
        assert result.query_type == "count"

    def test_explicit_count_various_units(self) -> None:
        for query, count in [("5가지 방법", 5), ("2곳의 지점", 2), ("4단계 과정", 4)]:
            result = detect_expected_parts(query)
            assert result is not None, f"Failed for: {query}"
            assert result.expected_count == count

    def test_single_count_ignored(self) -> None:
        result = detect_expected_parts("1건의 계약")
        assert result is None

    def test_comparison_vs(self) -> None:
        result = detect_expected_parts("A vs B 성능 비교")
        assert result is not None
        assert result.query_type == "comparison"
        assert "A" in result.expected_items
        assert "B" in result.expected_items

    def test_comparison_korean(self) -> None:
        result = detect_expected_parts("삼성과 SK 차이")
        assert result is not None
        assert result.query_type == "comparison"

    def test_conjunction_list(self) -> None:
        result = detect_expected_parts("매출과 비용 및 이익을 알려줘")
        assert result is not None
        assert len(result.expected_items) >= 2

    def test_each_pattern(self) -> None:
        result = detect_expected_parts("각각 설명해주세요")
        assert result is not None
        assert result.query_type == "collection"

    def test_all_multi(self) -> None:
        result = detect_expected_parts("모든 항목을 나열해주세요")
        assert result is not None
        assert result.expected_count is None

    def test_simple_query_returns_none(self) -> None:
        assert detect_expected_parts("파이썬이란 무엇인가요?") is None
        assert detect_expected_parts("HBM 시장 규모는?") is None

    def test_empty_or_short_returns_none(self) -> None:
        assert detect_expected_parts("") is None
        assert detect_expected_parts("ab") is None


# --- verify_completeness ---
class TestVerifyCompleteness:
    def test_all_items_found(self) -> None:
        parts = ExpectedParts(expected_count=2, expected_items=["삼성", "SK"])
        answer = "삼성전자와 SK하이닉스의 실적을 비교합니다."
        result = verify_completeness("query", answer, parts)
        assert result.is_complete is True
        assert len(result.found_items) == 2
        assert result.missing_items == []

    def test_missing_items(self) -> None:
        parts = ExpectedParts(expected_count=3, expected_items=["삼성", "SK", "인텔"])
        answer = "삼성전자와 SK하이닉스의 실적입니다."
        result = verify_completeness("query", answer, parts)
        assert result.is_complete is False
        assert "인텔" in result.missing_items
        assert result.missing_query is not None

    def test_count_based_complete(self) -> None:
        parts = ExpectedParts(expected_count=3, expected_items=[], query_type="count")
        answer = "1. 첫 번째\n2. 두 번째\n3. 세 번째"
        result = verify_completeness("3가지 방법", answer, parts)
        assert result.is_complete is True

    def test_count_based_short(self) -> None:
        parts = ExpectedParts(expected_count=5, expected_items=[], query_type="count")
        answer = "1. 첫 번째\n2. 두 번째"
        result = verify_completeness("5가지 방법", answer, parts)
        assert result.is_complete is False
        assert "3" in (result.missing_query or "")  # shortfall=3

    def test_collection_no_items_assumed_complete(self) -> None:
        parts = ExpectedParts(expected_count=None, expected_items=[], query_type="collection")
        answer = "여러 항목이 있습니다."
        result = verify_completeness("모든 것을 알려줘", answer, parts)
        assert result.is_complete is True

    def test_empty_answer_incomplete(self) -> None:
        parts = ExpectedParts(expected_count=2, expected_items=["A", "B"])
        result = verify_completeness("A와 B", "", parts)
        assert result.is_complete is False
        assert result.missing_items == ["A", "B"]


# --- count_distinct_items ---
class TestCountDistinctItems:
    def test_numbered_list(self) -> None:
        assert _count_distinct_items("1. A\n2. B\n3. C") == 3

    def test_parenthesis_numbered(self) -> None:
        assert _count_distinct_items("1) A\n2) B") == 2

    def test_bullet_list(self) -> None:
        assert _count_distinct_items("- A\n- B\n- C\n- D") == 4

    def test_bold_items(self) -> None:
        assert _count_distinct_items("**항목1**: 설명\n**항목2**: 설명") == 2

    def test_single_paragraph(self) -> None:
        assert _count_distinct_items("단일 단락 텍스트입니다.") == 1

    def test_empty(self) -> None:
        assert _count_distinct_items("") == 1


# --- extract_conjunction_items ---
class TestExtractConjunctionItems:
    def test_korean_conjunctions(self) -> None:
        items = _extract_conjunction_items("매출과 비용 및 이익")
        assert len(items) >= 2

    def test_comma_separated(self) -> None:
        items = _extract_conjunction_items("A, B, C에 대해")
        assert len(items) == 3

    def test_no_conjunctions(self) -> None:
        items = _extract_conjunction_items("단일 항목입니다")
        assert items == []
