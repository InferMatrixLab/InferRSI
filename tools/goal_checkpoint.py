from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from inferrsi.infra.artifacts import digest, sha256
from tools.skill_eval_compare import CONTROLLERS, ROLES, ROOT, read_report

Action = Literal[
    "repair_evidence", "prepare_new_plan", "stop_budget", "wait_dependency",
    "wait_acceptance", "request_authorization", "propose_step", "report_accepted",
]


@dataclass(frozen=True)
class Recommendation:
    action: Action
    reasons: tuple[str, ...]
    evidence: tuple[str, ...]
    input_sha256: str


def _fields(value, required: set[str], optional: set[str] = frozenset()) -> None:
    if not isinstance(value, dict) or required - value.keys() or (
        value.keys() - required - optional
    ):
        raise ValueError("Missing or unsupported checkpoint input fields")


def _text(value) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Checkpoint text fields must be nonempty strings")


def _hash(value) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Expected a lowercase SHA-256 digest")


def _pin(value) -> None:
    _fields(value, {"path", "sha256"})
    _text(value["path"])
    _hash(value["sha256"])
    if Path(value["path"]).is_absolute():
        raise ValueError("Evidence paths must be relative to the goal input")


def _validate(goal: dict) -> None:
    _fields(goal, {"schema_version", "id", "title", "scope", "acceptance_owner", "criteria",
                   "dependencies", "next_step", "plan_sha256", "authorization"})
    if type(goal["schema_version"]) is not int or goal["schema_version"] != 1:
        raise ValueError("Unsupported goal checkpoint schema")
    for name in ("id", "title", "next_step"):
        _text(goal[name])
    _hash(goal["plan_sha256"])
    _pin(goal["scope"])
    if goal["acceptance_owner"] is not None:
        _text(goal["acceptance_owner"])
    if not isinstance(goal["criteria"], list) or not goal["criteria"]:
        raise ValueError("Explicit nonempty accepted criteria are required")
    for criterion in goal["criteria"]:
        _fields(criterion, {"id", "description", "evidence", "acceptance"})
        _text(criterion["id"])
        _text(criterion["description"])
        if not isinstance(criterion["evidence"], list):
            raise ValueError("Criterion evidence must be a list of pinned files")
        for pin in criterion["evidence"]:
            _pin(pin)
        if criterion["acceptance"] is not None:
            _pin(criterion["acceptance"])
    if len({c["id"] for c in goal["criteria"]}) != len(goal["criteria"]):
        raise ValueError("Criterion IDs must be unique")
    if not isinstance(goal["dependencies"], list):
        raise ValueError("Dependencies must be an explicit list")
    for dependency in goal["dependencies"]:
        _fields(dependency, {"id", "description", "state", "evidence"})
        _text(dependency["id"])
        _text(dependency["description"])
        if dependency["state"] not in ("waiting", "resolved"):
            raise ValueError("Dependency state must be waiting or resolved")
        _pin(dependency["evidence"])
    if len({d["id"] for d in goal["dependencies"]}) != len(goal["dependencies"]):
        raise ValueError("Dependency IDs must be unique")
    if goal["authorization"] is not None:
        _pin(goal["authorization"])


def criterion_sha256(goal: dict, criterion: dict) -> str:
    return digest({"goal_id": goal["id"], "scope": goal["scope"],
                   "plan_sha256": goal["plan_sha256"],
                   "criterion": {k: criterion[k] for k in ("id", "description", "evidence")}})


def _trial_problem(trial: dict) -> str | None:
    error = trial.get("evaluation_error")
    if trial.get("inputs_unchanged") is False:
        return "inputs_changed"
    if error in ("interrupted_attempt", "inputs_changed") or (error and error.startswith(
        ("missing_retained_", "invalid_retained_", "retained_")
    )):
        return error
    if trial["missing"]:
        return None
    expected = trial["evidence_sha256"]
    if expected is None or trial["output_sha256"] != trial["retained_output_sha256"] or any(
        trial["retained_evidence_sha256"].get(name) != value for name, value in expected.items()
    ):
        # A recorded execution error must not hide independently damaged evidence.
        return "retained_trial_integrity_mismatch"
    return None


def recommend(checkpoint: dict) -> Recommendation:
    def decision(action: Action, *reasons: str) -> Recommendation:
        return Recommendation(action, reasons, tuple(checkpoint["sources"]),
                              checkpoint["input_sha256"])

    if checkpoint["problems"]:
        return decision("repair_evidence", *checkpoint["problems"])
    comparison = checkpoint["comparison"]
    status = comparison["status"]
    state = status["execution_state"]
    if state == "completed" and not checkpoint["remaining"] and not checkpoint["waiting"]:
        return decision("report_accepted", "all_criteria_explicitly_accepted")
    if status.get("stop_reason") in ("token_budget", "time_budget"):
        return decision("stop_budget", "declared_limit_reached")
    if (status.get("observed_tokens") is not None
            and status["observed_tokens"] >= comparison["limits"]["token_stop_new_trials"]):
        return decision("stop_budget", "observed_token_limit_reached")
    if state == "stopped":
        return decision("prepare_new_plan", "attempt_stopped_no_resume")
    if not checkpoint["remaining"] and not checkpoint["waiting"]:
        return decision("report_accepted", "all_criteria_explicitly_accepted")
    if checkpoint["waiting"]:
        return decision("wait_dependency", *("dependency:" + d for d in checkpoint["waiting"]))
    if state == "completed":
        return decision("wait_acceptance", "criteria_not_accepted", "comparison_already_executed")
    if not checkpoint["authorized"]:
        return decision("request_authorization", "exact_plan_authorization_missing")
    return decision("propose_step", "fresh_plan_and_recorded_authorization")


def build_checkpoint(goal_path: Path, comparison_dir: Path) -> dict:
    raw_goal = goal_path.read_bytes()
    goal = json.loads(raw_goal)
    _validate(goal)
    sources = {"goal": {"sha256": hashlib.sha256(raw_goal).hexdigest()}}
    problems = []
    cache = {}

    def read(pin: dict) -> bytes | None:
        key = (pin["path"], pin["sha256"])
        if key not in cache:
            try:
                data = (goal_path.parent / pin["path"]).read_bytes()
                actual = hashlib.sha256(data).hexdigest()
            except OSError:
                data, actual = None, None
            sources[pin["path"] + "@" + pin["sha256"]] = {
                "expected_sha256": pin["sha256"], "actual_sha256": actual}
            cache[key] = data if actual == pin["sha256"] else None
            if cache[key] is None:
                problems.append("missing_or_changed:" + pin["path"])
        return cache[key]

    def record(pin: dict) -> dict | None:
        data = read(pin)
        if data is None:
            return None
        try:
            value = json.loads(data)
        except ValueError:
            value = None
        if not isinstance(value, dict):
            problems.append("invalid_record:" + pin["path"])
            return None
        return value

    read(goal["scope"])
    criteria = []
    for criterion in goal["criteria"]:
        complete = bool(criterion["evidence"])
        for pin in criterion["evidence"]:
            complete = read(pin) is not None and complete
        acceptance = record(criterion["acceptance"]) if criterion["acceptance"] else None
        accepted = False
        if acceptance is not None:
            expected = {"goal_id": goal["id"], "criterion_id": criterion["id"],
                        "criterion_sha256": criterion_sha256(goal, criterion),
                        "accepted_by": goal["acceptance_owner"], "decision": "accepted"}
            accepted = complete and goal["acceptance_owner"] is not None and acceptance == expected
            if not accepted:
                problems.append("unbound_acceptance:" + criterion["id"])
        criteria.append({**criterion, "accepted": accepted})
    waiting = []
    for dependency in goal["dependencies"]:
        read(dependency["evidence"])
        if dependency["state"] == "waiting":
            waiting.append(dependency["id"])
    authorization = record(goal["authorization"]) if goal["authorization"] else None
    authorized = False
    if authorization is not None:
        _fields(authorization, {"plan_sha256", "authorized_by", "reference"})
        _text(authorization["authorized_by"])
        _text(authorization["reference"])
        _hash(authorization["plan_sha256"])
        authorized = authorization["plan_sha256"] == goal["plan_sha256"]

    comparison = None
    sources["comparison"] = {"artifacts": {}}
    artifact_names = {"plan/freeze.json", "results/start.json", "results/status.json",
                      "results/status.receipt.json"}
    try:
        # Failed reads still need the identities of the actual damaged inputs.
        for folder in ("plan", "validator", "results"):
            artifact_names.update(p.relative_to(comparison_dir).as_posix()
                                  for p in (comparison_dir / folder).rglob("*") if p.is_file())
        report = read_report(comparison_dir)
        sources["comparison"].update(plan_sha256=report["plan_sha256"],
                                     report_sha256=digest(report))
        if report["plan_sha256"] != goal["plan_sha256"]:
            problems.append("stale_plan")
        trials = [arm for pair in report["pairs"] for arm in (pair[r] for r in ROLES)]
        trials.extend(report["discovery"])
        for trial in trials:
            artifact_names.update(trial["evidence"].values())
        for trial in trials:
            problem = _trial_problem(trial)
            if problem is not None:
                problems.append("trial:" + trial["task_id"] + ":" + trial["condition"]
                                + ":" + problem)
        status = report["status"]
        state = status["execution_state"]
        if state == "unverified":
            problems.append(status["evaluation_error"])
        elif state == "not_completed":
            if any((comparison_dir / "results").iterdir()):
                problems.append("interrupted_or_ambiguous_attempt")
        elif state in ("completed", "stopped"):
            for name in ("recorded_trials", "expected_trials", "observed_tokens"):
                if type(status[name]) is not int or status[name] < 0:
                    problems.append("invalid_status:" + name)
            if state == "stopped" and not isinstance(status["stop_reason"], str):
                problems.append("missing_stop_reason")
            recorded = sum(not t["missing"] for t in trials)
            if status["recorded_trials"] != recorded or status["expected_trials"] != len(trials):
                problems.append("inconsistent_trial_counts")
            if state == "completed" and (recorded != len(trials) or status["stop_reason"]):
                problems.append("incomplete_or_stopped_attempt")
        else:
            problems.append("unknown_execution_state")
        comparison = {name: report[name] for name in (
            "plan_sha256", "model", "limits", "status", "counts", "conditions",
            "discovery_conditions")}
        comparison["revisions"] = {r: report["arms"][r]["git_revision"] for r in ROLES}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        problems.append("comparison_unreadable_or_stale")
    for name in sorted(artifact_names):
        path = comparison_dir / name
        try:
            actual = sha256(path) if path.is_file() else None
        except OSError:
            actual = None
            problems.append("unreadable_artifact:" + name)
        sources["comparison"]["artifacts"][name] = actual
    sources["controllers"] = {}
    for name in CONTROLLERS:
        try:
            actual = sha256(ROOT / name)
        except OSError:
            actual = None
            problems.append("unreadable_controller:" + name)
        sources["controllers"][name] = actual

    checkpoint = {"schema_version": 1, "id": goal["id"], "title": goal["title"],
                  "acceptance_owner": goal["acceptance_owner"], "criteria": criteria,
                  "remaining": [c["id"] for c in criteria if not c["accepted"]],
                  "dependencies": goal["dependencies"], "waiting": waiting,
                  "next_step": goal["next_step"], "authorized": authorized,
                  "comparison": comparison, "sources": sources,
                  "problems": sorted(set(problems))}
    checkpoint["input_sha256"] = digest(checkpoint)
    checkpoint["recommendation"] = asdict(recommend(checkpoint))
    return checkpoint


def markdown(checkpoint: dict) -> str:
    def text(value) -> str:
        return str(value).replace("\n", " ").replace("\r", " ").replace("|", "\\|")

    recommendation = checkpoint["recommendation"]
    lines = [f"# Goal checkpoint: {text(checkpoint['title'])}", "",
             f"Goal: {text(checkpoint['id'])}",
             f"Acceptance owner: {text(checkpoint['acceptance_owner'] or 'unknown')}",
             f"Input SHA-256: `{checkpoint['input_sha256']}`", "",
             f"Next action: **{recommendation['action']}**",
             "Reasons: " + ", ".join(text(r) for r in recommendation["reasons"]),
             f"Proposed step: {text(checkpoint['next_step'])}", "",
             "| Criterion | Requirement | Acceptance |",
             "| --- | --- | --- |"]
    lines.extend(f"| {text(c['id'])} | {text(c['description'])} | "
                 + ("accepted" if c["accepted"] else "remaining / unknown") + " |"
                 for c in checkpoint["criteria"])
    lines.extend(["", "Dependencies:"])
    lines.extend(f"- {text(d['id'])}: {text(d['description'])} ({d['state']})"
                 for d in checkpoint["dependencies"])
    if not checkpoint["dependencies"]:
        lines.append("- None declared.")
    if checkpoint["comparison"] is not None:
        lines.extend(["", "Comparison facts (existing verdicts and usage unchanged):", "```json",
                      json.dumps(checkpoint["comparison"], sort_keys=True, indent=2,
                                 ensure_ascii=False, allow_nan=False), "```"])
    lines.extend(["", "Evidence identities:"])
    lines.extend(f"- {text(name)}: `{json.dumps(value, sort_keys=True)}`"
                 for name, value in checkpoint["sources"].items())
    lines.extend(["", "Recommendation only. This view cannot execute, resume, authorize or "
                  "accept work. Unknown usage remains unknown. Owner records are supplied "
                  "explicitly; file digests verify bytes, not the signer's identity.", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild an offline goal checkpoint")
    parser.add_argument("--goal", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        checkpoint = build_checkpoint(args.goal, args.comparison)
        output = markdown(checkpoint) if args.format == "markdown" else (
            json.dumps(checkpoint, sort_keys=True, ensure_ascii=False, indent=2,
                       allow_nan=False) + "\n")
        if args.output is None:
            print(output, end="")
        else:
            # Derived views must never overwrite their inputs or retained evidence.
            if args.output.resolve().is_relative_to(args.comparison.resolve()):
                raise ValueError("Checkpoint output must be outside the comparison evidence")
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
