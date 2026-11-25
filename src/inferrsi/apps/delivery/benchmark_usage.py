"""Project identity-bound native usage for single and paired Benchmark reports."""

from pathlib import Path

from ...benchmark.summary import POLICY, supported_policy, token_usage
from ...harness import agent_sessions
from ...harness.usage import normalize_usage
from .schema import number
from .snapshot import Snapshot, SnapshotChanged


def terminal_token_usage(host, payload, *, trial_id, control, source):
    """A terminal meter needs a matching session, interval and declared full scope."""
    coverage = payload.get("benchmark_token_coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    native = host.get("native_session") or {}
    usage = normalize_usage(payload.get("usage"))
    bound = (payload.get("usage_scope") == "session_total"
             and usage is not None and usage == host.get("usage")
             and all(payload.get(key) == native.get(key)
                     for key in ("host", "host_id", "session_id")))
    start, end = (number(coverage.get(key)) for key in ("started_at", "ended_at"))
    campaign_start, campaign_end = (number(control.get(key))
                                    for key in ("started_at", "settled_at"))
    complete = (
        bound and host.get("state") == payload.get("state") == "completed"
        and bool(native.get("session_id"))
        and coverage.get("trial_id") == trial_id
        and coverage.get("session_id") == native["session_id"]
        and coverage.get("scope") == POLICY["token_scope"]
        and isinstance(coverage.get("includes"), dict)
        and all(coverage["includes"].get(key) is True for key in (
            "pre_start", "retrieval", "failures_retries", "final"))
        and start is not None and end is not None
        and campaign_start is not None and campaign_end is not None
        and start <= campaign_start <= campaign_end <= end
    )
    return token_usage({"value": usage if bound else None, "source": source,
                        "scope": coverage.get("scope"),
                        "coverage": "complete" if complete else "partial"})


def update_metrics(metrics, usage):
    metrics["token_usage"] = usage
    if usage["total_tokens"] is not None:
        metrics["missing_reasons"].pop("token_usage", None)
    else:
        metrics["missing_reasons"]["token_usage"] = [usage["missing_reason"]]


def attach_native_usage(snapshot, result, job):
    """Read an explicitly selected retained job; never infer a host from counters."""
    if result.get("benchmark_metrics") is None:
        raise ValueError("--agent-job requires a retained Benchmark campaign")
    native = Snapshot(job, snapshot.observed_at)
    request, _ = native.object("request.json", "native_request", required=True)
    state, state_ref = native.object("state.json", "native_state", required=True)
    native.file("prompt.md", "native_prompt", request.get("prompt_sha256"))
    # Validate paths before the Harness reader opens them. Keep all original receipts.
    for record in [*state.get("receipts", []), *state.get("artifacts", [])]:
        native.file(record["path"], "native_evidence", record["sha256"])
    for index, record in enumerate(request.get("frozen_inputs", [])):
        path = Path(record["path"]).absolute()
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("Symbolic native frozen input")
        dependency = Snapshot(path.parent, snapshot.observed_at)
        dependency.file(path.name, "native_frozen_input", record["sha256"])
        # Include alongside the job: each source keeps its own root and stability probe.
        snapshot.include(dependency, f"agent-input-{index}:")
    host = agent_sessions.status(job)
    if (host["request"] != request or host["last_observation"] != state["last_observation"]
            or host["usage"] != state["usage"] or host["state"] != state["state"]
            or host["native_session"] != state["native_session"]):
        raise SnapshotChanged("Native job changed during snapshot")
    receipt = host["last_observation"]
    payload, ref = (native.object(receipt["path"], "native_usage", receipt["sha256"],
                                  required=True) if receipt else ({}, state_ref))
    plan, _ = snapshot.object("plan.json", "plan", required=True)
    control, _ = snapshot.object("state.json", "control", required=True)
    coverage = payload.get("benchmark_token_coverage") or {}
    workspace_bound = snapshot.root.resolve().is_relative_to(Path(request["workspace"]).resolve())
    policy = plan.get("report_metadata", {}).get("benchmark_metrics")
    usage = None
    # A standalone job can contain several campaigns: bind the exact frozen plan too.
    if (supported_policy(policy) and workspace_bound and isinstance(coverage, dict)
            and coverage.get("campaign_plan_digest") == control["plan_digest"]):
        usage = terminal_token_usage(host, payload, trial_id=plan.get("condition"),
                                     control=control, source=ref)
    refs = snapshot.include(native, "agent-job:")
    if usage is not None and usage["observed_tokens"] is not None:
        usage["source"] = refs[ref]
        result["usage"]["session_tokens"] = {
            "value": {key: usage[key] for key in (
                "input_tokens", "output_tokens", "cached_input_tokens")},
            "coverage": usage["coverage"], "scope": usage["scope"], "source": usage["source"],
        }
        update_metrics(result["benchmark_metrics"], usage)
    result["sources"].append({"artifact_ref": refs[ref], "type": "native_agent_usage",
                              "revision": native.entries[ref]["source_revision"]})
