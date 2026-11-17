"""Historical adapters keep their original scope and explicitly disclose mapping gaps."""

from ..result import _selected_verdict
from ..result import validate_result as validate_apps_result
from .projection import assessment, metric
from .schema import gap, timestamp


def _source(result, snapshot, ref, kind):
    result["sources"].append(
        {"artifact_ref": ref, "type": kind, "revision": snapshot.entries[ref]["source_revision"]}
    )


def legacy(snapshot, result):
    plan, plan_ref = snapshot.object("run.lock.json", "plan", required=True)
    evaluation, ref = snapshot.object("evaluation.json", "assessment")
    status, status_ref = snapshot.object("status.json", "execution")
    _source(result, snapshot, plan_ref, "legacy_run")
    _source(result, snapshot, ref, "legacy_evaluation")
    _source(result, snapshot, status_ref, "legacy_status")
    state = (status or {}).get("state")
    result["campaign"].update(
        id=plan.get("run_id"),
        task_kind="single_experiment",
        plan_ref=plan_ref,
        acceptance_basis=plan,
    )
    result["execution"] = {
        "namespace": "inferrsi.legacy.run",
        "state": state,
        "completed_rounds": None,
        "round_limit": None,
        "started_at": timestamp((status or {}).get("started_at")),
        "ended_at": timestamp((status or {}).get("ended_at")),
    }
    assessment(result, evaluation, ref, scope=plan.get("comparison_scope"))
    if state == "completed":
        result["completion"] = {"status": "completed", "reason": "Single experiment completed"}
    result["export"]["kind"] = (
        "final" if state in ("completed", "failed", "cancelled") else "progress"
    )
    if evaluation:
        before, after = evaluation.get("baseline", {}), evaluation.get("candidate", {})
        result["metrics"] = [
            metric(
                {
                    "name": evaluation.get("metric_key", plan.get("metric_key")),
                    "unit": evaluation.get("metric_unit", plan.get("metric_unit")),
                    "direction": evaluation.get("direction", plan.get("direction")),
                    "scope": plan.get("comparison_scope"),
                    "workload_id": plan.get("workload_id"),
                    "statistic": "median",
                    "baseline": before.get("median"),
                    "candidate": after.get("median"),
                    "configuration": plan,
                    "sample_counts": {
                        "baseline": len(before["values"]) if "values" in before else None,
                        "candidate": len(after["values"]) if "values" in after else None,
                    },
                    "repetitions": plan.get("repetitions"),
                },
                phase="single_experiment",
                ref=ref,
                protocol_ref=plan_ref,
                comparable=bool(before and after),
            )
        ]
    gap(
        result,
        "LEGACY_SCOPE",
        "final_acceptance",
        "Single A/B experiment only; no iterative rounds or independent final were recorded",
    )


def summary(snapshot, result, name="summary.json"):
    document, ref = snapshot.object(name, "historical_summary", required=True)
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise ValueError("Unsupported historical summary version")
    _source(result, snapshot, ref, "historical_summary")
    result["campaign"].update(
        id=document.get("campaign_id"),
        goal=document.get("goal"),
        task_kind="historical_summary",
        task=document.get("task"),
    )
    result["execution"] = {
        "namespace": "historical_summary",
        "state": document.get("state"),
        "completed_rounds": document.get("completed_rounds"),
        "round_limit": document.get("planned_rounds"),
        "stop_reason": document.get("stop_reason"),
    }
    result["export"]["kind"] = (
        "final" if document.get("state") in ("completed", "blocked") else "progress"
    )
    assessment(result, document.get("final_assessment"), ref)
    if document.get("state") == "completed":
        result["completion"] = {
            "status": "completed",
            "reason": "Historical summary reports workflow completion",
        }
    result["selected_candidate"] = document.get("selected_candidate")
    # The curve is retained verbatim as source material, never mistaken for attempt records.
    gap(
        result,
        "SUMMARY_ONLY",
        "verification",
        "Only a rebuildable historical summary is available; original control, attempts, "
        "usage coverage and final candidate binding cannot be verified",
    )


def operation(snapshot, result, name="result.json"):
    document, ref = snapshot.object(name, "operation_result", required=True)
    validate_apps_result(document)
    _source(result, snapshot, ref, "apps_operation")
    result["campaign"].update(
        id=document.get("attempt_id"),
        task_kind="operation",
        acceptance_basis=document.get("prepared_ref"),
    )
    result["execution"] = {
        "namespace": "inferrsi.apps.result",
        "operation": document["operation"],
        "outcome": document["outcome"],
        "record_ref": document["record_ref"],
        "execution": document["execution"],
    }
    result["export"]["kind"] = (
        "final" if document["outcome"] not in ("in_progress", "recovery_required") else "progress"
    )
    if document["assessment"] is not None:
        verdict = _selected_verdict(
            document["assessment"], (document["primary_claim_id"], document["primary_scope"])
        )
        assessment(
            result,
            {"verdict": verdict},
            ref,
            scope=document["primary_scope"],
            claim_id=document["primary_claim_id"],
        )
        result["acceptance"]["original_assessment_ref"] = document["assessment_ref"]
        result["acceptance"]["claims"] = document["assessment"]["claims"]
    gap(
        result,
        "OPERATION_SCOPE",
        "completion",
        "Operation outcome is not completion or acceptance of an optimization campaign; "
        "fixed storage references are preserved, not fetched",
    )


def external(snapshot, result, name):
    document, ref = snapshot.object(name, "external_record", required=True)
    if (
        document.get("kind") != "external_optimization_record"
        or type(document.get("schema_version")) is not int
        or document["schema_version"] != 1
    ):
        raise ValueError("Unsupported external optimization record")
    _source(result, snapshot, ref, "external_optimization_record")
    refs = []
    for source in document.get("source_refs", []):
        refs.append(snapshot.file(source["path"], "external_source", source.get("sha256")))
    result["campaign"].update(
        id=document.get("candidate_id"),
        task_kind="external_records",
        goal=document.get("goal"),
        acceptance_basis=document.get("protocol"),
    )
    result["execution"] = {
        "namespace": "external_optimization_record",
        "state": document.get("state"),
    }
    result["export"]["kind"] = (
        "final" if document.get("state") in ("completed", "failed", "blocked") else "progress"
    )
    if document.get("state") == "completed":
        result["completion"] = {
            "status": "completed",
            "reason": "External source reports completion",
        }
    assessment(
        result,
        {"verdict": document.get("performance_verdict")},
        ref,
        scope=document.get("scope"),
        claim_id=document.get("claim_id"),
    )
    result["acceptance"]["locally_revalidated"] = False
    result["metrics"] = [
        metric(
            {
                **row,
                "candidate": row.get("aggregate"),
                "statistic": row.get("statistic", row.get("aggregation")),
            },
            phase="external",
            ref=ref,
            protocol_ref=ref,
            comparable=False,
        )
        for row in document.get("metrics", [])
    ]
    result["checks"] = [
        {
            "name": "external_quality",
            "required": None,
            "execution_state": None,
            "gate_ref": None,
            "observation": document.get("quality"),
            "verdict": (document.get("quality") or {}).get("verdict"),
            "evidence_refs": refs,
        }
    ]
    gap(
        result,
        "EXTERNAL_SCOPE",
        "final_acceptance",
        "Externally reported facts have not been locally revalidated; "
        "source hashes only verify bytes",
    )
