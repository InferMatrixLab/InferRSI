"""Unexecuted trusted synthetic EvalPlus diagnostic; never accepts real task data."""

import contextlib
import hashlib
import importlib
import io
import json
import os
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/site-packages")
# This proposal measures a known, bounded handwritten process tree. It does not
# qualify these broad benign limits for model-generated code.
resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
assert resource.getrlimit(resource.RLIMIT_AS) == (2147483648, 2147483648)
os.environ["EVALPLUS_MAX_MEMORY_BYTES"] = str(resource.getrlimit(resource.RLIMIT_AS)[0])
os.environ.pop("EVALPLUS_TIMEOUT_PER_TASK", None)
os.environ["XDG_CACHE_HOME"] = "/work/cache"
os.environ["HUMANEVAL_OVERRIDE_PATH"] = "/work/synthetic-dataset.jsonl"

import psutil


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    work = Path("/work")
    samples = work / "synthetic-samples.jsonl"
    dataset = work / "synthetic-dataset.jsonl"
    output = work / "output/synthetic-results.json"
    assert not samples.exists() and not dataset.exists() and not output.exists()
    assert not (work / "cache").exists()
    solutions = {
        "Synthetic/correct": "def f(x):\n    return x + 1\n",
        "Synthetic/plus_wrong": "def f(x):\n    return 1\n",
        "Synthetic/exception": "def f(x):\n    raise ArithmeticError('synthetic')\n",
        "Synthetic/input_timeout": "import time\ndef f(x):\n    time.sleep(5)\n    return x + 1\n",
    }
    rows = [
        {
            "task_id": task_id,
            "prompt": "def f(x):\n",
            "canonical_solution": "    return x + 1\n",
            "contract": "",
            "entry_point": "f",
            "base_input": [[0]],
            "plus_input": [[1]],
            "atol": 0,
        }
        for task_id in solutions
    ]
    dataset.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    samples.write_text("".join(
        json.dumps({"task_id": key, "solution": value}, sort_keys=True) + "\n"
        for key, value in solutions.items()
    ))
    parent = psutil.Process()
    captured_out, captured_err = io.StringIO(), io.StringIO()
    started = time.monotonic()
    with contextlib.redirect_stdout(captured_out), contextlib.redirect_stderr(captured_err):
        evaluator = importlib.import_module("evalplus.evaluate")
        evaluator.evaluate(
            dataset="humaneval", samples=str(samples), output_file=str(output),
            parallel=1, base_only=False, mini=False, noextreme=False,
            test_details=True,
        )
    result = json.loads(output.read_bytes())
    statuses = {
        task_id: [[row["base_status"], row["plus_status"]] for row in values]
        for task_id, values in result["eval"].items()
    }
    # The upstream per-input exception handler reports time-limit exceptions as
    # fail. This is distinct from its outer child-process timeout classification.
    expected = {
        "Synthetic/correct": [["pass", "pass"]],
        "Synthetic/plus_wrong": [["pass", "fail"]],
        "Synthetic/exception": [["fail", "fail"]],
        "Synthetic/input_timeout": [["fail", "fail"]],
    }
    checks = {
        "four_exact_status_pairs": statuses == expected,
        "dataset_hash": result["hash"] == hashlib.md5(dataset.read_bytes()).hexdigest(),
        "bounded_output": output.stat().st_size <= 1048576,
        "timeout_override_absent": "EVALPLUS_TIMEOUT_PER_TASK" not in os.environ,
    }
    payload = {
        "checks": checks, "passed": all(checks.values()), "statuses": statuses,
        "elapsed_seconds": time.monotonic() - started,
        "dataset_sha256": digest(dataset.read_bytes()), "samples_sha256": digest(samples.read_bytes()),
        "results_sha256": digest(output.read_bytes()), "results": result,
        "evaluator_module_sha256": digest(Path(evaluator.__file__).read_bytes()),
        "evaluator_stdout": captured_out.getvalue(), "evaluator_stderr": captured_err.getvalue(),
        "live_children_after_evaluate": len(parent.children(recursive=True)),
        "generated_code_executed": False, "real_benchmark_data_mounted": False,
        "full_evaluator_executed": True, "qualified_generated_code_executor": False,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
