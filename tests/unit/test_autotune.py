"""Tests for the AutoTune system — checklist, scorer, tuner."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantumrag.core.autotune.checklist import Checklist, ChecklistResult, Criterion

# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------


class TestChecklist:
    def test_default_has_criteria(self) -> None:
        cl = Checklist.default()
        assert len(cl.criteria) >= 5

    def test_weights_sum_to_one(self) -> None:
        cl = Checklist.default()
        total = sum(c.weight for c in cl.criteria)
        assert abs(total - 1.0) < 0.02

    def test_evaluate_perfect_score(self) -> None:
        cl = Checklist(
            [
                Criterion("a", "desc", target=0.8, weight=0.5, metric="m1"),
                Criterion("b", "desc", target=0.7, weight=0.5, metric="m2"),
            ]
        )
        result = cl.evaluate({"m1": 0.9, "m2": 0.8})
        assert result.total_score > 0.9
        assert result.passed_count == 2

    def test_evaluate_partial_pass(self) -> None:
        cl = Checklist(
            [
                Criterion("a", "desc", target=0.8, weight=0.5, metric="m1"),
                Criterion("b", "desc", target=0.7, weight=0.5, metric="m2"),
            ]
        )
        result = cl.evaluate({"m1": 0.9, "m2": 0.3})
        assert result.passed_count == 1
        assert result.total_count == 2
        assert 0.0 < result.total_score < 1.0

    def test_evaluate_minimize_direction(self) -> None:
        cl = Checklist(
            [
                Criterion(
                    "lat", "latency", target=5.0, weight=1.0, metric="latency", direction="minimize"
                ),
            ]
        )
        # Below target = pass
        result_good = cl.evaluate({"latency": 3.0})
        assert result_good.passed_count == 1
        assert result_good.total_score == 1.0

        # Above target = fail
        result_bad = cl.evaluate({"latency": 10.0})
        assert result_bad.passed_count == 0
        assert result_bad.total_score < 1.0

    def test_evaluate_missing_metric(self) -> None:
        cl = Checklist(
            [
                Criterion("a", "desc", target=0.8, weight=1.0, metric="missing"),
            ]
        )
        result = cl.evaluate({})
        assert result.passed_count == 0
        assert result.total_score == 0.0

    def test_weight_normalization(self) -> None:
        cl = Checklist(
            [
                Criterion("a", "desc", target=0.5, weight=3.0, metric="m1"),
                Criterion("b", "desc", target=0.5, weight=7.0, metric="m2"),
            ]
        )
        total = sum(c.weight for c in cl.criteria)
        assert abs(total - 1.0) < 0.01

    def test_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = """\
criteria:
  - id: test_metric
    description: "Test metric"
    target: 0.9
    weight: 1.0
    metric: test_key
    direction: maximize
"""
        f = tmp_path / "checklist.yaml"
        f.write_text(yaml_content)
        cl = Checklist.from_yaml(f)
        assert len(cl.criteria) == 1
        assert cl.criteria[0].id == "test_metric"

    def test_from_yaml_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            Checklist.from_yaml("/nonexistent.yaml")

    def test_checklist_result_summary(self) -> None:
        cl = Checklist.default()
        result = cl.evaluate(
            {
                "scenario_pass_rate": 0.92,
                "hard_scenario_pass_rate": 0.88,
                "retrieval_recall": 0.85,
                "faithfulness": 0.75,
                "latency_p95": 4.0,
                "latency_median": 2.5,
                "cost_efficiency": 0.70,
                "context_precision": 0.72,
            }
        )
        summary = result.summary()
        assert "Score:" in summary
        assert "PASS" in summary or "FAIL" in summary

    def test_pass_rate_property(self) -> None:
        result = ChecklistResult(
            criteria_results=[],
            total_score=0.8,
            passed_count=4,
            total_count=5,
        )
        assert abs(result.pass_rate - 0.8) < 0.01


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class TestScorer:
    def test_default_scenarios_exist(self) -> None:
        from quantumrag.core.autotune.scorer import _get_default_scenarios

        scenarios = _get_default_scenarios()
        assert len(scenarios) >= 5
        for sc in scenarios:
            assert "question" in sc
            assert "expected_keywords" in sc
            assert "difficulty" in sc

    def test_scenario_score_metrics(self) -> None:
        from quantumrag.core.autotune.scorer import ScenarioScore

        score = ScenarioScore(
            total=10,
            passed=8,
            hard_total=4,
            hard_passed=3,
            latencies=[1.0, 2.0, 3.0, 4.0, 5.0],
        )
        assert score.pass_rate == 0.8
        assert score.hard_pass_rate == 0.75
        assert score.latency_median == 3.0
        assert score.latency_p95 == 5.0

        metrics = score.to_metrics()
        assert "scenario_pass_rate" in metrics
        assert "hard_scenario_pass_rate" in metrics
        assert "latency_p95" in metrics

    def test_scenario_score_empty(self) -> None:
        from quantumrag.core.autotune.scorer import ScenarioScore

        score = ScenarioScore()
        assert score.pass_rate == 0.0
        assert score.latency_median == 0.0


# ---------------------------------------------------------------------------
# Tuner (unit-level, no actual Optuna run)
# ---------------------------------------------------------------------------


class TestTunerParamSpace:
    def test_retrieval_params_defined(self) -> None:
        from quantumrag.core.autotune.tuner import RETRIEVAL_PARAMS

        names = [p.name for p in RETRIEVAL_PARAMS]
        assert "retrieval.fusion_weights.original" in names
        assert "retrieval.top_k" in names

    def test_generation_params_defined(self) -> None:
        from quantumrag.core.autotune.tuner import GENERATION_PARAMS

        names = [p.name for p in GENERATION_PARAMS]
        assert "generation.temperature" in names

    def test_normalize_fusion_weights(self) -> None:
        from quantumrag.core.autotune.tuner import AutoTuner

        tuner = AutoTuner.__new__(AutoTuner)
        params = {
            "retrieval.fusion_weights.original": 0.6,
            "retrieval.fusion_weights.hype": 0.3,
            "retrieval.fusion_weights.bm25": 0.1,
        }
        normalized = tuner._normalize_fusion_weights(params)
        total = sum(
            normalized[k]
            for k in [
                "retrieval.fusion_weights.original",
                "retrieval.fusion_weights.hype",
                "retrieval.fusion_weights.bm25",
            ]
        )
        assert abs(total - 1.0) < 0.01

    def test_tune_result_to_json(self, tmp_path: Path) -> None:
        from quantumrag.core.autotune.tuner import TuneResult

        result = TuneResult(
            best_params={"retrieval.top_k": 8},
            best_score=0.92,
            best_checklist=ChecklistResult(
                criteria_results=[],
                total_score=0.92,
                passed_count=5,
                total_count=6,
            ),
            history=[],
            n_trials=10,
            elapsed_seconds=120.0,
            target="retrieval",
        )
        out = tmp_path / "result.json"
        result.to_json(out)
        assert out.exists()

        import json

        data = json.loads(out.read_text())
        assert data["best_score"] == 0.92
        assert data["best_params"]["retrieval.top_k"] == 8

    def test_get_param_space_invalid(self) -> None:
        from quantumrag.core.autotune.tuner import AutoTuner

        tuner = AutoTuner.__new__(AutoTuner)
        with pytest.raises(ValueError, match="Unknown target"):
            tuner._get_param_space("invalid_target")
