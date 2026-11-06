"""CLI argument declarations and RunSpec construction."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from . import __version__
from ._skill_selection import RELEVANCE_METHODS
from .catalog import BACKENDS, KNOWLEDGE_REPOS, KNOWLEDGE_SCOPES, REPO_TYPES
from .runspec import RunSpec

TARGET_DEFAULTS = {
    "repo": ".", "repo_type": "vllm_omni", "backend": "cpu", "device_ids": "",
    "device_model": None, "python": sys.executable,
}
EXPERIMENT_DEFAULTS = {
    **TARGET_DEFAULTS,
    "candidate_repo": None,
    "scenario": "external_benchmark",
    "mode": "config",
    "agent": "manual",
    "executor": "local",
    "validation_command": None,
    "metric_key": "metrics.latency_ms",
    "require_trial_check": (),
    "metric_unit": "ms",
    "comparison_scope": "external_command",
    "direction": "minimize",
    "repetitions": 3,
    "min_improvement_pct": 0.0,
    "max_minutes": 120.0,
    "workload_id": None,
    "model": None,
    "model_revision": None,
    "output_dir": "runs",
}


class _ArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        if parsed.command in ("plan", "run") and not hasattr(parsed, "task"):
            if getattr(parsed, "confirm_acceptance", False):
                self.error("--confirm-acceptance requires --task")
            required = ("baseline_command", "candidate_command")
            missing = [
                f"--{name.replace('_', '-')}" for name in required if not hasattr(parsed, name)
            ]
            if missing:
                self.error("the following arguments are required: " + ", ".join(missing))
            return argparse.Namespace(**(EXPERIMENT_DEFAULTS | vars(parsed)))
        return parsed


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", help="Prepared target Git checkout")
    parser.add_argument("--repo-type", choices=REPO_TYPES)
    parser.add_argument("--backend", choices=BACKENDS)
    parser.add_argument(
        "--device-ids",
        help=(
            "Comma-separated caller-assigned device IDs; "
            "unsupported by MLX unified-memory discovery"
        ),
    )
    parser.add_argument(
        "--device-model",
        help="Expected CUDA device model or Apple Silicon chip (case-insensitive match)",
    )
    parser.add_argument(
        "--python", help="Python used for target package inspection"
    )


def _experiment_options(child: argparse.ArgumentParser) -> None:
    _common(child)
    child.add_argument(
        "--candidate-repo", help="Candidate checkout; defaults to the baseline checkout"
    )
    child.add_argument(
        "--scenario", help="Caller-declared scenario label"
    )
    child.add_argument("--mode", choices=("config", "code", "semantic"))
    child.add_argument(
        "--agent",
        choices=("manual", "codex", "external"),
        help="Handoff label only; no Agent is launched",
    )
    child.add_argument(
        "--executor",
        choices=("local",),
        help="Install this CLI on the remote machine for this first release",
    )
    child.add_argument(
        "--baseline-command",
        help="Quoted argv command; {result} is replaced with a fresh output path",
    )
    child.add_argument("--candidate-command")
    child.add_argument(
        "--validation-command",
        help="Explicit quality/correctness command; missing evidence is INCONCLUSIVE",
    )
    child.add_argument(
        "--metric-key",
        help="Flat or dotted key in benchmark JSON",
    )
    child.add_argument(
        "--require-trial-check", action="append", metavar="DOTTED_KEY",
        help="Require a literal true qualification field in every benchmark JSON; repeatable",
    )
    child.add_argument("--metric-unit")
    child.add_argument("--comparison-scope")
    child.add_argument("--direction", choices=("minimize", "maximize"))
    child.add_argument("--repetitions", type=int)
    child.add_argument("--min-improvement-pct", type=float)
    child.add_argument(
        "--max-minutes",
        type=float,
        help="Experiment deadline, at most seven days",
    )
    child.add_argument("--workload-id", help="Caller-declared fixed workload identity")
    child.add_argument("--model", help="Model identity/path recorded in the experiment")
    child.add_argument("--model-revision")
    child.add_argument("--output-dir")


def parser() -> argparse.ArgumentParser:
    root = _ArgumentParser(
        description="CLI-first reproducible experiments and tuning knowledge"
    )
    commands = root.add_subparsers(dest="command", required=True)
    root.add_argument("--version", action="version", version=__version__)
    doctor = commands.add_parser(
        "doctor", help="Inspect a prepared local target without installing dependencies"
    )
    _common(doctor)
    doctor.set_defaults(**TARGET_DEFAULTS)

    for name in ("plan", "run"):
        child = commands.add_parser(
            name,
            help="Preview an external-command experiment"
            if name == "plan"
            else "Measure baseline and candidate commands",
            argument_default=argparse.SUPPRESS,
        )
        _experiment_options(child)
        child.add_argument("--task", help="Read a versioned YAML task")
        child.add_argument("--dry-run", action="store_true", default=False)
        if name == "run":
            child.add_argument(
                "--confirm-acceptance", action="store_true",
                help="Confirm the effective YAML task was checked against the frozen gates",
            )

    task = commands.add_parser("task", help="Read or inspect shared YAML tasks")
    actions = task.add_subparsers(dest="task_action", required=True)
    for name in ("validate", "preview"):
        child = actions.add_parser(name, argument_default=argparse.SUPPRESS)
        child.add_argument("task", help="Path to the YAML task")
        child.add_argument("--json", action="store_true", default=False)
        if name == "preview":
            _experiment_options(child)
    actions.add_parser("schema", help="Print the packaged v1 schema")
    actions.add_parser("template", help="Print the packaged v1 YAML template")

    for name in ("status", "report"):
        child = commands.add_parser(
            name,
            help="Read a recorded experiment" if name == "status" else "Regenerate its HTML report",
        )
        child.add_argument("--run-id", required=True)
        child.add_argument("--output-dir", default="runs")

    dashboard = commands.add_parser(
        "dashboard", help="Export an offline dashboard for one run or recorded campaign"
    )
    dashboard.add_argument("--input", type=Path, required=True, help="Run or campaign directory")
    dashboard.add_argument(
        "--output", type=Path, help="HTML output (default: input/dashboard.html)"
    )
    dashboard.add_argument(
        "--translations", type=Path, help="Reviewed bilingual text overlay in JSON"
    )
    dashboard.add_argument(
        "--live", action="store_true", help="Serve a live read-only view on loopback"
    )
    dashboard.add_argument("--port", type=int, help="Live loopback port (default: 8765)")

    campaign = commands.add_parser("campaign", help="Create local campaign correlation records")
    campaign_actions = campaign.add_subparsers(dest="campaign_action", required=True)
    create = campaign_actions.add_parser("init", help="Create a new campaign manifest")
    create.add_argument("--directory", type=Path, required=True)
    create.add_argument("--id", required=True)
    create.add_argument("--target-pct", type=float)
    create.add_argument("--noise-pct", type=float)
    create.add_argument("--synthetic", action="store_true")
    assemble = campaign_actions.add_parser(
        "assemble-trace",
        help="Insert an explicitly reviewed context file into a trace template",
    )
    assemble.add_argument("--directory", type=Path, required=True)
    assemble.add_argument("--template", type=Path, required=True)
    assemble.add_argument("--context-file", type=Path, required=True)
    assemble.add_argument("--output", required=True, help="New JSON filename in the campaign root")
    record = campaign_actions.add_parser("record", help="Associate a candidate with one run")
    record.add_argument("--directory", type=Path, required=True)
    record.add_argument("--candidate", required=True)
    record.add_argument("--run-id", required=True)
    record.add_argument("--round", type=int, required=True)
    record.add_argument("--title", required=True)
    record.add_argument("--details-json", type=Path,
                        help="JSON file describing the optimization and code locations")
    record.add_argument("--agent-trace", help="Existing campaign-relative JSONL trace")
    record.add_argument("--profile", help="Existing campaign-relative profile artifact")
    record.add_argument("--optimization-trace",
                        help="Caller-reviewed campaign-relative optimization trace JSON")
    capture = campaign_actions.add_parser(
        "capture-context",
        help="Run collect and keep the exact knowledge context it assembled",
    )
    capture.add_argument("--directory", type=Path, required=True)
    capture.add_argument("--id", required=True, help="New context id, e.g. r1-diagnosis")
    capture.add_argument("query", nargs="?", default="")
    capture.add_argument("--relevance", help="Lexical cue for packaged skill selection")
    capture.add_argument("--relevance-method", choices=RELEVANCE_METHODS,
                         default="weighted-lexical-v1")
    capture.add_argument("--id-ref", action="append", dest="ids", metavar="ID",
                         help="Exact knowledge identity to include (repeatable)")
    capture.add_argument("--kind", choices=("skill", "knowledge", "case"))
    capture.add_argument("--repo-type", dest="knowledge_repo", choices=KNOWLEDGE_REPOS)
    capture.add_argument("--tier", choices=KNOWLEDGE_SCOPES)
    capture.add_argument("--backend", choices=BACKENDS)
    capture.add_argument("--scenario")
    capture.add_argument("--limit", type=int, default=5)
    capture.add_argument("--context-bytes", type=int, default=65536)
    capture.add_argument("--skill-root", type=Path)
    capture.add_argument("--store", type=Path)
    log = campaign_actions.add_parser(
        "log", help="Record a new version of the campaign optimization log"
    )
    log.add_argument("--directory", type=Path, required=True)
    log.add_argument("--file", type=Path, required=True, help="Optimization log JSON")
    decision = campaign_actions.add_parser("decide", help="Record one round decision")
    decision.add_argument("--directory", type=Path, required=True)
    decision.add_argument("--candidate", required=True)
    decision.add_argument("--round", type=int, required=True)
    decision.add_argument("--outcome", required=True,
                          choices=("adopted", "rejected", "rolled_back", "no_gain", "noise"))

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
    research = actions.add_parser(
        "research", help="Union model/framework/task/modality/mechanism queries for preparation"
    )
    research.add_argument("model")
    for dimension in ("framework", "task", "modality", "mechanism"):
        research.add_argument(
            f"--{dimension}", action="append", default=[],
            help=f"Additional independent {dimension} query (repeatable)",
        )
    research.add_argument("--repo-type", choices=KNOWLEDGE_REPOS)
    research.add_argument("--tier", choices=KNOWLEDGE_SCOPES)
    research.add_argument("--backend", choices=BACKENDS, help="Hard package-record filter")
    research.add_argument("--scenario")
    research.add_argument("--limit", type=int, default=10)
    research.add_argument(
        "--target-backend", help="Research target only; no runtime support implied"
    )
    research.add_argument("--target-device", help="Caller-declared research target")
    research.add_argument(
        "--target-memory-gib", type=float, help="Caller-declared unified/device GiB"
    )

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
    collect.add_argument("--relevance", help="Opt-in lexical cue for packaged skill selection")
    collect.add_argument(
        "--relevance-method", choices=RELEVANCE_METHODS, default="weighted-lexical-v1",
        help="Packaged skill ranking method; nondefault method requires --relevance",
    )
    collect.add_argument(
        "--context-bytes", type=int,
        help="Opt-in context view; total UTF-8 resource-body byte budget",
    )
    collect.add_argument(
        "--skill-root",
        type=Path,
        help="Select an explicit skills root",
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
        help="Select an explicit skills root",
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
        help="Select an explicit skills root",
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


def command_argv(value: str | list[str] | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    parsed = tuple(shlex.split(value, posix=True)) if isinstance(value, str) else tuple(value)
    if not parsed:
        raise ValueError("Commands cannot be empty")
    return parsed


def make_spec(args: argparse.Namespace) -> RunSpec:

    spec = RunSpec(
        repo=str(Path(args.repo).resolve()),
        candidate_repo=str(Path(args.candidate_repo).resolve()) if args.candidate_repo else None,
        repo_type=args.repo_type,
        backend=args.backend,
        scenario=args.scenario,
        mode=args.mode,
        baseline_command=command_argv(args.baseline_command),
        candidate_command=command_argv(args.candidate_command),
        validation_command=command_argv(args.validation_command),
        metric_key=args.metric_key,
        required_trial_checks=tuple(args.require_trial_check),
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
