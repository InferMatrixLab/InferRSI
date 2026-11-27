"""Freeze service protocol settings and the declared candidate Git files."""

import os
import re
import subprocess
import time
from pathlib import Path

from ...records import service_io
from ...records.atomic_json import atomic_write_json
from ..candidates import members, retain


def validate_service_conditions(conditions):
    if not isinstance(conditions, dict):
        raise ValueError("Explicit test conditions required")
    if not isinstance(conditions.get("id"), str) or not conditions["id"].strip():
        raise ValueError("Conditions require a nonempty string ID")
    for key in ("id", "workload", "model", "precision", "topology", "runtime", "timing_scope"):
        if not conditions.get(key):
            raise ValueError(f"conditions.{key} is required")
    if not isinstance(conditions.get("effective_config"), dict):
        raise ValueError("conditions.effective_config must be an object")
    service_io.no_fingerprints(conditions)


def validate_service_settings(settings, *, new_campaign=False):
    service_io.no_fingerprints(settings)
    for name in ("conditions", "commands", "sampling", "quality", "stagnation"):
        if not isinstance(settings.get(name), dict):
            raise ValueError(f"{name} must be an explicit object")
    if type(settings.get("schema_version")) is not int or settings["schema_version"] != 1:
        raise ValueError("Service evaluation schema_version must be 1")
    if not isinstance(settings.get("protocol_id"), str) or not settings["protocol_id"].strip():
        raise ValueError("Explicit protocol_id required")
    validate_service_conditions(settings.get("conditions"))
    commands = settings.get("commands", {})
    stages = ("precheck", "service", "ready", "warmup", "measure", "quality", "stop")
    if "profile" in commands:
        stages += ("profile",)
    for name in stages:
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
    if not service_io.positive_number(sampling.get("stage_timeout_seconds")):
        raise ValueError("Positive stage timeout required")
    if "profile_timeout_seconds" in sampling and not service_io.positive_number(
        sampling["profile_timeout_seconds"]
    ):
        raise ValueError("Positive profiling timeout required")
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
            not service_io.finite_number(domain.get("min"))
            or not service_io.finite_number(domain.get("max"))
            or (domain["min"] > domain["max"])
        ):
            raise ValueError("Finite ordered objective domain required")
        if obj["threshold_type"] == "percentage_point" and obj["unit"] != "%":
            raise ValueError("Percentage-point objectives use percent values and unit %")
        if obj["threshold_type"] == "relative_percent" and domain["min"] < 0:
            raise ValueError("Use absolute thresholds for negative-valued metrics")
        for key in ("gain_threshold", "parent_regression_limit", "cumulative_regression_limit"):
            if not service_io.finite_number(obj.get(key)) or obj[key] < 0:
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
    if new_campaign or "unit" in quality:
        from inferrsi.harness.evaluator import validate_quality_unit

        validate_quality_unit(quality.get("unit"))
    gate = "threshold" if quality["mode"] == "absolute" else "tolerance"
    if type(quality.get("samples")) is not int or quality["samples"] < 1:
        raise ValueError("Declare the required quality sample count")
    if not service_io.finite_number(quality.get(gate)) or (
        gate == "tolerance" and quality[gate] < 0
    ):
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
            or not service_io.positive_number(screen.get("estimated_gain"))
        ):
            raise ValueError("Screening command and positive estimated_gain required")
        if not any("{result}" in arg for arg in screen["command"]) or not any(
            "{protocol}" in arg for arg in screen["command"]
        ):
            raise ValueError("Screening must use retained protocol and result")


def service_revision(source, includes):
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
    # Deleted tracked files are absent from members but still belong to the inputs.
    if any(name not in tracked for name in selected) or git(
        "status", "--porcelain", "--untracked-files=no", "--", *(includes or ["."])
    ):
        raise ValueError("Commit declared candidate inputs before service-reuse evaluation")
    return commit


def retain_service_revision(source, destination, includes, commit, *, deadline=None):
    if not isinstance(commit, str) or not re.fullmatch(r"[a-f0-9]{40,64}", commit):
        raise ValueError("Candidate requires an existing Git commit")

    def git(*args):
        timeout = None if deadline is None else deadline - time.monotonic()
        if timeout is not None and timeout <= 0:
            raise TimeoutError("Profiling timeout while restoring the recorded revision")
        try:
            return subprocess.check_output(["git", "-C", str(source), *args], timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("Profiling timeout while restoring the recorded revision") from error

    entries = {}
    for name in includes or ["."]:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Candidate includes must be relative paths inside the project")
        listing = git(
            "ls-tree", "-rz", "--full-tree", "--format=%(objectmode) %(objecttype)%x09%(path)",
            commit, "--", relative.as_posix(),
        )
        if not listing:
            raise ValueError("Declared candidate files are missing from the retained commit")
        for entry in listing.rstrip(b"\0").split(b"\0"):
            metadata, path = entry.split(b"\t", 1)
            mode, kind = metadata.split()
            if kind != b"blob" or mode not in (b"100644", b"100755"):
                raise ValueError("Candidate tree contains symbolic or special files")
            entries[os.fsdecode(path)] = int(mode, 8) & 0o555
    destination.mkdir()
    for name, mode in entries.items():
        target = service_io.safe_path(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Read raw tree content; archive export attributes can omit or rewrite inputs.
        target.write_bytes(git("cat-file", "blob", f"{commit}:{name}"))
        target.chmod(mode)


def prepare_service(root, args):
    from inferrsi import __version__

    settings = service_io.read(args.evaluation_config)
    validate_service_settings(settings, new_campaign=True)
    source, protocol = args.repo.resolve(), args.protocol.resolve()
    if args.repo.is_symlink() or args.protocol.is_symlink():
        raise ValueError("Project and protocol roots cannot be symbolic")
    if root.exists() or root.is_relative_to(source) or root.is_relative_to(protocol):
        raise ValueError("Use a new campaign directory outside project/protocol")
    from ._stage_plan import stages

    transitions = stages(settings, protocol, args.rounds)
    commit = service_revision(source, args.include)
    members(protocol)
    if not args.instructions.is_file() or args.instructions.is_symlink():
        raise ValueError("Regular task instructions required")
    (root / "frozen").mkdir(parents=True)
    retain_service_revision(source, root / "frozen/baseline", args.include, commit)
    if service_revision(source, args.include) != commit:
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
        **({"stage_transitions": transitions} if transitions else {}),
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
