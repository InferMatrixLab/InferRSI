# The old `evaluate` entry: a RunSpec goes in and the original result dict comes out.
# The gates live in Benchmark; this module only converts the old argument.

from inferrsi.benchmark.legacy_run_v0 import RunRules, _summary, read_metric
from inferrsi.benchmark.legacy_run_v0 import evaluate as _evaluate
from inferrsi.runspec import RunSpec

__all__ = ["evaluate", "read_metric", "run_rules", "_summary"]


def run_rules(spec: RunSpec) -> RunRules:
    return RunRules(
        repetitions=spec.repetitions,
        required_trial_checks=spec.required_trial_checks,
        metric_key=spec.metric_key,
        metric_unit=spec.metric_unit,
        comparison_scope=spec.comparison_scope,
        direction=spec.direction,
        min_improvement_pct=spec.min_improvement_pct,
    )


def evaluate(
    spec: RunSpec,
    baseline: list[dict],
    candidate: list[dict],
    validation: dict | None,
    integrity: dict | None = None,
) -> dict:
    return _evaluate(run_rules(spec), baseline, candidate, validation, integrity)
