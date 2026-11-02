"""Prepare, submit and measure one offline parallel round.

Directory diffs stand in for git clones. ``close`` and incumbent advancement are
not implemented. A synthetic latency number is not a campaign verdict.
"""

import hashlib
import json
import os
import shutil
import stat
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


class RoundPlanError(ValueError):
    """The frozen round plan is internally inconsistent."""


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
        try:
            file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dirfd)
        except OSError:
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
        try:
            file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dirfd)
        except OSError:
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
    seen_entries: set[str] = set()
    seen_ids: set[str] = set()
    files = _files(incumbent)
    normalized = []
    for lane in lanes:
        lane_id = lane.get("id")
        entry = lane.get("entry")
        plane = lane.get("plane")
        globs = lane.get("globs")
        if not isinstance(lane_id, str) or not lane_id or lane_id in seen_ids:
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
        if any(_match(path, globs) and _match(path, protected) for path in files):
            raise RoundPlanError(f"{lane_id} reaches a protected path")
        seen_ids.add(lane_id)
        seen_entries.add(entry)
        normalized.append(dict(lane))
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
        "device_id": spec["device_id"],
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


def _materialize(incumbent: Path, overlay: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(incumbent, destination, ignore=shutil.ignore_patterns("manifest.json"))
    manifest = json.loads((overlay / "manifest.json").read_text(encoding="utf-8"))
    for relative in manifest["files"]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(overlay / relative, target)


def _command(template: list[str], result: Path) -> tuple[str, ...]:
    return tuple(part.replace("{result}", str(result)) for part in template)


def _record(round_dir: Path, ticket: str, **fields) -> dict:
    body = {"ticket": ticket, "synthetic": True, **fields}
    write_json(round_dir / "results" / f"{ticket}.json", body)
    return body


def _claimed_entry(ledger, ticket: str):
    suffix = f"@{ticket}"
    for entry in ledger.entries:
        if entry.binding.run_id.endswith(suffix) and entry.phase == "claimed":
            return entry
    return None


def _launch(
    plan: dict, lane: dict, candidate: Path, incumbent: Path, trial_dir: Path, *, backend, current
):
    """Run build and both trials. Each start is bounded by the same absolute deadline."""
    build_dir = candidate / "build-output"
    build_dir.mkdir(parents=True, exist_ok=True)
    trial_dir.mkdir(parents=True, exist_ok=True)

    def run(argv, cwd, writable, readable) -> None:
        remaining = min(seconds_remaining(lane["deadline_utc"], current()), 30)
        confined_execute(
            argv, cwd, writable, readable, time.monotonic() + remaining, backend=backend
        )

    if plan["build"]:
        run(tuple(plan["build"]), candidate, (candidate, build_dir), ())
    candidate_result = trial_dir / "candidate.json"
    run(_command(plan["trial"], candidate_result), candidate, (trial_dir,), (candidate,))
    incumbent_result = trial_dir / "incumbent.json"
    run(_command(plan["trial"], incumbent_result), incumbent, (trial_dir,), (incumbent,))
    return candidate_result, incumbent_result


def serve_ticket(
    round_dir: Path,
    ticket: str,
    incumbent: Path,
    *,
    backend,
    now: datetime,
    clock=None,
) -> dict:
    """Measure one ticket. A busy device leaves it queued and does not reserve an attempt."""
    def current() -> datetime:
        return clock() if clock is not None else now

    plan = json.loads((round_dir / "round-plan.json").read_text(encoding="utf-8"))
    result_path = round_dir / "results" / f"{ticket}.json"
    if result_path.exists():
        return json.loads(result_path.read_text(encoding="utf-8"))
    overlay = round_dir / "outbox" / ticket
    manifest = json.loads((overlay / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("deleted"):
        return _record(round_dir, ticket, status="rejected", reason="deletion")
    lane = _lane(plan, manifest["lane_id"])
    if _claimed_entry(_load_ledger(round_dir, plan, lane), ticket) is not None:
        return _record(
            round_dir,
            ticket,
            status="unsettled",
            reason="claimed execution was not settled",
        )
    try:
        held = DeviceLease(round_dir / "leases").acquire(plan["device_id"])
    except LeaseError:
        return {"ticket": ticket, "status": "queued"}
    try:
        try:
            loaded = _load_ledger(round_dir, plan, lane)
            ledger, binding = admit_attempt(plan, loaded, lane["id"], current(), token=ticket)
        except BudgetError as exc:
            return _record(round_dir, ticket, status="rejected", reason=str(exc))
        _save_ledger(round_dir, ledger)
        candidate = round_dir / "candidates" / ticket
        trial_dir = round_dir / "trials" / ticket
        _materialize(incumbent, overlay, candidate)
        try:
            seconds_remaining(lane["deadline_utc"], current())
        except BudgetError as exc:
            _save_ledger(round_dir, advance(ledger, binding, "cancelled"))
            return _record(round_dir, ticket, status="rejected", reason=str(exc))
        ledger = advance(ledger, binding, "claimed")
        _save_ledger(round_dir, ledger)
        try:
            candidate_result, incumbent_result = _launch(
                plan, lane, candidate, incumbent, trial_dir, backend=backend, current=current
            )
        except (ConfinementUnavailable, BudgetError) as exc:
            return _record(round_dir, ticket, status="unsettled", reason=str(exc))
        candidate_body = json.loads(candidate_result.read_text(encoding="utf-8"))
        incumbent_body = json.loads(incumbent_result.read_text(encoding="utf-8"))
        candidate_metric = candidate_body["metrics"]["latency_ms"]
        incumbent_metric = incumbent_body["metrics"]["latency_ms"]
        finished = advance(ledger, binding, "finished", actual_cost=0)
        _save_ledger(round_dir, finished)
        return _record(
            round_dir,
            ticket,
            status="measured",
            candidate_latency_ms=candidate_metric,
            incumbent_latency_ms=incumbent_metric,
            gain_ms=incumbent_metric - candidate_metric,
            confinement=getattr(backend, "name", "unknown"),
        )
    finally:
        held.release()


def ticket_status(round_dir: Path, ticket: str) -> dict:
    path = round_dir / "results" / f"{ticket}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"ticket": ticket, "status": "queued"}
