"""Execute one frozen task action under an existing InferRSI executor."""

import argparse
import json
import os
from pathlib import Path

from ...infra.artifacts import atomic_write_json
from .contract import load_task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "measure", "profile"))
    for field in (
        "package",
        "candidate",
        "task-sha256",
        "grader-sha256",
        "candidate-sha256",
        "runtime-sha256",
    ):
        parser.add_argument("--" + field, required=True)
    args = parser.parse_args()
    destination = Path(os.environ["INFERRSI_RESULT_PATH"])
    result = {"status": "error", "action": args.action, "passed": False}
    try:
        task = load_task(args.package)
        candidate = Path(args.candidate)
        expected = {
            "task_id": task.manifest["id"],
            "task_sha256": args.task_sha256,
            "grader_sha256": args.grader_sha256,
            "candidate_sha256": args.candidate_sha256,
            "runtime_sha256": args.runtime_sha256,
        }
        if task.identity(candidate) != expected:
            raise ValueError("Frozen task, grader or candidate changed")
        if task.manifest["adapter"] == "torch-npu-rmsnorm-v1":
            from .npu_task import evaluate
        else:
            from .numpy_task import evaluate

        result = evaluate(task, candidate, args.action, destination.parent)
        if task.identity(candidate) != expected:
            raise ValueError("Frozen task, grader or candidate changed during execution")
        result["identity"] = expected
    except Exception as error:
        # Errors are incomplete evidence, never numerical correctness failures.
        # Do not capture arbitrary exception text that may expose private paths.
        result = {
            "status": "error",
            "action": args.action,
            "passed": False,
            "error_type": type(error).__name__,
        }
    atomic_write_json(destination, result)
    print(json.dumps({k: result[k] for k in ("status", "action", "passed")}))
    return 0 if result["status"] == "completed" and result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
