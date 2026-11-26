"""Project retained iterative records without invoking execution or assessment."""

import re

from ...harness.usage import normalize_usage
from ..storage.artifacts import digest
from .schema import gap, number, timestamp


def assessment(result, value, ref, *, scope=None, claim_id=None):
    if not isinstance(value, dict) or value.get("verdict") not in ("PASS", "FAIL", "INCONCLUSIVE"):
        gap(result, "ASSESSMENT_UNAVAILABLE", "acceptance", "No readable original assessment")
        return
    result["acceptance"].update(
        status="assessed",
        verdict=value["verdict"],
        assessment_ref=ref,
        claim_id=value.get("claim_id", claim_id),
        scope=value.get("scope", scope),
    )
    if any(result["acceptance"][key] is None for key in ("claim_id", "scope", "assessment_ref")):
        gap(
            result,
            "identity_incomplete",
            "acceptance",
            "The source did not record all claim identities; none were invented",
        )


def metric(value, *, phase, ref, protocol_ref, comparable=False):
    before, after = number(value.get("baseline")), number(value.get("candidate"))
    direction = value.get("direction")
    valid = (
        comparable
        and bool(value.get("unit"))
        and bool(value.get("statistic"))
        and direction in ("minimize", "maximize")
        and before is not None
        and after is not None
        and before > 0
        and after > 0
        and value.get("ratio_applicable", True)
    )
    speedup = improvement = None
    if valid:
        speedup = number(before / after if direction == "minimize" else after / before)
        improvement = number(
            (after - before) / before * 100 * (-1 if direction == "minimize" else 1)
        )
    reason = (
        None
        if speedup is not None and improvement is not None
        else (
            "Comparable protocol, workload, unit and statistic with positive finite values "
            "and an applicable ratio are required"
        )
    )
    return {
        "name": value.get("name"),
        "unit": value.get("unit"),
        "direction": direction,
        "scope": value.get("scope"),
        "workload_id": value.get("workload_id"),
        "configuration": value.get("configuration"),
        "statistic": value.get("statistic"),
        "baseline": before,
        "candidate": after,
        "sample_counts": value.get("sample_counts"),
        "repetitions": value.get("repetitions"),
        "phase": phase,
        "evidence_refs": [ref],
        "protocol_ref": protocol_ref,
        "comparability": {"comparable": comparable, "reason": reason},
        "speedup": speedup if reason is None else None,
        "improvement_pct": improvement if reason is None else None,
    }


def _metrics(value, plan, phase, ref):
    settings = plan.get("evaluation_settings", {})
    common = {
        "scope": value.get("scope", settings.get("scope")),
        "configuration": settings,
        "repetitions": settings.get("repetitions"),
    }
    if plan.get("task_source") == "project" and isinstance(value.get("metrics"), dict):
        raw = value["metrics"]
        samples = raw.get("samples", {})
        return [
            metric(
                {
                    **common,
                    **raw,
                    "statistic": "median",
                    "sample_counts": {
                        side: len(samples[side]) if side in samples else None
                        for side in ("baseline", "candidate")
                    },
                },
                phase=phase,
                ref=ref,
                protocol_ref="source:plan.json",
                comparable=True,
            )
        ]
    rows = []
    for case in value.get("case_metrics", []):
        samples = case.get("samples_ms", {})
        rows.append(
            metric(
                {
                    **common,
                    "name": "elapsed",
                    "unit": "ms",
                    "direction": "minimize",
                    "scope": "task_case",
                    "workload_id": case.get("id", case.get("case")),
                    "statistic": "median",
                    "baseline": case.get("baseline_median_ms"),
                    "candidate": case.get("candidate_median_ms"),
                    "sample_counts": {
                        side: len(samples[side]) if side in samples else None
                        for side in ("baseline", "candidate")
                    },
                },
                phase=phase,
                ref=ref,
                protocol_ref="source:plan.json",
                comparable=True,
            )
        )
    return rows


def _usage(records, source, scope):
    observed = [
        normalize_usage((record.get("observations") or {}).get("usage")) for record in records
    ]
    totals = {}
    counts = {}
    for field in ("input_tokens", "output_tokens", "cached_input_tokens"):
        values = [item[field] for item in observed if item and item.get(field) is not None]
        totals[field] = sum(values) if values else None
        counts[field] = len(values)
    # Only paired observations contribute to total_tokens; cache is an input subset.
    paired = [
        item["input_tokens"] + item["output_tokens"]
        for item in observed
        if item and item.get("input_tokens") is not None and item.get("output_tokens") is not None
    ]
    totals["total_tokens"] = sum(paired) if paired else None
    counts["total_tokens"] = len(paired)
    return {
        "value": totals if any(counts.values()) else None,
        "source": source,
        "coverage": "complete"
        if observed
        and all(n == len(records) for n in (counts["input_tokens"], counts["output_tokens"]))
        else "partial"
        if any(counts.values())
        else "unknown",
        "scope": scope,
        "observed_counts": counts,
        "record_count": len(records),
    }


def _binding(snapshot, selected, final, *, attempt_id, protocol_digest):
    """A fixed run/config pair can bind an exact revision without file fingerprints.

    The run must itself record the exact revision and the same configuration ref;
    matching two caller-supplied strings alone is insufficient.
    """
    if not selected or not final or selected != final:
        return False
    revision = selected.get("revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
        return False
    refs = []
    documents = []
    for field in ("run_ref", "configuration_ref"):
        ref = selected.get(field)
        if not isinstance(ref, dict) or not re.fullmatch(r"[0-9a-f]{64}", ref.get("sha256", "")):
            return False
        document, identity = snapshot.object(ref["path"], field, ref["sha256"])
        documents.append(document)
        refs.append(identity)
    run, config = documents
    return bool(
        snapshot.verified(refs)
        and run
        and config
        and run.get("candidate_revision") == revision
        and config.get("candidate_revision") == revision
        and run.get("configuration_ref") == selected["configuration_ref"]
        and run.get("attempt_id") == attempt_id
        and run.get("protocol_digest") == protocol_digest
    )


def _service_reuse(snapshot, result, plan, state, campaign, *, plan_ref, state_ref):
    """Report the service controller's retained assessment without re-running it."""
    settings = plan.get("evaluation_settings")
    protocol_id = settings.get("protocol_id") if isinstance(settings, dict) else None
    if (
        type(plan.get("schema_version")) is not int or plan["schema_version"] != 3
        or type(state.get("schema_version")) is not int or state["schema_version"] != 2
        or plan.get("evaluation_mode") != "service_reuse"
        or campaign.get("evaluation_mode") != "service_reuse"
        or not isinstance(protocol_id, str) or not protocol_id
        or state.get("protocol_id") != protocol_id or campaign.get("protocol_id") != protocol_id
        or campaign.get("ranking_policy") != plan.get("ranking_policy")
        or campaign.get("diagnosis_required", False) != plan.get("diagnosis_required", False)
    ):
        raise ValueError("Incompatible service campaign records")
    protocol, protocol_ref = snapshot.object("frozen/evaluation.json", "protocol", required=True)
    if protocol != settings:
        raise ValueError("Retained service protocol and plan disagree")
    result["campaign"].update(
        id=campaign.get("campaign_id"), task_kind=plan.get("task_source"), task=plan.get("task"),
        plan_ref=plan_ref,
        acceptance_basis={"protocol_id": protocol_id, "protocol_ref": protocol_ref},
    )
    result["execution"] = {
        "namespace": "inferrsi.harness.optimization",
        "evaluation_mode": "service_reuse",
        "state": state.get("state"),
        "completed_rounds": sum(row.get("terminal") is True for row in state["rounds"]),
        "round_limit": plan.get("round_limit"),
        "started_at": timestamp(state.get("started_at")),
    }
    for field, candidate in (("baseline", state.get("initial_reference")),
                             ("selected_candidate", state.get("best"))):
        if candidate:
            result[field] = {
                key: candidate.get(key) for key in ("candidate_id", "revision", "kind")
            }
    if state.get("state") in ("completed", "blocked"):
        result["export"]["kind"] = "final"
    final = state.get("final")
    if final is None:
        gap(result, "FINAL_NOT_RUN", "final_acceptance", "Independent final evaluation is absent")
        return
    if (not isinstance(final, dict) or final.get("kind") != "final"
            or final not in state["attempts"]):
        raise ValueError("Service final is missing from committed attempts")
    observation, ref = snapshot.object(final["path"] + "/observation.json", "assessment")
    retained = observation == final
    if not retained:
        gap(result, "CACHED_ASSESSMENT_UNVERIFIED", ref,
            "The retained final is unavailable or differs from committed service state")
    assessment_ref = ref if retained else state_ref
    value = final.get("assessment")
    assessment(result, value, assessment_ref, scope="independent_final")
    provenance = {
        "kind": "retained_observation" if retained else "cached_state",
        "artifact_ref": assessment_ref,
        "json_pointer": "/assessment" if retained else "/final/assessment",
        "verification": "verified" if retained else "unverified",
    } if result["acceptance"]["status"] == "assessed" else None
    result["acceptance"]["assessment_provenance"] = provenance
    result["final"] = {
        "attempt_id": final.get("attempt_id"), "revision": final.get("revision"),
        "protocol_ref": protocol_ref, "assessment_ref": assessment_ref,
        "assessment_provenance": provenance,
        "binding": {"verified": False, "kind": None},
    }
    gap(result, "CANDIDATE_BINDING_UNVERIFIED", "final_acceptance",
        "Delivery acceptance requires a digest-bound run and configuration")
    if (state.get("state") == "completed" and state.get("pending") is None
            and result["acceptance"]["verdict"] in ("PASS", "FAIL")):
        result["completion"] = {
            "status": "completed",
            "reason": "Service controller recorded a completed independent final" if retained else
            "Service controller recorded a completed independent final in unverified cached state",
        }


def iterative(snapshot, result):
    plan, plan_ref = snapshot.object("plan.json", "plan", required=True)
    state, state_ref = snapshot.object("state.json", "control", required=True)
    campaign, campaign_ref = snapshot.object("campaign.json", "campaign", required=True)
    result["sources"] = [
        {"artifact_ref": ref, "type": kind, "revision": snapshot.entries[ref]["source_revision"]}
        for ref, kind in (
            (plan_ref, "plan"),
            (state_ref, "optimization_state"),
            (campaign_ref, "campaign"),
        )
    ]
    if (plan.get("schema_version") == 3 or plan.get("evaluation_mode") == "service_reuse"
            or campaign.get("evaluation_mode") == "service_reuse"):
        _service_reuse(
            snapshot, result, plan, state, campaign, plan_ref=plan_ref, state_ref=state_ref,
        )
        return
    if (
        type(plan.get("schema_version")) is not int
        or plan["schema_version"] not in (1, 2)
        or type(state.get("schema_version")) is not int
        or state["schema_version"] != 1
    ):
        raise ValueError("Unsupported optimization record version")
    if digest(plan) != state.get("plan_digest") or campaign.get("plan_digest") != digest(plan):
        raise ValueError("Frozen plan and committed state disagree")
    result["campaign"].update(
        id=campaign.get("campaign_id"),
        goal=plan.get("goal"),
        task_kind=plan["task_source"],
        acceptance_basis=plan.get("evaluation_settings"),
        plan_ref=plan_ref,
        task=plan.get("task"),
        instructions_ref="source:frozen/TASK.md",
    )
    frozen_refs = [
        snapshot.file("frozen/" + name, "protocol", expected)
        for name, expected in plan["frozen_files"].items()
    ]
    # A changed member set also invalidates the frozen task, even if known files match.
    frozen = snapshot.path("frozen")
    if frozen.is_dir():
        snapshot.watch_tree("frozen")
        actual = {p.relative_to(frozen).as_posix() for p in frozen.rglob("*") if p.is_file()}
        if actual != set(plan["frozen_files"]):
            gap(result, "FROZEN_INPUTS_CHANGED", "final_acceptance", "Frozen file set changed")
    for context in state.get("contexts", []):
        snapshot.file(context["path"], "knowledge", context.get("sha256"))
    best = state.get("best")
    baseline = snapshot.candidate(plan["baseline_path"], plan.get("baseline_sha256"))
    result["baseline"] = {**baseline, "configuration": plan.get("evaluation_settings")}
    selected = None
    if best:
        selected = (
            snapshot.candidate(best["path"], best.get("sha256"))
            if best.get("path")
            else {"fingerprint": None, "verified": False}
        )
        result["selected_candidate"] = {
            **best,
            **selected,
            "configuration": plan.get("evaluation_settings"),
        }
    rounds = state.get("rounds", [])
    final = state.get("final")
    parsed = []
    final_value = None
    final_refs = []
    final_candidate = None
    final_observation = None
    final_assessment_verified = False
    result["rounds"], result["metrics"], result["checks"] = [], [], []
    records = [*rounds, *([final] if final else [])]
    for index, record in enumerate(records):
        is_final = index == len(rounds)
        phase = "final" if is_final else "search"
        directory = record["path"]
        observation, ref = snapshot.object(
            directory + "/observation.json", "assessment", record.get("observation_sha256")
        )
        # Compare cached assessment with its independently retained original.
        if observation is not None and observation != {
            k: v for k, v in record.items() if k != "observation_sha256"
        }:
            observation = None
            gap(result, "ASSESSMENT_CONFLICT", ref, "Cached and retained observations disagree")
        # Committed state retains history when the original is lost or conflicts;
        # this fallback is never current verification.
        historical = observation if observation is not None else record
        assessment_ref = ref if observation is not None else state_ref
        provenance = {
            "kind": "retained_observation" if observation is not None else "cached_state",
            "artifact_ref": assessment_ref,
            "json_pointer": (
                "" if observation is not None else "/final" if is_final else f"/rounds/{index}"
            )
            + "/assessment",
            "verification": "verified" if observation is not None else "unverified",
        }
        value = historical.get("assessment")
        if (
            not isinstance(value, dict)
            or value.get("status")
            not in ("completed", "candidate_failure", "infrastructure_failure", "interrupted")
            or value.get("verdict") not in ("PASS", "FAIL", "INCONCLUSIVE")
        ):
            value = None
            gap(
                result,
                "ASSESSMENT_UNAVAILABLE",
                ref,
                "No readable assessment remains in the retained observation or committed state",
            )
        elif observation is None:
            gap(
                result,
                "CACHED_ASSESSMENT_UNVERIFIED",
                ref,
                "Cached historical assessment from state.json is retained for audit; "
                "the original observation is unavailable or conflicts. Current verification "
                "is not established by this cached record.",
            )
        candidate = (
            snapshot.candidate(
                directory + "/" + plan["candidate_name"], record.get("candidate_sha256")
            )
            if record.get("candidate_sha256")
            else None
        )
        interrupted = (value or {}).get("status") == "interrupted"
        execution = historical.get("execution") or {}
        if interrupted:
            recovery = historical.get("recovery")
            evidence_refs = []
            if (isinstance(recovery, dict) and isinstance(recovery.get("path"), str)
                    and isinstance(recovery.get("sha256"), str)):
                evidence_refs.append(snapshot.file(
                    recovery["path"], "recovery", recovery["sha256"]
                ))
            else:
                gap(result, "RECOVERY_EVIDENCE_MISSING", ref, "Recovery evidence is unavailable")
        else:
            evidence_refs = [snapshot.file(
                directory + "/execution/execution.json", "execution", record.get("execution_sha256")
            )]
        for name, expected in (value or {}).get("evidence_files", {}).items():
            evidence_refs.append(snapshot.file(directory + "/" + name, "measurement", expected))
        usage_source = (record.get("observations") or {}).get("usage_source")
        usage_record = observation or {}
        if usage_source:
            usage_ref = snapshot.file(
                directory + "/agent-usage.json", "usage", usage_source.get("sha256")
            )
            if not snapshot.verified([usage_ref]):
                usage_record = {}
        parsed.append(usage_record)
        metric_start = len(result["metrics"])
        if value:
            if observation is not None:
                result["metrics"].extend(_metrics(value, plan, phase, ref))
            result["checks"].append(
                {
                    "name": "frozen_assessment",
                    "required": True,
                    "phase": phase,
                    "execution_state": value.get("status"),
                    "gate_ref": plan_ref,
                    "observation": value,
                    "verdict": value.get("verdict"),
                    "assessment_provenance": provenance,
                    "evidence_refs": list(dict.fromkeys([assessment_ref, ref, *evidence_refs])),
                }
            )
        if is_final:
            final_value, final_refs = value, [ref, *evidence_refs]
            final_candidate, final_observation = candidate, historical
            final_assessment_verified = observation is not None and value is not None
            result["final"] = {
                "attempt_id": directory.rsplit("/", 1)[-1],
                "fingerprint": record.get("candidate_sha256"),
                "protocol_ref": plan_ref,
                "assessment_ref": assessment_ref,
                "assessment_provenance": provenance if value else None,
                "execution": historical.get("execution"),
                "status": (value or {}).get("status"),
                "candidate_binding": record.get("candidate_binding"),
            }
            assessment(
                result,
                value,
                assessment_ref,
                scope=plan.get("evaluation_settings", {}).get("scope"),
            )
            if value:
                result["acceptance"]["assessment_provenance"] = provenance
        else:
            best_after = record.get("best_after", {})
            result["rounds"].append(
                {
                    "round": index + 1,
                    "attempt_id": directory.rsplit("/", 1)[-1],
                    "candidate_fingerprint": record.get("candidate_sha256"),
                    "candidate_id": record.get("candidate_id"),
                    "assessment_status": (value or {}).get("status"),
                    "record_verified": bool(observation is not None and candidate
                                            and candidate.get("verified")
                                            and snapshot.verified([ref, *evidence_refs])),
                    "hypothesis": record.get("hypothesis"),
                    "strategy": record.get("strategy"),
                    "knowledge_refs": record.get("knowledge_refs"),
                    "knowledge_attribution": "agent_declared",
                    "change_summary": record.get("change_summary"),
                    "execution_state": "interrupted" if interrupted else execution.get("status"),
                    "execution_returncode": execution.get("returncode"),
                    "assessment_ref": assessment_ref,
                    "assessment_provenance": provenance if value else None,
                    "verdict": (value or {}).get("verdict"),
                    "reason": (value or {}).get("reason"),
                    "score": (value or {}).get("score"),
                    "metric_refs": list(range(metric_start, len(result["metrics"]))),
                    "selection_decision": (
                        "interrupted" if interrupted else "retained"
                        if best_after.get("candidate_id") == record.get("candidate_id")
                        else "not_retained"
                    ),
                    "best_candidate": best_after,
                    "best_score": best_after.get("score"),
                }
            )
    for record in state.get("final_attempts", []):
        directory = record["path"]
        recovery = record["recovery"]
        result.setdefault("final_attempts", []).append({
            "attempt_id": directory.rsplit("/", 1)[-1],
            "status": "interrupted",
            "assessment_ref": snapshot.file(
                directory + "/observation.json", "assessment", record["observation_sha256"]
            ),
            "recovery_ref": snapshot.file(recovery["path"], "recovery", recovery["sha256"]),
        })
    if pending := state.get("pending"):
        result["rounds"].append(
            {
                "round": None if pending["kind"] == "final" else len(rounds) + 1,
                "attempt_id": pending["path"].rsplit("/", 1)[-1],
                "phase": pending["kind"],
                "candidate_fingerprint": pending.get("candidate_sha256"),
                "hypothesis": pending.get("hypothesis"),
                "change_summary": None,
                "execution_state": "pending",
                "assessment_ref": None,
                "metric_refs": [],
                "selection_decision": None,
                "best_candidate": best,
            }
        )
    terminal = state.get("state") in ("completed", "blocked")
    result["export"]["kind"] = "final" if terminal else "progress"
    result["execution"] = {
        "namespace": "inferrsi.harness.optimization",
        "state": state.get("state"),
        "budget": {
            "max_seconds": plan.get("max_seconds"),
            "final_reserve_seconds": plan.get("final_reserve_seconds"),
        },
        "completed_rounds": len(rounds),
        "round_limit": plan.get("round_limit"),
        "round_mode": plan.get("round_mode"),
        "stop_reason": state.get("stop_reason"),
        "started_at": timestamp(state.get("started_at")),
        "ended_at": timestamp(state.get("settled_at")),
    }
    if gate := state.get("cleanup_unconfirmed"):
        result["execution"]["cleanup_unconfirmed"] = snapshot.file(
            gate["path"], "recovery", gate["recovery_sha256"]
        )
    rounds_complete = (
        len(rounds) == plan["round_limit"]
        if plan["round_mode"] == "exact"
        else 0 < len(rounds) <= plan["round_limit"] and bool(state.get("stop_reason"))
    )
    finished = (
        rounds_complete
        and final_value is not None
        and final_value.get("status") in ("completed", "candidate_failure")
        and (final_observation.get("execution") or {}).get("status") in ("completed", "failed")
        and state.get("pending") is None
    )
    result["completion"] = {
        "status": "completed" if finished else "incomplete",
        "reason": "Required search and independent final assessment completed"
        if finished
        else "Required rounds or independent final assessment are incomplete",
    }
    if finished and not final_assessment_verified:
        result["completion"]["reason"] = (
            "Required search and independent final assessment completed according to "
            "cached state; unverified against the retained final observation"
        )
    if not final:
        gap(result, "FINAL_NOT_RUN", "final_acceptance", "Independent final evaluation is absent")
    fingerprint_bound = bool(
        selected
        and final_candidate
        and selected["verified"]
        and final_candidate["verified"]
        and selected["fingerprint"] == final_candidate["fingerprint"]
    )
    # Substitute metadata cannot override a contradictory file fingerprint.
    substitute_bound = (
        not (best or {}).get("sha256")
        and not (final or {}).get("candidate_sha256")
        and _binding(
            snapshot,
            (best or {}).get("binding"),
            (final or {}).get("candidate_binding"),
            attempt_id=(final or {}).get("path", "").rsplit("/", 1)[-1],
            protocol_digest=state["plan_digest"],
        )
    )
    bound = fingerprint_bound or substitute_bound
    if result["final"] is not None:
        result["final"]["binding"] = {
            "verified": bound,
            "kind": "fingerprint"
            if fingerprint_bound
            else "exact_revision"
            if substitute_bound
            else None,
        }
        if not bound:
            gap(
                result,
                "CANDIDATE_BINDING_UNVERIFIED",
                "final_acceptance",
                "Neither file fingerprint nor exact revision/run/config binding verifies",
            )
    current = (
        bound
        and final_assessment_verified
        and snapshot.verified(frozen_refs)
        and snapshot.verified(final_refs)
        and baseline["verified"]
        and not state.get("integrity_error")
        and not any(g["code"] == "FROZEN_INPUTS_CHANGED" for g in result["gaps"])
    )
    result["acceptance"]["delivery_accepted"] = bool(
        finished and current and result["acceptance"]["verdict"] == "PASS"
    )
    optimization_speedup = None
    if best and best.get("kind") == "baseline":
        result["outcome"] = {
            "kind": "baseline_retained",
            "reason": "Controller retained the baseline",
        }
        # A final without a usable score (paired statistics unavailable) shows no speedup.
        if (finished and current and final_value.get("status") == "completed"
                and number(final_value.get("score")) is not None):
            optimization_speedup = 1.0
    elif result["acceptance"]["delivery_accepted"]:
        selection = plan.get("selection", {})
        score = number(final_value.get("score"))
        baseline_score = number(final_value.get("baseline_score", selection.get("initial_score")))
        improved = (
            score is not None
            and baseline_score is not None
            and (
                score < baseline_score
                if selection.get("direction") == "minimize"
                else score > baseline_score
            )
        )
        if improved and final_value.get("eligible", True):
            result["outcome"] = {
                "kind": "improved",
                "reason": "Selected code passed independent final",
            }
            optimization_speedup = number(final_value.get("speedup"))
            if optimization_speedup is None and selection.get("metric") == "speedup":
                optimization_speedup = score
    result["outcome"]["optimization_speedup"] = optimization_speedup
    result["usage"]["tokens"] = _usage(parsed[: len(rounds)], state_ref, "settled_search_rounds")
    if final:
        # A final caller export observes the whole session; never add it to round usage.
        result["usage"]["session_tokens"] = _usage(
            parsed[-1:], final_refs[0], "caller_session_export"
        )
        result["usage"]["session_tokens"]["coverage"] = "unknown"
    if plan.get("task_source") == "benchmark":
        from ...benchmark.summary import single

        result["benchmark_metrics"] = single(
            plan.get("report_metadata", {}).get("benchmark_metrics"),
            result["rounds"], final_value, best or {}, selection=plan.get("selection"),
            final_verified=bool(finished and current and final_value
                                and final_value.get("status") == "completed"
                                and (final_value.get("quality_passed") is True
                                     or final_value.get("verdict") == "PASS")),
            usage=result["usage"].get("session_tokens", result["usage"].get("tokens")),
        )
    start = number(state.get("started_at"))
    end = number(state.get("settled_at"))
    if end is None:
        from datetime import datetime

        end = datetime.fromisoformat(result["export"]["snapshot_at"]).timestamp()
    if start is not None and end >= start:
        result["usage"]["wall_seconds"] = {
            "value": end - start,
            "source": state_ref,
            "coverage": "complete" if terminal else "partial",
        }
