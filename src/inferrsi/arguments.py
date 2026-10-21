"""The user configuration surface is argparse, not task files."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from . import __version__
from .catalog import BACKENDS, KNOWLEDGE_REPOS, KNOWLEDGE_SCOPES, REPO_TYPES
from .runspec import RunSpec


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".", help="Prepared target Git checkout")
    parser.add_argument("--repo-type", choices=REPO_TYPES, default="vllm_omni")
    parser.add_argument("--backend", choices=BACKENDS, default="cpu")
    parser.add_argument(
        "--device-ids", default="", help="Comma-separated caller-assigned device IDs"
    )
    parser.add_argument(
        "--device-model", help="Expected CUDA device model; other probes retain raw output"
    )
    parser.add_argument(
        "--python", default=sys.executable, help="Python used for target package inspection"
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="CLI-first reproducible experiments and tuning knowledge"
    )
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser(
        "doctor", help="Inspect a prepared local target without installing dependencies"
    )
    _common(doctor)

    for name in ("plan", "run"):
        child = commands.add_parser(
            name,
            help="Freeze an external-command experiment"
            if name == "plan"
            else "Measure baseline and candidate commands",
        )
        _common(child)
        child.add_argument(
            "--candidate-repo", help="Candidate checkout; defaults to the baseline checkout"
        )
        child.add_argument(
            "--scenario", default="external_benchmark", help="Caller-declared scenario label"
        )
        child.add_argument("--mode", choices=("config", "code", "semantic"), default="config")
        child.add_argument(
            "--objective", choices=("performance", "correctness"), default="performance",
            help="Correctness compares paired outputs without a performance metric or claim",
        )
        child.add_argument(
            "--agent",
            choices=("manual", "codex", "external"),
            default="manual",
            help="Handoff label only; no Agent is launched",
        )
        child.add_argument(
            "--executor",
            choices=("local",),
            default="local",
            help="Install this CLI on the remote machine for this first release",
        )
        child.add_argument(
            "--baseline-command",
            required=True,
            help="Quoted argv command; {result} is replaced with a fresh output path",
        )
        child.add_argument("--candidate-command", required=True)
        child.add_argument(
            "--validation-command",
            help="Explicit quality/correctness command; missing evidence is INCONCLUSIVE",
        )
        child.add_argument(
            "--metric-key",
            default="metrics.latency_ms",
            help="Flat or dotted key in benchmark JSON",
        )
        child.add_argument("--metric-unit", default="ms")
        child.add_argument("--comparison-scope", default="external_command")
        child.add_argument("--direction", choices=("minimize", "maximize"), default="minimize")
        child.add_argument("--repetitions", type=int, default=3)
        child.add_argument("--min-improvement-pct", type=float, default=0.0)
        child.add_argument(
            "--max-minutes",
            type=float,
            default=120.0,
            help="Experiment deadline, at most seven days",
        )
        child.add_argument("--workload-id", help="Caller-declared fixed workload identity")
        child.add_argument("--model", help="Model identity/path recorded in the experiment")
        child.add_argument("--model-revision")
        child.add_argument("--output-dir", default="runs")
        child.add_argument("--dry-run", action="store_true")

    for name in ("status", "report"):
        child = commands.add_parser(
            name,
            help="Read a recorded experiment" if name == "status" else "Regenerate its HTML report",
        )
        child.add_argument("--run-id", required=True)
        child.add_argument("--output-dir", default="runs")

    skills = commands.add_parser(
        "skills", help="Read explicitly selected skills; never install or execute them"
    )
    skills.add_argument(
        "--root",
        type=Path,
        help="Skill library or flat skill directory (default: installed library)",
    )
    actions = skills.add_subparsers(dest="skills_action", required=True)
    listing = actions.add_parser("list", help="List frontmatter and sidecar metadata only")
    listing.add_argument("--json", action="store_true")
    show = actions.add_parser("show", help="Load one skill's instructions and resource names")
    show.add_argument("name")
    resource = actions.add_parser("resource", help="Resolve one resource without executing it")
    resource.add_argument("name")
    resource.add_argument("path")
    reference = actions.add_parser("reference", help="Resolve a declared shared checkout reference")
    reference.add_argument("name")
    reference.add_argument("path")

    knowledge = commands.add_parser(
        "knowledge", help="Search or inspect source-grounded imported experience"
    )
    actions = knowledge.add_subparsers(dest="knowledge_action", required=True)
    search = actions.add_parser(
        "search",
        help="Search installed package records only; the repo/tier/backend/scenario "
        "filters exclude checkout and store items",
    )
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--repo-type", choices=KNOWLEDGE_REPOS)
    search.add_argument("--tier", choices=KNOWLEDGE_SCOPES)
    search.add_argument("--backend", choices=BACKENDS)
    search.add_argument("--scenario")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--json", action="store_true")
    show = actions.add_parser("show")
    show.add_argument("id")

    collect = commands.add_parser(
        "collect",
        help="Collect explicitly selected sources as a revision-pinned envelope; "
        "package-only unless --skill-root or --store adds them",
    )
    collect.add_argument("query", nargs="?", default="")
    collect.add_argument("--kind", choices=("skill", "knowledge", "case"))
    collect.add_argument(
        "--id", action="append", dest="ids", metavar="ID", help="Exact requested identity"
    )
    collect.add_argument(
        "--revision",
        action="append",
        dest="revisions",
        metavar="ID=REV",
        help="Pin a requested ID to its exact revision",
    )
    collect.add_argument("--limit", type=int, default=10)
    collect.add_argument("--max-bytes", type=int)
    collect.add_argument("--material", action="store_true")
    collect.add_argument(
        "--skill-root",
        type=Path,
        help="Select an explicit skills root (requires the 'skills' extra)",
    )
    collect.add_argument(
        "--store",
        type=Path,
        help="Open an existing store read-only; its database must already exist",
    )
    collect.add_argument("--json", action="store_true")

    read = commands.add_parser(
        "read",
        help="Read one bundle; select sources explicitly with --skill-root/--store",
    )
    read.add_argument("id")
    read.add_argument("--revision", help="Exact revision returned by collect or read")
    read.add_argument("--material", action="store_true")
    read.add_argument(
        "--skill-root",
        type=Path,
        help="Select an explicit skills root (requires the 'skills' extra)",
    )
    read.add_argument(
        "--store",
        type=Path,
        help="Open an existing store read-only; its database must already exist",
    )

    resource = commands.add_parser(
        "resource",
        help="Write one raw bundle resource of an exact revision to --output",
    )
    resource.add_argument("id")
    resource.add_argument("path")
    resource.add_argument(
        "--revision", required=True, help="Exact revision returned by collect or read"
    )
    resource.add_argument(
        "--skill-root",
        type=Path,
        help="Select an explicit skills root (requires the 'skills' extra)",
    )
    resource.add_argument(
        "--store",
        type=Path,
        help="Open an existing store read-only; its database must already exist",
    )
    resource.add_argument("--output", type=Path, required=True, help="File receiving the raw bytes")

    context = commands.add_parser(
        "context", help="Export cited knowledge for manual Codex/Agent handoff"
    )
    context.add_argument("query", nargs="?", default="")
    context.add_argument("--repo-type", choices=KNOWLEDGE_REPOS, required=True)
    context.add_argument("--tier", choices=KNOWLEDGE_SCOPES)
    context.add_argument("--backend", choices=BACKENDS, required=True)
    context.add_argument("--scenario")
    context.add_argument("--limit", type=int, default=5)
    context.add_argument("--output", help="Write a Markdown context file instead of stdout")
    return root


def device_ids(args: argparse.Namespace) -> tuple[str, ...]:
    values = tuple(value.strip() for value in args.device_ids.split(",") if value.strip())
    if len(set(values)) != len(values):
        raise ValueError("device IDs must be unique")
    return values


def make_spec(args: argparse.Namespace) -> RunSpec:
    def command(value: str | None) -> tuple[str, ...] | None:
        if value is None:
            return None
        parsed = tuple(shlex.split(value, posix=True))
        if not parsed:
            raise ValueError("Commands cannot be empty")
        return parsed

    spec = RunSpec(
        repo=str(Path(args.repo).resolve()),
        candidate_repo=str(Path(args.candidate_repo).resolve()) if args.candidate_repo else None,
        repo_type=args.repo_type,
        backend=args.backend,
        scenario=args.scenario,
        mode=args.mode,
        objective=args.objective,
        baseline_command=command(args.baseline_command),
        candidate_command=command(args.candidate_command),
        validation_command=command(args.validation_command),
        metric_key=args.metric_key,
        metric_unit=args.metric_unit,
        comparison_scope=args.comparison_scope,
        direction=args.direction,
        repetitions=args.repetitions,
        min_improvement_pct=args.min_improvement_pct,
        max_minutes=args.max_minutes,
        workload_id=args.workload_id,
        model=args.model,
        model_revision=args.model_revision,
        agent=args.agent,
        device_ids=device_ids(args),
        output_dir=str(Path(args.output_dir).resolve()),
    )
    spec.validate()
    return spec
