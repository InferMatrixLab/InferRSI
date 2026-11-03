"""Versioned task truth and bindings to existing Workbench/SkillEval contracts."""

import hashlib
import json
import math
import platform
import re
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from pathlib import Path

from ...runspec import RunSpec


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    entries = {}
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError("Task packages must not contain symlinks")
        if path.is_file():
            entries[path.relative_to(root).as_posix()] = digest(path)
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def grader_digest() -> str:
    return tree_digest(Path(__file__).parent)


def runtime_digest() -> str:
    try:
        numpy_version = version("numpy")
    except PackageNotFoundError:
        numpy_version = "unavailable"
    facts = [platform.python_version(), platform.system(), platform.machine(), numpy_version]
    return hashlib.sha256(json.dumps(facts).encode()).hexdigest()


def builtin_tasks() -> list[str]:
    root = files("inferrsi").joinpath("data/engineering_benchmarks")
    return sorted(p.name for p in root.iterdir() if p.joinpath("task.json").is_file())


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")


def _positive(value, field, *, integer=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, int if integer else (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{field} must be positive and finite")


@dataclass(frozen=True)
class TaskPackage:
    root: Path
    frozen_manifest: str
    task_sha256: str
    grader_sha256: str

    @property
    def manifest(self) -> dict:
        # Callers cannot mutate the task by changing a returned dictionary.
        return json.loads(self.frozen_manifest)

    def assert_unchanged(self) -> None:
        if tree_digest(self.root) != self.task_sha256 or grader_digest() != self.grader_sha256:
            raise ValueError("Frozen task or grader changed")

    def identity(self, candidate: Path) -> dict:
        self.assert_unchanged()
        candidate = candidate.absolute()
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("Candidate must be a regular source file")
        return {
            "task_id": self.manifest["id"],
            "task_sha256": self.task_sha256,
            "grader_sha256": self.grader_sha256,
            "candidate_sha256": digest(candidate),
            "runtime_sha256": runtime_digest(),
        }

    def command(self, action: str, candidate: Path) -> tuple[str, ...]:
        if action not in {"check", "measure", "profile"}:
            raise ValueError("Unknown task action")
        identity = self.identity(candidate)
        return (
            sys.executable,
            "-B",
            "-m",
            "inferrsi.harness.benchmarks.worker",
            action,
            "--package",
            str(self.root),
            "--candidate",
            str(candidate.resolve()),
            "--task-sha256",
            identity["task_sha256"],
            "--grader-sha256",
            identity["grader_sha256"],
            "--candidate-sha256",
            identity["candidate_sha256"],
            "--runtime-sha256",
            identity["runtime_sha256"],
        )

    def runspec(
        self,
        candidate: Path,
        *,
        repo: Path,
        output_dir: Path,
        repetitions: int,
        max_minutes: float,
        min_improvement_pct: float,
    ) -> RunSpec:
        """Bind one task to AB/BA; the caller owns repetition/budget/gain gates."""
        metric = self.manifest["measurement"]
        spec = RunSpec(
            repo=str(repo.resolve()),
            repo_type="engineering_task",
            backend=self.manifest["environment"]["backend"],
            baseline_command=self.command("measure", self.root / "baseline.py"),
            candidate_command=self.command("measure", candidate),
            validation_command=self.command("check", candidate),
            metric_key=metric["key"],
            metric_unit=metric["unit"],
            comparison_scope=self.manifest["id"] + ":" + metric["boundary"],
            direction="minimize",
            repetitions=repetitions,
            max_minutes=max_minutes,
            min_improvement_pct=min_improvement_pct,
            workload_id=self.task_sha256,
            output_dir=str(output_dir.resolve()),
            mode="code",
        )
        spec.validate()
        return spec


def load_task(name: str | Path) -> TaskPackage:
    root = Path(name)
    if not root.is_dir():
        if str(name) not in builtin_tasks():
            raise ValueError(f"Unknown task package: {name}")
        root = Path(str(files("inferrsi").joinpath("data/engineering_benchmarks", str(name))))
    if root.is_symlink():
        raise ValueError("Task root must not be a symlink")
    root = root.resolve()
    data = json.loads((root / "task.json").read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "id",
        "description",
        "searchspace",
        "source",
        "environment",
        "candidate",
        "oracle",
        "measurement",
        "workloads",
        "coverage",
        "adapter",
    }
    if (
        not isinstance(data, dict)
        or set(data) != required
        or type(data["schema_version"]) is not int
    ):
        raise ValueError("Invalid task fields")
    if data["schema_version"] != 1 or data["adapter"] != "numpy-axis1-v2":
        raise ValueError("Unsupported task schema or adapter")
    if not isinstance(data["id"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", data["id"]):
        raise ValueError("Invalid task id")
    for field in ("description", "searchspace"):
        _text(data[field], field)
    source = data["source"]
    if not isinstance(source, dict) or set(source) != {"url", "revision", "license", "adaptation"}:
        raise ValueError("Source provenance is required")
    for key, value in source.items():
        _text(value, "source." + key)
    if not re.fullmatch(r"[0-9a-f]{40}", source["revision"]):
        raise ValueError("Source revision must be a full commit")
    env = data["environment"]
    if env != {"backend": "cpu", "runtime": "numpy", "dtype": "float32"}:
        raise ValueError("Unsupported environment; no implicit device fallback")
    if data["candidate"] != {"entrypoint": "compute", "editable": ["implementation.py"]}:
        raise ValueError("Unsupported candidate contract")
    oracle = data["oracle"]
    if (
        not isinstance(oracle, dict)
        or set(oracle) != {"operation", "axis", "eps", "rtol", "atol"}
        or oracle["operation"] not in {"softmax", "rmsnorm"}
        or type(oracle["axis"]) is not int
        or oracle["axis"] != 1
    ):
        raise ValueError("Unsupported oracle")
    for key in ("eps", "rtol", "atol"):
        _positive(oracle[key], "oracle." + key)
    metric = data["measurement"]
    if (
        not isinstance(metric, dict)
        or set(metric)
        != {
            "key",
            "unit",
            "boundary",
            "aggregation",
            "warmups",
            "samples",
            "input_sequence",
            "case_ids",
        }
        or metric["key"] != "metrics.suite_latency_ms"
        or metric["unit"] != "ms"
        or metric["boundary"] != "synchronous-compute-call"
        or metric["aggregation"] != "sum-of-per-case-medians"
        or metric["input_sequence"] != "seeded-distinct-per-call-v1"
    ):
        raise ValueError("Unsupported measurement contract")
    for key in ("warmups", "samples"):
        _positive(metric[key], "measurement." + key, integer=True)
    if (
        not isinstance(metric["case_ids"], list)
        or not metric["case_ids"]
        or any(not isinstance(name, str) for name in metric["case_ids"])
        or len(set(metric["case_ids"])) != len(metric["case_ids"])
    ):
        raise ValueError("Distinct measured case IDs are required")
    if not isinstance(data["workloads"], list) or not data["workloads"]:
        raise ValueError("Workloads are required")
    names = set()
    for case in data["workloads"]:
        if not isinstance(case, dict) or set(case) != {
            "id",
            "shape",
            "seed",
            "distribution",
            "layout",
        }:
            raise ValueError("Invalid workload fields")
        _text(case["id"], "workload id")
        if case["id"] in names:
            raise ValueError("Duplicate workload id")
        names.add(case["id"])
        if (
            not isinstance(case["shape"], list)
            or not 2 <= len(case["shape"]) <= 4
            or any(type(n) is not int or n < 1 for n in case["shape"])
            or math.prod(case["shape"]) > 1048576
        ):
            raise ValueError("Invalid or oversized CPU workload")
        if type(case["seed"]) is not int or case["seed"] < 0:
            raise ValueError("Seed must be a nonnegative integer")
        if case["distribution"] not in {"normal", "zeros", "large", "tiny"}:
            raise ValueError("Unknown distribution")
        if case["layout"] not in {"contiguous", "strided"}:
            raise ValueError("Unknown layout")
    measured_cases = [case for case in data["workloads"] if case["id"] in metric["case_ids"]]
    if [case["id"] for case in measured_cases] != metric["case_ids"]:
        raise ValueError("Measured case IDs must follow workload order")
    if any(case["distribution"] == "zeros" for case in measured_cases):
        raise ValueError("Invariant zero workloads are correctness-only")
    prepared_elements = sum(math.prod(case["shape"]) for case in data["workloads"])
    prepared_elements += (metric["warmups"] + metric["samples"]) * sum(
        math.prod(case["shape"]) for case in measured_cases
    )
    if prepared_elements > 1048576:
        raise ValueError("Prepared input sequence exceeds the CPU workload bound")
    if (
        not isinstance(data["coverage"], list)
        or not data["coverage"]
        or any(not isinstance(v, str) or not v.strip() for v in data["coverage"])
    ):
        raise ValueError("Coverage limits are required")
    for path in ("baseline.py", "candidate.py", "LICENSE", "README.md"):
        if not (root / path).is_file():
            raise ValueError(f"Task package missing {path}")
    return TaskPackage(root, json.dumps(data, sort_keys=True), tree_digest(root), grader_digest())
