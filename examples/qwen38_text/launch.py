"""Run the scoped reference self-check through InferRSI inside an allocation."""

import argparse
import json
import os
import sys
from pathlib import Path

from examples.qwen38_text.trial import HEX40, load_workload
from inferrsi.harness.runner import run_experiment
from inferrsi.infra.inspection import inspect_environment
from inferrsi.runspec import RunSpec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "model-path", "manifest", "workload", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--device-model", required=True)
    for name in ("max-nrmse", "min-top1", "rms-floor", "max-minutes"):
        parser.add_argument("--" + name, required=True, type=float)
    parser.add_argument("--repetitions", required=True, type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    control_repo = Path(__file__).resolve().parents[2]
    if args.repo.resolve() != control_repo:
        parser.error("reference self-check must snapshot its actual control checkout")
    task_root = os.environ.get("TASK_ROOT")
    if task_root and not args.output_dir.resolve().is_relative_to(Path(task_root).resolve()):
        parser.error("output directory must stay inside the authorized task root")
    if not HEX40.fullmatch(args.model_revision):
        parser.error("model revision must be an immutable commit")
    _, workload_hash = load_workload(args.workload)
    example = Path(__file__).resolve().parent
    trial = (sys.executable, str(example / "trial.py"),
             "--model-path", str(args.model_path.resolve()),
             "--model-revision", args.model_revision,
             "--manifest", str(args.manifest.resolve()),
             "--workload", str(args.workload.resolve()),
             "--device-model", args.device_model, "--output", "{result}")
    validator = (sys.executable, str(example / "validate.py"),
                 "--run-dir", "{run_dir}", "--workload", str(args.workload.resolve()),
                 "--manifest", str(args.manifest.resolve()),
                 "--max-nrmse", str(args.max_nrmse), "--min-top1", str(args.min_top1),
                 "--rms-floor", str(args.rms_floor), "--output", "{result}")
    spec = RunSpec(
        repo=str(args.repo.resolve()), repo_type="nano_vllm", backend="cuda",
        scenario="llm.text.reference_self_check", mode="config", objective="correctness",
        baseline_command=trial + ("--mode", "full"),
        candidate_command=trial + ("--mode", "cached"), validation_command=validator,
        comparison_scope="reference_self_check", repetitions=args.repetitions,
        max_minutes=args.max_minutes, workload_id=workload_hash,
        model="Qwen/Qwen3.8-27B", model_revision=args.model_revision,
        agent="codex", device_ids=tuple(filter(None, os.environ.get(
            "CUDA_VISIBLE_DEVICES", "").split(","))), executor="local",
        output_dir=str(args.output_dir.resolve()),
    )
    spec.validate()
    if args.dry_run:
        # Contains operational paths: keep this preview in private task storage.
        print(json.dumps(spec.to_dict(), indent=2))
        return 0
    if not os.environ.get("SLURM_JOB_ID"):
        parser.error("model validation requires an active Slurm allocation")
    if len(spec.device_ids) != 1:
        parser.error("Slurm must expose exactly one allocated CUDA device")
    environment = inspect_environment(
        spec.repo, spec.repo_type, spec.backend, device_ids=spec.device_ids,
        device_model=args.device_model, python=sys.executable,
    )
    run_dir = run_experiment(spec, environment)
    evaluation = json.loads((run_dir / "evaluation.json").read_text())
    print(json.dumps({"run_id": run_dir.name, "verdict": evaluation["verdict"],
                      "qualification_scope": "reference_self_check"}))
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[evaluation["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
