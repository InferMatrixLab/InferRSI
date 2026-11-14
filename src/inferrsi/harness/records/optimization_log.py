"""Campaign-level optimization log: why each optimization was chosen and how it ended.

The log is the reviewable account of a whole campaign: which knowledge was
retrieved and why, the declared search space and how it was narrowed, each
iteration's hypothesis and rationale, its decision, and the success and failure
summaries. Narrative text is caller-authored; the dashboard cross-checks every
reference in it against captured knowledge and recorded measurements and shows
each disagreement instead of silently trusting the narrative.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path

MAX_LOG_BYTES = 2 * 1024 * 1024
MAX_INDEX_BYTES = 2 * 1024 * 1024
STAGES = ("diagnosis", "knowledge", "search", "execution", "validation", "review")
OPTION_STATUSES = ("tried", "pruned", "untried")
OUTCOMES = ("adopted", "rejected", "rolled_back", "no_gain", "noise", "pending")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SHA256 = re.compile(r"[a-fA-F0-9]{64}")
_SECTION_STATES = ("complete", "partial", "redacted")


class LogError(ValueError):
    """A validation failure naming the offending field, never its content."""


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise LogError(f"duplicate key: {key}")
        result[key] = value
    return result


def _fields(value: object, required: set[str], optional: set[str], where: str) -> dict:
    if not isinstance(value, dict):
        raise LogError(f"{where} must be an object")
    missing, extra = required - set(value), set(value) - required - optional
    if missing:
        raise LogError(f"{where} is missing {', '.join(sorted(missing))}")
    if extra:
        raise LogError(f"{where} has unsupported {', '.join(sorted(extra))}")
    return value


def _text(value: object, where: str, *, required: bool = True, limit: int = 20000) -> str:
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise LogError(f"{where} must be a {'nonempty ' if required else ''}string "
                       f"of at most {limit} characters")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise LogError(f"{where} contains control characters")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise LogError(f"{where} must contain valid Unicode") from exc
    return value


def _texts(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 200:
        raise LogError(f"{where} must be a list of at most 200 strings")
    return [_text(item, f"{where}[{index}]") for index, item in enumerate(value)]


def _identifier(value: object, where: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise LogError(f"{where} must be a safe identifier")
    return value


def _identifiers(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 200:
        raise LogError(f"{where} must be a list of identifiers")
    return [_identifier(item, f"{where}[{index}]") for index, item in enumerate(value)]


def _refs(value: object, where: str) -> list[str]:
    """Knowledge references are authority-qualified identities like ``package:x``."""
    if not isinstance(value, list) or len(value) > 200:
        raise LogError(f"{where} must be a list of knowledge references")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not re.fullmatch(r"[a-z]+:[A-Za-z0-9_.:/-]{1,240}", item):
            raise LogError(f"{where}[{index}] must be an authority-qualified reference")
    return value


def _section_state(value: dict, where: str) -> None:
    if value["state"] not in _SECTION_STATES:
        raise LogError(f"{where}.state must be one of {', '.join(_SECTION_STATES)}")
    reason = _text(value["missing_reason"], f"{where}.missing_reason", required=False)
    if value["state"] != "complete" and not reason.strip():
        raise LogError(f"{where}.missing_reason must explain a {value['state']} section")


def _evidence(value: object, where: str) -> list[str]:
    """Evidence points at a recorded candidate (``candidate:<id>``) or knowledge ref."""
    if not isinstance(value, list) or len(value) > 50:
        raise LogError(f"{where} must be a list of evidence references")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not re.fullmatch(
                r"(?:candidate:[A-Za-z0-9][A-Za-z0-9_.-]{0,127}|[a-z]+:[A-Za-z0-9_.:/-]{1,240})",
                item):
            raise LogError(f"{where}[{index}] must be candidate:<id> or a knowledge reference")
    return value


def parse_optimization_log(raw: bytes) -> dict:
    """Validate a complete log. Errors name the field so the author can fix it."""
    if not isinstance(raw, bytes) or len(raw) > MAX_LOG_BYTES:
        raise LogError("the log must be at most 2 MiB")
    try:
        log = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (UnicodeError, RecursionError) as exc:
        raise LogError("the log must be UTF-8 JSON") from exc
    except LogError:
        raise
    except ValueError as exc:
        raise LogError(f"invalid JSON: {exc}") from exc
    _fields(log, {"schema_version", "reviewed_by_caller", "campaign_id", "goal", "knowledge",
                  "search_space", "iterations", "summary"}, set(), "log")
    if log["schema_version"] != 2 or type(log["schema_version"]) is not int:
        raise LogError("schema_version must be 2")
    if log["reviewed_by_caller"] is not True:
        raise LogError("reviewed_by_caller must be true after reviewing the text for private data")
    _identifier(log["campaign_id"], "campaign_id")

    goal = _fields(log["goal"], {"statement", "metric"}, {"baseline", "target", "constraints"},
                   "goal")
    _text(goal["statement"], "goal.statement")
    _text(goal["metric"], "goal.metric")
    for key in ("baseline", "target"):
        if key in goal:
            _text(goal[key], f"goal.{key}")
    if "constraints" in goal:
        _texts(goal["constraints"], "goal.constraints")

    if not isinstance(log["knowledge"], list) or len(log["knowledge"]) > 100:
        raise LogError("knowledge must be a list of at most 100 retrievals")
    context_ids = set()
    for index, entry in enumerate(log["knowledge"]):
        where = f"knowledge[{index}]"
        _fields(entry, {"context_id", "sha256", "stage", "purpose", "used_refs", "takeaways"},
                {"rejected_refs"}, where)
        context_id = _identifier(entry["context_id"], f"{where}.context_id")
        if context_id in context_ids:
            raise LogError(f"{where}.context_id repeats {context_id}")
        context_ids.add(context_id)
        if not isinstance(entry["sha256"], str) or not _SHA256.fullmatch(entry["sha256"]):
            raise LogError(f"{where}.sha256 must be the capture's SHA-256")
        if entry["stage"] not in STAGES:
            raise LogError(f"{where}.stage must be one of {', '.join(STAGES)}")
        _text(entry["purpose"], f"{where}.purpose")
        _refs(entry["used_refs"], f"{where}.used_refs")
        _texts(entry["takeaways"], f"{where}.takeaways")
        if "rejected_refs" in entry:
            if not isinstance(entry["rejected_refs"], list):
                raise LogError(f"{where}.rejected_refs must be a list")
            for position, rejected in enumerate(entry["rejected_refs"]):
                item = _fields(rejected, {"ref", "reason"}, set(),
                               f"{where}.rejected_refs[{position}]")
                _refs([item["ref"]], f"{where}.rejected_refs[{position}].ref")
                _text(item["reason"], f"{where}.rejected_refs[{position}].reason")

    space = _fields(log["search_space"], {"state", "missing_reason", "dimensions"}, set(),
                    "search_space")
    _section_state(space, "search_space")
    if not isinstance(space["dimensions"], list) or len(space["dimensions"]) > 50:
        raise LogError("search_space.dimensions must be a list of at most 50 dimensions")
    option_ids = set()
    for index, dimension in enumerate(space["dimensions"]):
        where = f"search_space.dimensions[{index}]"
        _fields(dimension, {"id", "name", "options"}, {"rationale"}, where)
        _identifier(dimension["id"], f"{where}.id")
        _text(dimension["name"], f"{where}.name")
        if "rationale" in dimension:
            _text(dimension["rationale"], f"{where}.rationale")
        if not isinstance(dimension["options"], list) or not 1 <= len(dimension["options"]) <= 100:
            raise LogError(f"{where}.options must list 1 to 100 options")
        for position, option in enumerate(dimension["options"]):
            spot = f"{where}.options[{position}]"
            _fields(option, {"id", "description", "status", "reason"}, {"source_refs"}, spot)
            qualified = f"{dimension['id']}.{_identifier(option['id'], f'{spot}.id')}"
            if qualified in option_ids:
                raise LogError(f"{spot}.id repeats {qualified}")
            option_ids.add(qualified)
            _text(option["description"], f"{spot}.description")
            if option["status"] not in OPTION_STATUSES:
                raise LogError(f"{spot}.status must be one of {', '.join(OPTION_STATUSES)}")
            _text(option["reason"], f"{spot}.reason")
            if "source_refs" in option:
                _refs(option["source_refs"], f"{spot}.source_refs")

    if not isinstance(log["iterations"], list) or len(log["iterations"]) > 200:
        raise LogError("iterations must be a list of at most 200 rounds")
    previous = 0
    for index, iteration in enumerate(log["iterations"]):
        where = f"iterations[{index}]"
        _fields(iteration, {"round", "hypothesis", "rationale", "knowledge_refs", "candidates",
                            "decision"}, {"context_ids", "observations", "next_step"}, where)
        if type(iteration["round"]) is not int or iteration["round"] <= previous:
            raise LogError(f"{where}.round must increase from the previous round")
        previous = iteration["round"]
        _text(iteration["hypothesis"], f"{where}.hypothesis")
        _text(iteration["rationale"], f"{where}.rationale")
        _refs(iteration["knowledge_refs"], f"{where}.knowledge_refs")
        for context_id in _identifiers(iteration.get("context_ids", []), f"{where}.context_ids"):
            if context_id not in context_ids:
                raise LogError(f"{where}.context_ids names unknown capture {context_id}")
        if "observations" in iteration:
            _texts(iteration["observations"], f"{where}.observations")
        if "next_step" in iteration:
            _text(iteration["next_step"], f"{where}.next_step")
        if not isinstance(iteration["candidates"], list) or not iteration["candidates"]:
            raise LogError(f"{where}.candidates must name at least one candidate")
        for position, candidate in enumerate(iteration["candidates"]):
            spot = f"{where}.candidates[{position}]"
            _fields(candidate, {"candidate_id", "option_ids", "why"}, {"expected"}, spot)
            _identifier(candidate["candidate_id"], f"{spot}.candidate_id")
            if not isinstance(candidate["option_ids"], list):
                raise LogError(f"{spot}.option_ids must be a list")
            for option in candidate["option_ids"]:
                if not isinstance(option, str) or (space["state"] == "complete"
                                                   and option not in option_ids):
                    raise LogError(f"{spot}.option_ids names unknown option {option!s:.80}")
            _text(candidate["why"], f"{spot}.why")
            if "expected" in candidate:
                _text(candidate["expected"], f"{spot}.expected")
        decision = _fields(iteration["decision"], {"outcome", "reason"}, {"candidate_id"},
                           f"{where}.decision")
        if decision["outcome"] not in OUTCOMES:
            raise LogError(f"{where}.decision.outcome must be one of {', '.join(OUTCOMES)}")
        _text(decision["reason"], f"{where}.decision.reason")
        if "candidate_id" in decision:
            _identifier(decision["candidate_id"], f"{where}.decision.candidate_id")

    summary = _fields(log["summary"], {"state", "missing_reason", "successes", "failures",
                                       "lessons", "limitations"}, set(), "summary")
    _section_state(summary, "summary")
    for key in ("successes", "failures"):
        if not isinstance(summary[key], list):
            raise LogError(f"summary.{key} must be a list")
        for index, entry in enumerate(summary[key]):
            where = f"summary.{key}[{index}]"
            optional = {"cause_stage"} if key == "failures" else set()
            _fields(entry, {"text", "evidence"}, optional, where)
            _text(entry["text"], f"{where}.text")
            _evidence(entry["evidence"], f"{where}.evidence")
            if "cause_stage" in entry and entry["cause_stage"] not in STAGES:
                raise LogError(f"{where}.cause_stage must be one of {', '.join(STAGES)}")
    _texts(summary["lessons"], "summary.lessons")
    _texts(summary["limitations"], "summary.limitations")
    return log


def record_log(root: Path, source: Path) -> tuple[Path, str]:
    """Store a validated log as a new numbered version and append it to the index.

    Earlier versions are kept, so a reviewer can see how the account changed.
    """
    root = Path(root).resolve()
    try:
        campaign = json.loads((root / "campaign.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("campaign.json is missing or invalid") from exc
    with Path(source).open("rb") as stream:
        raw = stream.read(MAX_LOG_BYTES + 1)
    log = parse_optimization_log(raw)
    if not isinstance(campaign, dict) or log["campaign_id"] != campaign.get("campaign_id"):
        raise ValueError("log campaign_id does not match campaign.json")
    index_path = root / "optimization-log.jsonl"
    versions = _index(index_path)
    number = len(versions) + 1
    name = f"optimization-log-v{number}.json"
    target = root / name
    digest = hashlib.sha256(raw).hexdigest()
    temporary = root / f".log-{os.getpid()}-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
        os.link(temporary, target)
    except FileExistsError as exc:
        raise ValueError(f"{name} already exists; the index is out of date") from exc
    finally:
        if temporary.exists():
            temporary.unlink()
    entry = {"version": number, "path": name, "sha256": digest,
             "recorded_at": datetime.now(timezone.utc).isoformat()}
    append_index(index_path, (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8"))
    return target, digest


def read_regular(path: Path, limit: int) -> bytes:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or not before.st_ino:
        raise ValueError("unsafe log path")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or not opened.st_ino
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError("unsafe log path")
        return stream.read(limit + 1)


def append_index(path: Path, payload: bytes) -> None:
    try:
        before = path.lstat()
    except FileNotFoundError:
        before = None
    if before is not None and (not stat.S_ISREG(before.st_mode) or not before.st_ino):
        raise ValueError("unsafe optimization log index")
    flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= os.O_CREAT | (os.O_EXCL if before is None else 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "ab") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or not opened.st_ino
                or (before is not None and (opened.st_dev, opened.st_ino)
                    != (before.st_dev, before.st_ino))):
            raise ValueError("unsafe optimization log index")
        stream.write(payload)


def _index(path: Path) -> list[dict]:
    try:
        raw = read_regular(path, MAX_INDEX_BYTES)
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        raise ValueError("unsafe or unreadable optimization log index") from exc
    if len(raw) > MAX_INDEX_BYTES:
        raise ValueError("optimization log index is too large")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise ValueError("optimization log index is not UTF-8") from exc
    entries = []
    for number, line in enumerate(lines, 1):
        try:
            entry = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"optimization-log.jsonl line {number} is invalid") from exc
        if not isinstance(entry, dict):
            raise ValueError(f"optimization-log.jsonl line {number} is invalid")
        entries.append(entry)
    return entries


def read_latest_log(root: Path) -> tuple[dict | None, list[dict], str]:
    """Return the latest log if valid, the version list, and a state."""
    root = Path(root).resolve()
    try:
        versions = _index(root / "optimization-log.jsonl")
    except ValueError:
        return None, [], "corrupt_index"
    if not versions:
        return None, [], "not_recorded"
    checked = []
    for entry in versions:
        name, digest = entry.get("path"), entry.get("sha256")
        row = {"version": entry.get("version"), "path": name, "sha256": digest,
               "recorded_at": entry.get("recorded_at"), "state": "missing"}
        if (not isinstance(name, str) or not _IDENTIFIER.fullmatch(name)
                or not isinstance(digest, str)):
            row["missing_reason"] = "invalid_index_entry"
            checked.append(row)
            continue
        path = root / name
        try:
            raw = read_regular(path, MAX_LOG_BYTES)
        except (OSError, ValueError):
            raw = None
        if raw is None:
            row["missing_reason"] = "file_absent"
        elif hashlib.sha256(raw).hexdigest() != digest.lower():
            row["missing_reason"] = "hash_mismatch"
        else:
            try:
                row["log"] = parse_optimization_log(raw)
                row["state"] = "present"
            except LogError as exc:
                row["missing_reason"] = f"invalid: {exc}"
        checked.append(row)
    latest = checked[-1]
    if latest["state"] != "present":
        return None, [{k: v for k, v in row.items() if k != "log"} for row in checked], \
            f"latest_{latest['missing_reason'].split(':')[0]}"
    log = latest["log"]
    return log, [{k: v for k, v in row.items() if k != "log"} for row in checked], "present"
