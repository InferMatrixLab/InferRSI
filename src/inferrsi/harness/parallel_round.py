"""Prepare, submit and measure one offline parallel round.

Directory diffs stand in for git clones. ``close`` and incumbent advancement are
not implemented. A synthetic latency number is not a campaign verdict.
"""

import json
import shutil
import time
from datetime import datetime
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
)
from inferrsi.infra.artifacts import digest, sha256, write_json
from inferrsi.infra.confinement import ConfinementUnavailable, confined_execute
from inferrsi.infra.device_lease import DeviceLease, LeaseError

PLANES = {"harness", "model", "infra"}


class RoundPlanError(ValueError):
    """The frozen round plan is internally inconsistent."""


def _match(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def _files(root: Path) -> list[str]:
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        found.append(path.relative_to(root).as_posix())
    return found


def _lane(plan: dict, lane_id: str) -> dict:
    matches = [lane for lane in plan["lanes"] if lane["id"] == lane_id]
    if len(matches) != 1:
        raise RoundPlanError(f"unknown lane: {lane_id}")
    return matches[0]


def _hashes(root: Path) -> dict[str, str]:
    return {relative: sha256(root / relative) for relative in _files(root)}


def _changed(incumbent: Path, work: Path) -> list[str]:
    before, after = _hashes(incumbent), _hashes(work)
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


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


def submit(round_dir: Path, lane_id: str, incumbent: Path, work: Path) -> dict:
    """Copy in-glob changes to the outbox. The same manifest always returns the same ticket."""
    plan = json.loads((round_dir / "round-plan.json").read_text(encoding="utf-8"))
    lane = _lane(plan, lane_id)
    changed = _changed(incumbent, work)
    outside = [path for path in changed if not _match(path, lane["globs"])]
    if outside or not changed:
        return {"submitted": False, "outside": outside, "ticket": None}
    manifest = {path: sha256(work / path) for path in changed}
    ticket = digest(
        {"round_digest": plan["round_digest"], "lane_id": lane_id, "manifest": manifest}
    )[:16]
    destination = round_dir / "outbox" / ticket
    if not destination.exists():
        destination.mkdir(parents=True)
        for path in changed:
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(work / path, target)
        write_json(
            destination / "manifest.json",
            {"ticket": ticket, "lane_id": lane_id, "files": manifest},
        )
    return {"submitted": True, "outside": [], "ticket": ticket}


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


def serve_ticket(round_dir: Path, ticket: str, incumbent: Path, *, backend, now: datetime) -> dict:
    """Measure one ticket. A busy device leaves it queued and does not reserve an attempt."""
    plan = json.loads((round_dir / "round-plan.json").read_text(encoding="utf-8"))
    result_path = round_dir / "results" / f"{ticket}.json"
    if result_path.exists():
        return json.loads(result_path.read_text(encoding="utf-8"))
    overlay = round_dir / "outbox" / ticket
    manifest = json.loads((overlay / "manifest.json").read_text(encoding="utf-8"))
    lane = _lane(plan, manifest["lane_id"])
    try:
        held = DeviceLease(round_dir / "leases").acquire(plan["device_id"])
    except LeaseError:
        return {"ticket": ticket, "status": "queued"}
    try:
        try:
            loaded = _load_ledger(round_dir, plan, lane)
            ledger, binding = admit_attempt(plan, loaded, lane["id"], now)
        except BudgetError as exc:
            record = {"ticket": ticket, "status": "rejected", "reason": str(exc), "synthetic": True}
            write_json(result_path, record)
            return record
        _save_ledger(round_dir, ledger)
        candidate = round_dir / "candidates" / ticket
        trial_dir = round_dir / "trials" / ticket
        build_dir = candidate / "build-output"
        try:
            _materialize(incumbent, overlay, candidate)
            build_dir.mkdir(parents=True, exist_ok=True)
            trial_dir.mkdir(parents=True, exist_ok=True)
            if plan["build"]:
                confined_execute(
                    tuple(plan["build"]),
                    candidate,
                    (candidate, build_dir),
                    (),
                    time.monotonic() + 30,
                    backend=backend,
                )
            candidate_result = trial_dir / "candidate.json"
            confined_execute(
                _command(plan["trial"], candidate_result),
                candidate,
                (trial_dir,),
                (candidate,),
                time.monotonic() + 30,
                backend=backend,
            )
            incumbent_result = trial_dir / "incumbent.json"
            confined_execute(
                _command(plan["trial"], incumbent_result),
                incumbent,
                (trial_dir,),
                (incumbent,),
                time.monotonic() + 30,
                backend=backend,
            )
        except ConfinementUnavailable as exc:
            _save_ledger(round_dir, advance(ledger, binding, "cancelled"))
            record = {"ticket": ticket, "status": "rejected", "reason": str(exc), "synthetic": True}
            write_json(result_path, record)
            return record
        candidate_body = json.loads(candidate_result.read_text(encoding="utf-8"))
        incumbent_body = json.loads(incumbent_result.read_text(encoding="utf-8"))
        candidate_metric = candidate_body["metrics"]["latency_ms"]
        incumbent_metric = incumbent_body["metrics"]["latency_ms"]
        finished = advance(advance(ledger, binding, "claimed"), binding, "finished", actual_cost=0)
        _save_ledger(round_dir, finished)
        record = {
            "ticket": ticket,
            "status": "measured",
            "synthetic": True,
            "candidate_latency_ms": candidate_metric,
            "incumbent_latency_ms": incumbent_metric,
            "gain_ms": incumbent_metric - candidate_metric,
            "confinement": getattr(backend, "name", "unknown"),
        }
        write_json(result_path, record)
        return record
    finally:
        held.release()


def ticket_status(round_dir: Path, ticket: str) -> dict:
    path = round_dir / "results" / f"{ticket}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"ticket": ticket, "status": "queued"}
