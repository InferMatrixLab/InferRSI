"""Fixed visible KV workbench; submitted Python executes only through kv.invoke.

The visible suite contains extracted DEVELOPMENT cases and a public benchmark,
never the full verifier collection. Candidate sandboxes receive events only.
Hidden grading is a separate operation on the final immutable source snapshot.
"""

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path

from ..infra.artifacts import atomic_write_json, digest
from ..model import anthropic_agent as provider
from ..model.anthropic_edit_agent import EditPlan
from ..runspec import RunSpec
from . import kv_reclamation as kv
from .runner import run_experiment


def _copy(value):
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


def _compare(trace, actual):
    # Projection of frozen expected DATA, not a second state-machine oracle.
    expected = {"observations": trace["expected"],
                "pending": trace["expected"][-1]["pending"] if trace["expected"] else []}
    return digest(expected) == digest(actual)


def _traces(traces, split):
    if type(traces) is not list or not traces:
        raise ValueError("Nonempty frozen trace set required")
    ids = []
    for trace in traces:
        if (type(trace) is not dict or set(trace) != {"id", "split", "events", "expected"}
                or trace["split"] != split or type(trace["id"]) is not str
                or type(trace["events"]) is not list or type(trace["expected"]) is not list
                or len(trace["events"]) != len(trace["expected"])):
            raise ValueError("Wrong trace split or frozen trace shape")
        ids.append(trace["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate trace identity")
    return _copy(traces)


@dataclass(frozen=True)
class VisibleSuite:
    """The whole byte string is hashed in the actor's callback/dependency freeze."""

    serialized: bytes

    def __post_init__(self):
        if type(self.serialized) is not bytes or not 0 < len(self.serialized) <= 16 * 1024 * 1024:
            raise ValueError("Visible suite must be bounded immutable JSON bytes")
        value = json.loads(self.serialized, object_pairs_hook=provider.unique_object)
        if (type(value) is not dict or set(value) != {"schema", "development", "benchmark_events",
                                                    "benchmark_expected", "min_improvement_pct"}
                or value["schema"] != "kv-visible-suite-v1"
                or type(value["benchmark_events"]) is not list
                or type(value["benchmark_expected"]) is not dict
                or type(value["min_improvement_pct"]) not in (int, float)
                or not math.isfinite(value["min_improvement_pct"])
                or value["min_improvement_pct"] < 0):
            raise ValueError("Wrong visible suite shape")
        _traces(value["development"], "development")
        _copy(value)

    def read(self):
        return json.loads(self.serialized)


class VisibleWorkbench:
    """Fixed callbacks; no model-supplied paths, commands, traces or metric gates."""

    def __init__(self, plan: EditPlan, suite: VisibleSuite, baseline: bytes, output: Path):
        value = suite.read()
        if tuple(t["id"] for t in value["development"]) != plan.check_ids:
            raise ValueError("Actor check identities differ from the frozen visible suite")
        if (type(baseline) is not bytes or not 0 < len(baseline) <= plan.limits.max_source_bytes
                or plan.metric_key != "elapsed_seconds" or plan.metric_unit != "seconds"
                or plan.direction != "minimize"):
            raise ValueError("Wrong fixed KV source/metric contract")
        baseline.decode("utf-8")
        self.plan, self.suite, self.baseline = plan, suite, baseline
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.check_count = self.benchmark_count = 0

    def retain_revision(self, source, metadata, deadline):
        if time.monotonic() >= deadline:
            return False
        if hashlib.sha256(source).hexdigest() != metadata["sha256"]:
            raise ValueError("Revision digest does not match retained bytes")
        path = self.output / "revisions" / f"revision-{metadata['revision']:04d}"
        path.mkdir(parents=True, exist_ok=False)
        with os.fdopen(os.open(path / "candidate.py", os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                               0o600), "wb") as stream:
            stream.write(source)
            stream.flush()
            os.fsync(stream.fileno())
        atomic_write_json(path / "receipt.json", metadata)
        return kv.source_bytes(path / "candidate.py") == source

    def visible_checks(self, source, deadline):
        self.check_count += 1
        if self.check_count > self.plan.limits.max_checks:
            raise ValueError("Frozen visible-check count exhausted")
        traces = self.suite.read()["development"]
        try:
            result = kv.verify_source(source, traces, self.output / f"check-{self.check_count:03d}",
                                      deadline, _compare)
        except kv.SandboxUnavailable:
            return {"verdict": "INCONCLUSIVE", "checks": {}, "reason": "sandbox_unavailable"}
        reason = "none" if result["verdict"] == "PASS" else (
            "check_failed" if result["verdict"] == "FAIL" else
            "deadline" if result.get("reason") in {"timeout", "deadline"} else "candidate_error")
        return {"verdict": result["verdict"], "checks": result["checks"], "reason": reason}

    def visible_benchmark(self, source, deadline):
        self.benchmark_count += 1
        if self.benchmark_count > self.plan.limits.max_benchmarks:
            raise ValueError("Frozen visible-benchmark count exhausted")
        empty = {"verdict": "INCONCLUSIVE", "baseline_values": [], "candidate_values": [],
                 "quality_verdict": "INCONCLUSIVE", "improvement_pct": None,
                 "reason": "deadline"}
        left = deadline - time.monotonic()
        if left <= 0:
            return empty
        root = self.output / f"benchmark-{self.benchmark_count:03d}"
        sources = {"baseline": self.baseline, "candidate": bytes(source)}
        for label, data in sources.items():
            directory = root / "sources" / label
            directory.mkdir(parents=True)
            (directory / "candidate.py").write_bytes(data)
        suite = self.suite.read()
        expected = digest(suite["benchmark_expected"])
        quality = []

        def snapshot(repo, excluded):
            data = kv.source_bytes(repo / "candidate.py")
            return {"available": True, "snapshot_hash": hashlib.sha256(data).hexdigest(),
                    "kind": "immutable-candidate-bytes"}

        def execute(command, cwd, trial_dir, runner_deadline, metric_key):
            if command not in (("fixed-kv", "baseline"), ("fixed-kv", "candidate")):
                raise ValueError("Not a fixed KV workbench command")
            label = command[1]
            record, actual = kv.invoke(sources[label], {"mode": "benchmark",
                "events": _copy(suite["benchmark_events"])}, trial_dir,
                min(deadline, runner_deadline))
            valid = record["status"] == "completed" and digest(actual) == expected
            elapsed = record.get("elapsed_seconds")
            finite = type(elapsed) in (float, int) and math.isfinite(elapsed) and elapsed > 0
            record["metric"] = elapsed if valid and finite else None
            record["metric_error"] = None if valid and finite else "unverified complete trace"
            if record["status"] == "completed" and not valid:
                record["status"] = "failed"
            if metric_key is None:
                quality.append("PASS" if valid else "FAIL" if record["status"] == "failed"
                               else "INCONCLUSIVE")
            atomic_write_json(trial_dir / "execution.json", record)
            return record

        spec = RunSpec(
            repo=str(root / "sources/baseline"), candidate_repo=str(root / "sources/candidate"),
            repo_type="synthetic-cpu-kv", backend="cpu", mode="code",
            scenario="kv-visible-development", metric_key=self.plan.metric_key,
            metric_unit=self.plan.metric_unit, direction=self.plan.direction,
            comparison_scope="whole CPU task including sandbox and interpreter startup",
            baseline_command=("fixed-kv", "baseline"), candidate_command=("fixed-kv", "candidate"),
            validation_command=("fixed-kv", "candidate"),
            repetitions=self.plan.limits.benchmark_repetitions,
            max_minutes=left / 60, min_improvement_pct=suite["min_improvement_pct"],
            output_dir=str(root / "runs"),
            agent="bounded-edit-check-protocol")
        try:
            run = run_experiment(spec, {"scope": "synthetic visible development only"},
                                 execute=execute, snapshot=snapshot)
        except kv.SandboxUnavailable:
            return {**empty, "reason": "sandbox_unavailable"}
        evaluation = json.loads((run / "evaluation.json").read_text())
        return {"verdict": evaluation["verdict"],
                "baseline_values": (evaluation["baseline"] or {}).get("values", []),
                "candidate_values": (evaluation["candidate"] or {}).get("values", []),
                "quality_verdict": quality[-1] if quality else "INCONCLUSIVE",
                "improvement_pct": evaluation["improvement_pct"],
                "reason": "none" if evaluation["verdict"] == "PASS" else
                "check_failed" if evaluation["verdict"] == "FAIL" else "measurement_incomplete"}


def grade_final(source, expected_sha256, hidden_traces, output, deadline):
    """Separate post-submission grader; never return this data to the actor."""
    if type(source) is not bytes or hashlib.sha256(source).hexdigest() != expected_sha256:
        raise ValueError("Final grader requires the exact immutable submitted source")
    traces = _traces(hidden_traces, "grader")
    try:
        result = kv.verify_source(source, traces, output, deadline, _compare)
    except kv.SandboxUnavailable:
        result = {"verdict": "INCONCLUSIVE", "checks": {}, "reason": "sandbox_unavailable"}
    return {**result, "artifact_sha256": expected_sha256,
            "scope": "post-submission hidden correctness only; no search feedback"}
