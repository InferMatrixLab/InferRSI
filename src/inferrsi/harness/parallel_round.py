"""Prepare, submit and measure one offline parallel round.

Directory diffs stand in for git clones. A synthetic metric value is not a
campaign verdict.

Each lane declares ``device_count`` (default 1). The counts of all lanes must fit
in ``device_ids``. A ticket runs only after it holds that many devices at once.

Command placeholders: ``build`` gets ``{device}`` only. ``trial`` gets ``{device}``
and ``{result}``; it must write ``{"metrics": {<metric.name>: <finite number>}}``
to ``{result}``. The candidate is built once, then candidate and incumbent trials
run ``metric.repeats`` times each in ABBA order; the receipt keeps every sample
and the medians. ``{device}`` is the held device identities joined with commas.
Other text, including ``{result}`` inside ``build``, is passed through unchanged.

``device_paths`` (per device id), ``shared_device_paths``, ``runtime_paths`` and
``env`` (values may use ``{device}``) extend the confined view for GPU trials.
Each command is capped by ``command_timeout_seconds`` and the lane deadline.
"""

import hashlib
import json
import math
import os
import shutil
import stat
import statistics
import subprocess
import time
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

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
from inferrsi.infra.artifacts import digest, write_json
from inferrsi.infra.confinement import ConfinementUnavailable, confined_execute
from inferrsi.infra.device_lease import DeviceLease, LeaseError

PLANES = {"harness", "model", "infra"}
DIRECTIONS = {"lower", "higher"}


class RoundPlanError(ValueError):
    """The frozen round plan is internally inconsistent."""


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


def _files(root: Path) -> list[str]:
    hashes, _blocked = _snapshot(root)
    return sorted(hashes)


def _snapshot(root: Path) -> tuple[dict[str, str], list[str]]:
    """Hash regular files without following links. Symlinks are reported, not read."""
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
            hasher = hashlib.sha256()
            while True:
                block = os.read(file_fd, 1024 * 1024)
                if not block:
                    break
                hasher.update(block)
            hashes[relative] = hasher.hexdigest()
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
        or not {"name", "better"} <= set(metric) <= {"name", "better", "repeats"}
        or not isinstance(metric["name"], str)
        or not metric["name"]
        or not isinstance(metric["better"], str)
        or metric["better"] not in DIRECTIONS
    ):
        raise RoundPlanError("metric needs a name and better: lower or higher")
    repeats = metric.get("repeats", 1)
    if type(repeats) is not int or repeats < 1:
        raise RoundPlanError("metric repeats must be a positive integer")
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
    files = _files(incumbent)
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
        },
        "command_timeout_seconds": timeout,
        "device_paths": {device: list(device_paths[device]) for device in device_paths},
        "shared_device_paths": list(shared_paths),
        "runtime_paths": list(runtime_paths),
        "env": dict(env),
        "incumbent_id": spec["incumbent_id"],
        "protected": protected,
        "build": list(spec.get("build", [])),
        "trial": list(spec.get("trial", [])),
        "lanes": normalized,
    }
    body["round_digest"] = digest(body)
    round_dir.mkdir(parents=True, exist_ok=True)
    write_json(round_dir / "round-plan.json", body)
    return body


def submit(
    round_dir: Path, lane_id: str, incumbent: Path, work: Path, *, now: datetime | None = None
) -> dict:
    """Copy in-glob changes to the outbox. The same manifest always returns the same ticket."""
    moment = now or datetime.now(timezone.utc)
    plan = json.loads((round_dir / "round-plan.json").read_text(encoding="utf-8"))
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
    manifest = {path: after[path] for path in changed}
    ticket = digest(
        {"round_digest": plan["round_digest"], "lane_id": lane_id, "manifest": manifest}
    )[:16]
    destination = round_dir / "outbox" / ticket
    if not destination.exists():
        destination.mkdir(parents=True)
        try:
            for path in changed:
                payload = _read_nofollow(work, path)
                if payload is None:
                    raise OSError(path)
                target = destination / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
        except OSError:
            shutil.rmtree(destination)
            return _refusal("symlink", rejected=list(changed))
        write_json(
            destination / "manifest.json",
            {"ticket": ticket, "lane_id": lane_id, "files": manifest, "deleted": []},
        )
    return {"submitted": True, "outside": [], "deleted": [], "rejected": [], "ticket": ticket}


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
    """Copy the incumbent, then apply each outbox overlay in order."""
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(incumbent, destination, ignore=shutil.ignore_patterns("manifest.json"))
    for overlay in overlays:
        manifest = json.loads((overlay / "manifest.json").read_text(encoding="utf-8"))
        for relative in manifest["files"]:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(overlay / relative, target)


def _command(template: list[str], result: Path | None, device: str) -> tuple[str, ...]:
    parts = (part.replace("{device}", device) for part in template)
    if result is None:
        return tuple(parts)
    return tuple(part.replace("{result}", str(result)) for part in parts)


def _metric_value(path: Path, name: str) -> float:
    value = json.loads(path.read_text(encoding="utf-8"))["metrics"][name]
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} is not a finite number")
    return value


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


class MeasurementError(ValueError):
    """A trial finished without a readable metric value."""


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
    device = ",".join(devices)
    nodes = list(plan["shared_device_paths"])
    for held in devices:
        nodes.extend(plan["device_paths"].get(held, []))
    try:
        record = confined_execute(
            argv,
            cwd,
            writable,
            readable,
            time.monotonic() + remaining,
            backend=backend,
            device_paths=tuple(Path(path) for path in nodes),
            runtime_paths=tuple(Path(path) for path in plan["runtime_paths"]),
            env={key: value.replace("{device}", device) for key, value in plan["env"].items()},
        )
    except subprocess.TimeoutExpired as exc:
        raise ConfinementUnavailable(f"{stage} timed out") from exc
    if record.get("status") != "completed":
        raise ConfinementUnavailable(f"{stage} {record.get('status')}")


def compare(
    plan: dict,
    candidate: Path,
    incumbent: Path,
    trial_dir: Path,
    devices: list[str],
    deadline_utc: str | None,
    *,
    backend,
    current,
) -> tuple[list[float], list[float]]:
    """Build the candidate once, then run ``repeats`` trial pairs in ABBA order.

    Raises ``ConfinementUnavailable`` or ``BudgetError`` when a command cannot run, and
    ``MeasurementError`` when a finished trial left no readable metric.
    """
    device = ",".join(devices)
    build_dir = candidate / "build-output"
    build_dir.mkdir(parents=True, exist_ok=True)
    trial_dir.mkdir(parents=True, exist_ok=True)
    common = {"backend": backend, "current": current}
    if plan["build"]:
        _run_confined(
            plan,
            "build",
            _command(plan["build"], None, device),
            candidate,
            (candidate, build_dir),
            (),
            devices,
            deadline_utc,
            **common,
        )
    sides = {"candidate": candidate, "incumbent": incumbent}
    samples: dict[str, list[float]] = {"candidate": [], "incumbent": []}
    name = plan["metric"]["name"]
    for index in range(plan["metric"]["repeats"]):
        order = ("candidate", "incumbent") if index % 2 == 0 else ("incumbent", "candidate")
        for side in order:
            result = trial_dir / f"{side}-{index}.json"
            _run_confined(
                plan,
                side,
                _command(plan["trial"], result, device),
                sides[side],
                (trial_dir,),
                (sides[side],),
                devices,
                deadline_utc,
                **common,
            )
            try:
                samples[side].append(_metric_value(result, name))
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise MeasurementError(
                    f"trial finished without a readable {name} result: {exc}"
                ) from exc
    return samples["candidate"], samples["incumbent"]


def summarize(plan: dict, candidate_samples: list[float], incumbent_samples: list[float]) -> dict:
    """Medians and a gain where positive always means the candidate is better."""
    candidate_value = statistics.median(candidate_samples)
    incumbent_value = statistics.median(incumbent_samples)
    gain = incumbent_value - candidate_value
    if plan["metric"]["better"] == "higher":
        gain = -gain
    return {
        "metric": plan["metric"]["name"],
        "better": plan["metric"]["better"],
        "candidate_samples": candidate_samples,
        "incumbent_samples": incumbent_samples,
        "candidate": candidate_value,
        "incumbent": incumbent_value,
        "gain": gain,
        "relative_gain": gain / abs(incumbent_value) if incumbent_value else None,
    }


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
    now: datetime | None = None,
    clock=None,
) -> dict:
    """Measure one ticket on the lane's ``device_count`` free devices. A busy lane or too
    few free devices leaves it queued and does not reserve an attempt.

    ``now`` is accepted for older callers and is not a frozen deadline. Every
    admission and command reads ``clock`` or the current time again.
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
    overlay = round_dir / "outbox" / ticket
    manifest = json.loads((overlay / "manifest.json").read_text(encoding="utf-8"))
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
            return _measure(
                round_dir,
                plan,
                lane,
                ticket,
                overlay,
                incumbent,
                [device for device, _lease in held],
                backend=backend,
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
    current,
    reserved=None,
) -> dict:
    """``reserved`` is this ticket's surviving reservation from an interrupted serve."""
    ledger = _load_ledger(round_dir, plan, lane)
    if reserved is not None:
        binding = reserved.binding
    else:
        try:
            ledger, binding = admit_attempt(plan, ledger, lane["id"], current(), token=ticket)
        except BudgetError as exc:
            return _record(round_dir, ticket, status="rejected", reason=str(exc))
        _save_ledger(round_dir, ledger)
    candidate = round_dir / "candidates" / ticket
    trial_dir = round_dir / "trials" / ticket
    materialize(incumbent, [overlay], candidate)
    try:
        seconds_remaining(lane["deadline_utc"], current())
    except BudgetError as exc:
        _save_ledger(round_dir, advance(ledger, binding, "cancelled"))
        return _record(round_dir, ticket, status="rejected", reason=str(exc))
    ledger = advance(ledger, binding, "claimed")
    _save_ledger(round_dir, ledger)
    try:
        candidate_samples, incumbent_samples = compare(
            plan,
            candidate,
            incumbent,
            trial_dir,
            devices,
            lane["deadline_utc"],
            backend=backend,
            current=current,
        )
    except (ConfinementUnavailable, BudgetError, MeasurementError) as exc:
        return _record(round_dir, ticket, status="unsettled", reason=str(exc), devices=devices)
    finished = advance(ledger, binding, "finished", actual_cost=0)
    _save_ledger(round_dir, finished)
    return _record(
        round_dir,
        ticket,
        status="measured",
        lane_id=lane["id"],
        **summarize(plan, candidate_samples, incumbent_samples),
        devices=devices,
        confinement=getattr(backend, "name", "unknown"),
    )


def ticket_status(round_dir: Path, ticket: str) -> dict:
    path = round_dir / "results" / f"{ticket}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"ticket": ticket, "status": "queued"}
