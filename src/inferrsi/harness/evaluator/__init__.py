"""Assess ordinary and service attempts against frozen rules and retained evidence."""

from ._measurement import (
    CONFIDENCE,
    DIRECTIONS,
    METHOD,
    MIN_PAIRS,
    explain,
    gate_speedup,
    interval_rank,
    median_interval,
    min_pairs,
    paired_speedups,
    paired_statistics,
    profile_evidence,
    relative_mad,
    validate_mechanism,
)
from ._project import (
    assess_project,
    inspect_project_step,
    project_steps,
    validate_quality_unit,
)
from ._service import (
    ServiceStageDecision,
    aggregate_service_measurements,
    assess_service_performance,
    check_service_quality_reference,
    prefer_service_measurements,
    refresh_final_baseline,
    service_assessment,
    service_measurement_decision,
    service_metric_change,
    service_precheck_passed,
    service_profile_eligible,
    service_quality_decision,
    service_quality_passed,
    service_quality_score,
    service_ready,
    service_trial_gate,
)
from ._service_evidence import evaluation_reason as service_evaluation_reason
from ._service_evidence import (
    final_baseline_job,
    service_choice,
    service_reference_result,
    service_reference_snapshot,
    service_references_reason,
    service_settlement_reason,
)

__all__ = [
    "CONFIDENCE",
    "DIRECTIONS",
    "METHOD",
    "MIN_PAIRS",
    "ServiceStageDecision",
    "aggregate_service_measurements",
    "assess_ordinary",
    "assess_project",
    "assess_service_performance",
    "check_service_quality_reference",
    "explain",
    "gate_speedup",
    "inspect_project_step",
    "interval_rank",
    "median_interval",
    "min_pairs",
    "paired_speedups",
    "paired_statistics",
    "prefer_service_measurements",
    "profile_evidence",
    "project_steps",
    "relative_mad",
    "service_assessment",
    "final_baseline_job",
    "service_choice",
    "service_reference_result",
    "service_evaluation_reason",
    "service_measurement_decision",
    "service_metric_change",
    "service_precheck_passed",
    "service_profile_eligible",
    "service_quality_decision",
    "service_quality_passed",
    "service_quality_score",
    "service_ready",
    "refresh_final_baseline",
    "service_trial_gate",
    "service_reference_snapshot",
    "service_references_reason",
    "service_settlement_reason",
    "validate_mechanism",
    "validate_quality_unit",
]


def assess_ordinary(root, directory, plan, execution, mechanism=None, *, assess_packaged):
    """Read project evidence or delegate to the packaged task's supplied assessor."""
    if plan["task_source"] == "project":
        is_final = directory.parent == root / "final"
        final_target = plan.get("performance_target") if is_final else None
        return assess_project(
            directory, plan["evaluation_settings"], execution,
            mechanism=mechanism, final_target=final_target,
        )
    return assess_packaged(root, directory, plan, execution)
