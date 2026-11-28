"""Compose paired optimization experiments with native host handoffs.

The Agent calls the host tools returned by this application. Python never
creates a conversation, invents host observations, or edits a candidate.
"""

import hashlib
import json
import math
import os
import shlex
import shutil
import stat
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from inferrsi.benchmark.comparison import (
    DEFAULT_POLICY,
    DEFAULT_TASKS,
    STATUSES,
    attempt_accounting,
    summarize,
    validate_policy,
)
from inferrsi.benchmark.registry import has_iterative_protocol, task_resources
from inferrsi.benchmark.summary import POLICY, supported_policy
from inferrsi.benchmark.summary import comparison as metrics_comparison
from inferrsi.harness import manager
from inferrsi.harness.executor import run_task_protocol
from inferrsi.harness.manager import session_runtime_identity
from inferrsi.harness.records.artifact_primitives import digest, file_lock, sha256
from inferrsi.harness.records.atomic_json import atomic_write_json
from inferrsi.harness.records.knowledge_capture import verify_capture
from inferrsi.knowledge.catalog import SCENARIO_ALIASES
from inferrsi.knowledge.context_projection import assemble_context_text
from inferrsi.knowledge.knowledge_operations import KnowledgeReader

from ..delivery import project
from ..delivery.benchmark_usage import terminal_token_usage, update_metrics
from ..delivery.schema import decode
from ..delivery.schema import number as _finite
from ..storage.archive import _publish_directory
from ..views.comparison_report import write_comparison_report

DEFAULT_CONFIG = {
    "schema_version": 1, "tasks": list(DEFAULT_TASKS), "repeats": 1, "rounds": 8,
    "max_minutes": 60, "evaluation_timeout_seconds": 1200, "final_reserve_seconds": 1200,
    "job_max_minutes": 90, "model": None, "effort": None,
    "environment_id": None, "evaluation_prefix": "", "execution_instructions": "",
    "python": "python", "policy": DEFAULT_POLICY,
    "task_arguments": {
        "qwen21-denoise-npu": "--pairs 2 --samples 3 --warmups 1",
        "moe-forward-npu": "--pairs 2 --timeout-seconds 900",
    },
}
CONFIG_NAME = Path(".inferrsi/benchmarks.json")
OBSERVED_FIELDS = ("model", "effort", "environment_id", "environment_fingerprint")
SHARED_SESSION = "native_session_bound_to_multiple_attempts"
KNOWLEDGE_CONTEXT_BYTES = 64 * 1024


def _io_path(path):
    """Use Windows extended paths at I/O boundaries without persisting that spelling."""
    path = Path(path).absolute()
    value = str(path)
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    return Path(value)


def _object(path):
    path = _io_path(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Comparison JSON document exceeds 2 MiB")
    value = decode(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Comparison JSON must contain an object")
    return value


def resolve_config(args):
    """CLI > project JSON > built-ins; retain field-level provenance."""
    config = deepcopy(DEFAULT_CONFIG)
    sources = {key: "default" for key in config}
    path = args.config or (CONFIG_NAME if CONFIG_NAME.is_file() else None)
    if path is not None:
        supplied = _object(path)
        if supplied.keys() - config.keys():
            raise ValueError("Unknown comparison configuration fields")
        for key, value in supplied.items():
            if key in ("policy", "task_arguments"):
                if not isinstance(value, dict):
                    raise ValueError(f"{key} must be an object")
                if key == "policy" and isinstance(value.get("tolerances"), dict):
                    value = {**value, "tolerances": {
                        **config[key]["tolerances"], **value["tolerances"]}}
                config[key].update(value)
            else:
                config[key] = value
            sources[key] = "config"
    for key in config:
        value = getattr(args, "task" if key == "tasks" else key, None)
        if value is not None:
            config[key] = value
            sources[key] = "cli"
    for override in args.evaluation_args or []:
        task, sep, arguments = override.partition("=")
        if not sep or task not in config["tasks"]:
            raise ValueError("--evaluation-args requires selected TASK=ARGUMENTS")
        config["task_arguments"][task] = arguments
        sources["task_arguments"] = "cli"
    _validate_config(config)
    return config, sources


def _validate_config(config):
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ValueError("Unsupported comparison configuration version")
    for key in ("rounds", "repeats"):
        if type(config[key]) is not int or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    for key in ("max_minutes", "evaluation_timeout_seconds", "final_reserve_seconds",
                "job_max_minutes"):
        if (type(config[key]) not in (int, float) or not math.isfinite(config[key])
                or config[key] <= 0):
            raise ValueError(f"{key} must be finite and positive")
    if not config["evaluation_timeout_seconds"] <= config["final_reserve_seconds"] < (
        config["max_minutes"] * 60
    ):
        raise ValueError("Reserve at least one evaluation timeout within the campaign budget")
    if config["job_max_minutes"] <= config["max_minutes"]:
        raise ValueError("Agent job budget must exceed campaign budget for handoff and collection")
    tasks = config["tasks"]
    if (not isinstance(tasks, list) or not tasks or any(not isinstance(t, str) for t in tasks)
            or len(set(tasks)) != len(tasks)):
        raise ValueError("tasks must be a nonempty list of unique registered task names")
    for task in tasks:
        if not has_iterative_protocol(task):
            raise ValueError(f"Task has no iterative protocol: {task}")
        if not isinstance(config["task_arguments"].get(task), str):
            raise ValueError(f"Missing task arguments: {task}")
    for key in ("model", "effort", "environment_id"):
        if config[key] is not None and (not isinstance(config[key], str)
                                       or not config[key].strip()):
            raise ValueError(f"{key} must be nonempty or null")
    for key in ("evaluation_prefix", "execution_instructions", "python"):
        if not isinstance(config[key], str) or len(config[key]) > 16384:
            raise ValueError(f"{key} must be a bounded string")
    if not config["python"].strip():
        raise ValueError("python must name the prepared target interpreter")
    # Only the task-owned device count can be interpolated, never a shell command.
    shlex.split(config["evaluation_prefix"].replace("{devices}", "1"))
    if "{" in config["evaluation_prefix"].replace("{devices}", ""):
        raise ValueError("Only {devices} is supported in evaluation_prefix")
    config["policy"] = validate_policy(config["policy"])


def _manifest(root):
    root = _io_path(root)
    paths = sorted(root.rglob("*"))
    if root.is_symlink() or any(path.is_symlink() for path in paths):
        raise ValueError("Comparison resources cannot contain symbolic links")
    return {path.relative_to(root).as_posix(): sha256(path)
            for path in paths if path.is_file()
            and "__pycache__" not in path.parts and path.suffix != ".pyc"}


def _copy_runtime(source, destination, condition):
    source, destination = _io_path(source), _io_path(destination)
    def ignored(directory, names):
        result = [name for name in names if name == "__pycache__" or name.endswith(".pyc")]
        if Path(directory) == source / "knowledge" and condition == "off":
            result.append("data")
        return result
    shutil.copytree(source, destination, ignore=ignored)


def _prefix(config, manifest):
    devices = manifest.get("devices", manifest.get("world_size", 2))
    if type(devices) is not int or devices < 1:
        raise ValueError("Task must declare its positive device count")
    return config["evaluation_prefix"].replace("{devices}", str(devices))


def _freeze_knowledge_delivery(manifest, task):
    if "knowledge_delivery" not in manifest:
        return None
    requirement = manifest["knowledge_delivery"]
    fields = {"query", "scenario", "ref"}
    if (not isinstance(requirement, dict)
            or requirement.keys() not in (fields, fields | {"context_bytes"})
            or any(not isinstance(requirement[key], str) or not requirement[key].strip()
                   for key in fields)
            or not requirement["ref"].startswith("package:")):
        raise ValueError(f"{task}: knowledge_delivery requires a query, scenario and package ref")
    limit = requirement.get("context_bytes", KNOWLEDGE_CONTEXT_BYTES)
    if type(limit) is not int or limit < 0:
        raise ValueError(f"{task}: knowledge_delivery.context_bytes must be a nonnegative integer")
    card = KnowledgeReader().read(requirement["ref"]).view()
    scenario = SCENARIO_ALIASES.get(requirement["scenario"], requirement["scenario"])
    card_scenario = card.get("scenario")
    if (card["kind"] != "knowledge" or card["entrypoint"] != "record.json"
            or SCENARIO_ALIASES.get(card_scenario, card_scenario) != scenario):
        raise ValueError(f"{task}: expected a package knowledge card for the declared scenario")
    return {**requirement, "scenario": scenario, "revision": card["revision"],
            "body_sha256": card["resources"]["record.json"],
            "context_bytes": limit, "budget_source": "experiment_plan"}


def _knowledge_requirement(plan, trial):
    if trial["condition"] == "on":
        return plan["task_settings"][trial["task"]].get("knowledge_delivery")
    return None


def prepare(args):
    config, sources = resolve_config(args)
    if not config["environment_id"]:
        return {"state": "configuration_required", "resolved_config": config,
                "parameter_sources": sources,
                "next_action": {
                    "operation": "select_prepared_execution_environment",
                    "instructions": "Select an existing authorized environment satisfying the "
                    "task manifests. Supply --environment-id, --evaluation-prefix and optional "
                    "--execution-instructions or project .inferrsi/benchmarks.json. Inspect task "
                    "requirements with benchmarks show. Credentials stay outside configuration.",
                }}
    root = (args.output or Path("outputs") / (
        "knowledge-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-" + uuid.uuid4().hex[:8]
    )).resolve()
    if root.exists():
        raise ValueError("Comparison output must be new; use --action status to resume")
    runtime = Path(str(files("inferrsi"))).resolve()
    if root.is_relative_to(runtime) or any(p.is_symlink() for p in runtime.rglob("*")):
        raise ValueError("Runtime must contain regular files and output must be outside it")
    task_settings = {}
    for name in config["tasks"]:
        resource = Path(str(task_resources(name)))
        manifest = _object(resource / "task.json")
        settings = run_task_protocol(resource, sha256(resource / "optimization.py"),
                                      "validate_arguments",
                                      arguments=shlex.split(config["task_arguments"][name]))
        task_settings[name] = {"settings": settings, "files": _manifest(resource),
                               "evaluation_prefix": _prefix(config, manifest)}
        requirement = _freeze_knowledge_delivery(manifest, name)
        if requirement is not None:
            task_settings[name]["knowledge_delivery"] = requirement
    root.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".compare-", dir=_io_path(root.parent)) as temporary:
        staging = Path(temporary) / "experiment"
        staging.mkdir()
        _prepare_at(config, sources, runtime, task_settings, staging)
        _publish_directory(staging, _io_path(root))
    return status(root)


def _prepare_at(config, sources, runtime, task_settings, root):
    runtime_files = _manifest(runtime)
    knowledge_files = {key: value for key, value in runtime_files.items()
                       if key.startswith("knowledge/data/")}
    trials = []
    for task in config["tasks"]:
        for repeat in range(1, config["repeats"] + 1):
            for condition in (("on", "off") if repeat % 2 else ("off", "on")):
                trial_id = f"{task}-r{repeat:03d}-{condition}"
                workspace = root / "trials" / f"{len(trials) + 1:04d}"
                workspace.mkdir(parents=True)
                _copy_runtime(runtime, workspace / "runtime/inferrsi", condition)
                trials.append({"id": trial_id, "task": task, "repeat": repeat,
                               "condition": condition,
                               "workspace": workspace.relative_to(root).as_posix()})
    plan = {"schema_version": 1, "focus": "knowledge", "config": config,
            "metrics_policy": POLICY,
            "diagnosis_required": True, "knowledge_command": "find",
            "parameter_sources": sources, "task_settings": task_settings,
            "runtime_files": {key: value for key, value in runtime_files.items()
                              if key not in knowledge_files},
            "session_runtime_identity": session_runtime_identity(),
            "knowledge_files": knowledge_files,
            "trials": trials,
            "knowledge_boundary": "isolated runtime corpus and session gate; native host "
            "filesystem/network access follows identical task instructions, not an OS sandbox"}
    atomic_write_json(root / "experiment.json", plan)
    atomic_write_json(root / "state.json", {"schema_version": 1, "plan_digest": digest(plan),
                                            "collections": {}})


def _expected_runtime(plan, trial):
    expected = dict(plan["runtime_files"])
    if trial["condition"] == "on":
        expected.update(plan["knowledge_files"])
    return expected


def _attempts(state, trial):
    """Archived (collected, superseded) attempts of one trial, oldest first."""
    return state.get("attempts", {}).get(trial["id"], [])


def _attempt_number(state, trial):
    return len(_attempts(state, trial)) + 1


def _attempt_paths(trial, number):
    """Relative job and workspace; attempt 1 keeps the paths of earlier experiments."""
    suffix = "" if number == 1 else f"-attempt-{number:03d}"
    return "jobs/" + trial["id"] + suffix, trial["workspace"] + suffix


def _job(root, trial, number):
    return root / _attempt_paths(trial, number)[0]


def _workspace(root, trial, number):
    return root / _attempt_paths(trial, number)[1]


def _reference_shape(reference, keys):
    """A collection reference names one file directly under this experiment's collections/."""
    path = reference.get("path") if isinstance(reference, dict) else None
    parts = Path(path).parts if isinstance(path, str) else ()
    return (isinstance(reference, dict) and set(reference) in keys and len(parts) == 2
            and parts[0] == "collections" and parts[1] not in ("..", ".")
            and path == "collections/" + parts[1]
            and isinstance(reference["sha256"], str))


def _validate_attempts(plan, state):
    """Check every attempt and collection reference before any collection file is read."""
    trial_ids = {t["id"] for t in plan["trials"]}
    attempts = state.get("attempts", {})
    if not isinstance(attempts, dict) or attempts.keys() - trial_ids:
        raise ValueError("Malformed comparison attempts")
    if state["collections"].keys() - trial_ids:
        raise ValueError("Malformed comparison collections")
    paths = []
    for trial in plan["trials"]:
        archived = attempts.get(trial["id"], [])
        if not isinstance(archived, list) or trial["id"] in attempts and not archived:
            raise ValueError("Malformed comparison attempts")
        for number, entry in enumerate(archived, 1):
            job, workspace = _attempt_paths(trial, number)
            if (not isinstance(entry, dict)
                    or set(entry) != {"attempt", "job", "workspace", "collection"}
                    or entry["attempt"] != number or entry["job"] != job
                    or entry["workspace"] != workspace
                    or not _reference_shape(entry["collection"], ({"path", "sha256"},))):
                raise ValueError("Malformed comparison attempts")
            paths.append(entry["collection"]["path"])
        current = state["collections"].get(trial["id"])
        if current is None:
            continue
        # References written before retries existed carry no attempt number.
        if not _reference_shape(current, ({"path", "sha256"}, {"path", "sha256", "attempt"})):
            raise ValueError("Malformed comparison collections")
        attempt = current.get("attempt", 1)
        if type(attempt) is not int or attempt != len(archived) + 1:
            raise ValueError("Malformed comparison attempts")
        paths.append(current["path"])
    # Each attempt owns its own record; one file cannot stand for two attempts.
    if len(set(paths)) != len(paths):
        raise ValueError("Malformed comparison collections")


def _retained(root, reference, trial_id, attempt):
    """Return one retained collection record, refused unless it is still that attempt's own.

    The reference must name a regular file (not a link) directly under this experiment's
    collections/ directory. At most 2 MiB are read, once, checked against the recorded
    digest and decoded. The record's ``id`` must be the trial that holds the reference
    and its ``attempt`` the attempt the reference stands for, so two valid references
    exchanged between trials or between attempts of one trial are refused, not
    misattributed. Records collected before retries existed carry no ``attempt``; they
    can only be attempt 1.
    """
    if not _reference_shape(reference, ({"path", "sha256"}, {"path", "sha256", "attempt"})):
        raise ValueError("Malformed comparison collections")
    path = _io_path(root / reference["path"])
    limit = 2 * 1024 * 1024
    data = None
    try:
        directory = os.lstat(_io_path(root / "collections"))
        if stat.S_ISDIR(directory.st_mode) and stat.S_ISREG(os.lstat(path).st_mode):
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0)
                                 | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                if stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    # Bound the bytes actually read: the file may grow after it was opened.
                    data = stream.read(limit + 1)
                    if len(data) > limit:
                        raise ValueError("Comparison JSON document exceeds 2 MiB")
    except OSError:
        data = None
    if data is None or hashlib.sha256(data).hexdigest() != reference["sha256"]:
        raise ValueError("Retained comparison collection changed")
    record = decode(data)
    if not isinstance(record, dict) or record.get("id") != trial_id:
        raise ValueError("Retained comparison collection belongs to another trial")
    recorded = record.get("attempt", 1)
    if type(recorded) is not int or recorded != attempt:
        raise ValueError("Retained comparison collection belongs to another attempt")
    return record


def _load(root):
    """Strictly check the plan, attempt records, every retained collection and current runtime.

    Every operation loads first. All collection references (archived and current) are
    shape-checked before any file is read; then a changed, lost, foreign or exchanged
    collection record is refused before any workspace is published or state is written.
    Archived attempts' runtime copies are re-verified per attempt by report, so a
    lost or changed old copy is that attempt's gap, not a failure of every operation.
    """
    plan, state = _object(root / "experiment.json"), _object(root / "state.json")
    if plan.get("schema_version") != 1 or state.get("plan_digest") != digest(plan):
        raise ValueError("Frozen comparison plan changed")
    if not isinstance(state.get("collections"), dict):
        raise ValueError("Malformed comparison collections")
    _validate_attempts(plan, state)
    for trial in plan["trials"]:
        for entry in _attempts(state, trial):
            _retained(root, entry["collection"], trial["id"], entry["attempt"])
        if trial["id"] in state["collections"]:
            _retained(root, state["collections"][trial["id"]], trial["id"],
                      _attempt_number(state, trial))
    for trial in plan["trials"]:
        runtime = _workspace(root, trial, _attempt_number(state, trial)) / "runtime/inferrsi"
        if _manifest(runtime) != _expected_runtime(plan, trial):
            raise ValueError(f"Frozen comparison runtime changed: {trial['id']}")
    return plan, state


def _runtime_error(root, plan, trial, number):
    """Why an attempt's runtime copy no longer matches the frozen manifest, or None."""
    runtime = _io_path(_workspace(root, trial, number) / "runtime/inferrsi")
    try:
        if not runtime.is_dir():
            return "missing"
        return None if _manifest(runtime) == _expected_runtime(plan, trial) else "changed"
    except (OSError, ValueError) as error:
        return type(error).__name__


def _collection_digest(state):
    # Experiments without retries keep their published-report freshness digest.
    if not state.get("attempts"):
        return digest(state["collections"])
    return digest({"collections": state["collections"], "attempts": state["attempts"]})


def _archived_result(root, trial, entry):
    return _retained(root, entry["collection"], trial["id"], entry["attempt"])


def _session_key(native):
    # Optional routing metadata cannot establish that a reused ID is independent.
    return native["host"], native["session_id"]


def _select(plan, trial_id):
    found = [trial for trial in plan["trials"] if trial["id"] == trial_id]
    if len(found) != 1:
        raise ValueError("Select a declared --trial ID from comparison status")
    return found[0]


def _prompt(root, plan, trial, workspace):
    config = plan["config"]
    runtime = _io_path(workspace / "runtime")
    campaign = workspace / "campaign"
    start = [config["python"], "-B", "-m", "inferrsi", "benchmarks", "session", "start",
             trial["task"], "--session", str(campaign), "--rounds", str(config["rounds"]),
             "--max-minutes", str(config["max_minutes"]),
             "--evaluation-timeout-seconds", str(config["evaluation_timeout_seconds"]),
             "--final-reserve-seconds", str(config["final_reserve_seconds"]),
             "--condition", trial["id"], "--knowledge", trial["condition"],
             "--evaluation-prefix", plan["task_settings"][trial["task"]]["evaluation_prefix"],
             "--evaluation-args", config["task_arguments"][trial["task"]],
             "--python", config["python"]]
    diagnosis = ""
    if plan.get("diagnosis_required"):
        diagnosis = (
            "Before searching, profile the frozen baseline or inspect existing measurements "
            "for the same workload and environment. Record the bottleneck, workload scope and "
            "observed measurements with benchmarks session diagnose --session <campaign> "
            "--bottleneck <description> --evidence <UTF-8-measurement-summary>. "
        )
    retrieval = ""
    requirement = _knowledge_requirement(plan, trial)
    # Dispatch and retry also operate on experiments that froze an older runtime.
    scoped_find = plan.get("knowledge_command") == "find"
    lookup = "find with --session <campaign>" if scoped_find else "benchmarks session knowledge"
    if requirement is not None:
        entry = ([*start[:4], "find", requirement["query"], "--session", str(campaign)]
                 if scoped_find else
                 [*start[:6], "knowledge", "--session", str(campaign),
                  "--query", requirement["query"]])
        knowledge = [*entry, "--scenario", requirement["scenario"]]
        if requirement.get("budget_source") != "experiment_plan":
            knowledge.extend(("--context-bytes", str(requirement["context_bytes"])))
        retrieval = (
            "After diagnosis, run the frozen knowledge request before the first round. "
            f"Knowledge argv (a JSON array, execute without a shell): {json.dumps(knowledge)}\n"
        )
        if requirement.get("budget_source") == "experiment_plan":
            retrieval += (f"The first-round limit is {requirement['context_bytes']} UTF-8 resource "
                          "bytes from this search, including repeated reads.\n")
        if scoped_find:
            retrieval += (f"Select the hit whose material_ref equals {requirement['ref']} and "
                          "execute its read_args with the same runtime before the first round. "
                          "Retain the returned read receipt.\n")
    return (
        f"Run complete RSI optimization: {trial['task']}, condition {trial['condition']}.\n"
        f"Work only in {workspace}. Set PYTHONPATH to {runtime}; disable bytecode. "
        "Do not import another installed InferRSI or parent checkout. Use this fresh conversation; "
        "do not inspect other trials, prior solutions, the initiating conversation or reports. "
        "Do not delegate or create another conversation.\n"
        f"Prepared execution environment: {config['environment_id']}.\n"
        f"{config['execution_instructions']}\n"
        "Preflight before search; retain Python implementation/version, device model, framework "
        "and runtime versions, and allocator profile in environment-observation.json. "
        "Preserve shared dependencies. "
        "Record actual model/effort from the host observation when available; "
        "requested settings alone do not establish actual settings.\n"
        f"The permitted optimization knowledge source is this runtime's {lookup} "
        "when enabled. Other skill libraries, stores, external knowledge tools, web research "
        "and prior solutions are excluded in both. Public task/command operating instructions "
        "and target library APIs remain available to both. The off runtime omits the corpus. "
        "Report any observed policy violation; do not claim an OS sandbox.\n"
        f"Start argv (a JSON array, execute without a shell): {json.dumps(start)}\n"
        "For remote execution, copy this exact runtime to the prepared target. Use a private "
        "campaign directory there; return its entire unchanged tree to workspace/campaign above. "
        "Preserve bytes and relative paths. Exclude other trials and runtimes.\n"
        f"Read frozen TASK.md. {diagnosis}{retrieval}"
        "If the session returns candidate_find, inspect its hits before each candidate edit. "
        "Continue candidate_search with knowledge round for an unresolved question. "
        "Analyze feedback and choose a justified optimization each round. "
        "Submit candidate, --strategy and --hypothesis; cite delivered --knowledge-ref paths when "
        f"used and retain failures. When knowledge is enabled, use {lookup} for a "
        "specific implementation question after diagnosing the bottleneck. Complete frozen "
        "rounds and independently retest the selected candidate "
        "using session final. Never replace final with a search score.\n"
        "Return campaign, selected code, final delivery and environment observation. Report "
        "blocked/failed execution honestly. The initiator collects host receipts and actual usage."
    )


def status(root):
    return _status(root, *_load(root))


def _status(root, plan, state, *, host_views=None):
    rows, active = [], None
    for trial in plan["trials"]:
        number = _attempt_number(state, trial)
        job = _job(root, trial, number)
        if host_views is None:
            try:
                view = manager.agent_session_status(job) if job.exists() else None
            except (OSError, ValueError) as error:
                # As in report: unverifiable job evidence blocks only this trial.
                view = {"state": "blocked", "native_session": None,
                        "error": type(error).__name__}
        else:
            view = host_views[trial["id"]]
        collection = state["collections"].get(trial["id"])
        previous = [{"attempt": entry["attempt"], "collection": entry["collection"]["path"],
                     "status": _archived_result(root, trial, entry).get("status")}
                    for entry in _attempts(state, trial)]
        row = {**trial, "workspace": _attempt_paths(trial, number)[1], "attempt": number,
               "previous_attempts": previous, "job": str(job),
               "campaign": str(_workspace(root, trial, number) / "campaign"),
               "state": view["state"] if view else "pending", "collection": collection,
               "host": view}
        rows.append(row)
        if active is None and collection is None:
            active = row
    action = {"operation": "report", "instructions": "All declared trials were collected; "
              "generate the comparison report, including failures."}
    published = state.get("report")
    if (active is None and published
            and published["collection_digest"] == _collection_digest(state)):
        action = {"operation": "completed", "reports": published["paths"],
                  "instructions": "Read the generated comparison and report its scoped conclusion. "
                  "Use --action report to reverify evidence or regenerate a snapshot."}
    if active is not None:
        if active["host"] is None:
            action = {"operation": "dispatch", "trial": active["id"],
                      "instructions": "Reserve one handoff; call the host's fresh-session tool "
                      "with its exact prompt and workspace. Bind the returned native ID."}
        elif active["state"] == "blocked":
            action = {"operation": "inspect_retained_host_evidence", "trial": active["id"],
                      "instructions": "Verify the original native job receipts before collection."}
        elif active["state"] in manager.AGENT_TERMINAL_STATES:
            action = {"operation": "collect", "trial": active["id"],
                      "instructions": "Retain actual host metadata and campaign tree; collect. "
                      "Host completion is separate from independent final acceptance."}
        else:
            action = {"operation": active["host"]["next_action"], "trial": active["id"],
                      "native_session": active["host"]["native_session"],
                      "instructions": "Observe or resolve this original session before dispatching "
                      "another. Export observations with agents record or compare --action record.",
                      "observation_fields": {
                          "host": "bound host", "host_id": "bound host ID or null",
                          "session_id": "bound session ID", "state": "actual native state",
                          "native_receipt": "original host tool response object",
                          "benchmark_observation": {
                              "model": "actually observed model", "effort": "observed effort",
                              "environment_id": plan["config"]["environment_id"],
                              "environment_fingerprint": "digest of observed Python implementation "
                              "and version, runtime versions, device model and allocator profile",
                              "knowledge_policy_violation": "false only when no violation observed",
                          },
                          "usage": "optional actual cumulative input/output/cached_input tokens",
                          "usage_scope": "session_total when usage is present",
                          "native_session_window": "optional in the terminal observation: "
                          "{session_id, started_at, ended_at} in Unix seconds from the host's "
                          "own record of this session; never campaign or receipt times",
                      }}
    return {"output": str(root), "focus": plan["focus"], "config": plan["config"],
            "parameter_sources": plan["parameter_sources"], "trials": rows,
            "state": "collected" if active is None else "running", "next_action": action}


def dispatch(root, trial_id, *, parallel=False):
    plan, state = _load(root)
    trial = _select(plan, trial_id)
    number = _attempt_number(state, trial)
    job, workspace = _job(root, trial, number), _workspace(root, trial, number)
    if not job.exists():
        if not parallel:
            current = _status(root, plan, state)["next_action"]
            if current.get("trial") != trial_id or current["operation"] != "dispatch":
                raise ValueError("Dispatch the next declared trial or pass --parallel")
        job.parent.mkdir(exist_ok=True)
        manager.prepare_agent_session(
            job, prompt=_prompt(root, plan, trial, workspace), workspace=workspace,
            title=trial_id if number == 1 else f"{trial_id} attempt {number}",
            max_seconds=plan["config"]["job_max_minutes"] * 60,
            model=plan["config"]["model"], effort=plan["config"]["effort"],
            task_reference={"comparison": digest(plan), "trial": trial_id, "attempt": number},
            frozen_inputs=(root / "experiment.json",),
        )
    return manager.dispatch_agent_session(job)


def _host_payload(job, host):
    if host is None or host["state"] not in manager.AGENT_TERMINAL_STATES:
        return None
    receipt = host["last_observation"]
    return _object(job / receipt["path"]) if receipt else None


def _native_window(host, payload):
    """The attempt's own start/end: the bound native session's exported interval.

    Campaign start/end and the time a receipt was recorded are not attempt
    boundaries, so they never substitute for a missing interval.
    """
    native = host.get("native_session")
    if not native:
        return None, "native_session_not_created"
    window = payload.get("native_session_window") if payload is not None else None
    if not isinstance(window, dict):
        return None, "native_session_window_not_exported"
    start, end = _finite(window.get("started_at")), _finite(window.get("ended_at"))
    if (window.get("session_id") != native["session_id"] or start is None or end is None
            or end < start):
        return None, "native_session_window_invalid"
    return {"started_at": start, "ended_at": end,
            "source": "caller_exported_terminal_native_receipt"}, None


def _verified_capture(snapshot, reference, campaign_id):
    path = reference["path"]
    source = snapshot.file(path, "knowledge", reference["sha256"], document=True)
    if snapshot.verified([source]):
        capture, _ = verify_capture(snapshot.documents[path])
        if (capture is not None and capture["campaign_id"] == campaign_id
                and capture["assembled_text"] == assemble_context_text(capture["contexts"])):
            return capture
    return None


def _card_request(request, requirement):
    scenario = request.get("scenario")
    frozen = requirement["scenario"]
    return (request.get("relevance") == requirement["query"]
            and (not request.get("query") or request["query"] == requirement["query"])
            and SCENARIO_ALIASES.get(scenario, scenario) == SCENARIO_ALIASES.get(frozen, frozen))


def _complete_card_pages(pages, body_sha256):
    """Reconstruct bytes from verified intervals; keep the receipts that supplied them."""
    body = bytearray()
    contributors = []
    total = pages[0][0]["total_bytes"]
    for bounds, data, receipt in sorted(pages, key=lambda p: (p[0]["start"], -p[0]["end"])):
        start, end = bounds["start"], bounds["end"]
        if bounds["total_bytes"] != total or start > len(body):
            return []
        overlap = min(end, len(body)) - start
        if body[start:start + overlap] != data[:overlap]:
            return []
        if end > len(body):
            body.extend(data[overlap:])
            contributors.append(receipt)
    if len(body) == total and hashlib.sha256(body).hexdigest() == body_sha256:
        return contributors
    return []


def _card_delivery(snapshot, campaign_id, references, requirement):
    """Account for all actual resources in each frozen query's verified first-round inputs."""
    limit = requirement["context_bytes"]
    plan_budget = requirement.get("budget_source") == "experiment_plan"
    result = {"ref": requirement["ref"], "revision": requirement["revision"], "capture": None,
              "context_bytes": limit, "requests": []}
    if plan_budget:
        result["budget_source"] = "experiment_plan"
    groups = {}
    pages = {}
    card_hits = set()
    evidence_problem = False
    unknown_totals = set()
    for ref in references:
        kind = ref.get("kind")
        if kind not in ("knowledge_search", "delivered_context"):
            continue
        capture = _verified_capture(snapshot, ref, campaign_id)
        request = capture["request"] if capture else {}
        search_ref = ref.get("search_ref") or request.get("search_ref")
        if search_ref:
            group = groups.get(search_ref)
            if group is None:
                if capture and _card_request(request, requirement):
                    # A later valid query cannot account for this read's missing Find.
                    evidence_problem = True
                continue
            if capture is None:
                evidence_problem = True
                unknown_totals.add(search_ref)
                continue
            if (request.get("search_ref") != search_ref or not _card_request(request, requirement)
                    or request.get("context_bytes") != group.get("requested_bytes")):
                evidence_problem = True
        elif capture and _card_request(request, requirement):
            # Older managed commands ranked and delivered in one receipt.
            search_ref = ref["path"]
            group = {"search_ref": search_ref}
            if not plan_budget:
                group["requested_bytes"] = request.get("context_bytes")
            elif kind != "knowledge_search" or "context_bytes" in request:
                evidence_problem = True
            group.update(delivered_bytes=0, body_capture=None, omitted_for_budget=False)
            groups[search_ref] = group
            result["requests"].append(group)
            if kind == "knowledge_search":
                if any(hit.get("ref") == requirement["ref"]
                       and hit.get("revision") == requirement["revision"]
                       for hit in capture["items"]):
                    card_hits.add(search_ref)
                continue
            if (capture.get("retrieval") or {}).get("entrypoint") == "read":
                evidence_problem = True
                continue
            card_hits.add(search_ref)
        else:
            continue
        # Historical tools declared their own cap; the current protocol measures
        # delivered resource bytes directly against the frozen experiment plan.
        budget = capture.get("context_budget")
        if plan_budget and ("context_bytes" in request or budget is not None):
            evidence_problem = True
        if (not plan_budget and (budget is not None or search_ref == ref["path"])
                and (not isinstance(budget, dict) or type(budget.get("max_bytes")) is not int
                     or budget["max_bytes"] != group["requested_bytes"])):
            evidence_problem = True
        for context in capture["contexts"]:
            for resource in context["resources"]:
                data = resource["content"].encode("utf-8")
                group["delivered_bytes"] += len(data)
                if (context["ref"] != requirement["ref"] or search_ref not in card_hits
                        or context["revision"] != requirement["revision"]
                        or resource["path"] != "record.json"):
                    continue
                bounds = resource.get("content_range")
                if bounds is not None:
                    if (not request.get("search_ref")
                            or resource.get("source_sha256") != requirement["body_sha256"]):
                        continue
                    pages.setdefault(search_ref, []).append((bounds, data, ref))
                    if bounds["start"] != 0 or bounds["end"] != bounds["total_bytes"]:
                        continue
                if (resource["sha256"] == requirement["body_sha256"]
                        and group["body_capture"] is None):
                    group["body_capture"] = ref
        if any(o.get("ref") == requirement["ref"] and o.get("reason") == "context_limit"
               for o in capture["context_omissions"]):
            group["omitted_for_budget"] = True

    for search_ref, received in pages.items():
        group = groups[search_ref]
        if group["body_capture"] is None:
            group["body_captures"] = _complete_card_pages(received, requirement["body_sha256"])
    if evidence_problem:
        for search_ref in unknown_totals:
            groups[search_ref]["delivered_bytes"] = None
        return result, "First-round knowledge request or linked delivery could not be verified"
    for group in groups.values():
        used = group["delivered_bytes"]
        if (plan_budget or group["requested_bytes"] == limit) and used > limit:
            return result, (f"Frozen knowledge context budget exceeded before the first round "
                            f"({used} UTF-8 resource bytes delivered, {limit} allowed)")
    if not plan_budget and any(g["delivered_bytes"] and (type(g["requested_bytes"]) is not int
                               or g["requested_bytes"] != limit) for g in groups.values()):
        return result, "First-round knowledge context budget differs from the frozen plan"
    for group in groups.values():
        if not plan_budget and group["requested_bytes"] != limit:
            continue
        if group["body_capture"]:
            result["capture"] = group["body_capture"]
            return result, None
        if group.get("body_captures"):
            result["captures"] = group["body_captures"]
            return result, None
    gap = ("Required knowledge card body was not delivered before the first round: "
           + requirement["ref"])
    if any(g["omitted_for_budget"] for g in groups.values()):
        gap += " (recorded context budget omission)"
    return result, gap


def _trial_result(root, plan, trial, host, payload, *, workspace, host_error=None):
    result = {"id": trial["id"], "task": trial["task"], "repeat": trial["repeat"],
              "condition": trial["condition"], "status": "blocked", "eligible": False,
              "gaps": [], "metrics": {"speedup": None, "wall_seconds": None, "tokens": None},
              "trace": [], "final": None, "usage": {}, "knowledge_deliveries": [],
              "observed_settings": None, "metrics_comparable": False,
              "benchmark_metrics": None, "campaign_window": None, "attempt_tokens": None,
              "attempt_window": None, "attempt_window_missing": None}
    if host_error is not None:
        result["gaps"].append(f"Native job evidence could not be verified ({host_error})")
        result["attempt_window_missing"] = "native_job_evidence_not_verifiable"
        return result
    campaign = workspace / "campaign"
    if host is None or host["state"] not in manager.AGENT_TERMINAL_STATES:
        result["status"] = "pending" if host is None else "running"
        result["gaps"].append("Native execution has not terminated")
        result["attempt_window_missing"] = "native_execution_not_terminated"
        return result
    # A failed or blocked attempt still consumed its exported session total.
    if host["usage"] is not None:
        result["attempt_tokens"] = host["usage"]["input_tokens"] + host["usage"]["output_tokens"]
    # A failure before campaign creation still has its native session interval.
    result["attempt_window"], result["attempt_window_missing"] = _native_window(host, payload)
    result["status"] = "failed" if host["state"] != "completed" else "blocked"
    receipt = host["last_observation"]
    if payload is not None:
        observed = payload.get("benchmark_observation")
        if isinstance(observed, dict):
            result["observed_settings"] = observed
    observed = result["observed_settings"] or {}
    if any(not isinstance(observed.get(key), str) or not observed[key].strip()
           for key in OBSERVED_FIELDS):
        result["gaps"].append("Actual host model, effort or environment observation is missing")
    if observed.get("environment_id") != plan["config"]["environment_id"]:
        result["gaps"].append("Observed execution environment differs from the frozen profile")
    for key in ("model", "effort"):
        if plan["config"][key] and observed.get(key) != plan["config"][key]:
            result["gaps"].append(f"Observed {key} differs from the requested setting")
    if observed.get("knowledge_policy_violation") is not False:
        result["gaps"].append("Knowledge-policy observation is missing or reports a violation")
    if host["usage"] is not None and host["state"] == "completed":
        result["usage"]["host_session_tokens"] = {"value": host["usage"],
            "coverage": "complete", "source": "caller_exported_terminal_native_receipt"}
        result["metrics"]["tokens"] = host["usage"]["input_tokens"] + host["usage"]["output_tokens"]
    if not campaign.is_dir():
        result["gaps"].append("Campaign evidence was not returned")
        return result
    try:
        snapshot, delivery, _ = project(campaign, export_id="comparison-read")
        campaign_plan, control, _ = manager.read_session_records(campaign)
        result["campaign_window"] = {"started_at": control.get("started_at"),
                                     "ended_at": control.get("settled_at")}
        window = result["attempt_window"]
        bounds = [_finite(control.get(key)) for key in ("started_at", "settled_at")]
        if window is not None and any(
                value is not None and not window["started_at"] <= value <= window["ended_at"]
                for value in bounds):
            result["attempt_window"] = None
            result["attempt_window_missing"] = "native_session_window_excludes_campaign"
        settings = plan["task_settings"][trial["task"]]
        wanted = {"task": trial["task"], "condition": trial["id"],
                  "knowledge_allowed": trial["condition"] == "on",
                  "round_limit": plan["config"]["rounds"], "round_mode": "exact",
                  "max_seconds": plan["config"]["max_minutes"] * 60,
                  "evaluation_timeout_seconds": plan["config"]["evaluation_timeout_seconds"],
                  "final_reserve_seconds": plan["config"]["final_reserve_seconds"],
                  "evaluation_settings": settings["settings"],
                  "evaluation_prefix": shlex.split(settings["evaluation_prefix"]),
                  "frozen_files": settings["files"]}
        if "metrics_policy" in plan:
            wanted["report_metadata"] = {"benchmark_metrics": plan["metrics_policy"]}
        if any(campaign_plan.get(key) != value for key, value in wanted.items()):
            result["gaps"].append("Campaign task, condition, protocol or budget differs from plan")
        if plan.get("diagnosis_required") and campaign_plan.get("diagnosis_required") is not True:
            result["gaps"].append("Campaign did not require measured bottleneck evidence")
        if campaign_plan.get("runtime_identity") != plan["session_runtime_identity"]:
            result["gaps"].append("Campaign runtime identity differs from the frozen runtime")
        result["knowledge_deliveries"] = control["contexts"]
        if trial["condition"] == "off" and control["contexts"]:
            result["gaps"].append("Knowledge retrieval was recorded in the off condition")
        requirement = _knowledge_requirement(plan, trial)
        if requirement is not None:
            # The verified observation pins the inputs snapshotted at round start.
            first_inputs = []
            if (control["rounds"] and delivery["rounds"]
                    and delivery["rounds"][0].get("record_verified")):
                first_inputs = control["rounds"][0]["contexts"]
            result["knowledge_delivery"], gap = _card_delivery(
                snapshot, delivery["campaign"]["id"], first_inputs, requirement)
            if gap:
                result["gaps"].append(gap)
        result["usage"].update(delivery["usage"])
        result["benchmark_metrics"] = delivery.get("benchmark_metrics")
        child_metrics_policy = campaign_plan.get("report_metadata", {}).get("benchmark_metrics")
        result["metrics_comparable"] = (not result["gaps"]
                                        and supported_policy(plan.get("metrics_policy"))
                                        and supported_policy(child_metrics_policy))
        if (result["benchmark_metrics"] is not None and host["usage"] is not None
                and payload is not None
                and supported_policy(plan.get("metrics_policy"))
                and supported_policy(child_metrics_policy)):
            update_metrics(result["benchmark_metrics"], terminal_token_usage(
                host, payload, trial_id=trial["id"], control=control, source=receipt["sha256"]))
        if delivery["acceptance"]["delivery_accepted"] and control["final"]:
            final_assessment = control["final"]["assessment"]
            result["metrics"]["speedup"] = (
                1.0 if control["best"]["kind"] == "baseline"
                else (final_assessment.get("speedup")
                      if final_assessment.get("speedup") is not None
                      else final_assessment.get("score"))
            )
        result["metrics"]["wall_seconds"] = delivery["usage"]["wall_seconds"]["value"]
        result["final"] = {"assessment": control["final"]["assessment"]
                           if control["final"] else None,
                           "speedup": result["metrics"]["speedup"],
                           "binding": (delivery["final"] or {}).get("binding"),
                           "selected_candidate": control["best"],
                           "delivery_accepted": delivery["acceptance"]["delivery_accepted"]}
        for index, record in enumerate(control["rounds"], 1):
            assessment = record["assessment"]
            result["trace"].append({
                "round": index, "strategy": record.get("strategy") or record["hypothesis"],
                "diagnosis_id": record.get("diagnosis_id"),
                "hypothesis": record["hypothesis"],
                "knowledge_refs": record.get("knowledge_refs"),
                "available_contexts": record["contexts"],
                "knowledge_attribution": "agent_declared; delivery is not proof of use",
                "speedup": assessment.get("speedup", assessment.get("score")),
                "best_speedup": record["best_after"]["score"], "quality": assessment["verdict"],
                "assessment_status": assessment["status"],
                "adopted": (assessment["status"] != "interrupted" and
                            record["best_after"].get("candidate_id") == record["candidate_id"]),
            })
        if (host["state"] != "completed" or not delivery["acceptance"]["delivery_accepted"]
                or delivery["completion"]["status"] != "completed"):
            result["gaps"].append("A completed, verified independent final is required")
        if not snapshot.stable():
            result["gaps"].append("Campaign changed while collecting")
            result["metrics_comparable"] = False
        result["status"] = "completed" if control["state"] == "completed" else "blocked"
    except (OSError, ValueError, TypeError, KeyError) as error:
        result["metrics_comparable"] = False
        result["gaps"].append(f"Campaign evidence could not be verified: {type(error).__name__}")
    result["eligible"] = not result["gaps"]
    return result


def collect(root, trial_id):
    """Record one terminal attempt once; repeating it returns that first record.

    The first collection is the attempt's recorded classification, which report
    accounting and retry eligibility read. A repeated collect of the same attempt
    writes no new snapshot and keeps the pointer, so later evidence loss can
    neither rewrite that history nor open a retry. Report re-verifies live evidence.
    """
    plan, state = _load(root)
    trial = _select(plan, trial_id)
    reference = state["collections"].get(trial_id)
    number = _attempt_number(state, trial)
    if reference is not None:
        return {"trial": _retained(root, reference, trial_id, number), "already_collected": True,
                "collection": reference, "next": _status(root, plan, state)["next_action"]}
    job = _job(root, trial, number)
    host = manager.agent_session_status(job) if job.exists() else None
    if host is None or host["state"] not in manager.AGENT_TERMINAL_STATES:
        raise ValueError("Collect only after recording a terminal native host observation")
    result = _trial_result(root, plan, trial, host, _host_payload(job, host),
                           workspace=_workspace(root, trial, number))
    # The digest-checked record names its own attempt, so it cannot stand for another one.
    result["attempt"] = number
    directory = root / "collections"
    directory.mkdir(exist_ok=True)
    path = directory / (trial_id + "-" + uuid.uuid4().hex + ".json")
    atomic_write_json(path, result)
    state["collections"][trial_id] = {"path": path.relative_to(root).as_posix(),
                                       "sha256": sha256(path), "attempt": number}
    atomic_write_json(root / "state.json", state)
    return {"trial": result, "next": _status(root, plan, state)["next_action"]}


def retry(root, trial_id, *, parallel=False):
    """Open a fresh attempt after a collected, unsuccessful one; never automatic.

    The collected attempt stays retained evidence. The new attempt gets its own
    native job and workspace with the same frozen runtime and prompt. An eligible
    completed result cannot be retried, so a verdict cannot be re-rolled.
    """
    plan, state = _load(root)
    trial = _select(plan, trial_id)
    number = _attempt_number(state, trial)
    job = _job(root, trial, number)
    reference = state["collections"].get(trial_id)
    host = manager.agent_session_status(job) if job.exists() else None
    if reference is None or host is None or host["state"] not in manager.AGENT_TERMINAL_STATES:
        raise ValueError("Retry only after collecting a terminal attempt of this trial")
    retained = _retained(root, reference, trial_id, number)
    if retained.get("status") == "completed" and retained.get("eligible") is True:
        raise ValueError("An eligible completed attempt is the arm's result; retry is refused")
    if not parallel:
        for other in plan["trials"]:
            if (other["id"] != trial_id and other["id"] not in state["collections"]
                    and _job(root, other, _attempt_number(state, other)).exists()):
                raise ValueError("Collect active trial " + other["id"]
                                 + " before retrying, or pass --parallel")
    expected = _expected_runtime(plan, trial)
    destination = _io_path(_workspace(root, trial, number + 1))
    if destination.exists():
        # Only an identical runtime left by an interrupted retry is reused.
        if (sorted(path.name for path in destination.iterdir()) != ["runtime"]
                or _manifest(destination / "runtime/inferrsi") != expected):
            raise ValueError("Retry workspace already exists with other content")
    else:
        with TemporaryDirectory(prefix=".retry-", dir=_io_path(root)) as temporary:
            staging = Path(temporary) / "workspace"
            (staging / "runtime").mkdir(parents=True)
            # Copy the current attempt's runtime: _load verified it; older copies may be gone.
            shutil.copytree(_io_path(_workspace(root, trial, number) / "runtime/inferrsi"),
                            staging / "runtime/inferrsi",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if _manifest(staging / "runtime/inferrsi") != expected:
                raise ValueError(f"Frozen comparison runtime changed: {trial_id}")
            _publish_directory(staging, destination)
    job_path, workspace = _attempt_paths(trial, number)
    state.setdefault("attempts", {}).setdefault(trial_id, []).append({
        "attempt": number, "job": job_path, "workspace": workspace,
        "collection": {"path": reference["path"], "sha256": reference["sha256"]}})
    del state["collections"][trial_id]
    atomic_write_json(root / "state.json", state)
    return status(root)


def _reverify(root, plan, trial, number, *, collected=False, archived=False):
    """Rebuild one attempt from its own job and campaign; never trust a stale collection.

    An archived attempt also re-checks its own runtime copy (_load checks only the
    current one). A missing or changed copy is a gap of this re-read: the attempt is
    not re-verified and its cost is unknown; its recorded classification is untouched.
    """
    job = _job(root, trial, number)
    workspace = _workspace(root, trial, number)
    try:
        if collected and not job.is_dir():
            # A collected attempt had a terminal job: losing it is unverifiable, not "not run".
            raise FileNotFoundError("Collected native job is missing")
        host = manager.agent_session_status(job) if job.exists() else None
        payload = _host_payload(job, host)
    except (OSError, ValueError) as error:
        host = {"state": "blocked", "native_session": None}
        result = _trial_result(root, plan, trial, None, None, workspace=workspace,
                               host_error=type(error).__name__)
    else:
        result = _trial_result(root, plan, trial, host, payload, workspace=workspace)
    runtime_error = _runtime_error(root, plan, trial, number) if archived else None
    if runtime_error is not None:
        result["gaps"].append(f"Frozen runtime copy could not be verified ({runtime_error})")
        if result["attempt_window"] is not None:
            result["attempt_window_missing"] = "frozen_runtime_not_verifiable"
        result.update(eligible=False, metrics_comparable=False, attempt_tokens=None,
                      attempt_window=None, campaign_window=None,
                      metrics=dict.fromkeys(result["metrics"]))
    return host, result


def _attempt_row(number, result, host, recorded=None):
    """One attempt for accounting; recorded classification and current re-read stay apart.

    A collected attempt's ``status``, ``eligible`` and ``gaps`` are exactly those of
    its digest-checked collection, so a later re-read can neither turn a recorded
    failure into "not run" nor a recorded success into a failure. The current
    re-read is shown only under ``reverification`` (status, eligibility, added
    gaps); it, not the record, decides the verdict and the successful wall. Costs
    and attempt boundaries come only from evidence that re-reads now, so an
    unreadable attempt has unknown cost rather than a stale one.
    """
    row = {"attempt": number, "status": result["status"], "eligible": result["eligible"],
           "gaps": list(result["gaps"]), "wall_seconds": result["metrics"]["wall_seconds"],
           "campaign_window": result.get("campaign_window"),
           "attempt_window": result.get("attempt_window"),
           "attempt_window_missing": result.get("attempt_window_missing"),
           "tokens": result.get("attempt_tokens"),
           "tokens_missing": result.get("attempt_tokens_missing"),
           "native_session": (host or {}).get("native_session"), "reverification": None}
    if recorded is not None:
        if (recorded.get("status") not in STATUSES or type(recorded.get("eligible")) is not bool
                or not isinstance(recorded.get("gaps"), list)
                or any(not isinstance(gap, str) for gap in recorded["gaps"])):
            raise ValueError("Malformed retained comparison collection")
        added = [gap for gap in result["gaps"] if gap not in recorded["gaps"]]
        row.update(status=recorded["status"], eligible=recorded["eligible"],
                   gaps=list(recorded["gaps"]))
        row["reverification"] = {
            "verified": (result["status"] == recorded["status"] and not added
                         and (result["eligible"] or not recorded["eligible"])),
            "status": result["status"], "eligible": result["eligible"], "added_gaps": added}
    return row


def report(root):
    plan, state = _load(root)
    trials = []
    sessions = {}
    host_views = {}
    attempts = {}
    for trial in plan["trials"]:
        reference = state["collections"].get(trial["id"])
        collected = None
        if reference:
            collected = _retained(root, reference, trial["id"], _attempt_number(state, trial))
        attempts[trial["id"]] = []
        for entry in _attempts(state, trial):
            recorded = _archived_result(root, trial, entry)
            host, attempt = _reverify(root, plan, trial, entry["attempt"], collected=True,
                                      archived=True)
            attempts[trial["id"]].append((entry["attempt"], attempt, host, recorded))
        # Reverify current evidence; a stale collection cannot hide later evidence loss.
        number = _attempt_number(state, trial)
        host, result = _reverify(root, plan, trial, number, collected=collected is not None)
        host_views[trial["id"]] = host
        trials.append(result)
        attempts[trial["id"]].append((number, result, host, collected))
        for _, attempt, attempt_host, _ in attempts[trial["id"]]:
            if attempt_host and attempt_host["native_session"]:
                sessions.setdefault(_session_key(attempt_host["native_session"]), []).append(
                    (trial["id"], attempt))
    duplicated = set()
    for members in sessions.values():
        if len(members) > 1:
            for trial_id, attempt in members:
                duplicated.add(trial_id)
                attempt["eligible"] = False
                attempt["metrics_comparable"] = False
                # A shared session's usage and interval belong to no single attempt.
                attempt.update(attempt_tokens=None, attempt_tokens_missing=SHARED_SESSION,
                               attempt_window=None, attempt_window_missing=SHARED_SESSION)
                if "Native session is bound to multiple comparison trials" not in attempt["gaps"]:
                    attempt["gaps"].append("Native session is bound to multiple comparison trials")
    for trial in trials:
        if trial["id"] in duplicated:
            trial["eligible"] = False
            trial["metrics_comparable"] = False
            if "Native session is bound to multiple comparison trials" not in trial["gaps"]:
                trial["gaps"].append("Native session is bound to multiple comparison trials")
    # Rows describe each attempt's own evidence, before pair-level exclusions below.
    rows = {trial_id: [_attempt_row(*item) for item in items]
            for trial_id, items in attempts.items()}
    for task in plan["config"]["tasks"]:
        for repeat in range(1, plan["config"]["repeats"] + 1):
            pair = [t for t in trials if t["task"] == task and t["repeat"] == repeat]
            if (all(t["eligible"] for t in pair) and len(pair) == 2
                    and any(pair[0]["observed_settings"].get(key)
                            != pair[1]["observed_settings"].get(key) for key in OBSERVED_FIELDS)):
                for trial in pair:
                    trial["eligible"] = False
                    trial["gaps"].append("Paired actual Agent/environment settings differ")
            if (len(pair) == 2 and all(t.get("observed_settings") for t in pair)
                    and any(pair[0]["observed_settings"].get(key)
                            != pair[1]["observed_settings"].get(key) for key in OBSERVED_FIELDS)):
                for trial in pair:
                    trial["metrics_comparable"] = False
    # Accounting is descriptive; the verdict below still reads each arm's selected attempt.
    for result in trials:
        result["attempts"] = rows[result["id"]]
        result["attempt_accounting"] = attempt_accounting(rows[result["id"]])
    result = {"schema_version": 1, "focus": "knowledge", "tasks": plan["config"]["tasks"],
              "repeats": plan["config"]["repeats"], "policy": plan["config"]["policy"],
              "knowledge_boundary": plan["knowledge_boundary"], "plan_digest": digest(plan),
              "trials": trials, "assessment": summarize(trials, plan["config"]["tasks"],
                  plan["config"]["repeats"], plan["config"]["policy"])}
    result["benchmark_metrics"] = metrics_comparison(
        trials, plan["config"]["tasks"], plan["config"]["repeats"], plan.get("metrics_policy"))
    destination = root / "reports" / uuid.uuid4().hex
    paths = write_comparison_report(result, destination)
    state["report"] = {"collection_digest": _collection_digest(state), "paths": paths}
    atomic_write_json(root / "state.json", state)
    return {"assessment": result["assessment"], "benchmark_metrics": result["benchmark_metrics"],
            "reports": paths,
            "next_action": _status(root, plan, state, host_views=host_views)["next_action"]}


def compare_command(args):
    if args.action == "prepare":
        return prepare(args)
    if args.output is None:
        raise ValueError("Existing comparison operations require --output")
    root = args.output.resolve()
    with file_lock(root / ".compare.lock"):
        if args.action == "status":
            return status(root)
        if args.action == "report":
            return report(root)
        if args.action == "dispatch":
            return dispatch(root, args.trial, parallel=args.parallel)
        if args.action == "collect":
            return collect(root, args.trial)
        if args.action == "retry":
            return retry(root, args.trial, parallel=args.parallel)
        plan, state = _load(root)
        trial = _select(plan, args.trial)
        job = _job(root, trial, _attempt_number(state, trial))
        if args.action == "bind":
            if not args.host or not args.session_id or args.receipt is None:
                raise ValueError("bind requires --host, --session-id and --receipt")
            # Every attempt, archived or current, needs its own native session.
            for other in plan["trials"]:
                for number in range(1, _attempt_number(state, other) + 1):
                    other_job = _job(root, other, number)
                    if other_job == job or not other_job.exists():
                        continue
                    native = manager.agent_session_status(other_job)["native_session"]
                    if native and _session_key(native) == (args.host, args.session_id):
                        raise ValueError("Native session is already bound to trial "
                                         f"{other['id']} attempt {number}")
            return manager.bind_agent_session(job, host=args.host, session_id=args.session_id,
                                       host_id=args.host_id, receipt=args.receipt)
        if args.observation is None:
            raise ValueError("record requires --observation")
        return manager.record_agent_session(job, observation=args.observation)
