"""The user configuration surface: argparse flags, plus the read-only YAML task file.

``task validate`` and ``task preview`` read a schema v1 task file (``task_input``).
Preview accepts the mapped plan/run flags as explicit overrides; only flags the caller
supplies reach its namespace, so a parser default never replaces a YAML value.

``plan`` and ``run`` keep their flag defaults and also accept ``--task``. Their value
options record each dest the caller supplied in the namespace tuple ``_supplied``, so
task mode passes only those flags as overrides. ``--baseline-command`` and
``--candidate-command`` are required without ``--task``; ``main`` enforces that, because
a complete task file may supply them instead.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from ... import __version__
from ...contracts import RunSpec
from ...knowledge.catalog import BACKENDS, KNOWLEDGE_REPOS, KNOWLEDGE_SCOPES, REPO_TYPES
from .task_input import FIELDS as TASK_FIELDS


def _final_score(value: str) -> int | float:
    try:
        return int(value)
    except ValueError:
        score = float(value)
    if score.is_integer() and abs(score) >= 2**53:
        from decimal import Decimal

        # The finite float bounds the expanded integer to at most 309 digits.
        # Recover integral decimal/exponent spellings before they round to a weaker gate.
        exact = Decimal(value)
        if exact != exact.to_integral_value():
            raise argparse.ArgumentTypeError("Fractional final score exceeds float precision")
        return int(exact)
    return score


def _read_sources(parser: argparse.ArgumentParser) -> None:
    library = parser.add_mutually_exclusive_group()
    library.add_argument(
        "--skill-root", type=Path,
        help="Select a skills root; reading checkout skills requires PyYAML (a core dependency)",
    )
    library.add_argument(
        "--installed-library", action="store_true",
        help="Select the library bundled with this InferRSI installation",
    )
    parser.add_argument(
        "--store", type=Path,
        help="Open an existing store read-only; its database must already exist",
    )


def _fixed_attempt_args(
    parser: argparse.ArgumentParser, *, legacy_flag: str | None = None,
) -> None:
    source = parser
    if legacy_flag is not None:
        source = parser.add_mutually_exclusive_group(required=True)
        if legacy_flag == "--input":
            source.add_argument("--input", type=Path, help="Run or campaign directory")
        else:
            source.add_argument(legacy_flag)
    source.add_argument(
        "--record-ref", type=Path, required=legacy_flag is None,
        help="JSON file containing a RecordRef",
    )
    parser.add_argument("--storage-config", type=Path, help="Trusted storage config JSON")
    parser.add_argument("--assessment-ref", type=Path, help="Optional AssessmentRef JSON")


SUPPLIED = "_supplied"


class _Supplied:
    """Store as usual and record the dest, telling an explicit flag from its default."""

    def __call__(self, parser, namespace, values, option_string=None):
        super().__call__(parser, namespace, values, option_string)
        supplied = getattr(namespace, SUPPLIED, ())
        if self.dest not in supplied:
            setattr(namespace, SUPPLIED, (*supplied, self.dest))


class _SuppliedStore(_Supplied, argparse._StoreAction):
    pass


class _SuppliedAppend(_Supplied, argparse._AppendAction):
    pass


def command_parser(root: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser:
    """Return a subcommand's parser, so its errors keep that command's usage line."""
    for action in root._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[name]
    raise KeyError(name)


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


def _search_arguments(commands) -> None:
    search = commands.add_parser("search", help="Bounded SpecRSI search and role training")
    actions = search.add_subparsers(dest="search_action", required=True)
    run = actions.add_parser("engine", help="Run a supplied packaged Engine protocol")
    run.add_argument("--session", type=Path, required=True)
    run.add_argument("--store", type=Path, required=True, help="Shared resource/holdout RunStore")
    run.add_argument("--campaign", required=True, help="Unique campaign ID in the shared store")
    run.add_argument("--task", required=True)
    run.add_argument(
        "--edit",
        nargs=4,
        action="append",
        required=True,
        metavar=("TOKEN", "FILE", "BEFORE", "AFTER"),
    )
    run.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Initial trainable finite-edit role snapshot with provenance",
    )
    run.add_argument("--domain", required=True, help="Caller-owned exclusive measurement domain")
    run.add_argument("--max-seconds", type=int, required=True)
    run.add_argument("--evaluation-seconds", type=int, required=True)
    run.add_argument("--final-reserve-seconds", type=int, required=True)
    run.add_argument("--search-seconds", type=int, required=True)
    run.add_argument("--preparation-seconds", type=int, required=True)
    run.add_argument("--draft-seconds", type=int, required=True)
    run.add_argument("--training-seconds", type=int, required=True)
    run.add_argument("--candidates", type=int, required=True)
    run.add_argument("--depth", type=int, required=True)
    run.add_argument("--attempts", type=int, required=True)
    run.add_argument("--steps", type=int, required=True)
    run.add_argument("--plans", type=int, required=True)
    run.add_argument("--targets", type=int, required=True)
    run.add_argument("--groups", type=int, required=True, help="Independent searches per round")
    run.add_argument("--rounds", type=int, required=True)
    run.add_argument("--learning-rate", type=float, required=True)
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--mode", choices=("reset", "carry"), default="reset")
    run.add_argument("--final-scope", required=True)
    run.add_argument("--minimum-final-score", type=_final_score, required=True)
    run.add_argument("--python", default=sys.executable)
    run.add_argument("arguments", nargs="*", help="Task protocol arguments after --")
    for action in ("status", "export"):
        read = actions.add_parser(action)
        read.add_argument("--session", type=Path, required=True)
        if action == "export":
            read.add_argument("--output", type=Path, required=True)


def _optimization_actions(stages, *, project=False):
    start = stages.add_parser("start", help="Freeze explicit task conditions and search budget")
    start.set_defaults(session_action="start", project_task=project)
    if project:
        start.add_argument("--evaluation-mode", choices=("abba", "service_reuse"), default="abba",
                           help="AB/BA (default), or one owned service per retained attempt")
        start.add_argument("--evaluation-config", type=Path,
                           help="Explicit service-reuse JSON protocol (required in that mode)")
        start.add_argument("--repo", type=Path, required=True)
        start.add_argument("--include", action="append", required=True,
                           help="Project-relative input file/directory; repeat for dependencies")
        start.add_argument("--protocol", type=Path, required=True)
        start.add_argument("--instructions", type=Path, required=True)
        for name in ("measure-command", "quality-command", "metric-key", "metric-unit",
                     "quality-key", "scope"):
            start.add_argument("--" + name)
        start.add_argument("--direction", choices=("minimize", "maximize"))
        start.add_argument("--min-improvement-pct", type=float)
        start.add_argument("--repetitions", type=int)
        start.add_argument("--warmups", type=int)
        start.add_argument("--decision", choices=("point", "paired"), default="point",
                           help="point: independent medians (default); paired: the paired "
                                "interval must clear the gate (>= 6 repetitions) and "
                                "candidates are ranked by median paired speedup; "
                                "within-noise rounds are INCONCLUSIVE")
        start.add_argument("--require-explanation", action="store_true",
                           help="Adopt a candidate only when its declared mechanism is "
                                "confirmed by measured breakdown/counters")
        start.add_argument("--round-mode", choices=("exact", "up_to"), default="up_to")
        start.add_argument(
            "--allow-final-continuation", action="store_true",
            help="Allow one explicit continuation after a failed up-to-budget project final",
        )
    else:
        start.add_argument("task")
        start.add_argument("--evaluation-args", required=True)
        start.set_defaults(round_mode="exact")
    start.add_argument("--session", "--directory", dest="session", type=Path, required=True)
    start.add_argument("--rounds", type=int, required=True)
    start.add_argument("--max-minutes", type=float, required=True)
    start.add_argument("--evaluation-timeout-seconds", type=float, required=True)
    start.add_argument("--final-reserve-seconds", type=float)
    start.add_argument("--condition", default="current-agent" if project else None,
                       required=not project)
    start.add_argument("--knowledge", choices=("on", "off"), default="on")
    from ...knowledge.ranking_policy import MANAGED_RANKING_POLICIES

    start.add_argument("--ranking-policy", choices=tuple(MANAGED_RANKING_POLICIES),
                       default="default", help="Freeze the Knowledge ranking rule for this session")
    from ..integrations.cannbot.project import PLATFORMS

    start.add_argument("--cannbot-platform", choices=PLATFORMS,
                       help="Opt into CANNBot retrieval on the declared Ascend platform")
    start.add_argument("--evaluation-prefix", default="", help="Quoted allocator argv prefix")
    start.add_argument("--python", default=sys.executable)
    actions = ("status", "diagnose", "round", "final", "recover", "knowledge", "knowledge-read")
    if project:
        actions += ("baseline", "refresh-references", "resume", "profile")
    for name in actions:
        stage = stages.add_parser(name)
        stage.set_defaults(session_action=name)
        stage.add_argument("--session", "--directory", dest="session", type=Path, required=True)
        if name == "profile":
            stage.add_argument("--round", type=int, required=True,
                               help="Capture profiling for the last settled attempt of this round")
        if name == "diagnose":
            stage.add_argument("--bottleneck", required=True)
            stage.add_argument("--evidence", type=Path, required=True,
                               help="UTF-8 profile or measurement summary from this workload")
        if name == "round":
            stage.add_argument("--candidate", type=Path, required=True)
            stage.add_argument("--hypothesis", required=True)
            stage.add_argument("--strategy", help="Agent-declared optimization strategy")
            stage.add_argument("--alternative", action="append",
                               help="Another option considered for this round (repeatable, "
                                    "benchmark or AB/BA campaign)")
            stage.add_argument("--selection-reason",
                               help="Why this candidate was chosen to try (benchmark or AB/BA)")
            stage.add_argument("--knowledge-ref", action="append",
                               help="Delivered path, path#item-ref, or CANNBot receipt; repeatable")
            stage.add_argument("--mechanism-file", type=Path,
                               help="JSON mechanism with expected region/counter directions")
            if project:
                stage.add_argument("--continue-after-final", metavar="ATTEMPT_ID",
                                   help="Reopen a project campaign after this failed final")
                stage.add_argument("--continuation-reason",
                                   help="Why search should continue after the failed final")
        if name == "final":
            stage.add_argument("--reason", help="Why the caller stopped an up-to-budget search")
        if name == "recover":
            stage.add_argument(
                "--confirm-domain-empty", action="store_true",
                help="Attest that the interrupted optimization attempt has no live processes",
            )
        if name in ("round", "final"):
            stage.add_argument("--usage-export", type=Path)
        if project and name in ("round", "baseline", "refresh-references"):
            stage.add_argument("--retry-of", help="Explicitly rerun this failed attempt in full")
            stage.add_argument(
                "--repair-protocol",
                type=Path,
                help="Retain repaired execution scripts for an explicit full retry",
            )
            stage.add_argument(
                "--repair-reason", help="Investigation and repair before a new attempt"
            )
        if name == "refresh-references":
            stage.add_argument("--conditions", type=Path, required=True)
            stage.add_argument("--reason", required=True)
        if name == "resume":
            stage.add_argument("--reason", required=True)
        if project and name in ("recover", "resume", "round", "baseline", "refresh-references"):
            stage.add_argument(
                "--cleanup-receipt",
                type=Path,
                help="Investigation receipt proving interrupted resources were cleaned",
            )
        if name == "knowledge-read":
            stage.add_argument("--search-ref", required=True, help="Recorded CANNBot search path")
            stage.add_argument("--locator", required=True)
            stage.add_argument("--page", type=int, default=1)
        if name == "knowledge":
            stage.add_argument("--query", required=True)
            if not project:
                stage.add_argument("--scenario", help="Filter package records by workload scenario")
            stage.add_argument(
                "--relevance-method", metavar="find-lexical-v1",
                help="Find is the default and only ranking method",
            )
            stage.add_argument("--context-bytes", type=int, required=True)
            stage.add_argument("--limit", type=int, default=5)


def _task_overrides(parser: argparse.ArgumentParser) -> None:
    """Add the plan/run flags mapped to task fields, recording only explicit values."""
    types = {"count": int, "minutes": float, "percent": float}
    for field in TASK_FIELDS:
        if field.flag is None:
            continue
        options = {"dest": field.dest, "default": argparse.SUPPRESS,
                   "help": (field.help + "; " if field.help else "") + f"overrides {field.path}"}
        if field.acceptance:
            options["help"] = f"must equal {field.path} in the task file"
        if field.choices:
            options["choices"] = field.choices
        if field.kind in types:
            options["type"] = types[field.kind]
        if field.kind == "keys":
            options.update(action="append", metavar="DOTTED_KEY")
        parser.add_argument(field.flag, **options)


def parser(*, parser_class=argparse.ArgumentParser) -> argparse.ArgumentParser:
    root = parser_class(
        description="CLI-first reproducible experiments and tuning knowledge"
    )
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    from .evaluate import add_parser as add_evaluate_parser

    add_evaluate_parser(commands)
    _search_arguments(commands)
    mindie = commands.add_parser("mindie", help="Use project-approved, local MindIE knowledge")
    mindie_actions = mindie.add_subparsers(dest="mindie_action", required=True)
    enable = mindie_actions.add_parser("enable", help="Approve a MindIE domain for this checkout")
    enable.add_argument("--domain", default="operators")
    enable.add_argument(
        "--default-find", action="store_true",
        help="Include this MindIE grant in ordinary Find; requires --backend ascend",
    )
    enable.add_argument(
        "--backend", choices=("ascend",),
        help="Declare the checkout's default task backend for --default-find",
    )
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
    cannbot = commands.add_parser(
        "cannbot", help="Use a project-approved, external cannbot-knowledge checkout"
    )
    cannbot_actions = cannbot.add_subparsers(dest="cannbot_action", required=True)
    cannbot_enable = cannbot_actions.add_parser(
        "enable", help="Approve one cannbot-knowledge checkout for this project"
    )
    cannbot_enable.add_argument("--checkout", type=Path, required=True)
    cannbot_enable.add_argument(
        "--python", type=Path, required=True,
        help="Interpreter with pyyaml that can run the checkout's knowledge-query scripts",
    )
    cannbot_enable.add_argument("--backend", default="ascend")
    cannbot_enable.add_argument(
        "--platform", action="append", default=[],
        help="Default upstream platform; repeatable. Required for a platform-less search.",
    )
    cannbot_actions.add_parser("disable", help="Revoke the project grant")
    cannbot_actions.add_parser("describe", help="Probe the approved checkout and its index")
    cannbot_search = cannbot_actions.add_parser(
        "search", help="Search the approved checkout; returns card locators, not text"
    )
    cannbot_search.add_argument("query")
    cannbot_search.add_argument("--platform")
    cannbot_search.add_argument("--limit", type=int, default=100)
    cannbot_read = cannbot_actions.add_parser("read", help="Read one card by locator")
    cannbot_read.add_argument("locator")
    cannbot_read.add_argument(
        "--sha256",
        help="Expected card digest from a search result; refuse the read if the "
        "card changed since then",
    )
    cannbot_read.add_argument("--page", type=int, default=1)
    cannbot_read.add_argument(
        "--revision", help="Expected full checkout revision from a search result",
    )
    agents = commands.add_parser("agents", help="Record native host fresh-session handoffs")
    agent_actions = agents.add_subparsers(dest="agent_action", required=True)
    prepare = agent_actions.add_parser("prepare", help="Freeze a task for the current host")
    prepare.add_argument("--job", type=Path, required=True)
    prepare.add_argument("--prompt-file", type=Path, required=True)
    prepare.add_argument("--workspace", type=Path, required=True)
    prepare.add_argument("--title", required=True)
    prepare.add_argument("--max-minutes", type=float, required=True)
    prepare.add_argument("--model", help="Requested model, only if explicitly selected")
    prepare.add_argument("--effort", help="Requested effort, only if explicitly selected")
    prepare.add_argument("--plugin-ref", help="Requested plugin identity; not a loading receipt")
    for name in ("dispatch", "bind", "record", "status"):
        action = agent_actions.add_parser(name)
        action.add_argument("--job", type=Path, required=True)
        if name == "bind":
            action.add_argument("--host", required=True)
            action.add_argument("--session-id", required=True)
            action.add_argument("--host-id")
            action.add_argument("--receipt", type=Path, required=True)
        if name == "record":
            action.add_argument("--observation", type=Path, required=True)
            action.add_argument("--artifact", type=Path, action="append", default=[])
    benchmarks = commands.add_parser("benchmarks", help="Discover packaged engineering tasks")
    actions = benchmarks.add_subparsers(dest="benchmark_action", required=True)
    listing = actions.add_parser("list")
    listing.add_argument(
        "--iterative", action="store_true",
        help="List only tasks with a packaged optimization.py file for iterative sessions",
    )
    compare = actions.add_parser(
        "compare", help="Compare complete RSI optimization sessions (default: knowledge on/off)",
        description=("Apps coordinates paired fresh-Agent optimizations and reports. Knowledge "
                     "defaults to qwen21-denoise-npu and moe-forward-npu, each on/off. "
                     "CLI values override .inferrsi/benchmarks.json, then built-ins. "
                     "Python records handoffs; the initiating Agent calls native host tools "
                     "using returned next_action/handoff data. Complete all declared rounds "
                     "and independent finals, record actual host observations, collect every "
                     "attempt, then report. An explicit retry after collecting an "
                     "unsuccessful attempt opens a fresh one and retains the earlier attempt; "
                     "retries are never automatic. No dedicated skill is required."),
    )
    compare.add_argument("--focus", choices=("knowledge",), default="knowledge")
    compare.add_argument("--action", choices=("prepare", "status", "dispatch", "bind", "record",
                                              "collect", "retry", "report"), default="prepare",
                         help="Prepare a new experiment; use its --output for later operations")
    compare.add_argument("--config", type=Path, help="Non-secret project configuration JSON")
    compare.add_argument("--output", type=Path,
                         help="New comparison directory, or existing to resume")
    compare.add_argument("--task", action="append", help="Override default task set; repeatable")
    for name in ("rounds", "repeats"):
        compare.add_argument("--" + name, type=int)
    for name in ("max-minutes", "evaluation-timeout-seconds", "final-reserve-seconds",
                 "job-max-minutes"):
        compare.add_argument("--" + name, type=float)
    for name in ("model", "effort", "environment-id", "python"):
        compare.add_argument("--" + name)
    compare.add_argument("--evaluation-prefix", help="Allocator argv; task supplies {devices}")
    compare.add_argument("--execution-instructions", help="Prepared target/transfer instructions")
    compare.add_argument("--evaluation-args", action="append", help="Override TASK=ARGUMENTS")
    compare.add_argument("--trial", help="Declared trial ID from status/next_action")
    compare.add_argument("--parallel", action="store_true",
                         help="Allow dispatch while other declared trials are active")
    compare.add_argument("--host")
    compare.add_argument("--host-id")
    compare.add_argument("--session-id")
    compare.add_argument("--receipt", type=Path, help="Original host creation receipt for bind")
    compare.add_argument("--observation", type=Path, help="Native host observation JSON")
    show = actions.add_parser("show")
    show.add_argument("task", help="Packaged engineering task name")
    run = actions.add_parser("run", help="Run the selected task's benchmark.py")
    run.add_argument("task", help="Packaged engineering task name")
    run.add_argument("arguments", nargs=argparse.REMAINDER, help="Task-specific arguments")
    external = actions.add_parser(
        "external", help="Run a public suite's task and score it with that suite's grader",
        description=("Phi-Bench first. Lands a reference control (noop/negative/oracle), a "
                     "candidate patch or one agent command in the task's environment, "
                     "captures the patch and runs the suite grader. The docker executor "
                     "delegates to the suite's scripts/run_task.py; the rootless executor "
                     "replays the image layout under proot for hosts without Docker."),
    )
    external_actions = external.add_subparsers(dest="external_action", required=True)
    for name in ("list", "run", "selfcheck"):
        action = external_actions.add_parser(name)
        action.add_argument("--suite", choices=("phibench",), default="phibench")
        action.add_argument("--root", type=Path, required=True, help="Local clone of the suite")
        if name == "list":
            continue
        action.add_argument("--task", required=True, help="Suite task ID, e.g. kfc/<name>")
        action.add_argument("--output", type=Path, required=True,
                            help="New directory; each mode writes <output>/<mode>/result.json")
        action.add_argument("--executor", choices=("rootless", "docker"), default="docker")
        action.add_argument("--proot", help="proot binary for the rootless executor")
        action.add_argument("--python", help="Interpreter for the runner or the task venv")
        action.add_argument("--python-env", type=Path,
                            help="Prepared environment with the task's Python dependencies")
        action.add_argument("--runner-arg", action="append",
                            help="Extra argument for the suite runner (docker); repeatable")
        if name == "run":
            action.add_argument("--mode", required=True,
                                choices=("noop", "negative", "oracle", "candidate", "agent"))
            action.add_argument("--candidate-patch", type=Path,
                                help="Working-tree patch to score (mode candidate)")
            action.add_argument("--agent-command",
                                help="Shell command run in the task tree (mode agent)")
            action.add_argument("--agent-env", action="append", metavar="NAME",
                                help="Environment variable forwarded by name into the agent "
                                     "step, e.g. a model-provider key; repeatable")
            action.add_argument("--inferrsi-plugin", type=Path, metavar="DIR",
                                help="Mode agent, rootless: put this built InferRSI Codex "
                                     "plugin at /opt/inferrsi-plugin and tell the agent to "
                                     "use InferRSI (directory + prompt)")
        else:
            action.add_argument("--oracle-tolerance", type=float,
                                help="Allowed relative deviation of the oracle speedup from "
                                     "the task anchor; without it a performance oracle is "
                                     "INCONCLUSIVE")
    session = actions.add_parser(
        "session", help="Drive iterative optimization in the current Agent"
    )
    stages = session.add_subparsers(dest="session_action", required=True)
    _optimization_actions(stages)
    doctor = commands.add_parser(
        "doctor", help="Inspect a prepared local target without installing dependencies",
        description="Check the environment. Add --repo-type to include its target descriptor."
    )
    _common(doctor)
    doctor.set_defaults(repo_type=None)

    for name in ("plan", "run"):
        child = commands.add_parser(
            name,
            help="Freeze an external-command experiment"
            if name == "plan"
            else "Measure baseline and candidate commands",
        )
        for action in (None, "store"):
            child.register("action", action, _SuppliedStore)
        child.register("action", "append", _SuppliedAppend)
        _common(child)
        child.add_argument(
            "--task", dest="task_file", default=argparse.SUPPRESS, metavar="TASK_YAML",
            help="Complete schema v1 task file; supplied mapped flags override it, "
            "acceptance flags must match it (docs/guides/task-input.md)",
        )
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
            help="Quoted argv command; {result} is replaced with a fresh output path; "
            "required without --task",
        )
        child.add_argument("--candidate-command", help="Required without --task")
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

    task = commands.add_parser(
        "task", help="Read a YAML task file without starting or writing anything"
    )
    task_actions = task.add_subparsers(dest="task_action", required=True)
    for name, text in (
        ("validate", "Report format and value errors by field"),
        ("preview", "Show effective normalized values, their sources and plan/run blockers"),
    ):
        child = task_actions.add_parser(name, help=text)
        child.add_argument("task_file", type=Path, help="Task file (schema v1 YAML)")
        child.add_argument("--json", action="store_true", help="Print machine-readable JSON")
        if name == "preview":
            _task_overrides(child)
    task_actions.add_parser("schema", help="Print the packaged task JSON Schema")
    task_actions.add_parser("template", help="Print the packaged task template")

    for name in ("status", "report"):
        child = commands.add_parser(
            name,
            help="Read a recorded experiment" if name == "status" else "Regenerate its HTML report",
        )
        _fixed_attempt_args(child, legacy_flag="--run-id")
        if name == "report":
            child.add_argument("--output", type=Path, help="HTML output for a fixed RecordRef")
        child.add_argument("--output-dir", default="runs")

    trace = commands.add_parser("trace", help="Read recorded steps, checks and errors")
    _fixed_attempt_args(trace)

    delivery = commands.add_parser("export", help="Export retained results without remeasurement")
    delivery.add_argument("--input", type=Path, required=True, help="Campaign, run or record JSON")
    delivery.add_argument("--output", type=Path, required=True, help="New delivery directory")
    delivery.add_argument("--export-id", help="Optional identity for publication reconciliation")
    delivery.add_argument("--agent-job", type=Path,
                          help="Retained native Agent job supplying Benchmark terminal usage")

    dashboard = commands.add_parser(
        "dashboard", help="Export an offline dashboard for one run or recorded campaign"
    )
    _fixed_attempt_args(dashboard, legacy_flag="--input")
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
    _optimization_actions(campaign_actions, project=True)
    create = campaign_actions.add_parser("init", help="Create a new campaign manifest")
    create.add_argument("--directory", type=Path, required=True)
    create.add_argument("--id", required=True)
    create.add_argument("--target-pct", type=float)
    create.add_argument("--profile-first", action="store_true",
                        help="Lead the review with acceptance criteria and profile evidence")
    create.add_argument("--backend", choices=BACKENDS,
                        help="Target backend for campaign knowledge discovery")
    create.add_argument("--noise-pct", type=float)
    create.add_argument("--synthetic", action="store_true")
    profiler = campaign_actions.add_parser("attach-profile", help="Attach a reviewed Chrome trace")
    profiler.add_argument("--directory", type=Path, required=True)
    profiler.add_argument("--id", required=True)
    profiler.add_argument("--source", required=True, help="Campaign-relative profiles/*.json[.gz]")
    profiler.add_argument("--review", type=Path, required=True, help="Timing scope and conclusions")
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
        help="Save the exact knowledge context selected for a question or explicit IDs",
    )
    capture.add_argument("--directory", type=Path, required=True)
    capture.add_argument("--id", required=True, help="New context id, e.g. r1-diagnosis")
    capture.add_argument("query", nargs="?", default="")
    capture.add_argument("--relevance", help="Alternate spelling for one Find query")
    capture.add_argument("--relevance-method", metavar="find-lexical-v1",
                         help="Find is the default and only ranking method")
    capture.add_argument("--id-ref", action="append", dest="ids", metavar="ID",
                         help="Exact knowledge identity to include (repeatable)")
    capture.add_argument("--revision", action="append", metavar="ID=REV",
                         help="Require this revision of an explicit --id-ref (repeatable)")
    capture.add_argument("--kind", choices=("skill", "knowledge", "case"))
    capture.add_argument("--repo-type", dest="knowledge_repo", choices=KNOWLEDGE_REPOS)
    capture.add_argument("--tier", choices=KNOWLEDGE_SCOPES)
    capture.add_argument("--backend", choices=BACKENDS)
    capture.add_argument("--scenario")
    capture.add_argument("--limit", type=int, default=5)
    capture.add_argument("--context-bytes", type=int, default=65536)
    _read_sources(capture)
    search = campaign_actions.add_parser(
        "import-search", help="Import the observed knowledge searches for one campaign round"
    )
    search.add_argument("--directory", type=Path, required=True)
    search.add_argument("--round", type=int, required=True)
    search.add_argument("--trace", type=Path, help="Caller-selected Codex Desktop rollout JSONL")
    search.add_argument("--lines", nargs=2, type=int, metavar=("FIRST", "LAST"),
                        help="Inclusive, one-based round boundaries in that rollout")
    search.add_argument("--knowledge-root", type=Path, help="Absolute corpus path in the rollout")
    search.add_argument("--context-id", action="append", default=[], help="Capture in this round")
    search.add_argument("--archive-review", type=Path, metavar="FILE",
                        help="Build a round archive from reviewed passage and decision references")
    search.add_argument("--stage", help="Retrieval stage if known, e.g. diagnosis")
    search.add_argument("--used", action="append", nargs=2, metavar=("REF", "DECISION_LINE"),
                        default=[], help="Reviewed material use in a cited assistant message")
    search.add_argument("--rejected", action="append", nargs=2, metavar=("REF", "DECISION_LINE"),
                        default=[], help="Reviewed rejection in a cited assistant message")
    search.add_argument("--complete", action="store_true",
                        help="Caller confirms coverage of all in-scope retrievals in this round")
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
    listing = actions.add_parser("list", help="List skill metadata without the instruction body")
    listing.add_argument("--json", action="store_true")
    enter = actions.add_parser(
        "enter", help="Load the selected primary inference task before evidence search"
    )
    enter.add_argument("name", help="Registered primary task skill (for example, task-accuracy)")
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
        help="List filtered package records, or search that catalog with Find ranking",
    )
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--repo-type", choices=KNOWLEDGE_REPOS)
    search.add_argument("--tier", choices=KNOWLEDGE_SCOPES)
    search.add_argument("--backend", choices=BACKENDS)
    search.add_argument("--scenario")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--explain", action="store_true",
                        help="Return JSON with recorded matching and ranking observations")
    search.add_argument("--json", action="store_true")
    show = actions.add_parser("show")
    show.add_argument("id")
    research = actions.add_parser(
        "research", help="Combine model research dimensions with package-scoped Find queries"
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

    find = commands.add_parser(
        "find",
        help="Rank packaged skills, imported records and checkout cases for one "
        "question; returns corpus paths with optional pinned decision card reads",
    )
    find.add_argument("query", help="Describe the problem in your own words")
    find.add_argument("--decision-cards", action="store_true",
                      help="Add pinned L1 read commands and their UTF-8 card sizes")
    find.add_argument("--limit", type=int, default=5)
    find.add_argument(
        "--kinds", default="case,skill,record",
        help="Comma-separated subset of case,skill,record; default is all three",
    )
    find.add_argument(
        "--skill-root", type=Path,
        help="Root for case and skill searches, defaulting to the installed library",
    )
    find.add_argument(
        "--searchspace-coordinate", nargs=2, metavar=("RESOURCE", "STAGE"),
        help="Filter ranked local Skills by a matrix pair using an explicit checkout --skill-root",
    )
    find.add_argument(
        "--show-searchspace-coordinates", action="store_true",
        help="Show matrix pairs and coverage on local Skill hits from an explicit checkout",
    )
    find.add_argument(
        "--explain", action="store_true", help="Report each query term's contribution"
    )
    find.add_argument(
        "--backend",
        help="Declare the task backend once, e.g. ascend; external channels run only "
        "for a declared backend and are never inferred from the query",
    )
    find.add_argument("--platform", help="Override the CANNBot grant’s platform, e.g. a2")
    find.add_argument(
        "--external-source", choices=("mindie-agent",),
        help="Select only MindIE for this Find; requires --backend ascend. Ordinary Find "
        "includes project grants enabled with mindie enable --default-find",
    )
    find.add_argument(
        "--no-external", action="store_true",
        help="Skip every external channel; use in CI and offline runs",
    )
    find.add_argument(
        "--external-limit", type=int,
        help="Override the per-channel result cap (cannbot 100, MindIE 5 by default)",
    )
    find.add_argument(
        "--external-timeout", type=float, default=8.0,
        help="Shared discovery and query deadline in seconds for the external sources",
    )
    find.add_argument("--json", action="store_true")

    collect = commands.add_parser(
        "collect",
        help="Collect exact IDs, list material, or use Find to assemble context for a question",
    )
    collect.add_argument("query", nargs="?", default="")
    collect.add_argument("--kind", choices=("skill", "knowledge", "case"))
    collect.add_argument("--repo-type", choices=KNOWLEDGE_REPOS)
    collect.add_argument("--tier", choices=KNOWLEDGE_SCOPES)
    collect.add_argument("--backend", choices=BACKENDS, help="Include this backend and common")
    collect.add_argument("--scenario", help="Workload scenario (also admits packaged skills)")
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
        "--relevance", help="Alternate spelling for a Find query, or a resource cue with --id",
    )
    collect.add_argument("--relevance-method", metavar="find-lexical-v1",
                         help="Find is the default and only ranking method")
    collect.add_argument(
        "--context-bytes", type=int,
        help="UTF-8 budget for context bodies and any explicitly requested L1 cards",
    )
    collect.add_argument(
        "--decision-card", action="append", metavar="REF[=FINDING]",
        help="Add L1 for a qualified --id at its --revision; supply one original Case finding",
    )
    _read_sources(collect)
    collect.add_argument("--json", action="store_true")

    read = commands.add_parser(
        "read",
        help="Read one bundle from the package, a skill library, or a store",
    )
    read.add_argument("id")
    read.add_argument("--layer", choices=("L1",), help="Read a decision card at --revision")
    read.add_argument("--compact", action="store_true", help="Read the compact L1 decision card")
    read.add_argument("--finding", help="L1 Case selector returned by find --decision-cards")
    read.add_argument("--max-bytes", type=int, help="Maximum canonical UTF-8 L1 card bytes")
    read.add_argument("--revision", help="Exact revision returned by collect or read")
    read.add_argument("--material", action="store_true")
    read.add_argument(
        "--omit-resources", action="store_true",
        help="Omit the resource inventory from output; the revision still covers the full bundle",
    )
    read.add_argument("--resource", help="Include the UTF-8 text at this bundle resource key")
    _read_sources(read)

    resource = commands.add_parser(
        "resource",
        help="Write one raw bundle resource of an exact revision to --output",
    )
    resource.add_argument("id")
    resource.add_argument("path")
    resource.add_argument(
        "--revision", required=True, help="Exact revision returned by collect or read"
    )
    _read_sources(resource)
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
    def command(value: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is None:
            return None
        # A task file supplies an already-normalized argv list; a flag gives quoted text.
        if isinstance(value, (list, tuple)):
            parsed = tuple(value)
        else:
            parsed = tuple(shlex.split(value, posix=True))
        if not parsed:
            raise ValueError("Commands cannot be empty")
        return parsed

    spec = RunSpec(
        repo=str(Path(args.repo).resolve()),
        revision=getattr(args, "revision", ""),
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
