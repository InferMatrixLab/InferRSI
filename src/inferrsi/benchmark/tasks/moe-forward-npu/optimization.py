"""Frozen full-task protocol and raw-evidence rules for two-rank MoE sessions.

Only standard-library code runs here. The single-candidate driver and the
iterative assessor share these rules without importing an execution runtime.
"""

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

TASK_FILES = (
    "task.json", "TASK.md", "baseline.py", "oracle.py", "workload.py", "LICENSE",
    "benchmark.py", "grader.py", "optimization.py",
)

LAUNCHER_SOURCE = (
    "from pathlib import Path\nimport runpy, sys\n"
    "root = Path(sys.argv[1])\n"
    "runpy.run_path(str(root / 'task' / 'benchmark.py'))['_launch'](root, sys.argv[2])\n"
)


def validate_arguments(arguments):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    settings = vars(parser.parse_args(arguments))
    if settings["pairs"] < 1 or not _positive(settings["timeout_seconds"]):
        raise ValueError("pairs and timeout-seconds must be finite and positive")
    return settings


def arguments(candidate: Path, output: Path, settings):
    return ["--candidate", str(candidate), "--output-dir", str(output),
            "--pairs", str(settings["pairs"]),
            "--timeout-seconds", str(settings["timeout_seconds"])]


def _binding(directory, settings):
    output = directory / "measurement"
    identity = json.loads((output / "identity.json").read_text(encoding="utf-8"))
    required = {"task/" + name for name in TASK_FILES}
    required.update({"runner/grade.py", "runner/launch.py", "candidate/implementation.py",
                     "request.json"})
    if not isinstance(identity, dict) or identity.keys() != required:
        raise ValueError("Missing or unexpected evaluated source identities")
    expected = _hashes(Path(__file__).parent, TASK_FILES)
    for name in TASK_FILES:
        if identity["task/" + name] != expected[name]:
            raise ValueError("Evaluated task differs from the frozen task")
    if identity["runner/grade.py"] != expected["grader.py"]:
        raise ValueError("Evaluated grader differs from the frozen grader")
    if identity["runner/launch.py"] != hashlib.sha256(LAUNCHER_SOURCE.encode()).hexdigest():
        raise ValueError("Evaluated launcher differs from the frozen launcher")
    if identity["candidate/implementation.py"] != hashlib.sha256(
        (directory / "candidate.py").read_bytes()
    ).hexdigest():
        raise ValueError("Task result is bound to another candidate")
    for name, expected_hash in identity.items():
        path = output / name
        if (path.is_symlink() or any(parent.is_symlink() for parent in path.parents)
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash):
            raise ValueError("Evaluated source snapshot changed")
    request = json.loads((output / "request.json").read_text(encoding="utf-8"))
    if request != {"repetitions": settings["pairs"]}:
        raise ValueError("Frozen sampling protocol changed")
    return identity


def assess(directory: Path, settings, execution):
    output = directory / "measurement"
    result_path = output / "result.json"
    if not result_path.is_file():
        return {"status": "infrastructure_failure", "score": None,
                "verdict": "INCONCLUSIVE", "reason": "missing_task_result"}
    result = json.loads(result_path.read_text(encoding="utf-8"))
    evidence = {"measurement/result.json": hashlib.sha256(result_path.read_bytes()).hexdigest()}

    def incomplete(reason):
        return {"status": "infrastructure_failure", "score": None,
                "verdict": "INCONCLUSIVE", "reason": reason, "evidence_files": evidence,
                "round_consumed": result.get("round_consumed")}

    rejected = result.get("status") == "candidate_failure"
    expected_exit = ("failed", 2) if rejected else ("completed", 0)
    if (type(execution.get("returncode")) is not int
            or (execution.get("status"), execution["returncode"]) != expected_exit):
        return incomplete("incomplete_outer_execution")
    identity = _binding(directory, settings)
    for name, fingerprint in identity.items():
        evidence["measurement/" + name] = fingerprint
    evidence["measurement/identity.json"] = hashlib.sha256(
        (output / "identity.json").read_bytes()).hexdigest()
    if (result.get("pairs") != settings["pairs"]
            or result.get("timeout_seconds") != settings["timeout_seconds"]):
        raise ValueError("Evaluated sampling or timeout differs from the frozen protocol")
    inner_path = output / "execution/execution.json"
    if not inner_path.is_file():
        return incomplete("missing_inner_execution")
    inner = json.loads(inner_path.read_text(encoding="utf-8"))
    evidence["measurement/execution/execution.json"] = hashlib.sha256(
        inner_path.read_bytes()).hexdigest()
    if inner != result.get("execution"):
        raise ValueError("Task result differs from the retained execution receipt")
    if (inner.get("status") not in ("completed", "failed")
            or type(inner.get("returncode")) is not int or inner["returncode"] < 0):
        return incomplete("incomplete_inner_execution")
    guard = result.get("process_cleanup", {})
    if guard.get("verified") is not True or guard.get("remaining"):
        return incomplete("workload_cleanup_unverified")
    # A normal driver exit cannot turn a partial rank record into a resumable
    # rejection. Keep raw evidence alongside any rejected score.
    for name in ("results/rank-0.json", "results/rank-1.json", "results/summary.json"):
        path = output / name
        if path.is_file():
            evidence["measurement/" + name] = hashlib.sha256(path.read_bytes()).hexdigest()
    recomputed = _adjudicate(output, inner, guard, identity, settings["pairs"])
    if {name: result.get(name) for name in recomputed} != recomputed:
        raise ValueError("Task result disagrees with raw two-rank evidence")
    if len(recomputed.get("rank_status", [])) != 2:
        return incomplete("incomplete_rank_evidence")
    if rejected:
        if any(isinstance(value, str) and value.startswith("baseline_")
               for rank in recomputed["rank_status"]
               for value in (rank.get("phase"), rank.get("failure_kind"))):
            return incomplete("baseline_failure")
        return {"status": "candidate_failure", "score": None, "verdict": "FAIL",
                "quality_passed": False if result.get("correctness") == "FAIL" else None,
                "reason": recomputed.get("error"), "round_consumed": True,
                "evidence_files": evidence}
    if recomputed["status"] != "completed":
        return incomplete(recomputed.get("error", "incomplete_task"))
    return {"status": "completed", "verdict": "PASS", "score": recomputed["speedup"],
            "quality_passed": True, "case_metrics": recomputed["cases"],
            "round_consumed": True, "evidence_files": evidence}


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _hashes(root: Path, names) -> dict:
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


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
                    if (not isinstance(record, dict) or type(record.get("rank")) is not int
                            or record["rank"] != rank):
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
        # Invalid evidence can still record spent work, but cannot establish rejection.
        if any(not isinstance(r.get("phase"), str) or not r["phase"].strip()
               or not isinstance(r.get("failure_kind", ""), str) for r in ranks):
            raise ValueError("Malformed rank phase or failure_kind")
        failed = any(r["phase"].startswith("candidate_")
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
