import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..infra.artifacts import atomic_write_json, sha256
from ..infra.executors.local import execute_command
from ..knowledge_operations import KnowledgeReader


def global_skills() -> list[str]:
    # Disable global skills for this client only; do not modify user configuration.
    return sorted(
        str(path.resolve())
        for root in (Path.home() / ".codex/skills", Path.home() / ".agents/skills")
        if root.is_dir()
        for path in root.rglob("SKILL.md")
    )


def client_config() -> dict:
    return {
        "sandbox_mode": "danger-full-access",
        "approval_policy": "never",
        "project_doc_max_bytes": 0,
        "web_search": "disabled",
        "features.apps": False,
        "features.plugins": False,
        "features.memories": False,
        "features.browser_use": False,
        "features.computer_use": False,
        "features.multi_agent": False,
        "features.daemon_auto_start": False,
        "skills.bundled.enabled": False,
        "skills.config": [{"path": path, "enabled": False} for path in global_skills()],
    }


def toml_value(value) -> str:
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k) + "=" + toml_value(v) for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(toml_value(item) for item in value) + "]"
    return json.dumps(value)


@dataclass(frozen=True)
class CodexClient:
    model: str
    effort: str
    timeout_seconds: float
    executable: str = "codex"

    def command(self, workspace: Path, final: Path, schema: Path, prompt: str) -> tuple[str, ...]:
        values = {**client_config(), "model_reasoning_effort": self.effort}
        argv = [
            self.executable,
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--json",
            "--skip-git-repo-check",
            "--model",
            self.model,
            "--cd",
            str(workspace),
            "--output-schema",
            str(schema),
            "--output-last-message",
            str(final),
        ]
        for key, value in values.items():
            argv.extend(("-c", key + "=" + toml_value(value)))
        return (*argv, prompt)


def normalize_usage(usage) -> dict | None:
    """Keep valid token observations; malformed containers/fields remain unknown.

    The original provider event remains in the trace for diagnosis. This view is
    shared by live parsing and retained-result reporting, including older records.
    """
    if not isinstance(usage, dict):
        return None
    return {key: value if type(value) is int and value >= 0 else None
            for key, value in usage.items()
            if key in ("input_tokens", "output_tokens", "cached_input_tokens")}


def trace_metrics(path: Path) -> dict:
    # Missing usage stays unknown; cached_input is a subset of input.
    usage, commands, errors, completed = None, [], [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["type"] == "turn.completed":
            completed += 1
            usage = normalize_usage(event.get("usage"))
        elif event["type"] in ("turn.failed", "error"):
            errors.append(event)
        elif event["type"] == "item.completed":
            item = event["item"]
            if item["type"] == "command_execution":
                commands.append(item)
    return {"usage": usage, "commands": commands, "errors": errors, "completed_turns": completed}


def valid_checks(checks) -> bool:
    return (
        isinstance(checks, dict)
        and isinstance(checks.get("passed"), bool)
        and isinstance(checks.get("assertions"), dict)
        and bool(checks["assertions"])
        and all(isinstance(value, bool) for value in checks["assertions"].values())
        and checks["passed"] == all(checks["assertions"].values())
    )


def task_verdict(execution: dict, trace: dict, output, checks) -> str:
    if execution["status"] != "completed" or trace["completed_turns"] != 1 or trace["errors"]:
        return "INCONCLUSIVE"
    if not valid_checks(checks):
        return "INCONCLUSIVE"
    return "PASS" if isinstance(output, dict) and checks["passed"] else "FAIL"


def summarize(trials: list[dict]) -> dict:
    groups = {}
    for condition in sorted({t["condition"] for t in trials}):
        selected = [t for t in trials if t["condition"] == condition]
        usage = [normalize_usage(t["observations"]["usage"]) for t in selected]
        groups[condition] = {
            "trials": len(selected),
            "verdicts": {
                v: sum(t["verdict"] == v for t in selected)
                for v in ("PASS", "FAIL", "INCONCLUSIVE")
            },
            "evaluation_errors": sum(t.get("evaluation_error") is not None for t in selected),
            "elapsed_seconds": sum(t["elapsed_seconds"] for t in selected)
            if all(t["elapsed_seconds"] is not None for t in selected)
            else None,
            "input_tokens": sum(u["input_tokens"] for u in usage)
            if all(u and u.get("input_tokens") is not None for u in usage) else None,
            "output_tokens": sum(u["output_tokens"] for u in usage)
            if all(u and u.get("output_tokens") is not None for u in usage) else None,
            "cost": None,
        }
    paired = []
    baseline = {(t["task_id"], t["repeat"]): t for t in trials if t["condition"] == "N"}
    for trial in trials:
        key = trial["task_id"], trial["repeat"]
        if trial["condition"].startswith("E") and key in baseline:
            before = baseline[key]["verdict"]
            paired.append(
                {
                    "task_id": key[0],
                    "repeat": key[1],
                    "condition": trial["condition"],
                    "N": before,
                    "E": trial["verdict"],
                    "regression": before == "PASS" and trial["verdict"] == "FAIL",
                    "recovery": before == "FAIL" and trial["verdict"] == "PASS",
                }
            )
    return {"conditions": groups, "pairs": paired, "promotion": "not_evaluated"}


def export_bundle(reader: KnowledgeReader, reference: str, destination: Path) -> dict:
    bundle = reader.read(reference)
    for name, data in bundle.content.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return bundle.view()


def run_trial(
    client: CodexClient,
    task: dict,
    condition: str,
    repeat: int,
    workspace: Path,
    trial_dir: Path,
    schema: Path,
    verifier: Path,
    prompt: str,
    deadline: float,
    *,
    timeout_seconds: float | None = None,
) -> dict:
    trial_dir.mkdir(parents=True)
    final = trial_dir / "answer.json"
    before = {
        p.relative_to(workspace).as_posix(): sha256(p) for p in workspace.rglob("*") if p.is_file()
    }
    command = client.command(workspace, final, schema, prompt)
    # An injected client may tighten the frozen limit, but cannot extend it.
    timeout = client.timeout_seconds if timeout_seconds is None else min(
        client.timeout_seconds, timeout_seconds)
    execution = execute_command(
        command,
        workspace,
        trial_dir / "agent",
        min(deadline, time.monotonic() + timeout),
    )
    atomic_write_json(trial_dir / "execution.json", execution)
    try:
        parser = getattr(client, "trace_metrics", trace_metrics)
        trace = parser(trial_dir / "agent/stdout.log")
    except (ValueError, KeyError, TypeError, FileNotFoundError) as error:
        trace = {
            "usage": None,
            "commands": [],
            "errors": [type(error).__name__],
            "completed_turns": 0,
        }
    evaluation_error = None
    if execution["status"] != "completed":
        evaluation_error = "agent_" + execution["status"]
    elif trace["completed_turns"] != 1 or trace["errors"]:
        evaluation_error = "agent_trace_error"
    output, checks, verification = None, None, None
    if evaluation_error is None:
        if not final.is_file():
            evaluation_error = "missing_output"
        else:
            try:
                output = json.loads(final.read_text(encoding="utf-8"))
            except ValueError:
                evaluation_error = "invalid_output_json"
    if evaluation_error is None:
        verification = execute_command(
            (sys.executable, str(verifier), str(workspace / "task.json"), str(final)),
            workspace,
            trial_dir / "verification",
            min(deadline, time.monotonic() + 30),
        )
        result_path = trial_dir / "verification/result.json"
        if verification["status"] not in ("completed", "failed"):
            evaluation_error = "verifier_" + verification["status"]
        elif not result_path.is_file():
            evaluation_error = "missing_verifier_result"
        else:
            try:
                raw_checks = json.loads(result_path.read_text(encoding="utf-8"))
            except ValueError:
                evaluation_error = "invalid_verifier_result"
            else:
                if not valid_checks(raw_checks):
                    evaluation_error = "invalid_verifier_result"
                else:
                    # Keep raw results in verification/result.json; accept validated fields only.
                    checks = {key: raw_checks[key] for key in ("passed", "assertions")}
                    if verification["returncode"] != (0 if checks["passed"] else 1):
                        evaluation_error = "verifier_exit"
    after = {
        p.relative_to(workspace).as_posix(): sha256(p) for p in workspace.rglob("*") if p.is_file()
    }
    verdict = task_verdict(execution, trace, output, checks)
    if before != after:
        evaluation_error = evaluation_error or "inputs_changed"
    if evaluation_error is not None:
        verdict = "INCONCLUSIVE"
    record = {
        "task_id": task["id"],
        "condition": condition,
        "repeat": repeat,
        "split": task["split"],
        "execution_state": execution["status"],
        "verdict": verdict,
        "evaluation_error": evaluation_error,
        "checks": checks,
        "verification": verification,
        "elapsed_seconds": execution["elapsed_seconds"],
        "observations": trace,
        "inputs_unchanged": before == after,
        "input_hashes": before,
        "output_sha256": sha256(final) if final.is_file() else None,
    }
    atomic_write_json(trial_dir / "result.json", record)
    return record
