"""AutoTuner — Optuna-based parameter optimization for QuantumRAG.

Uses Bayesian optimization (TPE) to find optimal parameters by maximizing
a composite score from the quality checklist.

Usage:
    from quantumrag.core.autotune import AutoTuner, Checklist

    tuner = AutoTuner(engine, checklist=Checklist.default())
    best = tuner.run(n_trials=30, target="params")
    print(best.summary())
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from quantumrag.core.autotune.checklist import Checklist, ChecklistResult
from quantumrag.core.logging import get_logger

if TYPE_CHECKING:
    from quantumrag.core.engine import Engine

logger = get_logger("quantumrag.autotune")


@dataclass
class TuneResult:
    """Result of an autotune session."""

    best_params: dict[str, Any]
    best_score: float
    best_checklist: ChecklistResult
    history: list[ChecklistResult]
    n_trials: int
    elapsed_seconds: float
    target: str

    def summary(self) -> str:
        lines = [
            f"AutoTune Complete: {self.target}",
            f"  Trials: {self.n_trials} | Time: {self.elapsed_seconds:.0f}s",
            f"  Best Score: {self.best_score:.4f}",
            f"  Best Params: {json.dumps(self.best_params, ensure_ascii=False, indent=2)}",
            "",
            "Checklist:",
            self.best_checklist.summary(),
        ]
        return "\n".join(lines)

    def to_json(self, path: str | Path) -> None:
        """Save results to JSON."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "target": self.target,
            "n_trials": self.n_trials,
            "elapsed_seconds": self.elapsed_seconds,
            "best_score": self.best_score,
            "best_params": self.best_params,
            "history": [
                {
                    "trial": i,
                    "score": h.total_score,
                    "passed": h.passed_count,
                    "total": h.total_count,
                    "params": h.params,
                }
                for i, h in enumerate(self.history)
            ],
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class ParamSpace:
    """Defines the search space for a tunable parameter."""

    name: str
    param_type: str  # "float", "int", "categorical"
    low: float | None = None
    high: float | None = None
    choices: list[Any] | None = None
    log: bool = False  # Log-scale for float/int


# Default parameter search spaces
RETRIEVAL_PARAMS: list[ParamSpace] = [
    ParamSpace("retrieval.fusion_weights.original", "float", 0.1, 0.7),
    ParamSpace("retrieval.fusion_weights.hype", "float", 0.1, 0.5),
    ParamSpace("retrieval.fusion_weights.bm25", "float", 0.05, 0.5),
    ParamSpace("retrieval.top_k", "int", 5, 20),
    ParamSpace("retrieval.fusion_candidate_multiplier", "int", 2, 8),
]

GENERATION_PARAMS: list[ParamSpace] = [
    ParamSpace("generation.temperature", "float", 0.0, 0.3),
    ParamSpace("generation.max_context_chars", "int", 8000, 24000),
    ParamSpace("generation.high_confidence_threshold", "float", 0.6, 0.95),
    ParamSpace("generation.low_confidence_threshold", "float", 0.3, 0.7),
]

INGEST_PARAMS: list[ParamSpace] = [
    ParamSpace("ingest.chunking.chunk_size", "int", 256, 1024),
    ParamSpace("ingest.chunking.overlap", "int", 20, 100),
]

ALL_PARAMS = RETRIEVAL_PARAMS + GENERATION_PARAMS


class AutoTuner:
    """Bayesian optimization tuner for QuantumRAG parameters.

    Uses Optuna's TPE sampler to efficiently explore the parameter space,
    evaluated against a quality checklist.
    """

    def __init__(
        self,
        engine: Engine,
        checklist: Checklist | None = None,
        scorer: Any | None = None,
    ) -> None:
        self._engine = engine
        self._checklist = checklist or Checklist.default()
        self._scorer = scorer  # Optional custom scorer callable
        self._history: list[ChecklistResult] = []

    def run(
        self,
        n_trials: int = 30,
        target: str = "retrieval",
        timeout: int | None = None,
        output_dir: str | Path | None = None,
    ) -> TuneResult:
        """Run autotune optimization.

        Args:
            n_trials: Number of Optuna trials.
            target: What to optimize — "retrieval", "generation", or "all".
            timeout: Optional timeout in seconds.
            output_dir: Directory to save results.

        Returns:
            TuneResult with best parameters and history.
        """
        try:
            import optuna
        except ImportError as e:
            raise ImportError(
                "optuna is required for autotune. Install with: pip install optuna"
            ) from e

        t0 = time.perf_counter()

        # Select parameter space
        params = self._get_param_space(target)

        # Create Optuna study
        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=42),
            pruner=optuna.pruners.MedianPruner(n_startup_trials=5),
        )

        # Suppress Optuna logs (we log ourselves)
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial: optuna.Trial) -> float:
            # Sample parameters
            param_values = self._sample_params(trial, params)

            # Apply fusion weight constraint: sum = 1.0
            param_values = self._normalize_fusion_weights(param_values)

            # Score with checklist
            try:
                metrics = self._evaluate_params(param_values)
                result = self._checklist.evaluate(metrics, params=param_values)
                self._history.append(result)

                logger.info(
                    "autotune_trial",
                    trial=trial.number,
                    score=result.total_score,
                    passed=f"{result.passed_count}/{result.total_count}",
                    params=param_values,
                )
                return result.total_score

            except Exception as e:
                logger.warning("autotune_trial_failed", trial=trial.number, error=str(e))
                return 0.0

        study.optimize(objective, n_trials=n_trials, timeout=timeout)

        elapsed = time.perf_counter() - t0

        # Get best result
        best_params = self._normalize_fusion_weights(study.best_params)
        best_checklist = (
            self._history[study.best_trial.number]
            if self._history
            else ChecklistResult(
                criteria_results=[],
                total_score=0.0,
                passed_count=0,
                total_count=0,
            )
        )

        result = TuneResult(
            best_params=best_params,
            best_score=study.best_value,
            best_checklist=best_checklist,
            history=list(self._history),
            n_trials=n_trials,
            elapsed_seconds=elapsed,
            target=target,
        )

        # Save results
        if output_dir:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            result.to_json(out / f"autotune_{target}_{datetime.now():%Y%m%d_%H%M%S}.json")

        logger.info(
            "autotune_complete",
            target=target,
            best_score=result.best_score,
            trials=n_trials,
            elapsed=f"{elapsed:.0f}s",
        )

        return result

    def _get_param_space(self, target: str) -> list[ParamSpace]:
        if target == "retrieval":
            return RETRIEVAL_PARAMS
        elif target == "generation":
            return GENERATION_PARAMS
        elif target == "ingest":
            return INGEST_PARAMS
        elif target == "all":
            return ALL_PARAMS
        else:
            raise ValueError(
                f"Unknown target: {target}. Use 'retrieval', 'generation', 'ingest', or 'all'."
            )

    def _sample_params(self, trial: Any, params: list[ParamSpace]) -> dict[str, Any]:
        """Sample parameter values from Optuna trial."""
        values: dict[str, Any] = {}
        for p in params:
            if p.param_type == "float":
                values[p.name] = trial.suggest_float(p.name, p.low, p.high, log=p.log)
            elif p.param_type == "int":
                values[p.name] = trial.suggest_int(
                    p.name, int(p.low or 0), int(p.high or 100), log=p.log
                )
            elif p.param_type == "categorical":
                values[p.name] = trial.suggest_categorical(p.name, p.choices)
        return values

    def _normalize_fusion_weights(self, params: dict[str, Any]) -> dict[str, Any]:
        """Ensure fusion weights sum to 1.0."""
        keys = [
            "retrieval.fusion_weights.original",
            "retrieval.fusion_weights.hype",
            "retrieval.fusion_weights.bm25",
        ]
        weights = {k: params[k] for k in keys if k in params}
        if len(weights) == 3:
            total = sum(weights.values())
            if total > 0:
                for k in weights:
                    params[k] = round(weights[k] / total, 4)
        return params

    def _evaluate_params(self, params: dict[str, Any]) -> dict[str, float]:
        """Apply parameters to engine and run evaluation.

        Returns a dict of metric_key -> measured_value.
        """
        if self._scorer:
            return dict(self._scorer(self._engine, params))

        # Default: apply params to engine config and run built-in evaluation
        self._apply_params(params)
        return self._run_evaluation()

    def _apply_params(self, params: dict[str, Any]) -> None:
        """Apply parameter dict to engine config using dot-notation keys."""
        config = self._engine._config

        for key, value in params.items():
            parts = key.split(".")
            obj = config
            for part in parts[:-1]:
                obj = getattr(obj, part)
            setattr(obj, parts[-1], value)

    def _run_evaluation(self) -> dict[str, float]:
        """Run evaluation and return metrics dict.

        Uses the built-in Evaluator if available, or returns placeholder metrics.
        Override this method or provide a custom scorer for scenario-test-based evaluation.
        """
        import asyncio

        from quantumrag.core.evaluate.evaluator import Evaluator

        async def _eval() -> dict[str, float]:
            evaluator = Evaluator(self._engine)
            result = await evaluator.evaluate(sample_count=10)
            metrics: dict[str, float] = {}
            for m in result.metrics:
                metrics[m.name] = m.score
            # Map to checklist metric keys
            return {
                "scenario_pass_rate": metrics.get("token_f1", 0.0),  # Proxy
                "hard_scenario_pass_rate": metrics.get("completeness", 0.0),
                "retrieval_recall": metrics.get("retrieval_recall", 0.0),
                "faithfulness": metrics.get("faithfulness", 0.0),
                "latency_p95": metrics.get("latency", 5.0),
                "cost_efficiency": 0.7,  # Placeholder
            }

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, _eval()).result()
        else:
            return asyncio.run(_eval())

    def apply_best(self, result: TuneResult) -> None:
        """Apply the best parameters from a TuneResult to the engine config."""
        self._apply_params(result.best_params)
        logger.info("autotune_applied", params=result.best_params)

    def export_config(self, result: TuneResult, path: str | Path) -> None:
        """Export best parameters as a YAML config patch."""
        patch: dict[str, Any] = {}
        for key, value in result.best_params.items():
            parts = key.split(".")
            d = patch
            for part in parts[:-1]:
                d = d.setdefault(part, {})
            d[parts[-1]] = value

        import yaml  # type: ignore[import-untyped]

        Path(path).write_text(
            yaml.dump(patch, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
        logger.info("autotune_config_exported", path=str(path))
