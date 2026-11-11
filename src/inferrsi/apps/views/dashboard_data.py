"""Read recorded run and campaign evidence into a dashboard view model.

Only known fields and explicitly referenced artifacts are exposed. Commands
are reduced to a conservative display representation; environments, arbitrary
error messages and log contents are deliberately omitted.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path, PurePosixPath, PureWindowsPath

from ...harness.optimization_trace import read_optimization_trace
from ...harness.records import STAGES, fields
from ...harness.records.fields import (
    _file_ref,
    _inside,
    _number,
    _object,
    _object_snapshot,
    _relative_location,
    _safe_argv,
    _text,
)
from .trace import _read_events


def _optimization(candidate: dict) -> dict:
    data = candidate.get("details")
    data = data if isinstance(data, dict) else {}
    kind = data.get("change_kind")
    if kind not in ("code", "configuration", "mixed", "other"):
        kind = None
    locations = []
    raw_locations = data.get("code_locations")
    if isinstance(raw_locations, list):
        for entry in raw_locations[:50]:
            if not isinstance(entry, dict):
                continue
            path = _relative_location(entry.get("path"))
            start = entry.get("line_start")
            end = entry.get("line_end")
            revision = entry.get("revision")
            revision = (revision.lower() if isinstance(revision, str)
                        and re.fullmatch(r"[a-fA-F0-9]{7,64}", revision) else None)
            start = start if type(start) is int and 0 < start <= 10_000_000 else None
            end = end if (start is not None and type(end) is int
                          and start <= end <= 10_000_000) else None
            locations.append({"path": path, "line_start": start, "line_end": end,
                              "revision": revision,
                              "scope": _text(entry.get("scope"), "Not recorded"),
                              "note": _text(entry.get("note"), "Not recorded", 1000)})
    commands = []
    candidate_id = candidate.get("candidate_id")
    candidate_ids = {candidate_id} if isinstance(candidate_id, str) else None
    raw_commands = data.get("commands")
    if isinstance(raw_commands, list):
        for entry in raw_commands[:20]:
            if isinstance(entry, dict):
                command = _display_command(entry.get("argv"), candidate_ids=candidate_ids)
                if command is not None:
                    commands.append({"label": _text(entry.get("label"), "Caller-recorded command"),
                                     "argv": command})
    return {"kind": kind, "summary": _text(data.get("summary"), "Not recorded", 1500),
            "hypothesis": _text(data.get("hypothesis"), "Not recorded", 1500),
            "benchmark": _text(data.get("benchmark"), "Not recorded", 1500),
            "accuracy": _text(data.get("accuracy"), "Not recorded", 1500),
            "code_locations": locations, "commands": commands}


def _display_command(value: object, *, candidate_ids: set[str] | None = None) -> str | None:
    safe = _safe_argv(value, candidate_ids=candidate_ids)
    return shlex.join(safe) if safe is not None else None


def _explicit_ref(root: Path, value: object, kind: str) -> dict:
    if not isinstance(value, dict):
        return {"kind": kind, "state": "missing", "missing_reason": "not_collected"}
    if value.get("state") == "missing":
        reason = value.get("missing_reason")
        allowed = {"not_collected", "file_absent", "redacted", "not_applicable"}
        result = {"kind": kind, "state": "missing", "missing_reason": reason
                  if isinstance(reason, str) and reason in allowed else "not_collected"}
        expected = value.get("sha256")
        if isinstance(expected, str) and re.fullmatch(r"[a-fA-F0-9]{64}", expected):
            result["sha256"] = expected.lower()
        return result
    raw_path = value.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return {"kind": kind, "state": "missing", "missing_reason": "not_collected"}
    posix, windows = PurePosixPath(raw_path), PureWindowsPath(raw_path)
    if (posix.is_absolute() or windows.is_absolute() or windows.drive
            or ".." in posix.parts or ".." in windows.parts):
        return {"kind": kind, "state": "missing", "missing_reason": "unsafe_path"}
    ref = _file_ref(root, root.joinpath(*posix.parts), kind)
    if ref["state"] == "present":
        expected = value.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
            return {"kind": kind, "state": "missing", "missing_reason": "hash_not_recorded"}
        if expected.lower() != ref["sha256"]:
            return {"kind": kind, "state": "missing", "missing_reason": "hash_mismatch"}
    return ref


def _environment_signature(environment: dict, devices: object, backend: object) -> tuple | None:
    """Compare verified device/runtime identity privately; never expose it in the view."""
    if backend not in ("cuda", "ascend") or not isinstance(devices, list) or not devices:
        return None
    device = environment.get("device")
    host = environment.get("host")
    target = environment.get("target_python")
    target = target.get("environment") if isinstance(target, dict) else None
    if (not isinstance(device, dict) or device.get("status") != "available"
            or device.get("selection_verified") is not True
            or not isinstance(device.get("devices"), list)
            or not isinstance(host, dict) or not isinstance(host.get("platform"), str)
            or not host["platform"] or not isinstance(target, dict)
            or not isinstance(target.get("python"), str) or not target["python"]
            or not isinstance(target.get("packages"), dict)):
        return None
    packages = target["packages"]
    if not all(isinstance(key, str) and (value is None or isinstance(value, str))
               for key, value in packages.items()):
        return None
    if not all(isinstance(packages.get(key), str) and packages[key] for key in ("torch", "vllm")):
        return None
    runtime_identity = ()
    if backend == "ascend":
        ascend = environment.get("ascend")
        if not isinstance(ascend, dict) or not all(
            isinstance(ascend.get(k), str) and ascend[k]
            for k in ("cann_version", "firmware_version")
        ) or not all(isinstance(packages.get(k), str) and packages[k]
                     for k in ("torch_npu", "vllm_ascend")):
            return None
        runtime_identity = (ascend["cann_version"], ascend["firmware_version"])
    selected = []
    for identity in devices:
        matches = [row for row in device["devices"] if isinstance(row, dict)
                   and identity in (row.get("index"), row.get("uuid"))]
        if len(matches) != 1:
            return None
        row = matches[0]
        fields = tuple(row.get(key) for key in ("uuid", "name", "driver_version"))
        if not all(isinstance(value, str) and value for value in fields):
            return None
        selected.append(fields)
    return (backend, host["platform"], target["python"], tuple(sorted(packages.items())),
            tuple(selected), runtime_identity)


def _run(root: Path, path: Path, candidate: dict, run_id: str | None, noise: float | None,
         campaign_id: object = None, unique_candidate: bool = False,
         candidate_ref: dict | None = None, candidate_ids: set[str] | None = None) -> dict:
    if run_id is None:
        def missing(kind: str) -> dict:
            return {"kind": kind, "state": "missing", "missing_reason": "not_collected"}

        lock = repositories = environment = evaluation = status = validation = {}
        lock_ref, evaluation_ref, status_ref, quality_ref, events_ref = (
            missing(kind) for kind in ("run_lock", "evaluation", "status", "quality", "events")
        )
        evaluation_state = status_state = validation_state = event_state = "missing"
        events, corrupt = [], []
    else:
        lock, _, lock_ref = _object_snapshot(path / "run.lock.json", root, "run_lock")
        repositories, _ = _object(path / "repositories.lock.json", root)
        environment, _ = _object(path / "environment.json", root)
        evaluation, evaluation_state, evaluation_ref = _object_snapshot(
            path / "evaluation.json", root, "evaluation"
        )
        status, status_state, status_ref = _object_snapshot(path / "status.json", root, "status")
        validation, validation_state, quality_ref = _object_snapshot(
            path / "validation" / "execution.json", root, "quality"
        )
        events, corrupt, event_state, _, events_ref = _read_events(path / "events.jsonl", root)
    corrupt_sources = {"events": list(corrupt), "agent_trace": []}
    refs = {
        "run_lock": lock_ref,
        "events": events_ref,
        "evaluation": evaluation_ref,
        "status": status_ref,
        "quality": quality_ref,
        "agent_trace": _explicit_ref(root, candidate.get("agent_trace_ref"), "agent_trace"),
        "profile": _explicit_ref(root, candidate.get("profile_ref"), "profile"),
    }
    if candidate_ref is not None:
        refs["candidate_metadata"] = candidate_ref
    optimization_trace, refs["optimization_trace"] = read_optimization_trace(
        root, candidate.get("optimization_trace_ref"), campaign_id=campaign_id,
        candidate_id=candidate.get("candidate_id"), round_number=candidate.get("round"),
        unique_candidate=unique_candidate, run_id=run_id,
        round_ambiguous=candidate.get("_round_state") == "ambiguous",
    )
    def attach_declared(event: dict) -> None:
        for item in event.pop("_declared_refs", []):
            kind = item.get("kind") if isinstance(item, dict) else None
            if not isinstance(kind, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", kind):
                kind = "artifact"
            event["refs"].append(_explicit_ref(root, item, kind))

    for event in events:
        event.pop("_link_state", None)
        event["source"] = "events"
        event["refs"] = [refs["events"]]
        if event["phase"] == "measurement" and event["side"] and event["trial"]:
            trial = path / event["side"] / f'trial-{event["trial"]:03d}'
            event["refs"].extend(
                _file_ref(root, trial / name, kind)
                for name, kind in (("execution.json", "execution"), ("stdout.log", "stdout"),
                                   ("stderr.log", "stderr"))
            )
        elif event["phase"] == "quality_validation":
            event["refs"].append(refs["quality"])
        attach_declared(event)
    agent_links = {"unlinked": [], "mismatched": []}
    unlinked_events = []
    if refs["agent_trace"]["state"] == "present":
        expected = {"campaign_id": campaign_id, "candidate_id": candidate.get("candidate_id"),
                    "run_id": run_id, "round": candidate.get("round")}
        agent_events, agent_corrupt, agent_state, agent_links, agent_snapshot = _read_events(
            root / refs["agent_trace"]["path"], root, expected, unique_candidate
        )
        if (agent_state == "present" and
                agent_snapshot.get("sha256") != refs["agent_trace"].get("sha256")):
            agent_state = "changed"
        if agent_state != "present":
            refs["agent_trace"] = {**refs["agent_trace"], "state": "missing",
                                   "missing_reason": "unsafe_path" if agent_state == "unsafe"
                                   else "hash_mismatch" if agent_state == "changed"
                                   else "file_absent" if agent_state == "missing" else "corrupt"}
            agent_events = []
            agent_corrupt = []
            agent_links = {"unlinked": [], "mismatched": []}
        for event in agent_events:
            event["source"] = "agent_trace"
            event["refs"] = [refs["agent_trace"]]
            attach_declared(event)
            if event.pop("_link_state") == "unlinked":
                unlinked_events.append(event)
            else:
                events.append(event)
        corrupt.extend(agent_corrupt)
        corrupt_sources["agent_trace"] = agent_corrupt
    tool_events = [event for event in events if event["source"] == "agent_trace"
                   and event["type"] == "agent.tool"]
    refs["tool_calls"] = ({**refs["agent_trace"], "kind": "tool_calls"} if tool_events else {
        "kind": "tool_calls", "state": "missing", "missing_reason": "not_collected"
    })
    validation_status = validation.get("status")
    returncode = validation.get("returncode")
    if validation_status == "completed" and type(returncode) is int and returncode == 0:
        quality = "passed"
    elif validation_status == "failed" and type(returncode) is int and returncode != 0:
        quality = "failed"
    else:
        quality = "not_recorded"
    integrity = evaluation.get("source_integrity")
    verified_value = integrity.get("verified") if isinstance(integrity, dict) else None
    verified = verified_value if isinstance(verified_value, bool) else None
    baseline = evaluation.get("baseline") if isinstance(evaluation.get("baseline"), dict) else {}
    measured = evaluation.get("candidate") if isinstance(evaluation.get("candidate"), dict) else {}
    gain = _number(evaluation.get("improvement_pct"))
    if noise is None:
        ranges = [_number(item.get("range_pct_of_median")) for item in (baseline, measured)]
        ranges = [item for item in ranges if item is not None and item >= 0]
        noise = max(ranges) if ranges else None
    state_value = status.get("state")
    state = state_value if isinstance(state_value, str) and state_value in {
        "running", "completed", "failed", "crashed", "timeout", "cancelled", "termination_failed"
    } else "not_recorded"
    verdict_value = evaluation.get("verdict")
    verdict = verdict_value if verdict_value in ("PASS", "FAIL", "INCONCLUSIVE") else "not_recorded"
    if state == "cancelled":
        outcome = "cancelled"
    elif quality == "failed":
        outcome = "quality_failed"
    elif state in {"failed", "crashed", "timeout", "termination_failed"}:
        outcome = "failed"
    elif gain is None:
        outcome = "not_recorded"
    elif state != "completed" or verdict not in ("PASS", "FAIL"):
        outcome = "unverified"
    elif quality != "passed" or not verified:
        outcome = "unverified"
    elif noise is None:
        outcome = "noise_not_recorded"
    elif abs(gain) <= noise:
        outcome = "noise"
    else:
        outcome = "improved" if gain > 0 else "regressed"
    candidate_id = candidate.get("candidate_id")
    signature_values = [lock.get(key) for key in (
        "model", "model_revision", "workload_id", "scenario", "backend", "comparison_scope"
    )] + [evaluation.get(key) for key in ("metric_key", "metric_unit", "direction")]
    repository = repositories.get("baseline")
    snapshot = repository.get("snapshot_hash") if isinstance(repository, dict) else None
    command, devices = lock.get("baseline_command"), lock.get("device_ids")
    validator = lock.get("validation_command")
    environment_signature = _environment_signature(environment, devices, lock.get("backend"))
    valid_sequences = all(
        isinstance(seq, list) and seq and all(isinstance(item, str) and item for item in seq)
        for seq in (command, devices, validator)
    )
    signature = (tuple(signature_values) + (snapshot, tuple(command), tuple(devices),
                                              tuple(validator), environment_signature)) if (
        all(isinstance(value, str) and value for value in signature_values)
        and isinstance(snapshot, str) and snapshot and valid_sequences
        and environment_signature is not None
    ) else None
    return {
        "candidate_id": _text(candidate_id) if isinstance(candidate_id, str) else None,
        "title": _text(candidate.get("title"), "Recorded candidate"),
        "run_id": _text(run_id) if run_id else None,
        "round": candidate.get("round") if isinstance(candidate.get("round"), int)
        and not isinstance(candidate.get("round"), bool) and candidate["round"] > 0 else None,
        "round_state": candidate.get("_round_state", "not_recorded"),
        "state": state, "status_state": status_state, "evaluation_state": evaluation_state,
        "validation_state": validation_state, "event_state": event_state,
        "quality": quality, "source_verified": verified, "improvement_pct": gain,
        "minimum_improvement_pct": _number(evaluation.get("min_improvement_pct")),
        "baseline_median": _number(baseline.get("median")),
        "candidate_median": _number(measured.get("median")), "noise_band_pct": noise,
        "metric_key": _text(evaluation.get("metric_key")),
        "metric_unit": _text(evaluation.get("metric_unit")),
        "direction": evaluation.get("direction")
        if evaluation.get("direction") in ("minimize", "maximize") else None,
        "verdict": verdict,
        "outcome": outcome, "events": events, "corrupt_event_lines": corrupt,
        "corrupt_event_sources": corrupt_sources,
        "agent_trace_links": agent_links, "unlinked_agent_events": unlinked_events,
        "optimization": _optimization(candidate),
        "optimization_trace": optimization_trace,
        "benchmark_context": {"scenario": _text(lock.get("scenario"), "Not recorded"),
                              "workload": _text(lock.get("workload_id"), "Not recorded"),
                              "repetitions": lock.get("repetitions")
                              if type(lock.get("repetitions")) is int
                              and 0 < lock["repetitions"] <= 1_000_000 else None,
                              "baseline_samples": [_number(v)
                                                   for v in baseline.get("values", [])[:100]]
                              if isinstance(baseline.get("values"), list) else [],
                              "candidate_samples": [_number(v)
                                                    for v in measured.get("values", [])[:100]]
                              if isinstance(measured.get("values"), list) else []},
        "commands": {key: _display_command(lock.get(source), candidate_ids=candidate_ids)
                     for key, source in (
            ("baseline", "baseline_command"), ("candidate", "candidate_command"),
            ("accuracy", "validation_command"),
        )},
        "candidate_metadata_state": (candidate_ref.get("missing_reason", "present")
                                     if candidate_ref else "not_applicable"),
        "artifacts": refs, "_comparison_signature": signature,
    }


def _rounds(path: Path, root: Path) -> tuple[list[dict] | None, str, list[int], dict]:
    raw, ref = fields._snapshot(root, path, "rounds")
    if raw is None:
        state = "unsafe" if ref["missing_reason"] == "unsafe_path" else "missing"
        return None, state, [], ref
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError:
        return None, "corrupt", [], {**ref, "state": "missing", "missing_reason": "corrupt"}
    result, corrupt = [], []
    for line_number, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            corrupt.append(line_number)
            continue
        if (isinstance(row, dict) and isinstance(row.get("round"), int)
                and not isinstance(row.get("round"), bool) and row["round"] > 0):
            record = {"round": row["round"]}
            if isinstance(row.get("candidates"), list):
                record["candidates"] = [item for item in row["candidates"]
                                        if isinstance(item, str) and re.fullmatch(
                                            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", item
                                        )]
            decision = row.get("decision")
            if (isinstance(decision, dict) and isinstance(decision.get("candidate_id"), str)
                    and decision.get("outcome") in (
                        "adopted", "rejected", "rolled_back", "no_gain", "noise"
                    )):
                record["decision"] = {"candidate_id": _text(decision["candidate_id"]),
                                      "outcome": decision["outcome"]}
            result.append(record)
        else:
            corrupt.append(line_number)
    return result, "corrupt" if corrupt else "present", corrupt, ref


def load_dashboard(source: Path) -> dict:
    """Aggregate a single legacy run or a campaign without inventing records."""
    root = Path(source).resolve()
    if not root.is_dir():
        raise ValueError("dashboard input must be an existing directory")
    single = (root / "run.lock.json").is_file()
    campaign, campaign_state = _object(root / "campaign.json", root)
    if not single and campaign_state != "present":
        raise ValueError("dashboard input must contain run.lock.json or campaign.json")
    noise_data = campaign.get("noise") if isinstance(campaign.get("noise"), dict) else {}
    noise = _number(noise_data.get("band_pct"))
    if noise is not None and noise < 0:
        noise = None
    rounds, rounds_state, corrupt_round_lines, rounds_ref = (
        (None, "missing", [], None) if single else _rounds(root / "rounds.jsonl", root)
    )
    rows = []
    if single:
        rows.append(_run(root, root, {}, root.name, noise))
    else:
        candidate_root = root / "candidates"
        entries = []
        candidate_rounds: dict[str, set[int]] = {}
        for round_record in rounds or []:
            names = list(round_record.get("candidates", []))
            decision = round_record.get("decision")
            if isinstance(decision, dict):
                names.append(decision["candidate_id"])
            for name in names:
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
                    candidate_rounds.setdefault(name, set()).add(round_record["round"])
        if _inside(root, candidate_root) and candidate_root.is_dir():
            for directory in sorted(candidate_root.iterdir()):
                if not directory.is_dir() or directory.is_symlink():
                    continue
                metadata, state, metadata_ref = _object_snapshot(
                    directory / "candidate.json", root, "candidate_metadata"
                )
                if state != "present":
                    metadata = {"candidate_id": directory.name, "title": directory.name}
                run_id = metadata.get("run_id")
                if (not isinstance(run_id, str) or Path(run_id).name != run_id
                        or run_id in {".", ".."}):
                    run_id = None
                entries.append((directory, metadata, run_id, metadata_ref))
        known = {entry[1].get("candidate_id") for entry in entries
                 if isinstance(entry[1].get("candidate_id"), str)}
        for candidate_id in candidate_rounds:
            if candidate_id in known:
                continue
            directory = candidate_root / candidate_id
            _, _, metadata_ref = _object_snapshot(directory / "candidate.json", root,
                                                    "candidate_metadata")
            entries.append((directory, {"candidate_id": candidate_id, "title": candidate_id},
                            None, metadata_ref))
            known.add(candidate_id)
        for directory, metadata, run_id, metadata_ref in entries:
            candidate_id = metadata.get("candidate_id")
            recorded_round = metadata.get("round")
            possibilities = set(candidate_rounds.get(candidate_id, set())) \
                if isinstance(candidate_id, str) else set()
            if type(recorded_round) is int and recorded_round > 0:
                possibilities.add(recorded_round)
            metadata = {**metadata, "round": next(iter(possibilities)) if len(possibilities) == 1
                        else None, "_round_state": "ambiguous" if len(possibilities) > 1 else
                        "recorded" if possibilities else "not_recorded"}
            unique = (isinstance(candidate_id, str) and bool(candidate_id) and
                      sum(entry[1].get("candidate_id") == candidate_id for entry in entries) == 1)
            run_path = root / "runs" / run_id if run_id else directory / "missing-run"
            rows.append(_run(root, run_path, metadata, run_id, noise, campaign.get("campaign_id"),
                             unique, metadata_ref, known))
        if not rows and _inside(root, root / "runs") and (root / "runs").is_dir():
            for directory in sorted((root / "runs").iterdir()):
                if directory.is_dir() and not directory.is_symlink():
                    rows.append(_run(root, directory, {}, directory.name, noise))
    from .dashboard_external import external_record

    for row, entry in zip(rows, entries if not single else []):
        reference = entry[1].get("external_record_ref")
        if reference is not None:
            external, ref = external_record(root, reference, row["candidate_id"])
            row["artifacts"]["external_record"] = ref
            row["external"] = external
            if row["run_id"] is not None:
                external = {}
                row["external"] = {}
                row["artifacts"]["external_record"] = {**ref, "state": "missing",
                                                        "missing_reason": "conflicting_run"}
            if external:
                # External-only candidates do not promise a native harness run tree.
                row["artifacts"] = {key: value for key, value in row["artifacts"].items()
                                    if key in ("candidate_metadata", "external_record")}
                for index, source in enumerate(external["source_refs"]):
                    row["artifacts"][f"external_source_{index}"] = source
                row["metric_key"] = external["protocol"]
                row["metric_unit"] = "protocol_specific"
                row["state"] = external["state"]
                row["verdict"] = external["performance_verdict"]
                row["events"].extend(external["events"])
                row["quality"] = {"PASS": "passed", "FAIL": "failed"}.get(
                    external["quality_verdict"], "not_recorded")
                row["outcome"] = "unverified"
    decisions = {(item["round"], item["decision"]["candidate_id"]): item["decision"]["outcome"]
                 for item in (rounds or []) if "decision" in item}
    for row in rows:
        row["decision"] = decisions.get((row["round"], row["candidate_id"]), "not_recorded")
    signatures = []
    for row in rows:
        signature = row.pop("_comparison_signature")
        if row["improvement_pct"] is not None:
            signatures.append(signature)
    comparison_state = "comparable" if signatures else "no_data"
    if len(signatures) >= 2:
        if any(signature is None for signature in signatures):
            comparison_state = "unverified"
        elif len(set(signatures)) != 1:
            comparison_state = "incompatible"
    valid_gains = [row["improvement_pct"] for row in rows if row["improvement_pct"] is not None
                   and row["quality"] == "passed" and row["source_verified"] is True
                   and row["state"] == "completed" and row["verdict"] in ("PASS", "FAIL")
                   and row["decision"] != "rolled_back"]
    if comparison_state != "comparable":
        valid_gains = []
    best = max(valid_gains) if valid_gains else None
    goal = campaign.get("goal") if isinstance(campaign.get("goal"), dict) else {}
    target = _number(goal.get("target_improvement_pct"))
    if target is None and single and rows:
        target = rows[0]["minimum_improvement_pct"]
    diagnostics = []
    for row in rows:
        identity = {"candidate_id": row["candidate_id"], "run_id": row["run_id"],
                    "round": row["round"]}
        if row["outcome"] == "failed" and row["artifacts"]["status"]["state"] == "present":
            diagnostics.append({**identity, "kind": "execution_failed",
                                "refs": [row["artifacts"]["status"]]})
        elif row["outcome"] == "quality_failed" and row["improvement_pct"] is not None \
                and row["improvement_pct"] > 0:
            refs = [row["artifacts"][key] for key in ("evaluation", "quality")]
            if all(ref["state"] == "present" for ref in refs):
                diagnostics.append({**identity, "kind": "quality_failed_with_gain", "refs": refs})
        if row["outcome"] in {"noise", "regressed"}:
            ref = row["artifacts"]["evaluation"]
            if ref["state"] == "present":
                diagnostics.append({**identity, "kind": "within_noise" if row["outcome"] == "noise"
                                    else "measured_regression", "refs": [ref]})
        if row["decision"] == "rolled_back":
            if rounds_ref and rounds_ref["state"] == "present":
                diagnostics.append({**identity, "kind": "rolled_back", "refs": [rounds_ref]})
    recorded = {event["stage"] for row in rows for event in row["events"] if event["stage"]}
    if single:
        story = {"state": "not_applicable", "versions": []}
    else:
        from ...harness.optimization_story import build_story

        story = build_story(root, rows, decisions, campaign.get("campaign_id"))
    collection = campaign.get("collection")
    collection = collection if isinstance(collection, dict) else {}
    declared = campaign.get("stages_declared")
    if not isinstance(declared, list):
        declared = None
    return {
        "campaign_id": _text(campaign.get("campaign_id"), "Single run" if single else "Campaign"),
        "synthetic": campaign.get("synthetic") is True,
        "rounds": rounds, "rounds_state": rounds_state,
        "corrupt_round_lines": corrupt_round_lines,
        "candidates": rows,
        "integration": {"state": "not_connected" if not rows else "connected",
                        "stage_declaration": "explicit_empty" if declared == [] else
                        "missing" if declared is None else "declared",
                        "external_records": sum(bool(row.get("external")) for row in rows),
                        "collection": {"state": _text(collection.get("state"), ""),
                                       "observed_at": _text(collection.get("observed_at"), "")}},
        "overview": {"comparison_state": comparison_state,
                     "best_improvement_pct": best, "target_improvement_pct": target,
                     "target_gap_pct": (_number(target - best)
                                        if target is not None and best is not None else None)},
        "stages": [{"name": stage, "state": "recorded" if stage in recorded else
                    "not_applicable" if declared is not None and stage not in declared else
                    "stage_not_recorded"} for stage in STAGES],
        "diagnostics": diagnostics,
        "story": story,
    }
