"""CLI-first engineering benchmark operations; all execution is explicit."""

import math
from pathlib import Path

from ...infra.artifacts import atomic_write_json
from ..runner import run_experiment
from .consumers import grade_artifact, run_action
from .contract import builtin_tasks, load_task


def add_parser(commands):
    root = commands.add_parser("benchmarks", help="Shared engineering tasks (trusted CPU sources)")
    actions = root.add_subparsers(dest="benchmark_action", required=True)
    actions.add_parser("list")
    show = actions.add_parser("show")
    show.add_argument("task")
    for name in ("check", "measure", "profile", "grade", "plan", "compare"):
        child = actions.add_parser(name)
        child.add_argument("task", help="Built-in task ID or local task package directory")
        child.add_argument(
            "--candidate",
            type=Path,
            required=True,
            help="Reviewed self-contained Python source; no security sandbox",
        )
        child.add_argument("--output-dir", type=Path, required=True)
        if name in {"plan", "compare"}:
            child.add_argument("--repo", type=Path, required=True)
            child.add_argument("--repetitions", type=int, required=True)
            child.add_argument("--max-minutes", type=float, required=True)
            child.add_argument("--min-improvement-pct", type=float, required=True)
        else:
            child.add_argument("--timeout-seconds", type=float, required=True)


def dispatch(args) -> dict | list:
    action = args.benchmark_action
    if action == "list":
        return builtin_tasks()
    task = load_task(args.task)
    if action == "show":
        return {
            "manifest": task.manifest,
            "task_sha256": task.task_sha256,
            "grader_sha256": task.grader_sha256,
        }
    if action in {"plan", "compare"}:
        spec = task.runspec(
            args.candidate,
            repo=args.repo,
            output_dir=args.output_dir,
            repetitions=args.repetitions,
            max_minutes=args.max_minutes,
            min_improvement_pct=args.min_improvement_pct,
        )
        if action == "plan":
            return spec.to_dict()
        identity = task.identity(args.candidate)
        run_dir = run_experiment(
            spec,
            {
                "benchmark": identity,
                "backend": "cpu",
                "qualification": "local CPU development workload only",
            },
        )
        atomic_write_json(run_dir / "task.lock.json", task.manifest)
        return {
            "run_dir": str(run_dir),
            "scope": "local-artifact-comparison",
            "campaign_acceptance": "not established",
        }
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        raise ValueError("Timeout must be positive and finite")
    if action == "grade":
        return grade_artifact(
            task, args.candidate, args.output_dir, timeout_seconds=args.timeout_seconds
        )
    return run_action(
        task, args.candidate, action, args.output_dir, timeout_seconds=args.timeout_seconds
    )
