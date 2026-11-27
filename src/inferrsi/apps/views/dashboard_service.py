"""Adapt service-reuse evidence to the shared Dashboard views."""

from datetime import datetime, timezone

from inferrsi.harness.records import service_io
from inferrsi.harness.records.evidence import STAGES, relative_location, sanitized_text

from .dashboard_data import _managed_submission, _number, _optimization
from .dashboard_experiments import project_experiments
from .retrieval_projection import public_value


def service_inputs(root, plan, state):
    settings = plan["evaluation_settings"]
    workloads = {item["id"]: item["workload"] for item in settings["scenarios"]}
    objectives = {
        item["id"]: {"workload": workloads.get(item["scenario"]), "unit": item["unit"],
                     "aggregate": item["aggregate"], "direction": item["direction"]}
        for item in settings["objectives"]
    }
    diagnoses = [{"rounds": sorted({a["round_number"] for a in state["attempts"]
                                  if a.get("diagnosis_id") == d["id"]
                                  and a.get("round_number") is not None}),
                  "bottleneck": d["bottleneck"],
                  "measurement_summary": d["measurement_summary"]}
                 for d in state.get("diagnoses", [])]
    queries = []
    for reference in state.get("contexts", []):
        if reference.get("kind") != "delivered_context":
            continue
        try:
            record = service_io.read(service_io.safe_path(root, reference["path"]))
        except (ValueError, OSError):
            continue  # A retained record can disappear during a live refresh.
        delivered = {item["ref"] for item in record.get("contexts", []) if item.get("resources")}
        request = record.get("request", {})
        queries.append({"round": reference.get("round"), "path": reference["path"],
                        "query": request.get("relevance") or request.get("query"),
                        "items": [{**{key: item.get(key) for key in ("ref", "title", "revision")},
                                   "delivered": item["ref"] in delivered}
                                  for item in record.get("items", [])]})
    pending = state.get("pending")
    return public_value({"service_objectives": objectives, "service_pending": pending,
                         "managed_diagnoses": diagnoses, "managed_retrievals": queries})


def _timestamp(value):
    seconds = _number(value)
    if seconds is not None:
        try:
            return datetime.fromtimestamp(seconds, timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            pass
    return None


def _stages(attempt, refs):
    nodes, events = [], []
    for index, step in enumerate(attempt.get("execution", {}).get("steps", []), start=1):
        label = step["id"]
        stage = "validation" if label in ("quality", "quality_reference") else "execution"
        start, end = _timestamp(step.get("started_at")), _timestamp(step.get("ended_at"))
        status = step.get("status", "unknown")
        seconds = _number(step.get("elapsed_seconds"))
        nodes.append({"kind": "service_stage", "label": label, "state": status,
                      "start": start, "end": end, "seconds": seconds,
                      "source": "service_steps", "line": index})
        events.append({"source": "service_steps", "line": index, "stage": stage,
                       "phase": label, "time": end or start, "type": "service_stage",
                       "details": {"state": status, "summary": step.get("reason") or status},
                       "refs": refs})
    groups = []
    for label, kind, unit in (("measure", "measurement", "trials"),
                              ("quality", "quality_validation", "checks")):
        work = [node for node in nodes if node["label"] == label]
        if work:
            groups.append({"kind": kind, "unit": unit, "state": work[-1]["state"],
                           "completed": sum(node["state"] == "completed" for node in work),
                           "total": None, "wall_seconds": None})
    return {"nodes": nodes, "groups": groups}, events


def _objective_rows(attempt, objectives, order):
    assessed = (attempt.get("assessment", {}).get("performance") or {}).get("metrics", {})
    measured = (attempt.get("execution", {}).get("measurements") or {}).get("values", {})
    measurement_times = [_timestamp(step.get("ended_at"))
                         for step in attempt.get("execution", {}).get("steps", [])
                         if step.get("id") == "measure" and step.get("status") == "completed"]
    measured_at = max((time for time in measurement_times if time), default=None)
    rows, points = [], []
    for name in dict.fromkeys([*assessed, *measured]):
        metric, spec = assessed.get(name, {}), objectives.get(name, {})
        value = _number(metric.get("value", measured.get(name)))
        unit = metric.get("unit") or spec.get("unit")
        rows.append({"objective": name, "value": value, "unit": unit,
                     "parent_change": _number(metric.get("parent_change")),
                     "initial_change": _number(metric.get("initial_change"))})
        if value is None:
            continue
        points.append({"measurement_id": name, "value": value, "metric": name, "unit": unit,
                       "direction": spec.get("direction"), "statistic": spec.get("aggregate"),
                       "workload": spec.get("workload"), "order": order,
                       "scope": (attempt.get("conditions") or {}).get("timing_scope"),
                       "timestamp": measured_at})
    return rows, points


def _attempt_row(attempt, summary, objectives, order, pending):
    identity, kind = attempt["attempt_id"], attempt["kind"]
    number = attempt.get("round_number")
    assessment = attempt.get("assessment", {})
    execution = attempt.get("execution", {})
    verdict = assessment.get("verdict", "not_recorded")
    quality = assessment.get("quality_passed")
    selected = attempt.get("selected") is True
    accepted = identity in summary["accepted_attempt_ids"]
    decision = ("pending" if pending else "adopted" if selected else "accepted" if accepted
                else "rejected" if kind == "round" and verdict == "FAIL" else "not_recorded")
    path = relative_location(attempt.get("path"))
    refs = {} if pending or not path else {
        "assessment": {"state": "present", "kind": "assessment", "path": path + "/observation.json"}
    }
    profile = attempt.get("profiling")
    if profile and profile.get("available"):
        for index, item in enumerate([profile["result"], *profile["artifacts"]]):
            if item_path := relative_location(item):
                refs[f"profile_{index}"] = {"state": "present", "kind": "profile",
                                            "path": item_path}
    workflow, events = _stages(attempt, list(refs.values()))
    metrics, points = _objective_rows(attempt, objectives, order)
    epoch = attempt.get("reference_epoch")
    hypothesis = attempt.get("hypothesis")
    contexts = [ref["path"] for ref in attempt.get("contexts", [])
                if ref.get("kind") == "delivered_context"]
    title = (f"Round {number}" if number is not None else kind.capitalize())
    return {
        "candidate_id": attempt.get("candidate_id") or kind, "run_id": identity, "round": number,
        "title": title, "round_state": "recorded" if number is not None else "not_recorded",
        "state": "pending" if pending else execution.get("status", "not_recorded"),
        "verdict": verdict, "quality": ("passed" if quality is True else "failed"
                                        if quality is False else "not_recorded"),
        "outcome": assessment.get("status") or "not_recorded", "decision": decision,
        "improvement_pct": None, "candidate_median": None, "baseline_median": None,
        "noise_band_pct": None, "metric_key": "Service objectives", "metric_unit": "",
        "candidate_metadata_state": "not_applicable", "events": events,
        "unlinked_agent_events": [], "artifacts": refs, "optimization_trace": None,
        "optimization": _optimization({"details": {"hypothesis": hypothesis}}),
        "managed_submission": _managed_submission(attempt),
        "run_workflow": workflow,
        "_plot_measurements": points,
        "_plot_comparison_signature": ("service_reuse", epoch) if type(epoch) is int else None,
        "service_attempt": {"kind": kind, "reason": assessment.get("reason"), "metrics": metrics,
                            "quality_score": execution.get("quality_score"),
                            "revision": attempt.get("revision"), "reference_epoch": epoch,
                            "available_contexts": contexts,
                            "retry_of": attempt.get("retry_of"), "repair_reason": attempt.get(
                                "repair_reason"), "elapsed_seconds": attempt.get("elapsed_seconds"),
                            "profile_available": bool(profile and profile.get("available"))},
    }


def service_dashboard_view(view):
    summary = view["service_optimization"]
    pending = view.get("service_pending")
    attempts = summary["attempts"]
    rows = [_attempt_row(record, summary, view.get("service_objectives", {}), index, False)
            for index, record in enumerate(attempts, start=1)]
    if pending and not any(row["run_id"] == pending["attempt_id"] for row in rows):
        rows.append(_attempt_row(pending, summary, {}, len(rows) + 1, True))
    rounds = sorted({row["round"] for row in rows if row["round"] is not None})
    story = {"state": "not_recorded", "versions": []}
    experiments = project_experiments(view.get("campaign_id", "Campaign"), rows, story)
    for row in rows:
        row.pop("_plot_comparison_signature", None)
    recorded = {event["stage"] for row in rows for event in row["events"]}
    if view.get("managed_diagnoses"):
        recorded.add("diagnosis")
    if view.get("managed_retrievals"):
        recorded.add("knowledge")
    public = {key: item for key, item in view.items()
              if key not in ("service_pending", "service_objectives")}
    return {**public, "candidates": rows, "synthetic": False, "experiments": experiments,
            "rounds": [{"round": number} for number in rounds], "corrupt_round_lines": [],
            "stages": [{"name": stage, "state": "recorded" if stage in recorded
                        else "stage_not_recorded"} for stage in STAGES],
            "overview": {"comparison_state": "unverified", "best_improvement_pct": None,
                         "target_improvement_pct": None, "target_gap_pct": None},
            "integration": {"state": "connected"}, "diagnostics": [], "story": story,
            "chart_note": sanitized_text("Service objective measurements"),
            "knowledge_trace": {"retrievals": [], "searches": []}}
