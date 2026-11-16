"""Full-task evaluation protocol for an Agent-driven denoiser optimization session."""

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path


def validate_arguments(arguments):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, required=True)
    parser.add_argument("--samples", type=int, required=True)
    parser.add_argument("--warmups", type=int, required=True)
    values = vars(parser.parse_args(arguments))
    if values["pairs"] < 1 or values["samples"] < 1 or values["warmups"] < 0:
        raise ValueError("pairs and samples must be positive, warmups must be nonnegative")
    return values


def arguments(candidate: Path, output: Path, settings):
    return ["--candidate", str(candidate), "--output-dir", str(output), "--device", "npu",
            "--pairs", str(settings["pairs"]), "--samples", str(settings["samples"]),
            "--warmups", str(settings["warmups"])]


def assess(directory: Path, settings, execution):
    output = directory / "measurement"
    result_path = output / "result.json"
    if not result_path.is_file():
        return {"status": "infrastructure_failure", "score": None,
                "verdict": "INCONCLUSIVE", "reason": "missing_task_result"}
    result = json.loads(result_path.read_text(encoding="utf-8"))
    evidence = {"measurement/result.json": hashlib.sha256(result_path.read_bytes()).hexdigest()}
    if result.get("status") == "candidate_failure":
        return {"status": "candidate_failure", "score": None, "verdict": "FAIL",
                "reason": result.get("error"), "evidence_files": evidence,
                "quality_passed": False if result.get("correctness") == "FAIL" else None}
    if (execution.get("status") != "completed" or execution.get("returncode") != 0
            or result.get("status") != "completed" or result.get("correctness") != "PASS"):
        return {"status": "infrastructure_failure", "score": None,
                "verdict": "INCONCLUSIVE", "reason": "incomplete_execution_or_task",
                "evidence_files": evidence}
    task = json.loads((Path(__file__).parent / "task.json").read_text(encoding="utf-8"))
    expected_cases = {case["id"] for case in task["cases"]}
    measured_cases = {case["id"] for case in task["cases"] if case["measured"]}
    if (result.get("score_scope") != "complete_task"
            or set(result.get("selected_cases", [])) != expected_cases
            or result.get("protocol") != {**settings, "check_only": False}):
        raise ValueError("Full-task scope or frozen sampling protocol changed")
    identity = json.loads((output / "identity.json").read_text(encoding="utf-8"))
    required = {"candidate.py", "baseline.py", "reference.py", "workload.py", "task.json",
                "TASK.md", "benchmark.py", "LICENSE", "NOTICE.md"}
    if not required <= identity.keys():
        raise ValueError("Missing evaluated source identities")
    if identity.get("candidate.py") != hashlib.sha256((directory / "candidate.py").read_bytes()
                                                     ).hexdigest():
        raise ValueError("Task result is bound to another candidate")
    for name, expected in identity.items():
        path = output / "snapshot" / name
        if path.parent != output / "snapshot" or hashlib.sha256(path.read_bytes()).hexdigest() != (
            expected
        ):
            raise ValueError("Evaluated source snapshot changed")
        if name != "candidate.py" and hashlib.sha256(
            (Path(__file__).parent / name).read_bytes()
        ).hexdigest() != expected:
            raise ValueError("Evaluated task differs from the frozen task")
        evidence["measurement/snapshot/" + name] = expected
    evidence["measurement/identity.json"] = hashlib.sha256(
        (output / "identity.json").read_bytes()).hexdigest()
    cases = result.get("cases", [])
    if len(cases) != len(measured_cases) or {case["id"] for case in cases} != measured_cases:
        raise ValueError("Missing or duplicated performance cases")
    expected_calls, calls = Counter(), Counter()
    timed = {}
    steps = {}
    for case in task["cases"]:
        config = {**task["defaults"], **case}
        steps[case["id"]] = len(config["sigmas"]) - 1
        for label in ("baseline", "candidate"):
            for phase, count in (("correctness", 1), ("warmup", settings["warmups"]),
                                 ("weight_update", 1)):
                expected_calls[(case["id"], label, phase, None, None)] = count
            for index in range(settings["pairs"] * settings["samples"] if case["measured"] else 0):
                expected_calls[(case["id"], label, "measurement",
                                index // settings["samples"], index)] = 1
    for call in result.get("calls", []):
        key = (call["case"], call["label"], call["phase"], call["pair"], call["sample"])
        calls[key] += 1
        errors = call["step_nrmse"]
        if (call["correctness"] != "PASS" or len(errors) != steps[call["case"]]
                or any(type(value) not in (int, float) or not math.isfinite(value)
                       or not 0 <= value <= task["tolerance"]["max_nrmse"] for value in errors)):
            raise ValueError("Incomplete or failed per-step correctness evidence")
        if call["phase"] == "measurement":
            timed.setdefault((call["case"], call["label"]), []).append(call["elapsed_ms"])
    if calls != expected_calls:
        raise ValueError("Incomplete or duplicated invocation evidence")
    ratios = []
    for case in cases:
        medians = {}
        for label in ("baseline", "candidate"):
            samples = case["samples_ms"][label]
            if samples != timed.get((case["id"], label)):
                raise ValueError("Timing samples disagree with invocation evidence")
            if (len(samples) != settings["pairs"] * settings["samples"]
                    or any(type(value) not in (int, float) or not math.isfinite(value)
                           or value <= 0 for value in samples)):
                raise ValueError("Incomplete or invalid timing samples")
            medians[label] = statistics.median(samples)
            if medians[label] != case[label + "_median_ms"]:
                raise ValueError("Case median disagrees with raw samples")
        ratios.append(medians["baseline"] / medians["candidate"])
    score = math.exp(statistics.mean(math.log(value) for value in ratios))
    if not math.isclose(score, result["speedup"], rel_tol=1e-12, abs_tol=0):
        raise ValueError("Aggregate score disagrees with raw samples")
    return {"status": "completed", "verdict": "PASS", "score": score,
            "quality_passed": True, "case_metrics": cases, "evidence_files": evidence}
