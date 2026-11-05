"""Evaluate one reviewed MoE candidate on two caller-allocated Ascend NPUs.

No agent, scheduler, SSH, search policy or token accounting is started here.
Importing this module and reading task resources require no device libraries.
"""

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
import uuid
from importlib.resources import files
from pathlib import Path

from ...infra.artifacts import atomic_write_json
from ._moe_processes import MARKER, cleanup
from .external import execute_trial

TASK_FILES = ("task.json", "TASK.md", "baseline.py", "oracle.py", "workload.py", "LICENSE")


def task_resources():
    return files("inferrsi").joinpath("data", "engineering_scenarios", "moe-forward-npu")


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _preflight(candidate: Path, output: Path, pairs: int, timeout_seconds: float):
    if type(pairs) is not int or pairs <= 0:
        raise ValueError("pairs must be a positive integer")
    if not _positive(timeout_seconds):
        raise ValueError("timeout-seconds must be finite and positive")
    if not candidate.is_file() or candidate.suffix != ".py":
        raise ValueError("candidate must be a reviewed, self-contained Python file")
    if output.exists():
        raise FileExistsError("output-dir must be new; use a separate directory per candidate")
    if sys.platform != "linux":
        raise OSError("MoE execution requires Linux, readable /proc and two allocated Ascend NPUs")
    Path("/proc/self/stat").read_text()
    visible = os.environ.get("ASCEND_RT_VISIBLE_DEVICES", "").split(",")
    if len(visible) != 2 or any(not x.strip().isdigit() for x in visible):
        raise ValueError("Allocate two NPUs first (npu run --gpus 2); do not choose fixed card IDs")
    if len({int(x.strip()) for x in visible}) != 2:
        raise ValueError("ASCEND_RT_VISIBLE_DEVICES must contain two distinct allocated devices")


def _hashes(root: Path, names) -> dict:
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


def _prepare(candidate: Path, output: Path, pairs: int) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    for directory in ("task", "candidate", "runner", "results"):
        (output / directory).mkdir()
    for name in TASK_FILES:
        (output / "task" / name).write_bytes(task_resources().joinpath(name).read_bytes())
    (output / "candidate" / "implementation.py").write_bytes(candidate.read_bytes())
    grader = files("inferrsi.harness.scenarios").joinpath("moe_grader.py").read_bytes()
    (output / "runner" / "grade.py").write_bytes(grader)
    atomic_write_json(output / "request.json", {"repetitions": pairs})
    names = ["task/" + name for name in TASK_FILES]
    names += ["candidate/implementation.py", "runner/grade.py", "request.json"]
    identity = _hashes(output, names)
    atomic_write_json(output / "identity.json", identity)
    return identity


def _launch(root: Path, token: str):
    # exec starts a process with the marker in its initial environment, visible
    # in /proc and inherited even by torchrun children with their own sessions.
    os.environ[MARKER] = token
    argv = [sys.executable, "-B", "-m", "torch.distributed.run", "--standalone",
            "--nnodes=1", "--nproc-per-node=2", str(root / "runner" / "grade.py"),
            "--run-dir", str(root)]
    os.execv(sys.executable, argv)


def _expected_calls(task: dict, pairs: int) -> dict:
    expected = {}
    measure = task["measurement"]
    for index, case in enumerate(task["cases"]):
        base = 100000 + index * 10000
        calls = [(base + i, "correctness", "standard", None, None, False) for i in range(2)]
        if case["measured"]:
            calls += [(base + 10 + i, "warmup", "standard", None, None, False)
                      for i in range(measure["warmups"])]
            calls += [(base + 100 + pair * 100 + sample, phase, variant, pair, sample, timed)
                      for pair in range(pairs) for sample in range(measure["samples_per_pair"])
                      for phase, variant, timed in (("shape_warmup", "shape_warmup", False),
                                                    ("measurement", "standard", True))]
        for seed, phase, variant, pair, sample, timed in calls:
            for label in ("baseline", "candidate"):
                expected[(case["id"], seed, label, phase, variant, pair, sample)] = timed
    return expected


def _score(task: dict, ranks: list[dict], summary: dict, pairs: int) -> dict:
    """Recompute from complete raw calls/samples; a rank-0 summary is insufficient."""
    if (len(ranks) != 2 or {r.get("rank") for r in ranks} != {0, 1}
            or any(type(r.get("rank")) is not int or r.get("completed") is not True
                   or r.get("correctness") != "PASS" or r.get("error") for r in ranks)):
        raise ValueError("Both ranks must complete correctly without errors")
    expected = _expected_calls(task, pairs)
    checks = ("shape_dtype_device", "input_parameters_preserved", "finite", "values", "nrmse_pass")
    by_rank = []
    for rank in ranks:
        observed = {}
        for call in rank["calls"]:
            key = tuple(call[k] for k in ("case_id", "seed", "label", "phase", "variant",
                                          "pair", "sample"))
            if (key in observed or key not in expected
                    or call["included_in_score"] is not expected[key]
                    or call["all_ranks_correct"] is not True
                    or not all(call["checks"].get(k) is True for k in checks)
                    or not _positive(call["local_elapsed_ms"])):
                raise ValueError("Missing, duplicated or invalid forward verification")
            observed[key] = call
        if set(observed) != set(expected):
            raise ValueError("Incomplete correctness/warmup/measurement calls")
        samples = {}
        for sample in rank["samples"]:
            key = tuple(sample[k] for k in ("case_id", "seed", "label", "pair", "sample"))
            call_key = key[:3] + ("measurement", "standard") + key[3:]
            if (key in samples or call_key not in observed
                    or sample["local_elapsed_ms"] != observed[call_key]["local_elapsed_ms"]
                    or sample["input_sha256"] != observed[call_key]["input_sha256"]
                    or not _positive(sample["slowest_rank_elapsed_ms"])):
                raise ValueError("Invalid timed sample")
            samples[key] = sample
        if len(samples) != sum(expected.values()):
            raise ValueError("Incomplete timed samples")
        by_rank.append(samples)
    if by_rank[0].keys() != by_rank[1].keys():
        raise ValueError("Ranks disagree on timed calls")
    for key, first in by_rank[0].items():
        second = by_rank[1][key]
        maximum = max(first["local_elapsed_ms"], second["local_elapsed_ms"])
        if (first["slowest_rank_elapsed_ms"] != second["slowest_rank_elapsed_ms"]
                or not math.isclose(first["slowest_rank_elapsed_ms"], maximum, rel_tol=1e-6)):
            raise ValueError("Timing does not use the maximum of both ranks")
    cases = []
    for case in task["cases"]:
        if not case["measured"]:
            continue
        grouped = {label: [s["slowest_rank_elapsed_ms"] for s in by_rank[0].values()
                           if s["case_id"] == case["id"] and s["label"] == label]
                   for label in ("baseline", "candidate")}
        b, c = (statistics.median(grouped[label]) for label in ("baseline", "candidate"))
        cases.append({"id": case["id"], "baseline_median_ms": b, "candidate_median_ms": c,
                      "speedup": b / c, "samples_ms": grouped})
    speedup = math.exp(statistics.mean(math.log(c["speedup"]) for c in cases))
    score = {"completed": True, "correctness": "PASS", "cases": cases, "speedup": speedup,
             "aggregation": "geometric_mean_case_speedups",
             "measurement_protocol":
                 "shape-matched-different-values-warmup-both-labels-before-paired-timing",
             "metrics": {"suite_latency_ms": sum(c["candidate_median_ms"] for c in cases)}}
    if summary != score or any(r["cases"] != cases or r["speedup"] != speedup for r in ranks):
        raise ValueError("Summary disagrees with raw two-rank samples")
    return score


def _adjudicate(root: Path, execution: dict, guard: dict, identity: dict, pairs: int) -> dict:
    result = {"status": "infrastructure_failure", "completed": False,
              "correctness": "INCONCLUSIVE", "speedup": None, "metrics": {},
              "round_consumed": False, "process_cleanup": guard, "execution": execution}
    ranks = []
    try:
        malformed_ranks = []
        for rank in range(2):
            path = root / "results" / f"rank-{rank}.json"
            if path.exists():
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(record, dict) or record.get("rank") != rank:
                        raise ValueError("Rank/file identity mismatch")
                except (OSError, ValueError):
                    malformed_ranks.append(rank)
                    continue
                ranks.append(record)
                # A peer may leave a truncated record when the job is stopped.
                # Preserve observed candidate work before parsing the next rank.
                phase, kind, calls = (record.get(k) for k in ("phase", "failure_kind", "calls"))
                if ((isinstance(phase, str) and phase.startswith("candidate_"))
                        or (isinstance(kind, str) and kind.startswith("candidate_"))
                        or (isinstance(calls, list) and any(
                            isinstance(c, dict) and c.get("label") == "candidate" for c in calls))):
                    result["round_consumed"] = True
        result["rank_status"] = [{k: r.get(k) for k in (
            "rank", "phase", "completed", "correctness", "failure_kind", "error")} for r in ranks]
        failed = any(r.get("phase", "").startswith("candidate_")
                     or r.get("failure_kind", "").startswith("candidate_") for r in ranks)
        # A later cleanup/integrity failure cannot erase observed candidate work
        # and turn a consumed attempt into a free infrastructure retry.
        if failed:
            result.update(status="candidate_failure", correctness="FAIL", round_consumed=True)
        if malformed_ranks:
            raise ValueError("Incomplete or malformed rank records; no usable score")
        if not guard.get("verified"):
            raise ValueError("Workload process cleanup was not verified")
        if _hashes(root, identity) != identity:
            raise ValueError("Frozen task, grader, request or candidate changed during execution")
        if failed:
            raise ValueError("Candidate failed or did not complete; inspect retained rank logs")
        if (execution.get("status") != "completed" or execution.get("returncode") != 0
                or execution.get("metric_error") or not _positive(execution.get("metric"))):
            raise ValueError("Executor did not complete with a valid result; no usable score")
        summary = json.loads((root / "results" / "summary.json").read_text(encoding="utf-8"))
        task = json.loads((root / "task" / "task.json").read_text(encoding="utf-8"))
        score = _score(task, ranks, summary, pairs)
        if execution["metric"] != score["metrics"]["suite_latency_ms"]:
            raise ValueError("Execution metric disagrees with raw samples")
        result.update(score, status="completed", round_consumed=True)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        result["error"] = str(exc)
    return result


def evaluate(candidate: Path, output: Path, *, pairs: int, timeout_seconds: float) -> dict:
    started = time.monotonic()
    candidate, output = candidate.resolve(), output.resolve()
    _preflight(candidate, output, pairs, timeout_seconds)
    identity = _prepare(candidate, output, pairs)
    token = uuid.uuid4().hex
    # This small launcher is frozen too and receives the marker only after the
    # executor starts it; the calling shell and npu allocator never inherit it.
    launcher = output / "runner" / "launch.py"
    launcher.write_text("from inferrsi.harness.scenarios.moe import _launch\n"
                        "from pathlib import Path\nimport sys\n"
                        "_launch(Path(sys.argv[1]), sys.argv[2])\n", encoding="utf-8")
    identity.update(_hashes(output, ["runner/launch.py"]))
    atomic_write_json(output / "identity.json", identity)
    execution = {"status": "error", "metric": None, "returncode": None}
    try:
        execution = execute_trial(
            (sys.executable, "-B", str(launcher), str(output), token), output,
            output / "execution", started + timeout_seconds, "metrics.suite_latency_ms")
    except (OSError, ValueError, RuntimeError) as exc:
        execution["error"] = str(exc)
    finally:
        guard = cleanup(token)
    result = _adjudicate(output, execution, guard, identity, pairs)
    result["elapsed_seconds"] = time.monotonic() - started
    result["pairs"] = pairs
    result["timeout_seconds"] = timeout_seconds
    atomic_write_json(output / "result.json", result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pairs", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    args = parser.parse_args(argv)
    try:
        result = evaluate(args.candidate, args.output_dir, pairs=args.pairs,
                          timeout_seconds=args.timeout_seconds)
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps({k: result.get(k) for k in (
        "status", "correctness", "speedup", "metrics", "elapsed_seconds", "error")}))
    return 0 if result["completed"] else 2 if result["status"] == "candidate_failure" else 1


if __name__ == "__main__":
    sys.exit(main())
