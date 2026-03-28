"""Checklist-based evaluation for AutoTune.

A Checklist defines "what good looks like" as a set of measurable criteria.
Each criterion is a yes/no check with a weight. The composite score drives
Optuna's objective function.

Checklist Format (YAML):
    name: "QuantumRAG Quality Checklist"
    criteria:
      - id: scenario_pass_rate
        description: "시나리오 테스트 통과율"
        target: 0.95
        weight: 0.40
        metric: scenario_pass_rate
      - id: retrieval_recall
        description: "검색 재현율 (Recall@5)"
        target: 0.80
        weight: 0.15
        metric: retrieval_recall
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.autotune")


@dataclass
class Criterion:
    """A single measurable quality criterion."""

    id: str
    description: str
    target: float  # Target value (0.0~1.0 for ratios, or absolute for latency)
    weight: float  # Importance weight (all weights sum to 1.0)
    metric: str  # Metric key (maps to a scorer function)
    direction: str = "maximize"  # "maximize" or "minimize"


@dataclass
class CriterionResult:
    """Result of evaluating a single criterion."""

    criterion: Criterion
    value: float
    passed: bool
    score: float  # Weighted contribution to total score


@dataclass
class ChecklistResult:
    """Result of evaluating the full checklist."""

    criteria_results: list[CriterionResult]
    total_score: float  # 0.0~1.0 composite score
    passed_count: int
    total_count: int
    params: dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    @property
    def pass_rate(self) -> float:
        return self.passed_count / self.total_count if self.total_count > 0 else 0.0

    def summary(self) -> str:
        lines = [
            f"Score: {self.total_score:.4f} | Passed: {self.passed_count}/{self.total_count} "
            f"({self.pass_rate:.0%}) | Time: {self.elapsed_seconds:.1f}s",
        ]
        for cr in self.criteria_results:
            status = "PASS" if cr.passed else "FAIL"
            lines.append(
                f"  [{status}] {cr.criterion.id}: {cr.value:.4f} "
                f"(target: {cr.criterion.target}, weight: {cr.criterion.weight})"
            )
        return "\n".join(lines)


class Checklist:
    """Loads and evaluates a quality checklist."""

    def __init__(self, criteria: list[Criterion]) -> None:
        self._criteria = criteria
        # Normalize weights
        total_weight = sum(c.weight for c in criteria)
        if total_weight > 0 and abs(total_weight - 1.0) > 0.01:
            for c in self._criteria:
                c.weight = c.weight / total_weight

    @classmethod
    def from_yaml(cls, path: str | Path) -> Checklist:
        """Load checklist from a YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Checklist not found: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        criteria = [
            Criterion(
                id=c["id"],
                description=c.get("description", ""),
                target=float(c["target"]),
                weight=float(c.get("weight", 1.0)),
                metric=c["metric"],
                direction=c.get("direction", "maximize"),
            )
            for c in data.get("criteria", [])
        ]
        return cls(criteria)

    @classmethod
    def default(cls) -> Checklist:
        """Create the default QuantumRAG quality checklist."""
        return cls(
            [
                Criterion(
                    id="scenario_pass_rate",
                    description="시나리오 테스트 전체 통과율",
                    target=0.95,
                    weight=0.35,
                    metric="scenario_pass_rate",
                ),
                Criterion(
                    id="hard_scenario_pass_rate",
                    description="Hard/Extreme 난이도 통과율",
                    target=0.90,
                    weight=0.15,
                    metric="hard_scenario_pass_rate",
                ),
                Criterion(
                    id="retrieval_recall",
                    description="검색 재현율 (Recall@5)",
                    target=0.80,
                    weight=0.15,
                    metric="retrieval_recall",
                ),
                Criterion(
                    id="faithfulness",
                    description="답변 충실도 (할루시네이션 없음)",
                    target=0.70,
                    weight=0.15,
                    metric="faithfulness",
                ),
                Criterion(
                    id="latency_p95",
                    description="응답 속도 P95 ≤ 5초",
                    target=5.0,
                    weight=0.10,
                    metric="latency_p95",
                    direction="minimize",
                ),
                Criterion(
                    id="cost_efficiency",
                    description="쿼리당 평균 비용 효율",
                    target=0.70,
                    weight=0.10,
                    metric="cost_efficiency",
                ),
            ]
        )

    @property
    def criteria(self) -> list[Criterion]:
        return list(self._criteria)

    def evaluate(
        self, metrics: dict[str, float], params: dict[str, Any] | None = None
    ) -> ChecklistResult:
        """Evaluate metrics against the checklist.

        Args:
            metrics: Dict mapping metric keys to measured values.
            params: Optional parameter set that produced these metrics.

        Returns:
            ChecklistResult with per-criterion and composite scores.
        """
        t0 = time.perf_counter()
        results: list[CriterionResult] = []
        total_score = 0.0

        for criterion in self._criteria:
            value = metrics.get(criterion.metric, 0.0)

            if criterion.direction == "minimize":
                # For minimize: passed if value <= target, score proportional to how low
                passed = value <= criterion.target
                # Normalized score: 1.0 if at or below target, degrades above
                ratio = criterion.target / value if value > 0 else 1.0
                norm_score = min(ratio, 1.0)
            else:
                # For maximize: passed if value >= target
                passed = value >= criterion.target
                # Normalized score: value/target capped at 1.0
                ratio = value / criterion.target if criterion.target > 0 else 1.0
                norm_score = min(ratio, 1.0)

            weighted = norm_score * criterion.weight
            total_score += weighted

            results.append(
                CriterionResult(
                    criterion=criterion,
                    value=value,
                    passed=passed,
                    score=weighted,
                )
            )

        elapsed = time.perf_counter() - t0
        passed_count = sum(1 for r in results if r.passed)

        return ChecklistResult(
            criteria_results=results,
            total_score=round(total_score, 6),
            passed_count=passed_count,
            total_count=len(results),
            params=params or {},
            elapsed_seconds=elapsed,
        )
