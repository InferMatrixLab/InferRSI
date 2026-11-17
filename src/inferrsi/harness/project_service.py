"""Project-owned service protocols and their retained, multi-objective evidence.

No file/content fingerprints are calculated here. Revision, configuration and
actual service receipts establish the explicitly declared execution binding.
"""

import io
import json
import math
import os
import re
import subprocess
import tarfile
import time
import uuid
from pathlib import Path
from statistics import mean, median

from .atomic_json import atomic_write_json
from .candidates import members, retain


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Expected a campaign-relative path")
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise ValueError("Path must stay inside the campaign")
    target = root / part
    if not target.resolve().is_relative_to(root.resolve()) or any(
        p.is_symlink() for p in (target, *target.parents) if p.is_relative_to(root)
    ):
        raise ValueError("Symbolic or escaping campaign path")
    return target


def no_fingerprints(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or any(
                name in key.lower() for name in ("sha256", "fingerprint", "digest")
            ):
                raise ValueError("File fingerprints are not part of the service-reuse protocol")
            no_fingerprints(item)
    elif isinstance(value, list):
        for item in value:
            no_fingerprints(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite JSON value")


def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError(f"Missing, symbolic or oversized JSON: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Result must be a JSON object")
    no_fingerprints(value)
    return value


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def positive(value):
    return number(value) and value > 0


def validate_conditions(conditions):
    if not isinstance(conditions, dict):
        raise ValueError("Explicit test conditions required")
    if not isinstance(conditions.get("id"), str) or not conditions["id"].strip():
        raise ValueError("Conditions require a nonempty string ID")
    for key in ("id", "workload", "model", "precision", "topology", "runtime", "timing_scope"):
        if not conditions.get(key):
            raise ValueError(f"conditions.{key} is required")
    if not isinstance(conditions.get("effective_config"), dict):
        raise ValueError("conditions.effective_config must be an object")
    no_fingerprints(conditions)


def validate(settings):
    no_fingerprints(settings)
    for name in ("conditions", "commands", "sampling", "quality", "stagnation"):
        if not isinstance(settings.get(name), dict):
            raise ValueError(f"{name} must be an explicit object")
    if type(settings.get("schema_version")) is not int or settings["schema_version"] != 1:
        raise ValueError("Service evaluation schema_version must be 1")
    if not isinstance(settings.get("protocol_id"), str) or not settings["protocol_id"].strip():
        raise ValueError("Explicit protocol_id required")
    validate_conditions(settings.get("conditions"))
    commands = settings.get("commands", {})
    for name in ("precheck", "service", "ready", "warmup", "measure", "quality", "profile", "stop"):
        command = commands.get(name)
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(arg, str) or not arg for arg in command)
        ):
            raise ValueError(f"commands.{name} must be explicit argv")
        if not any("{protocol}" in arg for arg in command):
            raise ValueError(f"commands.{name} must use a retained protocol script")
        if name != "service" and not any("{result}" in arg for arg in command):
            raise ValueError(f"commands.{name} must write the supplied result")
    sampling = settings.get("sampling", {})
    if not positive(sampling.get("stage_timeout_seconds")):
        raise ValueError("Positive stage timeout required")
    for role in ("baseline", "candidate", "final"):
        config = sampling.get(role, {})
        if not isinstance(config, dict):
            raise ValueError("Sampling policies must be objects")
        if type(config.get("repetitions")) is not int or config["repetitions"] < 1:
            raise ValueError(f"Positive {role} repetitions required")
        if type(config.get("warmups")) is not int or config["warmups"] < 0:
            raise ValueError(f"Nonnegative {role} warmups required")
        if config["warmups"] == 0 and not config.get("warmup_reason"):
            raise ValueError("Explain why no warmup is necessary")
    scenarios = settings.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("Declare scenarios")
    ids = []
    for item in scenarios:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("Scenario must declare a string ID")
        if (
            not item.get("id")
            or not item.get("workload")
            or (type(item.get("requests")) is not int or item["requests"] < 1)
            or type(item.get("required_successes")) is not int
            or not (0 < item["required_successes"] <= item["requests"])
        ):
            raise ValueError("Declare scenario workload, request and success counts")
        ids.append(item["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate scenario")
    objectives = settings.get("objectives")
    if not isinstance(objectives, list) or not objectives:
        raise ValueError("Declare objectives")
    names = []
    for obj in objectives:
        if not isinstance(obj, dict) or not isinstance(obj.get("domain"), dict):
            raise ValueError("Objective and domain must be objects")
        for key in ("id", "key", "unit"):
            if not isinstance(obj.get(key), str) or not obj[key].strip():
                raise ValueError(f"Objective {key} required")
        names.append(obj["id"])
        if obj.get("scenario") not in ids or obj.get("direction") not in ("minimize", "maximize"):
            raise ValueError("Invalid objective scenario or direction")
        if (
            obj.get("aggregate") not in ("median", "mean")
            or obj.get("threshold_type") not in ("relative_percent", "absolute", "percentage_point")
            or type(obj.get("gain")) is not bool
        ):
            raise ValueError("Declare aggregation, threshold type and gain participation")
        domain = obj.get("domain", {})
        if (
            not number(domain.get("min"))
            or not number(domain.get("max"))
            or (domain["min"] > domain["max"])
        ):
            raise ValueError("Finite ordered objective domain required")
        if obj["threshold_type"] == "percentage_point" and obj["unit"] != "%":
            raise ValueError("Percentage-point objectives use percent values and unit %")
        if obj["threshold_type"] == "relative_percent" and domain["min"] < 0:
            raise ValueError("Use absolute thresholds for negative-valued metrics")
        for key in ("gain_threshold", "parent_regression_limit", "cumulative_regression_limit"):
            if not number(obj.get(key)) or obj[key] < 0:
                raise ValueError(f"Nonnegative finite {key} required")
    ranking = settings.get("ranking")
    if len(set(names)) != len(names) or not any(obj["gain"] for obj in objectives):
        raise ValueError("Unique objectives and at least one gain objective required")
    if (
        not isinstance(ranking, list)
        or not ranking
        or any(not isinstance(name, str) for name in ranking)
        or len(set(ranking)) != len(ranking)
        or any(name not in names for name in ranking)
    ):
        raise ValueError("Declare an ordered, unique ranking of known objectives")
    quality = settings.get("quality", {})
    if (
        quality.get("mode") not in ("absolute", "baseline_comparison")
        or quality.get("direction") not in ("minimize", "maximize")
        or not all(
            isinstance(quality.get(key), str) and quality[key].strip()
            for key in ("key", "dataset", "scorer")
        )
    ):
        raise ValueError("Declare quality mode, direction, dataset, scorer and key")
    gate = "threshold" if quality["mode"] == "absolute" else "tolerance"
    if type(quality.get("samples")) is not int or quality["samples"] < 1:
        raise ValueError("Declare the required quality sample count")
    if not number(quality.get(gate)) or (gate == "tolerance" and quality[gate] < 0):
        raise ValueError("Explicit quality gate required")
    reminder = settings.get("stagnation", {})
    if reminder != {"disabled": True} and (
        type(reminder.get("rounds")) is not int
        or reminder["rounds"] < 1
        or reminder.get("action") not in ("advisory", "pause")
    ):
        raise ValueError("Explicit stagnation threshold/action or disabled required")
    screen = settings.get("screening")
    if screen is not None:
        if not isinstance(screen, dict) or (
            not isinstance(screen.get("command"), list)
            or not screen["command"]
            or any(not isinstance(arg, str) or not arg for arg in screen["command"])
            or not positive(screen.get("estimated_gain"))
        ):
            raise ValueError("Screening command and positive estimated_gain required")
        if not any("{result}" in arg for arg in screen["command"]) or not any(
            "{protocol}" in arg for arg in screen["command"]
        ):
            raise ValueError("Screening must use retained protocol and result")


def value(document, key):
    for part in key.split("."):
        if not isinstance(document, dict) or part not in document:
            raise ValueError(f"Missing metric: {key}")
        document = document[part]
    return document


def aggregate(settings, documents, role):
    if len(documents) != settings["sampling"][role]["repetitions"]:
        raise ValueError("Incomplete performance repetitions")
    samples = {obj["id"]: [] for obj in settings["objectives"]}
    for document in documents:
        for scenario in settings["scenarios"]:
            result = document.get("scenarios", {}).get(scenario["id"], {})
            if (
                result.get("workload") != scenario["workload"]
                or type(result.get("requests")) is not int
                or result["requests"] != scenario["requests"]
                or type(result.get("successes")) is not int
                or not scenario["required_successes"] <= result["successes"] <= (result["requests"])
            ):
                raise ValueError("Incomplete or incompatible scenario requests")
        for obj in settings["objectives"]:
            result = document["scenarios"][obj["scenario"]]
            metric = value(result, obj["key"])
            if (
                result.get("units", {}).get(obj["id"]) != obj["unit"]
                or not number(metric)
                or not (obj["domain"]["min"] <= metric <= obj["domain"]["max"])
            ):
                raise ValueError(f"Invalid metric domain or unit: {obj['id']}")
            samples[obj["id"]].append(metric)
    aggregates = {
        obj["id"]: (median if obj["aggregate"] == "median" else mean)(samples[obj["id"]])
        for obj in settings["objectives"]
    }
    if not all(number(v) for v in aggregates.values()):
        raise ValueError("Nonfinite aggregate")
    return {"values": aggregates, "samples": samples}


def change(obj, candidate, reference):
    sign = 1 if obj["direction"] == "maximize" else -1
    delta = sign * (candidate - reference)
    if obj["threshold_type"] == "relative_percent":
        if reference == 0:
            if candidate != 0:
                raise ValueError(f"Undefined relative change from zero: {obj['id']}")
            return 0
        delta = 100 * delta / abs(reference)
    if not number(delta):
        raise ValueError("Nonfinite derived change")
    return delta


def performance(settings, measured, parent, initial, *, screening=False):
    metrics, limits, gain, actual_gain = {}, True, False, False
    for obj in settings["objectives"]:
        name = obj["id"]
        p = change(obj, measured["values"][name], parent["values"][name])
        b = change(obj, measured["values"][name], initial["values"][name])
        bounded = p >= -obj["parent_regression_limit"] and b >= -obj["cumulative_regression_limit"]
        improved = obj["gain"] and p > 0
        metrics[name] = {
            "value": measured["values"][name],
            "unit": obj["unit"],
            "parent_change": p,
            "initial_change": b,
            "limits_passed": bounded,
            "gain_passed": improved and p >= obj["gain_threshold"],
            "thresholds": {
                key: obj[key]
                for key in (
                    "threshold_type",
                    "gain_threshold",
                    "parent_regression_limit",
                    "cumulative_regression_limit",
                )
            },
        }
        limits &= bounded
        actual_gain |= improved
        gain |= metrics[name]["gain_passed"]
    passed = limits and (actual_gain if screening else gain)
    return {
        "passed": passed,
        "metrics": metrics,
        "reason": "performance_gate_satisfied" if passed else "performance_gate_not_met",
    }


def better(settings, left, right):
    by_id = {obj["id"]: obj for obj in settings["objectives"]}
    for name in settings["ranking"]:
        if left[name] != right[name]:
            return (
                left[name] < right[name]
                if by_id[name]["direction"] == "minimize"
                else left[name] > right[name]
            )
    return False


def quality_score(settings, document):
    config = settings["quality"]
    if document.get("dataset") != config["dataset"] or document.get("scorer") != config["scorer"]:
        raise ValueError("Incompatible quality dataset/scorer")
    score = value(document, config["key"])
    if (
        not number(score)
        or type(document.get("samples")) is not int
        or document["samples"] != config["samples"]
    ):
        raise ValueError("Missing numerical quality evidence")
    return score


def quality_passed(settings, score, reference=None):
    config = settings["quality"]
    sign = 1 if config["direction"] == "maximize" else -1
    if config["mode"] == "absolute":
        return sign * (score - config["threshold"]) >= 0
    if reference is None or not number(reference):
        raise ValueError("Missing compatible baseline quality reference")
    return sign * (score - reference) >= -config["tolerance"]


def revision(source, includes):
    """Use an existing commit, never a file fingerprint, for retained project inputs."""

    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()

    if Path(git("rev-parse", "--show-toplevel")).resolve() != source.resolve():
        raise ValueError("Use the Git checkout root as the service-reuse project")
    commit = git("rev-parse", "HEAD")
    if not re.fullmatch(r"[a-f0-9]{40,64}", commit):
        raise ValueError("Candidate requires an existing Git commit")
    selected = members(source, includes)
    tracked = set(git("ls-files", "-z").split("\0"))
    if any(name not in tracked for name in selected) or git(
        "status", "--porcelain", "--", *selected
    ):
        raise ValueError("Commit declared candidate inputs before service-reuse evaluation")
    return commit


def retain_revision(source, destination, includes, commit):
    if not isinstance(commit, str) or not re.fullmatch(r"[a-f0-9]{40,64}", commit):
        raise ValueError("Candidate requires an existing Git commit")
    archive = subprocess.check_output(
        ["git", "-C", str(source), "archive", "--format=tar", commit, "--", *includes]
    )
    destination.mkdir()
    copied = False
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        for item in stream.getmembers():
            if item.isdir():
                continue
            if not item.isfile():
                raise ValueError("Candidate archive contains symbolic or special files")
            target = safe_path(destination, item.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(stream.extractfile(item).read())
            target.chmod(item.mode & ~0o222)
            copied = True
    if not copied:
        raise ValueError("Declared candidate files are missing from the retained commit")


def prepare(root, args):
    from inferrsi import __version__

    settings = read(args.evaluation_config)
    validate(settings)
    source, protocol = args.repo.resolve(), args.protocol.resolve()
    if args.repo.is_symlink() or args.protocol.is_symlink():
        raise ValueError("Project and protocol roots cannot be symbolic")
    if root.exists() or root.is_relative_to(source) or root.is_relative_to(protocol):
        raise ValueError("Use a new campaign directory outside project/protocol")
    commit = revision(source, args.include)
    members(protocol)
    if not args.instructions.is_file() or args.instructions.is_symlink():
        raise ValueError("Regular task instructions required")
    (root / "frozen").mkdir(parents=True)
    retain_revision(source, root / "frozen/baseline", args.include, commit)
    if revision(source, args.include) != commit:
        raise ValueError("Candidate revision changed while retaining inputs")
    retain(protocol, root / "frozen/protocol", fingerprint=False)
    (root / "frozen/TASK.md").write_bytes(args.instructions.read_bytes())
    atomic_write_json(root / "frozen/evaluation.json", settings)
    for path in (root / "frozen").rglob("*"):
        if path.is_file():
            path.chmod(path.stat().st_mode & ~0o222)
    return {
        "runtime_version": __version__,
        "evaluation_settings": settings,
        "baseline_revision": commit,
        "baseline_path": "frozen/baseline",
        "candidate_name": "candidate",
        "candidate_kind": "directory",
        "candidate_includes": args.include,
        "working_candidate": str(source),
        "task_source": "project",
        "task": "project:" + source.name,
        "evaluation_mode": "service_reuse",
        "selection": {"ranking": settings["ranking"]},
    }


def assessment(verdict, reason, **fields):
    return {
        "status": "infrastructure_failure" if verdict == "INCONCLUSIVE" else "completed",
        "verdict": verdict,
        "eligible": verdict == "PASS",
        "reason": reason,
        **fields,
    }


def execute(root, directory, plan, pending, deadline):
    """One retained attempt, one owned service, ordered client stages, no silent retry."""
    from .local_process import supervised_service
    from .optimization_session import runtime_environment
    from .scenarios.external import execute_trial

    settings = plan["evaluation_settings"]
    conditions = pending["conditions"]
    config = conditions["effective_config"]
    source = directory / "candidate"
    workspace = directory / "workspace"
    expected = {
        "attempt_id": pending["attempt_id"],
        "service_id": uuid.uuid4().hex,
        "run_id": uuid.uuid4().hex,
        "revision": pending["revision"],
        "conditions": conditions,
        "effective_config": config,
    }
    atomic_write_json(directory / "request.json", expected)
    atomic_write_json(directory / "effective-config.json", config)
    receipt = directory / "service.json"
    values = {
        "python": plan["python"],
        "protocol": str(safe_path(root, pending.get("protocol_path", "frozen/protocol"))),
        "candidate": str(workspace),
        "baseline": str(root / plan["baseline_path"]),
        "service_receipt": str(receipt),
        "effective_config": str(directory / "effective-config.json"),
        "attempt_dir": str(directory),
    }
    environment = runtime_environment()
    environment.update(
        INFERRSI_ATTEMPT_REQUEST=str(directory / "request.json"), PYTHONDONTWRITEBYTECODE="1"
    )
    environment["PYTHONPATH"] = str(workspace) + os.pathsep + environment["PYTHONPATH"]
    end = time.monotonic() + min(plan["evaluation_timeout_seconds"], max(0, deadline - time.time()))
    record = {
        "status": "running",
        "steps": [],
        "cleanup_verified": None,
        "binding": expected,
        "assessment": None,
        "cleanup_timeout_seconds": settings["sampling"]["stage_timeout_seconds"],
        "cleanup_budget_scope": "separate_from_evaluation",
    }
    output = directory / "execution"
    output.mkdir()
    started, process, owner = time.monotonic(), None, None

    def save():
        atomic_write_json(output / "execution.json", record)

    def command(argv):
        for key, val in values.items():
            argv = [arg.replace("{" + key + "}", val) for arg in argv]
        return argv

    def binding(document):
        if document.get("binding") != expected:
            raise ValueError("Service/revision/configuration binding mismatch")

    def stage(name, *, bound=True, argv=None):
        definition = {
            "id": name,
            "status": "running",
            "started_at": time.time(),
            "execution_status": "not_started",
        }
        record["steps"].append(definition)
        save()
        if bound and (process is None or process.poll() is not None):
            raise ValueError(f"Service unavailable before {name}")
        stage_end = time.monotonic() + settings["sampling"]["stage_timeout_seconds"]
        if name != "stop":
            stage_end = min(end, stage_end)
        executed = execute_trial(
            tuple(command(argv or settings["commands"][name.split("-")[0]])),
            workspace,
            output / name,
            stage_end,
            None,
            environment=environment,
        )
        definition.update(executed, execution_status=executed["status"], ended_at=time.time())
        save()
        if executed["status"] != "completed":
            raise ValueError(f"{name}: {executed['status']}: {executed.get('error', '')}")
        document = read(output / name / "result.json")
        if bound:
            binding(document)
            if process.poll() is not None:
                raise ValueError(f"Service exited during {name}")
        if document.get("status") == "candidate_failure" and name.startswith(
            ("precheck", "quality")
        ):
            return document
        if document.get("status") != "completed":
            raise ValueError(f"{name}: missing completed stage evidence")
        definition["result"] = document
        save()
        return document

    def skipped(names, reason):
        record["steps"].extend(
            {"id": name, "status": "skipped", "reason": reason} for name in names
        )
        save()

    measured, gate, score, profile, quality_ok = None, None, None, None, None
    try:
        # Rebuild from Git objects; retained directories can be replaced after acceptance.
        repository = pending.get("source_repo")
        if not repository:
            raise ValueError("Authoritative source repository is unavailable")
        retain_revision(repository, workspace, plan["candidate_includes"], pending["revision"])
        if not source.exists():
            retain(workspace, source, fingerprint=False)
        precheck = stage("precheck", bound=False)
        if precheck.get("status") == "candidate_failure" or precheck.get("passed") is False:
            skipped(("service", "measurement", "quality", "profile"), "precheck_rejected")
            record["assessment"] = assessment("FAIL", "functional_check_rejected")
            record["cleanup_verified"] = True
        elif precheck.get("passed") is not True:
            raise ValueError("Missing functional/numerical check evidence")
        else:
            service_step = {"id": "service", "status": "running", "started_at": time.time()}
            record["steps"].append(service_step)
            save()
            with supervised_service(
                [*plan["evaluation_prefix"], *command(settings["commands"]["service"])],
                workspace,
                environment,
                directory / "service",
                expected,
            ) as (process, owner):
                service_step.update(pid=process.pid, owner_path="service/owner.json")
                save()
                try:
                    ready = stage("ready")
                    if (
                        ready.get("ready") is not True
                        or ready.get("ownership") != "local_process_domain"
                        or ready.get("owner_pid") != process.pid
                        or ready.get("loaded_revision") != expected["revision"]
                        or ready.get("loaded_root") != str(workspace.resolve())
                    ):
                        raise ValueError("Service readiness/ownership unverified")
                    role = pending["role"]
                    for index in range(settings["sampling"][role]["warmups"]):
                        stage(f"warmup-{index + 1:03d}")
                    parent, initial = pending.get("parent"), pending.get("initial")
                    screen = settings.get("screening")
                    screened = True
                    if role == "candidate" and screen:
                        docs = [
                            stage(f"screening-{i + 1:03d}", argv=screen["command"])
                            for i in range(settings["sampling"][role]["repetitions"])
                        ]
                        preview = aggregate(settings, docs, role)
                        record["screening"] = performance(
                            settings,
                            preview,
                            parent["measurements"],
                            initial["measurements"],
                            screening=True,
                        )
                        record["screening"].update(
                            measurements=preview, estimated_gain=screen["estimated_gain"]
                        )
                        screened = record["screening"]["passed"]
                    if screened:
                        docs = [
                            stage(f"measure-{i + 1:03d}")
                            for i in range(settings["sampling"][role]["repetitions"])
                        ]
                        measured = aggregate(settings, docs, role)
                        gate = (
                            performance(
                                settings, measured, parent["measurements"], initial["measurements"]
                            )
                            if parent is not None
                            else {"passed": True, "metrics": {}}
                        )
                    if not screened or not gate["passed"]:
                        skipped(("quality", "profile"), "performance_gate_not_met")
                        record["assessment"] = assessment(
                            "FAIL", "performance_gate_not_met", performance=gate
                        )
                    elif pending.get("reference_kind") == "parent":
                        skipped(("quality", "profile"), "performance_reference_only")
                        record["assessment"] = assessment(
                            "PASS", "performance_reference_refreshed", performance=gate,
                            eligible=False,
                        )
                    else:
                        reference_path = settings["quality"].get("reference_path")
                        if role == "baseline" and reference_path:
                            reference_step = {
                                "id": "quality",
                                "status": "running",
                                "source": "retained_baseline_reference",
                                "path": reference_path,
                                "started_at": time.time(),
                            }
                            record["steps"].append(reference_step)
                            save()
                            quality = read(
                                safe_path(
                                    safe_path(
                                        root, pending.get("protocol_path", "frozen/protocol")
                                    ),
                                    reference_path,
                                )
                            )
                            if (
                                quality.get("revision") != pending["revision"]
                                or quality.get("conditions") != conditions
                                or not quality.get("service_id")
                                or not quality.get("run_id")
                            ):
                                raise ValueError(
                                    "quality: missing/stale/incompatible baseline reference"
                                )
                            quality_score(settings, quality)
                            reference_step.update(
                                status="completed", ended_at=time.time(), result=quality
                            )
                            save()
                        else:
                            quality = stage("quality")
                        if quality.get("status") == "candidate_failure":
                            quality_ok = False
                        else:
                            score = quality_score(settings, quality)
                            quality_ok = quality_passed(
                                settings,
                                score,
                                (initial.get("quality_score") if initial else score),
                            )
                        if not quality_ok:
                            skipped(("profile",), "quality_gate_not_met")
                            record["assessment"] = assessment(
                                "FAIL",
                                "quality_gate_not_met",
                                quality_passed=False,
                                performance=gate,
                            )
                        else:
                            if role == "candidate":
                                trace = stage("profile")
                                artifacts = trace.get("artifacts")
                                if not isinstance(artifacts, list) or not artifacts:
                                    raise ValueError("profile: missing artifacts")
                                for relative in artifacts:
                                    path = safe_path(directory, relative)
                                    if not path.is_file() or path.stat().st_size == 0:
                                        raise ValueError("profile: missing or empty artifact")
                                if trace.get("validated") is not True:
                                    raise ValueError("profile: project validation missing")
                                start, finish = (
                                    trace.get("capture_started_at"),
                                    trace.get("capture_ended_at"),
                                )
                                if (
                                    not number(start)
                                    or not number(finish)
                                    or not (
                                        record["steps"][-1]["started_at"]
                                        <= start
                                        <= finish
                                        <= record["steps"][-1]["ended_at"]
                                    )
                                ):
                                    raise ValueError(
                                        "profile: missing or incompatible capture interval"
                                    )
                                profile = {
                                    "attempt_id": pending["attempt_id"],
                                    "conditions": conditions,
                                    "binding": expected,
                                    "receipt": trace,
                                    "artifacts": [
                                        str((directory / item).relative_to(root))
                                        for item in artifacts
                                    ],
                                    "result": str(
                                        (output / "profile/result.json").relative_to(root)
                                    ),
                                }
                            else:
                                skipped(
                                    ("profile",),
                                    "not_required"
                                    if role == "baseline"
                                    else "reuse_selected_candidate_profile",
                                )
                            record["assessment"] = assessment(
                                "PASS",
                                "fixed_checks_satisfied",
                                quality_passed=True,
                                performance=gate,
                            )
                except BaseException:
                    record["failed_stage"] = record["steps"][-1]["id"]
                    raise
                finally:
                    try:
                        cleanup = stage("stop", bound=False)
                        binding(cleanup)
                        record["external_cleanup_verified"] = (
                            cleanup.get("cleanup_complete") is True
                        )
                    except (OSError, ValueError, KeyError) as error:
                        record["external_cleanup_verified"] = False
                        record["cleanup_error"] = str(error)
            record["cleanup_verified"] = (
                owner["domain_empty"] is True and record.get("external_cleanup_verified") is True
            )
            if not record["cleanup_verified"]:
                raise ValueError("Service cleanup is unverified")
    except (Exception, KeyboardInterrupt) as error:
        failed = record.get(
            "failed_stage", record["steps"][-1]["id"] if record["steps"] else "startup"
        )
        record["assessment"] = assessment(
            "INCONCLUSIVE",
            f"{failed}: {type(error).__name__}: {error}",
            performance=gate,
            quality_passed=quality_ok,
        )
        for definition in record["steps"]:
            if definition["id"] == failed:
                definition.setdefault("execution_status", definition["status"])
                if definition["status"] in ("running", "completed"):
                    definition["status"] = "failed"
                definition["reason"] = str(error)
        if owner is not None:
            record["cleanup_verified"] = (
                owner["domain_empty"] is True and record.get("external_cleanup_verified") is True
            )
        for name in ("quality", "profile"):
            if not any(step["id"] == name for step in record["steps"]):
                skipped((name,), "prerequisite_incomplete")
    if owner is not None:
        service_step.update(
            status="completed" if owner["domain_empty"] is True else "failed",
            ended_at=time.time(),
            returncode=owner["returncode"],
        )
    record.update(
        status="completed",
        measurements=measured,
        quality_score=score,
        profile=profile,
        elapsed_seconds=time.monotonic() - started,
    )
    save()
    return record
