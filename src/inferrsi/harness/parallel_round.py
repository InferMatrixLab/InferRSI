"""Prepare, submit, measure and jointly close one offline parallel round.

Directory diffs stand in for git clones. A synthetic metric value is not a
campaign verdict.

Each lane declares ``device_count`` (default 1). The counts of all lanes must fit
in ``device_ids``. A ticket runs only after it holds that many devices at once.

Command placeholders: ``build`` and ``validation`` get ``{device}`` only. ``trial``
gets ``{device}`` and ``{result}``; it must write
``{"metrics": {<metric.name>: <finite positive number>}}`` to ``{result}``. The
candidate is built once in confinement; measurement is ``run_experiment`` with a
confined ``execute``, so incumbent and candidate trials alternate AB/BA
``metric.repeats`` times each, and the optional ``validation`` runs once on the
candidate. The composing application supplies ``make_assess`` so Harness never
imports Benchmark; that assess gives the verdict against ``metric.min_improvement_pct``.
``{device}`` is the held device identities joined with commas. Other text,
including ``{result}`` inside ``build``, is passed through unchanged.

With ``device_model`` set, ``qualify_devices`` checks the held devices before an
attempt is reserved; a device that fails the check leaves the ticket queued.

``device_paths`` (per device id), ``shared_device_paths``, ``runtime_paths`` and
``env`` (values may use ``{device}``) extend the confined view for GPU trials.
Each command is capped by ``command_timeout_seconds`` and the lane deadline.
If a timed-out command cannot be confirmed dead, its devices are quarantined:
``leases/<device>.quarantined`` is written before the lease is released, and
the device is refused until an operator removes that file.

``close`` is a joint single-rerun MVP (not #249 stepwise composition): after every
outbox ticket has a terminal receipt, each lane keeps one PASS winner (higher
``improvement_pct``, then lower ``ticket``). ``close`` copies that verified
incumbent to ``candidates/frozen-incumbent`` and overlays the winners onto that
snapshot. The joint build and trials run in that tree. A PASS run promotes
that measured tree, including regular files the build wrote into it.
Promotion copies only the files the snapshot verified, and only when that
snapshot still matches the candidate fingerprint stored for the evaluation.
Repository metadata is omitted, and a symlink is refused instead of followed.
Any other
completed verdict retains the incumbent and writes
``knowledge/joint-failure.json``. A build that started and exited non-zero
closes the round as retained and keeps the exit code. A joint confinement
failure, or a measurement that does not finish, returns ``refused`` and does
not write ``close.json``. File identity includes the executable bits, and an
overlay keeps them. Other PASS tickets on the same
lane are listed in ``close.json`` as ``dropped`` and are not overlaid.
``prepare`` freezes ``incumbent_tree_digest``; ``submit``, ``serve`` and
``close`` refuse a different tree. ``submit`` also refuses while ``close``
holds the round lock or after ``close.json`` exists. This is not Claude/Codex
drivers, SwarmFlow, or campaign incumbent advancement.
"""

import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import time
from collections.abc import Callable
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

from inferrsi.contracts import RunSpec
from inferrsi.harness.artifact_primitives import digest
from inferrsi.harness.confinement import (
    ConfinementUnavailable,
    UnreapedCommand,
    confined_execute,
)
from inferrsi.harness.device_lease import DeviceLease, LeaseError
from inferrsi.harness.round_budget import (
    Binding,
    BudgetError,
    Entry,
    Genesis,
    LaneKey,
    Ledger,
    admit_attempt,
    advance,
    empty_ledger,
    ensure_open,
    seconds_remaining,
)
from inferrsi.harness.runner import run_experiment as run_experiment_loop

_TERMINAL = frozenset({"measured", "rejected", "unsettled", "failed"})


def write_json(path, value) -> None:
    """Same bytes as ``infra.artifacts.write_json``. Harness does not import that module."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def read_metric(result: dict, key: str) -> float:
    """Same contract as ``model.protocols.metrics.read_metric``, without importing Model."""
    value = result
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"missing metric: {key}")
        value = value[part]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"metric {key} must be a number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"metric {key} must be finite and positive")
    return float(value)

PLANES = {"harness", "model", "infra"}
DIRECTIONS = {"lower", "higher"}


class RoundPlanError(ValueError):
    """The frozen round plan is internally inconsistent."""


class CommandFailed(Exception):
    """A confined command started and exited non-zero."""

    def __init__(self, stage: str, returncode: int | None):
        self.stage = stage
        self.returncode = returncode
        super().__init__(f"{stage} exited {returncode}")


def _segment(value) -> bool:
    return (
        isinstance(value, str)
        and value not in {"", ".", ".."}
        and not any(char in value for char in "/\\")
    )


def _host_paths(value) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str)
        and Path(item).is_absolute()
        and item != "/"
        and ".." not in Path(item).parts
        for item in value
    )


def _match(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def _snapshot(root: Path) -> tuple[dict[str, str], list[str]]:
    """Hash regular files and their executable bits. Symlinks are reported, not read."""
    hashes: dict[str, str] = {}
    blocked: list[str] = []
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        _scan(root_fd, "", hashes, blocked)
    finally:
        os.close(root_fd)
    return hashes, blocked


def _open_regular(name: str, dirfd: int) -> int | None:
    """Open without following a link or blocking on a FIFO; refuse anything not regular."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dirfd)
    except OSError:
        return None
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        return None
    return fd


def _scan(dirfd: int, prefix: str, hashes: dict[str, str], blocked: list[str]) -> None:
    for name in os.listdir(dirfd):
        if name in {".", "..", ".git"}:
            continue
        relative = f"{prefix}/{name}" if prefix else name
        try:
            info = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
        except OSError:
            blocked.append(relative)
            continue
        if stat.S_ISLNK(info.st_mode):
            blocked.append(relative)
            continue
        if stat.S_ISDIR(info.st_mode):
            try:
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dirfd)
            except OSError:
                blocked.append(relative)
                continue
            try:
                _scan(child, relative, hashes, blocked)
            finally:
                os.close(child)
            continue
        if not stat.S_ISREG(info.st_mode):
            blocked.append(relative)
            continue
        file_fd = _open_regular(name, dirfd)
        if file_fd is None:
            blocked.append(relative)
            continue
        try:
            hashes[relative] = _digest_fd(file_fd)
        finally:
            os.close(file_fd)


_CHUNK = 1024 * 1024


def _digest_fd(file_fd: int) -> str:
    """Stream one open file. Only the digest is kept."""
    executable = stat.S_IMODE(os.fstat(file_fd).st_mode) & 0o111
    hasher = hashlib.sha256()
    hasher.update(bytes([executable]))
    while True:
        block = os.read(file_fd, _CHUNK)
        if not block:
            break
        hasher.update(block)
    return hasher.hexdigest()


def _stream_copy(root: Path, relative: str, target: Path) -> str | None:
    """Copy one regular file in chunks. The digest matches ``_snapshot``."""
    dirfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = relative.split("/")
        for part in parts[:-1]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dirfd)
            except OSError:
                return None
            os.close(dirfd)
            dirfd = child
        file_fd = _open_regular(parts[-1], dirfd)
        if file_fd is None:
            return None
    finally:
        os.close(dirfd)
    try:
        out = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            executable = stat.S_IMODE(os.fstat(file_fd).st_mode) & 0o111
            hasher = hashlib.sha256()
            hasher.update(bytes([executable]))
            while True:
                block = os.read(file_fd, _CHUNK)
                if not block:
                    break
                hasher.update(block)
                view = memoryview(block)
                while view:
                    view = view[os.write(out, view) :]
        finally:
            os.close(out)
    finally:
        os.close(file_fd)
    if executable:
        os.chmod(target, stat.S_IMODE(target.stat().st_mode) | executable)
    return hasher.hexdigest()


def _digest_at(root: Path, relative: str) -> str | None:
    """Digest one regular file without following links, or return None."""
    dirfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = relative.split("/")
        for part in parts[:-1]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dirfd)
            except OSError:
                return None
            os.close(dirfd)
            dirfd = child
        file_fd = _open_regular(parts[-1], dirfd)
        if file_fd is None:
            return None
    finally:
        os.close(dirfd)
    try:
        return _digest_fd(file_fd)
    finally:
        os.close(file_fd)


def _read_nofollow(root: Path, relative: str) -> bytes | None:
    """Read one regular file through no-follow parent components, or return None."""
    dirfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = relative.split("/")
        for part in parts[:-1]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dirfd)
            except OSError:
                return None
            os.close(dirfd)
            dirfd = child
        file_fd = _open_regular(parts[-1], dirfd)
        if file_fd is None:
            return None
    finally:
        os.close(dirfd)
    try:
        chunks = []
        while True:
            block = os.read(file_fd, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        return b"".join(chunks)
    finally:
        os.close(file_fd)


def _refusal(reason: str, **fields) -> dict:
    body = {"submitted": False, "outside": [], "deleted": [], "rejected": [], "ticket": None}
    body.update(fields)
    body["reason"] = reason
    return body


def _tree_digest(root: Path) -> str:
    """Digest regular-file bytes and executable bits. Symlinks and unreadable paths are refused."""
    hashes, blocked = _snapshot(root)
    if blocked:
        raise RoundPlanError(f"incumbent has unreadable paths: {sorted(blocked)}")
    return digest({"files": hashes})


def _incumbent_mismatch(plan: dict, incumbent: Path) -> str | None:
    try:
        actual = _tree_digest(incumbent)
    except RoundPlanError as exc:
        return str(exc)
    if actual != plan.get("incumbent_tree_digest"):
        return "incumbent tree does not match the frozen digest"
    return None


def _promote_snapshot(source: Path, destination: Path, expected_hash: str) -> None:
    """Copy the verified files only when they still match the measured fingerprint."""
    hashes, blocked = _snapshot(source)
    if blocked:
        raise ValueError(f"unreadable paths: {sorted(blocked)}")
    if digest({"files": hashes}) != expected_hash:
        if destination.exists():
            shutil.rmtree(destination)
        raise ValueError("promoted tree does not match the measured snapshot")
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    try:
        for relative, expected in hashes.items():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if _stream_copy(source, relative, target) != expected:
                raise ValueError(f"snapshot changed during promotion: {relative}")
    except (OSError, ValueError):
        shutil.rmtree(destination)
        raise


def _freeze_incumbent(round_dir: Path, incumbent: Path) -> Path:
    """Copy the incumbent that just matched the digest. Close reads this tree."""
    frozen = round_dir / "candidates" / "frozen-incumbent"
    if frozen.exists():
        shutil.rmtree(frozen)
    frozen.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(incumbent, frozen, ignore=shutil.ignore_patterns(".git"))
    return frozen


def _acquire_close(round_dir: Path):
    try:
        return DeviceLease(round_dir / "round-locks").acquire("close")
    except LeaseError:
        return None


def _lane(plan: dict, lane_id: str) -> dict:
    matches = [lane for lane in plan["lanes"] if lane["id"] == lane_id]
    if len(matches) != 1:
        raise RoundPlanError(f"unknown lane: {lane_id}")
    return matches[0]


def prepare(spec: dict, incumbent: Path, round_dir: Path) -> dict:
    """Validate lane scopes and write ``round-plan.json``. The digest covers the validated body."""
    if not isinstance(spec, dict):
        raise RoundPlanError("round spec must be an object")
    lanes = spec.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        raise RoundPlanError("round spec needs at least one lane")
    protected = spec.get("protected", [])
    if not isinstance(protected, list):
        raise RoundPlanError("protected paths must be a list of globs")
    devices = spec.get("device_ids")
    if (
        not isinstance(devices, list)
        or not devices
        or not all(_segment(item) and "," not in item for item in devices)
        or len(set(devices)) != len(devices)
    ):
        raise RoundPlanError("device_ids must list distinct device identities")
    metric = spec.get("metric")
    if (
        not isinstance(metric, dict)
        or not {"name", "better"}
        <= set(metric)
        <= {"name", "better", "repeats", "min_improvement_pct"}
        or not isinstance(metric["name"], str)
        or not metric["name"]
        or not isinstance(metric["better"], str)
        or metric["better"] not in DIRECTIONS
    ):
        raise RoundPlanError("metric needs a name and better: lower or higher")
    repeats = metric.get("repeats", 1)
    if type(repeats) is not int or repeats < 1:
        raise RoundPlanError("metric repeats must be a positive integer")
    threshold = metric.get("min_improvement_pct", 0)
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or threshold < 0:
        raise RoundPlanError("metric min_improvement_pct must be a finite non-negative number")
    validation = spec.get("validation")
    if validation is not None and (
        not isinstance(validation, list)
        or not validation
        or any(type(item) is not str for item in validation)
    ):
        raise RoundPlanError("validation must be a non-empty argv list")
    device_model = spec.get("device_model")
    if device_model is not None and (type(device_model) is not str or not device_model):
        raise RoundPlanError("device_model must be a non-empty string")
    timeout = spec.get("command_timeout_seconds", 30)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise RoundPlanError("command_timeout_seconds must be a positive number")
    device_paths = spec.get("device_paths", {})
    if not isinstance(device_paths, dict) or not all(
        _host_paths(paths) for paths in device_paths.values()
    ):
        raise RoundPlanError("device_paths must map device ids to absolute host paths")
    if device_paths and set(device_paths) != set(devices):
        raise RoundPlanError("device_paths must list every device id and nothing else")
    shared_paths = spec.get("shared_device_paths", [])
    runtime_paths = spec.get("runtime_paths", [])
    if not _host_paths(shared_paths) or not _host_paths(runtime_paths):
        raise RoundPlanError("shared_device_paths and runtime_paths must be absolute host paths")
    env = spec.get("env", {})
    if not isinstance(env, dict) or not all(
        isinstance(key, str) and key and isinstance(value, str) for key, value in env.items()
    ):
        raise RoundPlanError("env must map names to strings")
    seen_entries: set[str] = set()
    seen_ids: set[str] = set()
    hashes, blocked = _snapshot(incumbent)
    if blocked:
        raise RoundPlanError(f"incumbent has unreadable paths: {sorted(blocked)}")
    incumbent_tree_digest = digest({"files": hashes})
    files = sorted(hashes)
    normalized = []
    for lane in lanes:
        lane_id = lane.get("id")
        entry = lane.get("entry")
        plane = lane.get("plane")
        globs = lane.get("globs")
        if not _segment(lane_id) or lane_id in seen_ids:
            raise RoundPlanError("each lane needs its own id")
        if not isinstance(entry, str) or not entry:
            raise RoundPlanError("each lane needs one search-plan entry")
        if entry in seen_entries:
            raise RoundPlanError(f"two lanes pursue {entry}")
        if type(plane) is not str or plane not in PLANES:
            raise RoundPlanError("a lane must name exactly one plane")
        if not isinstance(globs, list) or not globs or any(type(item) is not str for item in globs):
            raise RoundPlanError("a lane needs path globs")
        if type(lane.get("cap")) is not int or type(lane.get("per_attempt_worst_case")) is not int:
            raise RoundPlanError("cap and per-attempt cost must come from the plan")
        if not isinstance(lane.get("deadline_utc"), str):
            raise RoundPlanError("each lane needs a deadline")
        count = lane.get("device_count", 1)
        if type(count) is not int or count < 1:
            raise RoundPlanError(f"{lane_id} device_count must be a positive integer")
        if any(_match(path, globs) and _match(path, protected) for path in files):
            raise RoundPlanError(f"{lane_id} reaches a protected path")
        seen_ids.add(lane_id)
        seen_entries.add(entry)
        normalized.append({**lane, "device_count": count})
    demand = sum(lane["device_count"] for lane in normalized)
    if demand > len(devices):
        raise RoundPlanError(
            f"lanes ask for {demand} devices in total but device_ids lists {len(devices)}"
        )
    for index, lane in enumerate(normalized):
        for other in normalized[index + 1 :]:
            shared = set(lane["globs"]) & set(other["globs"])
            shared.update(
                path
                for path in files
                if _match(path, lane["globs"]) and _match(path, other["globs"])
            )
            if shared:
                raise RoundPlanError(f"{lane['id']} overlaps {other['id']}")
    body = {
        "round_id": spec["round_id"],
        "device_ids": list(devices),
        "metric": {
            "name": metric["name"],
            "better": metric["better"],
            "repeats": repeats,
            "min_improvement_pct": threshold,
        },
        "command_timeout_seconds": timeout,
        "device_paths": {device: list(device_paths[device]) for device in device_paths},
        "shared_device_paths": list(shared_paths),
        "runtime_paths": list(runtime_paths),
        "env": dict(env),
        "incumbent_id": spec["incumbent_id"],
        "incumbent_tree_digest": incumbent_tree_digest,
        "protected": protected,
        "build": list(spec.get("build", [])),
        "trial": list(spec.get("trial", [])),
        "validation": list(validation) if validation is not None else None,
        "device_model": device_model,
        "lanes": normalized,
    }
    body["round_digest"] = digest(body)
    round_dir.mkdir(parents=True, exist_ok=True)
    write_json(round_dir / "round-plan.json", body)
    return body


def submit(
    round_dir: Path, lane_id: str, incumbent: Path, work: Path, *, now: datetime | None = None
) -> dict:
    """Copy in-glob changes to the outbox. The same manifest always returns the same ticket.

    The payload directory and the metadata file beside it are one publication.
    A directory without matching metadata is not a ticket: it is removed and
    written again. A metadata write that fails removes both and reports refusal.
    """
    if (round_dir / "close.json").exists():
        return _refusal("round closed")
    lock = _acquire_close(round_dir)
    if lock is None:
        return _refusal("round closing")
    try:
        if (round_dir / "close.json").exists():
            return _refusal("round closed")
        return _submit_holding_lock(round_dir, lane_id, incumbent, work, now=now)
    finally:
        lock.release()


def _submit_holding_lock(
    round_dir: Path, lane_id: str, incumbent: Path, work: Path, *, now: datetime | None = None
) -> dict:
    moment = now or datetime.now(timezone.utc)
    plan = json.loads((round_dir / "round-plan.json").read_text(encoding="utf-8"))
    mismatch = _incumbent_mismatch(plan, incumbent)
    if mismatch:
        return _refusal(mismatch)
    lane = _lane(plan, lane_id)
    try:
        ensure_open(lane["deadline_utc"], moment)
    except BudgetError as exc:
        return _refusal(str(exc))
    before, _incumbent_blocked = _snapshot(incumbent)
    after, blocked = _snapshot(work)
    changed = sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )
    known = set(before) | set(after) | set(changed)
    linked = [
        path
        for path in blocked
        if any(item == path or item.startswith(path + "/") for item in known)
    ]
    if linked:
        return _refusal("symlink", rejected=sorted(linked))
    deleted = [path for path in changed if path not in after and _match(path, lane["globs"])]
    if deleted:
        return _refusal("deletion", deleted=deleted)
    outside = [path for path in changed if not _match(path, lane["globs"])]
    if outside or not changed:
        return _refusal("unchanged" if not changed else "outside", outside=outside)
    # Concrete paths, including newly created files: prepare only saw the incumbent.
    protected_hits = [path for path in changed if _match(path, plan.get("protected") or [])]
    if protected_hits:
        return _refusal("protected", rejected=protected_hits)
    others = [other for other in plan["lanes"] if other["id"] != lane_id]
    shared = [
        path
        for path in changed
        if any(_match(path, other["globs"]) for other in others)
    ]
    if shared:
        return _refusal("overlap", rejected=shared)
    manifest = {path: after[path] for path in changed}
    ticket = digest(
        {"round_digest": plan["round_digest"], "lane_id": lane_id, "manifest": manifest}
    )[:16]
    staging = round_dir / "submit-staging" / ticket
    if staging.exists():
        shutil.rmtree(staging)
    try:
        for path in changed:
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            copied = _stream_copy(work, path, target)
            if copied != after[path]:
                return _refusal("changed during submit", rejected=[path])
        destination = round_dir / "outbox" / ticket
        metadata = _ticket_metadata_path(destination)
        record = {"ticket": ticket, "lane_id": lane_id, "files": manifest, "deleted": []}
        if not _ticket_is_published(destination, metadata, record):
            _discard_unpublished_ticket(destination, metadata)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(staging, destination)
            try:
                write_json(metadata, record)
            except OSError:
                _discard_unpublished_ticket(destination, metadata)
                raise
    except OSError:
        return _refusal("symlink", rejected=list(changed))
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if staging.parent.exists() and not any(staging.parent.iterdir()):
            staging.parent.rmdir()
    return {"submitted": True, "outside": [], "deleted": [], "rejected": [], "ticket": ticket}


def _ticket_metadata_path(overlay: Path) -> Path:
    """Coordinator record beside the payload directory.

    The record must not live inside the overlay: a project file named
    ``manifest.json`` (root or nested) is a legitimate payload.
    """
    return overlay.parent / f"{overlay.name}.json"


def _ticket_is_published(destination: Path, metadata: Path, record: dict) -> bool:
    """True only when the metadata and every payload file match this manifest."""
    if not destination.is_dir() or destination.is_symlink() or not metadata.is_file():
        return False
    try:
        stored = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if stored != record:
        return False
    files = stored.get("files")
    if not isinstance(files, dict):
        return False
    return all(
        _digest_at(destination, relative) == expected for relative, expected in files.items()
    )


def _discard_unpublished_ticket(destination: Path, metadata: Path) -> None:
    """Remove a payload directory and metadata file that are not a finished ticket."""
    if destination.is_dir() and not destination.is_symlink():
        shutil.rmtree(destination)
    elif destination.exists() or destination.is_symlink():
        destination.unlink()
    if metadata.is_file() or metadata.is_symlink():
        metadata.unlink()


def _ledger_path(round_dir: Path, lane_id: str) -> Path:
    return round_dir / "ledgers" / f"{lane_id}.json"


def _load_ledger(round_dir: Path, plan: dict, lane: dict):
    path = _ledger_path(round_dir, lane["id"])
    if not path.exists():
        return empty_ledger(plan["round_digest"], lane["id"], lane["cap"])
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = tuple(
        Entry(
            Binding(item["plan_digest"], item["run_id"], item["worst_case"]),
            item["phase"],
            item["actual_cost"],
        )
        for item in raw["entries"]
    )
    return Ledger(
        LaneKey(raw["round_digest"], raw["lane_id"]),
        Genesis(raw["evidence"], raw["legacy_charge"]),
        raw["cap"],
        raw["revision"],
        entries,
    )


def _save_ledger(round_dir: Path, ledger) -> None:
    write_json(
        _ledger_path(round_dir, ledger.key.lane_id),
        {
            "round_digest": ledger.key.round_digest,
            "lane_id": ledger.key.lane_id,
            "evidence": ledger.genesis.evidence,
            "legacy_charge": ledger.genesis.legacy_charge,
            "cap": ledger.cap,
            "revision": ledger.revision,
            "entries": [
                {
                    "plan_digest": entry.binding.plan_digest,
                    "run_id": entry.binding.run_id,
                    "worst_case": entry.binding.worst_case,
                    "phase": entry.phase,
                    "actual_cost": entry.actual_cost,
                }
                for entry in ledger.entries
            ],
        },
    )


def materialize(incumbent: Path, overlays: list[Path], destination: Path) -> None:
    """Copy the incumbent, then apply each overlay whose bytes match its manifest.

    A missing or modified payload raises ``ValueError`` and leaves no destination.
    Links are not followed.
    """
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(incumbent, destination)
    try:
        for overlay in overlays:
            manifest = json.loads(_ticket_metadata_path(overlay).read_text(encoding="utf-8"))
            for relative, expected in manifest["files"].items():
                if _digest_at(overlay, relative) != expected:
                    raise ValueError(f"payload does not match the ticket manifest: {relative}")
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if _stream_copy(overlay, relative, target) != expected:
                    raise ValueError(f"payload does not match the ticket manifest: {relative}")
    except (OSError, ValueError, KeyError, TypeError):
        shutil.rmtree(destination)
        raise


def _command(template: list[str], result: Path | None, device: str) -> tuple[str, ...]:
    parts = (part.replace("{device}", device) for part in template)
    if result is None:
        return tuple(parts)
    return tuple(part.replace("{result}", str(result)) for part in parts)


def _record(round_dir: Path, ticket: str, **fields) -> dict:
    body = {"ticket": ticket, "synthetic": True, **fields}
    write_json(round_dir / "results" / f"{ticket}.json", body)
    return body


def _ticket_entry(ledger, ticket: str):
    suffix = f"@{ticket}"
    for entry in ledger.entries:
        if entry.binding.run_id.endswith(suffix):
            return entry
    return None


def _device_view(plan: dict, devices: list[str]) -> dict:
    """Confined-view extras for the held devices: their nodes, the runtime and the env."""
    device = ",".join(devices)
    nodes = list(plan["shared_device_paths"])
    for held in devices:
        nodes.extend(plan["device_paths"].get(held, []))
    return {
        "device_paths": tuple(Path(path) for path in nodes),
        "runtime_paths": tuple(Path(path) for path in plan["runtime_paths"]),
        "env": {key: value.replace("{device}", device) for key, value in plan["env"].items()},
    }


def _tree_identity(root: Path, exclude: Path | None = None) -> dict:
    """Fingerprint a tree by hashing regular files. Never invokes host ``git``.

    Build runs as a writable candidate and may rewrite ``.git``; calling
    ``repository_identity`` afterward would execute planted ``diff.external`` /
    ``core.fsmonitor`` hooks outside confinement. This digest stays inert.
    """
    root = Path(root).resolve()
    identity: dict = {"path": str(root), "available": False, "tool": "directory"}
    try:
        hashes, blocked = _snapshot(root)
        if blocked:
            raise ValueError(f"unreadable paths: {sorted(blocked)}")
        if exclude is not None:
            excluded = Path(exclude).resolve()
            hashes = {
                path: digest_value
                for path, digest_value in hashes.items()
                if not (root / path).resolve().is_relative_to(excluded)
            }
        snapshot_hash = digest({"files": hashes})
        identity.update(
            available=True,
            snapshot_hash=snapshot_hash,
            dirty=False,
            files=len(hashes),
        )
    except (OSError, ValueError) as exc:
        identity["error"] = str(exc)
    return identity


def _run_confined(
    plan: dict,
    stage: str,
    argv: tuple[str, ...],
    cwd: Path,
    writable: tuple[Path, ...],
    readable: tuple[Path, ...],
    devices: list[str],
    deadline_utc: str | None,
    *,
    backend,
    current,
) -> None:
    remaining = plan["command_timeout_seconds"]
    if deadline_utc is not None:
        remaining = min(seconds_remaining(deadline_utc, current()), remaining)
    try:
        record = confined_execute(
            argv,
            cwd,
            writable,
            readable,
            time.monotonic() + remaining,
            backend=backend,
            **_device_view(plan, devices),
        )
    except subprocess.TimeoutExpired as exc:
        raise ConfinementUnavailable(f"{stage} timed out") from exc
    status = record.get("status")
    if status == "failed":
        raise CommandFailed(stage, record.get("returncode"))
    if status != "completed":
        raise ConfinementUnavailable(f"{stage} {status}")


def _confined_trial(
    plan: dict, devices: list[str], deadline_utc: str, *, backend, current, failures: list[str]
):
    """``execute`` for ``run_experiment``: one command in confinement, never past the lane deadline.

    The trial directory is the only writable path and the repository is read-only.
    An unreaped command propagates so the caller can quarantine its devices.
    """
    view = _device_view(plan, devices)

    def execute(command, cwd, trial_dir, deadline, metric_key):
        trial_dir.mkdir(parents=True)
        result = trial_dir / "result.json"
        argv = tuple(part.replace("{result}", str(result)) for part in command)
        record = {
            "status": "pending",
            "argv": list(argv),
            "cwd": str(cwd),
            "returncode": None,
            "result_path": str(result),
            "metric": None,
            "metric_error": None,
        }
        try:
            remaining = min(
                deadline - time.monotonic(),
                plan["command_timeout_seconds"],
                seconds_remaining(deadline_utc, current()),
            )
            if remaining <= 0:
                raise BudgetError("run deadline passed")
            outcome = confined_execute(
                argv,
                cwd,
                (trial_dir,),
                (cwd,),
                time.monotonic() + remaining,
                backend=backend,
                **view,
            )
            record.update(status=outcome.get("status"), returncode=outcome.get("returncode"))
            for stream in ("stdout", "stderr"):
                (trial_dir / f"{stream}.log").write_text(
                    outcome.get(stream) or "", encoding="utf-8"
                )
        except UnreapedCommand:
            raise
        except BudgetError as exc:
            record.update(status="timeout", error=str(exc))
        except subprocess.TimeoutExpired:
            record.update(status="timeout", error="command timed out")
        except ConfinementUnavailable as exc:
            # Infrastructure refusal is not a quality-gate failure: evaluate maps
            # status "failed" to FAIL, while "error" stays incomplete / INCONCLUSIVE.
            status = "timeout" if "timed out" in str(exc) else "error"
            record.update(status=status, error=str(exc))
        if record["status"] == "completed" and metric_key is not None:
            try:
                document = json.loads(result.read_text(encoding="utf-8"))
                record["metric"] = read_metric(document, metric_key)
            except (OSError, ValueError, TypeError) as exc:
                record["metric_error"] = str(exc)
        if record.get("error") or record["metric_error"]:
            failures.append(record.get("error") or record["metric_error"])
        write_json(trial_dir / "execution.json", record)
        return record

    return execute


def _run_spec(
    plan: dict,
    candidate: Path,
    incumbent: Path,
    devices: list[str],
    output_dir: Path,
    seconds_left: float,
) -> RunSpec:
    device = ",".join(devices)
    trial = _command(plan["trial"], None, device)
    validation = plan.get("validation")
    return RunSpec(
        repo=str(incumbent),
        candidate_repo=str(candidate),
        baseline_command=trial,
        candidate_command=trial,
        validation_command=_command(validation, None, device) if validation else None,
        metric_key=f"metrics.{plan['metric']['name']}",
        metric_unit="metric",
        direction="minimize" if plan["metric"]["better"] == "lower" else "maximize",
        repetitions=plan["metric"]["repeats"],
        min_improvement_pct=plan["metric"].get("min_improvement_pct", 0),
        max_minutes=min(seconds_left, 7 * 24 * 3600) / 60,
        device_ids=tuple(devices),
        output_dir=str(output_dir),
    )


def _run_experiment(
    spec: RunSpec,
    environment: dict,
    *,
    execute,
    snapshot,
    make_assess: Callable[[RunSpec], Callable],
) -> Path:
    """Run the harness loop with an application-supplied assess port; report is a no-op."""
    return run_experiment_loop(
        spec,
        environment,
        execute=execute,
        snapshot=snapshot,
        assess=make_assess(spec),
        report=lambda _run_dir: None,
    )


def _qualify(device_model: str, devices: list[str], qualify_devices) -> None:
    """``qualify_devices`` reads the caller's reservation from ``CUDA_VISIBLE_DEVICES``."""
    previous = os.environ.get("CUDA_VISIBLE_DEVICES")
    os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(devices)
    try:
        qualify_devices(count=len(devices), device_model=device_model)
    finally:
        if previous is None:
            os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        else:
            os.environ["CUDA_VISIBLE_DEVICES"] = previous


def hold_devices(round_dir: Path, plan: dict, count: int) -> list[tuple[str, object]] | None:
    """Hold ``count`` free devices at once, or none. The caller releases what it gets."""
    leases = DeviceLease(round_dir / "leases")
    held: list[tuple[str, object]] = []
    for device in plan["device_ids"]:
        if len(held) == count:
            break
        try:
            held.append((device, leases.acquire(device)))
        except LeaseError:
            continue
    if len(held) < count:
        for _device, lease in held:
            lease.release()
        return None
    return held


def serve_ticket(
    round_dir: Path,
    ticket: str,
    incumbent: Path,
    *,
    backend,
    make_assess: Callable[[RunSpec], Callable],
    qualify_devices,
    now: datetime | None = None,
    clock=None,
) -> dict:
    """Measure one ticket on the lane's ``device_count`` free devices. A busy lane or too
    few free devices leaves it queued and does not reserve an attempt.

    ``make_assess`` binds Benchmark (or other) gates for one ``RunSpec``; Harness
    only calls the returned assess port. ``now`` is accepted for older callers and
    is not a frozen deadline. Every admission and command reads ``clock`` or the
    current time again.
    """
    del now

    def current() -> datetime:
        if clock is not None:
            return clock()
        return datetime.now(timezone.utc)

    plan = json.loads((round_dir / "round-plan.json").read_text(encoding="utf-8"))
    result_path = round_dir / "results" / f"{ticket}.json"
    if result_path.exists():
        return json.loads(result_path.read_text(encoding="utf-8"))
    mismatch = _incumbent_mismatch(plan, incumbent)
    if mismatch:
        return {"ticket": ticket, "status": "rejected", "reason": mismatch}
    overlay = round_dir / "outbox" / ticket
    manifest = json.loads(_ticket_metadata_path(overlay).read_text(encoding="utf-8"))
    if manifest.get("deleted"):
        return _record(round_dir, ticket, status="rejected", reason="deletion")
    lane = _lane(plan, manifest["lane_id"])
    try:
        lane_lock = DeviceLease(round_dir / "lane-locks").acquire(lane["id"])
    except LeaseError:
        return {"ticket": ticket, "status": "queued"}
    try:
        if result_path.exists():
            return json.loads(result_path.read_text(encoding="utf-8"))
        entry = _ticket_entry(_load_ledger(round_dir, plan, lane), ticket)
        if entry is not None and entry.phase == "cancelled":
            return _record(
                round_dir, ticket, status="rejected", reason="attempt was cancelled at the deadline"
            )
        if entry is not None and entry.phase != "reserved":
            return _record(
                round_dir,
                ticket,
                status="unsettled",
                reason=f"{entry.phase} execution was not settled",
            )
        try:
            ensure_open(lane["deadline_utc"], current())
        except BudgetError as exc:
            if entry is not None:
                _save_ledger(
                    round_dir,
                    advance(_load_ledger(round_dir, plan, lane), entry.binding, "cancelled"),
                )
            return _record(round_dir, ticket, status="rejected", reason=str(exc))
        held = hold_devices(round_dir, plan, lane["device_count"])
        if held is None:
            return {"ticket": ticket, "status": "queued"}
        try:
            if plan.get("device_model"):
                try:
                    _qualify(
                        plan["device_model"],
                        [device for device, _lease in held],
                        qualify_devices,
                    )
                except (ValueError, OSError, subprocess.SubprocessError) as exc:
                    return {"ticket": ticket, "status": "queued", "reason": str(exc)}
            return _measure(
                round_dir,
                plan,
                lane,
                ticket,
                overlay,
                incumbent,
                [device for device, _lease in held],
                backend=backend,
                make_assess=make_assess,
                current=current,
                reserved=entry,
            )
        finally:
            for _device, lease in held:
                lease.release()
    finally:
        lane_lock.release()


def _measure(
    round_dir: Path,
    plan: dict,
    lane: dict,
    ticket: str,
    overlay: Path,
    incumbent: Path,
    devices: list[str],
    *,
    backend,
    make_assess: Callable[[RunSpec], Callable],
    current,
    reserved=None,
) -> dict:
    """``reserved`` is this ticket's surviving reservation from an interrupted serve."""
    candidate = round_dir / "candidates" / ticket
    try:
        materialize(incumbent, [overlay], candidate)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"ticket": ticket, "status": "rejected", "reason": str(exc)}
    ledger = _load_ledger(round_dir, plan, lane)
    if reserved is not None:
        binding = reserved.binding
    else:
        try:
            ledger, binding = admit_attempt(plan, ledger, lane["id"], current(), token=ticket)
        except BudgetError as exc:
            shutil.rmtree(candidate, ignore_errors=True)
            return _record(round_dir, ticket, status="rejected", reason=str(exc))
        _save_ledger(round_dir, ledger)
    try:
        seconds_remaining(lane["deadline_utc"], current())
    except BudgetError as exc:
        _save_ledger(round_dir, advance(ledger, binding, "cancelled"))
        return _record(round_dir, ticket, status="rejected", reason=str(exc))
    ledger = advance(ledger, binding, "claimed")
    _save_ledger(round_dir, ledger)
    failures: list[str] = []
    try:
        if plan["build"]:
            build_dir = candidate / "build-output"
            build_dir.mkdir(parents=True, exist_ok=True)
            _run_confined(
                plan,
                "build",
                _command(plan["build"], None, ",".join(devices)),
                candidate,
                (candidate, build_dir),
                (),
                devices,
                lane["deadline_utc"],
                backend=backend,
                current=current,
            )
        spec = _run_spec(
            plan,
            candidate,
            incumbent,
            devices,
            round_dir / "runs" / ticket,
            seconds_remaining(lane["deadline_utc"], current()),
        )
        run_dir = _run_experiment(
            spec,
            {"round_id": plan["round_id"], "ticket": ticket, "lane_id": lane["id"]},
            execute=_confined_trial(
                plan,
                devices,
                lane["deadline_utc"],
                backend=backend,
                current=current,
                failures=failures,
            ),
            snapshot=_tree_identity,
            make_assess=make_assess,
        )
    except CommandFailed as exc:
        finished = advance(ledger, binding, "finished", actual_cost=0)
        _save_ledger(round_dir, finished)
        return _record(
            round_dir,
            ticket,
            status="failed",
            reason=str(exc),
            stage=exc.stage,
            returncode=exc.returncode,
            devices=devices,
        )
    except UnreapedCommand as exc:
        leases = DeviceLease(round_dir / "leases")
        for device in devices:
            leases.quarantine(device, f"{ticket}: {exc}")
        return _record(round_dir, ticket, status="unsettled", reason=str(exc), devices=devices)
    except (ConfinementUnavailable, BudgetError, ValueError) as exc:
        return _record(round_dir, ticket, status="unsettled", reason=str(exc), devices=devices)
    evaluation = json.loads((run_dir / "evaluation.json").read_text(encoding="utf-8"))
    # failures include ConfinementUnavailable during validation: that must not
    # settle as measured FAIL after metrics already produced an improvement_pct.
    if evaluation["improvement_pct"] is None or failures:
        reason = failures[-1] if failures else "; ".join(evaluation["reasons"])
        return _record(
            round_dir,
            ticket,
            status="unsettled",
            reason=reason,
            devices=devices,
            run_dir=str(run_dir),
        )
    finished = advance(ledger, binding, "finished", actual_cost=0)
    _save_ledger(round_dir, finished)
    return _record(
        round_dir,
        ticket,
        status="measured",
        lane_id=lane["id"],
        metric=plan["metric"]["name"],
        better=plan["metric"]["better"],
        verdict=evaluation["verdict"],
        improvement_pct=evaluation["improvement_pct"],
        reasons=evaluation["reasons"],
        candidate=evaluation["candidate"]["median"],
        incumbent=evaluation["baseline"]["median"],
        candidate_samples=evaluation["candidate"]["values"],
        incumbent_samples=evaluation["baseline"]["values"],
        run_dir=str(run_dir),
        devices=devices,
        confinement=getattr(backend, "name", "unknown"),
    )


def ticket_status(round_dir: Path, ticket: str) -> dict:
    path = round_dir / "results" / f"{ticket}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"ticket": ticket, "status": "queued"}


def _improvement_pct(body: dict) -> float:
    value = body.get("improvement_pct")
    if type(value) in (int, float) and math.isfinite(value):
        return float(value)
    return float("-inf")


def _one_winner_per_lane(passing: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep the best PASS ticket on each lane. Ties break toward the lower ticket id."""
    grouped: dict[str, list[dict]] = {}
    for body in passing:
        grouped.setdefault(body["lane_id"], []).append(body)
    selected: list[dict] = []
    dropped: list[dict] = []
    for lane_id in sorted(grouped):
        ranked = sorted(
            grouped[lane_id],
            key=lambda body: (-_improvement_pct(body), body["ticket"]),
        )
        selected.append(ranked[0])
        dropped.extend(ranked[1:])
    return selected, dropped


def _dropped_records(dropped: list[dict]) -> list[dict]:
    return [
        {
            "ticket": body["ticket"],
            "lane_id": body["lane_id"],
            "improvement_pct": body.get("improvement_pct"),
        }
        for body in dropped
    ]


def _write_joint_failure(
    round_dir: Path, plan: dict, selected: list[dict], evaluation: dict, run_dir: Path
) -> None:
    """Record a completed joint non-PASS. Harness does not import the knowledge package."""
    write_json(
        round_dir / "knowledge" / "joint-failure.json",
        {
            "kind": "inferrsi.parallel_round.joint_failure",
            "round_digest": plan["round_digest"],
            "incumbent_tree_digest": plan["incumbent_tree_digest"],
            "tickets": [
                {
                    "lane_id": item["lane_id"],
                    "ticket": item["ticket"],
                    "improvement_pct": item.get("improvement_pct"),
                }
                for item in selected
            ],
            "verdict": evaluation.get("verdict"),
            "reasons": evaluation.get("reasons"),
            "run_dir": str(run_dir),
            "outcome": "retained",
            "cause_stage": "validation",
        },
    )


def _receipts(round_dir: Path) -> dict[str, dict]:
    root = round_dir / "results"
    if not root.exists():
        return {}
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in root.glob("*.json")}


def close_round(
    round_dir: Path,
    incumbent: Path,
    *,
    backend,
    make_assess: Callable[[RunSpec], Callable],
    qualify_devices,
    now: datetime | None = None,
    clock=None,
) -> dict:
    """Joint single-rerun close. See the module docstring for the composition contract."""
    lock = _acquire_close(round_dir)
    if lock is None:
        return {
            "status": "queued",
            "composition": "joint-single-rerun",
            "reason": "round closing",
        }
    try:
        return _close_round_holding_lock(
            round_dir,
            incumbent,
            backend=backend,
            make_assess=make_assess,
            qualify_devices=qualify_devices,
            now=now,
            clock=clock,
        )
    finally:
        lock.release()


def _close_round_holding_lock(
    round_dir: Path,
    incumbent: Path,
    *,
    backend,
    make_assess: Callable[[RunSpec], Callable],
    qualify_devices,
    now: datetime | None = None,
    clock=None,
) -> dict:
    """Joint single-rerun close: compose PASS overlays once, measure once, keep or retain.

    ``make_assess`` is the same application-supplied port as ``serve_ticket``.
    Refuses while any outbox ticket lacks a terminal receipt, or any receipt is
    ``unsettled``. Device shortage returns ``queued`` without writing ``close.json``.
    """
    del now

    def current() -> datetime:
        if clock is not None:
            return clock()
        return datetime.now(timezone.utc)

    close_path = round_dir / "close.json"
    if close_path.exists():
        return json.loads(close_path.read_text(encoding="utf-8"))

    plan = json.loads((round_dir / "round-plan.json").read_text(encoding="utf-8"))
    mismatch = _incumbent_mismatch(plan, incumbent)
    if mismatch:
        return {
            "status": "refused",
            "composition": "joint-single-rerun",
            "reason": mismatch,
        }
    frozen = _freeze_incumbent(round_dir, incumbent)
    frozen_mismatch = _incumbent_mismatch(plan, frozen)
    if frozen_mismatch:
        return {
            "status": "refused",
            "composition": "joint-single-rerun",
            "reason": frozen_mismatch,
        }
    outbox = round_dir / "outbox"
    tickets = (
        sorted(path.name for path in outbox.iterdir() if path.is_dir()) if outbox.exists() else []
    )
    receipts = _receipts(round_dir)
    missing = [ticket for ticket in tickets if ticket not in receipts]
    if missing:
        return {
            "status": "refused",
            "composition": "joint-single-rerun",
            "reason": f"tickets without receipts: {', '.join(missing)}",
        }
    unsettled = [ticket for ticket in tickets if receipts[ticket].get("status") == "unsettled"]
    if unsettled:
        return {
            "status": "refused",
            "composition": "joint-single-rerun",
            "reason": f"unsettled tickets: {', '.join(unsettled)}",
        }
    bad = [ticket for ticket in tickets if receipts[ticket].get("status") not in _TERMINAL]
    if bad:
        return {
            "status": "refused",
            "composition": "joint-single-rerun",
            "reason": f"non-terminal receipts: {', '.join(bad)}",
        }

    passing = [
        receipts[ticket]
        for ticket in tickets
        if receipts[ticket].get("status") == "measured"
        and receipts[ticket].get("verdict") == "PASS"
    ]
    selected, dropped_bodies = _one_winner_per_lane(passing)
    dropped = _dropped_records(dropped_bodies)

    def finish(**fields) -> dict:
        body = {
            "status": "closed",
            "composition": "joint-single-rerun",
            "accepted": False,
            "retained": True,
            "composed": [],
            "dropped": dropped,
            "successor": None,
            **fields,
        }
        write_json(close_path, body)
        return body

    if not selected:
        return finish(reason="no PASS lanes")

    composed = [{"ticket": body["ticket"], "lane_id": body["lane_id"]} for body in selected]
    lanes = [_lane(plan, body["lane_id"]) for body in selected]
    deadline_utc = min(lane["deadline_utc"] for lane in lanes)
    try:
        ensure_open(deadline_utc, current())
    except BudgetError as exc:
        return finish(reason=str(exc), composed=composed)

    count = max(lane["device_count"] for lane in lanes)
    held = hold_devices(round_dir, plan, count)
    if held is None:
        return {
            "status": "queued",
            "composition": "joint-single-rerun",
            "reason": "devices unavailable",
            "composed": composed,
        }
    devices = [device for device, _lease in held]
    try:
        if plan.get("device_model"):
            try:
                _qualify(plan["device_model"], devices, qualify_devices)
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                return {
                    "status": "queued",
                    "composition": "joint-single-rerun",
                    "reason": str(exc),
                    "composed": composed,
                }
        overlays = [outbox / body["ticket"] for body in selected]
        joint = round_dir / "candidates" / "joint-close"
        try:
            materialize(frozen, overlays, joint)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if joint.exists():
                shutil.rmtree(joint)
            return {
                "status": "refused",
                "composition": "joint-single-rerun",
                "reason": str(exc),
                "composed": composed,
                "dropped": dropped,
                "devices": devices,
            }
        failures: list[str] = []
        try:
            if plan["build"]:
                build_dir = joint / "build-output"
                build_dir.mkdir(parents=True, exist_ok=True)
                _run_confined(
                    plan,
                    "build",
                    _command(plan["build"], None, ",".join(devices)),
                    joint,
                    (joint, build_dir),
                    (),
                    devices,
                    deadline_utc,
                    backend=backend,
                    current=current,
                )
            spec = _run_spec(
                plan,
                joint,
                frozen,
                devices,
                round_dir / "runs" / "joint-close",
                seconds_remaining(deadline_utc, current()),
            )
            run_dir = _run_experiment(
                spec,
                {"round_id": plan["round_id"], "ticket": "joint-close", "lane_id": "close"},
                execute=_confined_trial(
                    plan,
                    devices,
                    deadline_utc,
                    backend=backend,
                    current=current,
                    failures=failures,
                ),
                snapshot=_tree_identity,
                make_assess=make_assess,
            )
        except UnreapedCommand as exc:
            leases = DeviceLease(round_dir / "leases")
            for device in devices:
                leases.quarantine(device, f"joint-close: {exc}")
            return finish(
                reason=str(exc),
                composed=composed,
                devices=devices,
            )
        except CommandFailed as exc:
            return finish(
                reason=str(exc),
                composed=composed,
                devices=devices,
                stage=exc.stage,
                returncode=exc.returncode,
            )
        except ConfinementUnavailable as exc:
            return {
                "status": "refused",
                "composition": "joint-single-rerun",
                "reason": str(exc),
                "composed": composed,
                "dropped": dropped,
                "devices": devices,
            }
        except (BudgetError, ValueError) as exc:
            return finish(reason=str(exc), composed=composed, devices=devices)
        evaluation = json.loads((run_dir / "evaluation.json").read_text(encoding="utf-8"))
        if evaluation["improvement_pct"] is None or failures:
            return {
                "status": "refused",
                "composition": "joint-single-rerun",
                "reason": failures[-1] if failures else "; ".join(evaluation["reasons"]),
                "composed": composed,
                "dropped": dropped,
                "devices": devices,
                "run_dir": str(run_dir),
                "verdict": evaluation.get("verdict"),
                "improvement_pct": evaluation.get("improvement_pct"),
                "reasons": evaluation.get("reasons"),
            }
        if evaluation["verdict"] != "PASS":
            _write_joint_failure(round_dir, plan, selected, evaluation, run_dir)
            return finish(
                reason="joint measurement did not PASS",
                composed=composed,
                devices=devices,
                run_dir=str(run_dir),
                verdict=evaluation["verdict"],
                improvement_pct=evaluation["improvement_pct"],
                reasons=evaluation["reasons"],
            )
        successor = round_dir / "successor"
        try:
            final = json.loads((run_dir / "repositories.final.json").read_text(encoding="utf-8"))
            expected = final["candidate"]["snapshot_hash"]
            if not isinstance(expected, str) or not expected:
                raise ValueError("measured candidate snapshot is missing")
            _promote_snapshot(joint, successor, expected)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if successor.exists():
                shutil.rmtree(successor)
            return {
                "status": "refused",
                "composition": "joint-single-rerun",
                "reason": str(exc),
                "composed": composed,
                "dropped": dropped,
                "devices": devices,
                "run_dir": str(run_dir),
                "verdict": evaluation["verdict"],
                "improvement_pct": evaluation["improvement_pct"],
            }
        return finish(
            accepted=True,
            retained=False,
            reason="joint measurement PASS",
            composed=composed,
            successor=str(successor),
            devices=devices,
            run_dir=str(run_dir),
            verdict=evaluation["verdict"],
            improvement_pct=evaluation["improvement_pct"],
            reasons=evaluation["reasons"],
            candidate=evaluation["candidate"]["median"],
            incumbent=evaluation["baseline"]["median"],
        )
    finally:
        for _device, lease in held:
            lease.release()
