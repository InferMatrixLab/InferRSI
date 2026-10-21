"""Run explicit reference or native text smoke through InferRSI in an allocation."""

import argparse
import json
import os
import sys
from pathlib import Path

from examples.qwen38_text.profiles import BF16_MODEL_ID, FP8_MODEL_ID, MODEL_IDS
from examples.qwen38_text.trial import HEX40, load_workload
from inferrsi.harness.runner import run_experiment
from inferrsi.infra.inspection import inspect_environment
from inferrsi.runspec import RunSpec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "model-path", "manifest", "workload", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--model-id", choices=MODEL_IDS, default=BF16_MODEL_ID)
    parser.add_argument("--fp8-kernel-revision")
    parser.add_argument("--fp8-kernel-sha256")
    parser.add_argument("--device-model", required=True)
    parser.add_argument("--qualification-scope", default="reference_self_check",
                        choices=("reference_self_check", "native_text_smoke"))
    parser.add_argument("--candidate-repo", type=Path)
    for name in ("max-nrmse", "min-top1", "rms-floor", "max-minutes"):
        parser.add_argument("--" + name, required=True, type=float)
    parser.add_argument("--repetitions", required=True, type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    control_repo = Path(__file__).resolve().parents[2]
    if args.repo.resolve() != control_repo:
        parser.error("text smoke must snapshot its actual control checkout")
    native = args.qualification_scope == "native_text_smoke"
    if native and (args.candidate_repo is None or args.candidate_repo.resolve() == control_repo):
        parser.error("native smoke requires a separate explicit engine checkout")
    if not native and args.candidate_repo is not None:
        parser.error("reference self-check cannot declare a native candidate checkout")
    task_root = os.environ.get("TASK_ROOT")
    if task_root and not args.output_dir.resolve().is_relative_to(Path(task_root).resolve()):
        parser.error("output directory must stay inside the authorized task root")
    if native and task_root and not args.candidate_repo.resolve().is_relative_to(
        Path(task_root).resolve()
    ):
        parser.error("native engine checkout must stay inside the authorized task root")
    if not HEX40.fullmatch(args.model_revision):
        parser.error("model revision must be an immutable commit")
    _, workload_hash = load_workload(args.workload, args.model_id)
    fp8_args = ()
    if args.model_id == FP8_MODEL_ID:
        from examples.qwen38_text.trial import HEX64
        if (not args.fp8_kernel_revision or not HEX40.fullmatch(args.fp8_kernel_revision)
                or not args.fp8_kernel_sha256 or not HEX64.fullmatch(args.fp8_kernel_sha256)):
            parser.error("FP8 requires immutable reference kernel revision and source digest")
        fp8_args = ("--fp8-kernel-revision", args.fp8_kernel_revision,
                    "--fp8-kernel-sha256", args.fp8_kernel_sha256)
    elif args.fp8_kernel_revision or args.fp8_kernel_sha256:
        parser.error("BF16 cannot declare an FP8 reference kernel")
    example = Path(__file__).resolve().parent
    trial = (sys.executable, str(example / "trial.py"),
             "--model-path", str(args.model_path.resolve()),
             "--model-revision", args.model_revision, "--model-id", args.model_id,
             "--manifest", str(args.manifest.resolve()),
             "--workload", str(args.workload.resolve()),
             "--device-model", args.device_model, "--output", "{result}")
    validator = (sys.executable, str(example / "validate.py"),
                 "--run-dir", "{run_dir}", "--workload", str(args.workload.resolve()),
                 "--manifest", str(args.manifest.resolve()),
                 "--model-path", str(args.model_path.resolve()),
                 "--max-nrmse", str(args.max_nrmse), "--min-top1", str(args.min_top1),
                 "--rms-floor", str(args.rms_floor), "--output", "{result}")
    baseline = trial + ("--mode", "full", "--qualification-scope", args.qualification_scope)
    candidate = trial + ("--mode", "cached")
    if native:
        candidate = (sys.executable, str(example / "native_trial.py")) + trial[2:] + (
            "--engine-repo", str(args.candidate_repo.resolve()),
        )
    baseline += fp8_args
    if not native:
        candidate += fp8_args
    validator += ("--qualification-scope", args.qualification_scope,
                  "--model-id", args.model_id) + fp8_args
    spec = RunSpec(
        repo=str(args.repo.resolve()), repo_type="nano_vllm", backend="cuda",
        candidate_repo=str(args.candidate_repo.resolve()) if native else None,
        scenario="llm.text." + args.qualification_scope,
        mode="code" if native else "config", objective="correctness",
        baseline_command=baseline, candidate_command=candidate, validation_command=validator,
        comparison_scope=args.qualification_scope, repetitions=args.repetitions,
        max_minutes=args.max_minutes, workload_id=workload_hash,
        model=args.model_id, model_revision=args.model_revision,
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
                      "qualification_scope": args.qualification_scope}))
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[evaluation["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
