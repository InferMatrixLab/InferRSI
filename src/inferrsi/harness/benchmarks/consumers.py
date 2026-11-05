"""Thin consumers; no alternate runner, agent client or result truth."""

import json
import math
import time
from pathlib import Path

from ...infra.artifacts import atomic_write_json
from ..scenarios.external import execute_trial
from ..skill_evaluation import valid_checks


def run_action(task, candidate: Path, action: str, output: Path, *, timeout_seconds: float) -> dict:
    """Execute trusted local source. This API is not an untrusted-code sandbox."""
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= 7 * 24 * 3600
    ):
        raise ValueError("Timeout must be positive, finite and at most seven days")
    command = task.command(action, candidate)
    return execute_trial(
        command,
        candidate.resolve().parent,
        output.resolve(),
        time.monotonic() + timeout_seconds,
        task.manifest["measurement"]["key"] if action == "measure" else None,
    )


def grade_artifact(task, candidate: Path, output: Path, *, timeout_seconds: float) -> dict:
    """Independent correctness for offline engineering evaluation.

    Checks have SkillEval's existing shape. An agent/skill comparison must still
    establish its own task delivery, trace, budget and matched conditions.
    """
    identity = task.identity(candidate)
    execution = run_action(task, candidate, "check", output, timeout_seconds=timeout_seconds)
    result, checks = None, None
    try:
        result = json.loads(Path(execution["result_path"]).read_text(encoding="utf-8"))
        task.assert_unchanged()
        if (
            task.identity(candidate) == identity
            and result.get("identity") == identity
            and result.get("action") == "check"
            and result.get("status") == "completed"
        ):
            proposed = {key: result.get(key) for key in ("passed", "assertions")}
            if (
                valid_checks(proposed)
                and execution["status"] in {"completed", "failed"}
                and execution["returncode"] == (0 if proposed["passed"] else 1)
            ):
                checks = proposed
    except (OSError, ValueError, TypeError):
        pass
    verdict = "INCONCLUSIVE" if checks is None else "PASS" if checks["passed"] else "FAIL"
    record = {
        "scope": "artifact-correctness-only",
        "identity": identity,
        "verdict": verdict,
        "checks": checks,
        "execution_status": execution["status"],
        "agent_benefit": "not measured",
    }
    atomic_write_json(output / "artifact-evaluation.json", record)
    return record
