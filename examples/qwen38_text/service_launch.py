"""Run public-entry versus HTTP functional qualification through the common runner."""

import argparse
import json
import os
import sys
from pathlib import Path

from examples.qwen38_text.profiles import BF16_MODEL_ID, MODEL_IDS
from examples.qwen38_text.service_protocol import SCOPE, read_protocol
from examples.qwen38_text.trial import HEX40
from inferrsi.harness.runner import run_experiment
from inferrsi.infra.inspection import inspect_environment
from inferrsi.runspec import RunSpec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("engine-repo", "model-path", "manifest", "workload", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--model-id", choices=MODEL_IDS, default=BF16_MODEL_ID)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--device-model", required=True)
    parser.add_argument("--max-minutes", type=float, required=True)
    parser.add_argument("--repetitions", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    control = Path(__file__).resolve().parents[2]
    engine = args.engine_repo.resolve(strict=True)
    if engine == control or not HEX40.fullmatch(args.model_revision):
        parser.error(
            "service qualification requires a separate engine and immutable model revision"
        )
    task_root = os.environ.get("TASK_ROOT")
    if task_root and any(
        not path.resolve().is_relative_to(Path(task_root).resolve())
        for path in (args.output_dir, engine)
    ):
        parser.error("service engine and output paths must stay inside the authorized task root")
    _, workload_hash = read_protocol(args.workload, args.model_id)
    example = Path(__file__).resolve().parent
    common = (
        "--model-id",
        args.model_id,
        "--manifest",
        str(args.manifest.resolve()),
        "--workload",
        str(args.workload.resolve()),
    )
    trial = (
        sys.executable,
        str(example / "service_trial.py"),
        *common,
        "--engine-repo",
        str(engine),
        "--model-path",
        str(args.model_path.resolve()),
        "--model-revision",
        args.model_revision,
        "--output",
        "{result}",
    )
    spec = RunSpec(
        repo=str(control),
        candidate_repo=str(engine),
        repo_type="nano_vllm",
        backend="cuda",
        scenario="llm.text." + SCOPE,
        comparison_scope=SCOPE,
        objective="correctness",
        mode="config",
        baseline_command=trial + ("--mode", "public"),
        candidate_command=trial + ("--mode", "http"),
        validation_command=(
            sys.executable,
            str(example / "service_validate.py"),
            *common,
            "--run-dir",
            "{run_dir}",
            "--output",
            "{result}",
        ),
        repetitions=args.repetitions,
        max_minutes=args.max_minutes,
        model=args.model_id,
        model_revision=args.model_revision,
        workload_id=workload_hash,
        agent="codex",
        executor="local",
        device_ids=tuple(filter(None, os.environ.get("CUDA_VISIBLE_DEVICES", "").split(","))),
        output_dir=str(args.output_dir.resolve()),
    )
    spec.validate()
    if args.dry_run:
        print(json.dumps(spec.to_dict(), indent=2))
        return 0
    if not os.environ.get("SLURM_JOB_ID") or len(spec.device_ids) != 1:
        parser.error("service qualification requires one visible GPU in an active Slurm allocation")
    environment = inspect_environment(
        spec.repo,
        spec.repo_type,
        spec.backend,
        device_ids=spec.device_ids,
        device_model=args.device_model,
        python=sys.executable,
    )
    run = run_experiment(spec, environment)
    result = json.loads((run / "evaluation.json").read_text())
    print(
        json.dumps({"run_id": run.name, "verdict": result["verdict"], "qualification_scope": SCOPE})
    )
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[result["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
