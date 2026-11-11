"""The user configuration surface is argparse, not task files."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from . import __version__
from ._skill_selection import RELEVANCE_METHODS
from .catalog import BACKENDS, KNOWLEDGE_REPOS, KNOWLEDGE_SCOPES, REPO_TYPES
from .runspec import RunSpec


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".", help="Prepared target Git checkout")
    parser.add_argument("--repo-type", choices=REPO_TYPES, default="vllm_omni")
    parser.add_argument("--backend", choices=BACKENDS, default="cpu")
    parser.add_argument(
        "--device-ids", default="",
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
        "--python", default=sys.executable, help="Python used for target package inspection"
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="CLI-first reproducible experiments and tuning knowledge"
    )
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    mindie = commands.add_parser("mindie", help="Use project-approved, local MindIE knowledge")
    mindie_actions = mindie.add_subparsers(dest="mindie_action", required=True)
    enable = mindie_actions.add_parser("enable", help="Approve a MindIE domain for this checkout")
    enable.add_argument("--domain", default="operators")
    enable.add_argument(
        "--adapter-config", type=Path, default=Path.home() / ".config/mindie-agent/codex.json",
        help="Installed MindIE Codex adapter configuration",
    )
    mindie_actions.add_parser("disable", help="Revoke the project grant")
    mindie_actions.add_parser("describe", help="Discover read tools for the current project")
    mindie_actions.add_parser("serve", help="Expose the approved read tools over stdio MCP")
    for action in ("query", "explain"):
        read = mindie_actions.add_parser(action, help=f"Run a MindIE {action} and keep a receipt")
        read.add_argument("--input", type=Path, required=True, help="JSON tool arguments")
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
        child.add_argument(
            "--require-trial-check", action="append", default=[], metavar="DOTTED_KEY",
            help="Require a literal true qualification field in every benchmark JSON; repeatable",
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
    mindie = campaign_actions.add_parser(
        "import-mindie", help="Keep supplied MindIE query/explain evidence for a reviewed trace",
    )
    mindie.add_argument("--directory", type=Path, required=True)
    mindie.add_argument("--id", required=True, help="New local read id; never overwritten")
    for name in ("query-input", "query-result", "explain-input", "explain-result"):
        mindie.add_argument("--" + name, type=Path, required=True)
    mindie.add_argument("--query-exit-code", type=int, required=True)
    mindie.add_argument("--explain-exit-code", type=int, required=True)
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
        baseline_command=command(args.baseline_command),
        candidate_command=command(args.candidate_command),
        validation_command=command(args.validation_command),
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
