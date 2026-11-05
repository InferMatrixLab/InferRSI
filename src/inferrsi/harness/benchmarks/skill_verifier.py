"""SkillEval verifier for a controller-selected, reviewed retained artifact.

This is an offline handoff after artifact review, not live generated-code
execution. It deliberately leaves the production engineering sandbox unchanged.
"""

import json
import os
import sys
from pathlib import Path

from inferrsi.harness.benchmarks.consumers import grade_artifact
from inferrsi.harness.benchmarks.contract import load_task
from inferrsi.infra.artifacts import atomic_write_json


def task_descriptor(task, candidate: Path) -> dict:
    return {
        "id": task.manifest["id"],
        "split": "development",
        "request": "Submit the SHA-256 of the controller-reviewed retained implementation.",
        "provenance": task.manifest["source"]["url"],
        "benchmark": {
            "package": str(task.root),
            "candidate": str(candidate.resolve()),
            "identity": task.identity(candidate),
        },
    }


def verify(task: dict, answer: dict, output_dir: Path) -> dict:
    binding = task["benchmark"]
    package = load_task(binding["package"])
    candidate = Path(binding["candidate"])
    if package.identity(candidate) != binding["identity"]:
        raise ValueError("Retained artifact or task identity changed")
    if answer != {"candidate_sha256": binding["identity"]["candidate_sha256"]}:
        return {"passed": False, "assertions": {"artifact_identity": False}}
    record = grade_artifact(package, candidate, output_dir, timeout_seconds=25)
    if record["checks"] is None:
        raise ValueError("Artifact verification did not complete")
    return record["checks"]


def main():
    destination = Path(os.environ["INFERRSI_RESULT_PATH"])
    task = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    answer = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    result = verify(task, answer, destination.parent / "artifact")
    atomic_write_json(destination, result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
