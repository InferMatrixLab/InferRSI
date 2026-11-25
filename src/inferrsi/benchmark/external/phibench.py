"""Read Φ-Bench task packages and judge its grader output.

Φ-Bench (arXiv:2609.10226, Apache-2.0) ships every task as a Docker build
context with a starting tree, a grader under ``tests/`` and reference landings
under ``solution/``. This module only reads a local clone of the suite; it
never builds, runs or edits a task.

The control expectations follow the suite's own self-check (README "Important
Conventions" and SCORING.md):

- ``noop`` leaves the starting tree alone and must score 0;
- ``negative`` lands a known-bad change and must score 0;
- ``oracle`` lands the reference change. Implementation tasks must score 1.0.
  Performance tasks score 0 by design when they tie the calibrated anchor
  (curve ``reward_md_log_speedup_v2_oracle_zero``), so the oracle is judged on
  passing every gate and reproducing ``ref_speedup`` within a caller-supplied
  relative tolerance.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

SUITE = "phibench"
CONTROLS = ("noop", "negative", "oracle")
INDEX = "tasks_index.json"
_TASK_ID = re.compile(r"(kfc|lh|e2e)/[A-Za-z0-9][A-Za-z0-9_.-]*")


@dataclass(frozen=True)
class PhiTask:
    """One task entry from ``tasks_index.json`` resolved against a local clone."""

    suite_root: Path
    bench: str
    name: str
    package_root: Path
    gpus: int
    reward_class: str
    ref_speedup: float | None
    primary_edit_paths: tuple[str, ...]
    has_oracle: bool
    max_submissions: int | None

    @property
    def task_id(self) -> str:
        return f"{self.bench}/{self.name}"

    def describe(self) -> dict:
        return {
            "suite": SUITE,
            "task": self.task_id,
            "package_root": str(self.package_root),
            "gpus": self.gpus,
            "reward_class": self.reward_class,
            "ref_speedup": self.ref_speedup,
            "primary_edit_paths": list(self.primary_edit_paths),
            "has_oracle": self.has_oracle,
            "max_submissions": self.max_submissions,
        }


def _load_index(root: Path) -> dict:
    path = root / INDEX
    if not path.is_file():
        raise ValueError(f"Not a Φ-Bench clone (missing {INDEX}): {root}")
    index = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(index, dict) or not isinstance(index.get("tasks"), list):
        raise ValueError(f"{path} has no task list")
    return index


def _task(root: Path, entry: dict) -> PhiTask:
    package = (root / entry["package_root"]).resolve()
    if root.resolve() not in package.parents:
        raise ValueError(f"Task package escapes the suite root: {entry['package_root']}")
    ref = entry.get("ref_speedup")
    return PhiTask(
        suite_root=root.resolve(),
        bench=entry["bench"],
        name=entry["task"],
        package_root=package,
        gpus=int(entry.get("gpus") or 0),
        reward_class=entry.get("reward_class") or "unknown",
        ref_speedup=float(ref) if ref is not None else None,
        primary_edit_paths=tuple(entry.get("primary_edit_paths") or ()),
        has_oracle=bool(entry.get("has_oracle")),
        max_submissions=entry.get("max_submissions"),
    )


def list_tasks(root: Path) -> list[PhiTask]:
    root = Path(root)
    return [_task(root, entry) for entry in _load_index(root)["tasks"]]


def get_task(root: Path, task_id: str) -> PhiTask:
    if not _TASK_ID.fullmatch(task_id):
        raise ValueError("Φ-Bench task IDs look like kfc/<name>, lh/<name> or e2e/<name>: "
                         f"{task_id!r}")
    bench, name = task_id.split("/", 1)
    for entry in _load_index(Path(root))["tasks"]:
        if entry.get("bench") == bench and entry.get("task") == name:
            task = _task(Path(root), entry)
            if not (task.package_root / "task.toml").is_file():
                raise ValueError(f"Task package has no task.toml: {task.package_root}")
            return task
    raise ValueError(f"Unknown Φ-Bench task: {task_id}")


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def read_reward(verifier_dir: Path) -> dict:
    """Read the grader's ``reward.json`` and hard-fail reasons, as Φ-Bench's runner does."""
    verifier_dir = Path(verifier_dir)
    result = {"reward": None, "speedup": None, "ref_speedup": None,
              "hard_fail_reasons": [], "schema_version": None, "source": None}
    path = verifier_dir / "reward.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            data = None
        if isinstance(data, dict):
            result["reward"] = _finite(data.get("reward"))
            result["source"] = "reward.json" if result["reward"] is not None else None
            result["speedup"] = _finite(data.get("speedup"))
            result["ref_speedup"] = _finite(data.get("ref_speedup"))
            result["schema_version"] = data.get("schema_version")
            result["hard_fail_reasons"] = [str(r) for r in data.get("hard_fail_reasons") or []]
    if result["reward"] is None and (verifier_dir / "reward.txt").is_file():
        text = re.sub(r"[^0-9eE.+-]", "", (verifier_dir / "reward.txt").read_text().strip())
        result["reward"] = _finite(text)
        result["source"] = "reward.txt" if result["reward"] is not None else None
    state = verifier_dir / "verifier_state.json"
    if state.is_file():
        try:
            data = json.loads(state.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
        for reason in (data.get("hard_fail_reasons") or []) if isinstance(data, dict) else []:
            if str(reason) not in result["hard_fail_reasons"]:
                result["hard_fail_reasons"].append(str(reason))
    return result


def judge_control(task: PhiTask, control: str, score: dict | None, *,
                  oracle_tolerance: float | None = None) -> dict:
    """Judge one control against the suite's documented expectation.

    Returns ``{"control", "verdict", "reason"}`` with verdict PASS, FAIL or
    INCONCLUSIVE. A missing score is INCONCLUSIVE, never PASS.
    """
    if control not in CONTROLS:
        raise ValueError(f"Unknown control: {control}")
    if not score or score.get("reward") is None:
        return {"control": control, "verdict": "INCONCLUSIVE",
                "reason": "grader wrote no readable reward"}
    reward = score["reward"]
    if control in ("noop", "negative"):
        if reward == 0.0:
            return {"control": control, "verdict": "PASS", "reason": "reward is 0 as expected"}
        return {"control": control, "verdict": "FAIL",
                "reason": f"{control} must score 0, got {reward}"}
    if score["hard_fail_reasons"]:
        return {"control": control, "verdict": "FAIL",
                "reason": "oracle hit hard gates: " + ", ".join(score["hard_fail_reasons"])}
    if task.reward_class == "implementation":
        if reward == 1.0:
            return {"control": control, "verdict": "PASS", "reason": "oracle scores 1.0"}
        return {"control": control, "verdict": "FAIL",
                "reason": f"implementation oracle must score 1.0, got {reward}"}
    anchor = score.get("ref_speedup") or task.ref_speedup
    if oracle_tolerance is None:
        return {"control": control, "verdict": "INCONCLUSIVE",
                "reason": "no oracle tolerance was frozen for this check"}
    if score.get("speedup") is None or not anchor:
        return {"control": control, "verdict": "INCONCLUSIVE",
                "reason": "grader reported no speedup or anchor"}
    ratio = score["speedup"] / anchor
    if abs(ratio - 1.0) <= oracle_tolerance:
        return {"control": control, "verdict": "PASS",
                "reason": f"oracle speedup {score['speedup']} reproduces anchor {anchor} "
                          f"(ratio {ratio:.4f}, tolerance {oracle_tolerance})"}
    return {"control": control, "verdict": "FAIL",
            "reason": f"oracle speedup {score['speedup']} differs from anchor {anchor} "
                      f"(ratio {ratio:.4f}, tolerance {oracle_tolerance}); "
                      "re-calibrate on this host"}


def assess_controls(task: PhiTask, scores: dict[str, dict | None], *,
                    oracle_tolerance: float | None = None) -> dict:
    """Combine the three control judgments into one self-check verdict."""
    checks = [judge_control(task, control, scores.get(control),
                            oracle_tolerance=oracle_tolerance) for control in CONTROLS]
    verdicts = {check["verdict"] for check in checks}
    verdict = next((v for v in ("FAIL", "INCONCLUSIVE") if v in verdicts), "PASS")
    return {"suite": SUITE, "task": task.task_id, "verdict": verdict,
            "oracle_tolerance": oracle_tolerance, "checks": checks}
