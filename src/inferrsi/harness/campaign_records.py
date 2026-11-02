"""Create a local campaign manifest and associate completed or live runs."""

from __future__ import annotations

import json
import math
import os
import re
import uuid
from pathlib import Path

from .dashboard_data import _file_ref, _inside, _object


def _identifier(value: str, name: str) -> str:
    if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value)
            or value in {".", ".."}):
        raise ValueError(f"{name} must be a safe single identifier")
    return value


def create_campaign(root: Path, campaign_id: str, *, target: float | None = None,
                    noise: float | None = None, synthetic: bool = False) -> Path:
    _identifier(campaign_id, "campaign_id")
    for name, value in (("target", target), ("noise", noise)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or value < 0):
            raise ValueError(f"{name} must be finite and nonnegative")
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest = {"campaign_id": campaign_id, "synthetic": synthetic}
    if target is not None:
        manifest["goal"] = {"target_improvement_pct": target}
    if noise is not None:
        manifest["noise"] = {"band_pct": noise}
    path = root / "campaign.json"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return path


def _round_records(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    records = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError("existing rounds.jsonl contains invalid JSON") from error
        if (not isinstance(item, dict) or isinstance(item.get("round"), bool)
                or not isinstance(item.get("round"), int)
                or not isinstance(item.get("candidates"), list)):
            raise ValueError("existing rounds.jsonl contains an invalid round")
        records.append(item)
    if len({item["round"] for item in records}) != len(records):
        raise ValueError("existing rounds.jsonl repeats a round")
    return records


def _reference(root: Path, raw: str | None, kind: str) -> dict | None:
    if raw is None:
        return None
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{kind} must be a campaign-relative path")
    ref = _file_ref(root, root / path, kind)
    if ref["state"] != "present":
        raise ValueError(f"{kind} is missing or outside the campaign")
    return ref


def _write_rounds(root: Path, path: Path, records: list[dict]) -> None:
    temporary = root / f".rounds-{os.getpid()}-{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text("".join(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n"
                                     for item in records), encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def record_candidate(root: Path, *, candidate_id: str, run_id: str, round_number: int,
                     title: str, agent_trace: str | None = None,
                     profile: str | None = None) -> Path:
    """Associate a run and optional explicit evidence without copying raw data."""
    root = Path(root).resolve()
    _identifier(candidate_id, "candidate_id")
    _identifier(run_id, "run_id")
    if isinstance(round_number, bool) or not isinstance(round_number, int) or round_number < 1:
        raise ValueError("round must be a positive integer")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title is required")
    _, state = _object(root / "campaign.json", root)
    if state != "present":
        raise ValueError("campaign.json is missing or invalid")
    run = root / "runs" / run_id
    if not _inside(root, run / "run.lock.json") or not (run / "run.lock.json").is_file():
        raise ValueError("run must be an existing InferRSI run inside the campaign")
    candidate_dir = root / "candidates" / candidate_id
    if not _inside(root, candidate_dir):
        raise ValueError("candidate directory escapes the campaign")
    metadata = {"candidate_id": candidate_id, "run_id": run_id,
                "round": round_number, "title": title}
    for key, value in (("agent_trace_ref", agent_trace), ("profile_ref", profile)):
        ref = _reference(root, value, key)
        if ref is not None:
            metadata[key] = ref
    rounds_path = root / "rounds.jsonl"
    if not _inside(root, rounds_path):
        raise ValueError("rounds file escapes the campaign")
    records = _round_records(rounds_path)
    matching = next((item for item in records if item["round"] == round_number), None)
    if matching is None:
        matching = {"round": round_number, "candidates": []}
        records.append(matching)
    if candidate_id in matching["candidates"]:
        raise ValueError("candidate is already recorded in this round")
    matching["candidates"].append(candidate_id)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    target = candidate_dir / "candidate.json"
    payload = json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with target.open("x", encoding="utf-8") as stream:
        stream.write(payload)
    try:
        _write_rounds(root, rounds_path, records)
    except (OSError, ValueError):
        if target.exists() and target.read_text(encoding="utf-8") == payload:
            target.unlink()
        raise
    return target


def record_decision(root: Path, *, candidate_id: str, round_number: int, outcome: str) -> Path:
    """Record one round decision without overwriting an earlier one."""
    root = Path(root).resolve()
    _identifier(candidate_id, "candidate_id")
    if isinstance(round_number, bool) or not isinstance(round_number, int) or round_number < 1:
        raise ValueError("round must be a positive integer")
    if not isinstance(outcome, str) or outcome not in {
        "adopted", "rejected", "rolled_back", "no_gain", "noise"
    }:
        raise ValueError("unknown decision outcome")
    path = root / "rounds.jsonl"
    if not _inside(root, path):
        raise ValueError("rounds file escapes the campaign")
    records = _round_records(path)
    matching = next((item for item in records if item["round"] == round_number), None)
    if matching is None or candidate_id not in matching["candidates"]:
        raise ValueError("candidate is not recorded in this round")
    if "decision" in matching:
        raise ValueError("round already has a decision")
    matching["decision"] = {"candidate_id": candidate_id, "outcome": outcome}
    _write_rounds(root, path, records)
    return path
