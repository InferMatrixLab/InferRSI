"""Build a bounded overview of an explicitly reviewed Kineto/Chrome duration trace.

The overview spans every complete duration event. It embeds no event arguments,
stacks or raw trace bytes; the original local file remains the detailed record.
"""
from __future__ import annotations

import gzip
import hashlib
import heapq
import io
import json
import math
import os
import re
import stat
import uuid
from collections import Counter
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .optimization_log import _append_index, _read_regular

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}")
_INDEX = "profile-captures.jsonl"
_MAX_FILE = 64 << 20
_MAX_LANES = 512
_BINS = 256


def _label(value: object, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("invalid profile label")
    if any(ord(c) < 32 for c in value):
        raise ValueError("invalid profile label")
    return value


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("expected a timestamp with timezone")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("expected a timestamp with timezone")
    return parsed


def pre_profile_searches(capture: dict, retrievals: dict) -> list[dict]:
    """Link only explicitly named, verified searches completed before this capture."""
    links = []
    for key in capture.get("context_ids", []):
        search = retrievals.get(key)
        if not search or search["state"] != "verified":
            state = "unverified"
        else:
            try:
                searched_at = _timestamp(search.get("captured_at"))
                before = searched_at < _timestamp(capture.get("started_at"))
            except ValueError:
                state = "unknown_time"
            else:
                state = "verified" if before else "not_before"
        links.append({"context_id": key, "state": state})
    return links


def _review(value: object) -> dict:
    fields = {"title", "phase", "round", "workload_id", "comparison_key", "takeaway", "next_action"}
    optional = {"started_at", "context_ids", "timing"}
    if not isinstance(value, dict) or not fields <= value.keys() <= fields | optional:
        raise ValueError("profile review fields do not match the contract")
    n = value["round"]
    if not ((value["phase"] == "baseline" and n is None) or
            (value["phase"] == "candidate" and type(n) is int and 1 <= n <= 10000)):
        raise ValueError("baseline precedes round 1; a candidate needs its round number")
    for k in fields - {"round", "phase"}:
        _label(value[k], 1400 if k in {"takeaway", "next_action"} else 180)
    _review_history(value)
    return value


def _review_history(value: dict) -> None:
    if "started_at" in value:
        _timestamp(value["started_at"])
    if "context_ids" in value:
        ids = value["context_ids"]
        if ("started_at" not in value or not isinstance(ids, list) or len(ids) > 64
                or not all(isinstance(i, str) and _ID.fullmatch(i) for i in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError("expected unique capture context IDs and a profile start time")
    if "timing" in value:
        timing = value["timing"]
        if not isinstance(timing, dict) or set(timing) != {"basis", "stages_ms"}:
            raise ValueError("expected a timing basis and named stages in milliseconds")
        _label(timing["basis"], 240)
        stages = timing["stages_ms"]
        if not isinstance(stages, dict) or not 1 <= len(stages) <= 128:
            raise ValueError("expected 1 to 128 named stages")
        for name, ms in stages.items():
            _label(name, 180)
            if type(ms) not in (int, float) or not 0 <= ms < 1e18:
                raise ValueError("expected a finite non-negative stage duration")


def _profile_path(root: Path, name: str) -> Path:
    # Only accept an explicitly named file directly under the campaign's profiles/ directory.
    if not isinstance(name, str) or not re.fullmatch(
        r"profiles/[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.json(?:\.gz)?", name
    ):
        raise ValueError("profile must be profiles/<name>.json or .json.gz")
    path = root / name
    if path.parent.resolve() != root / "profiles":
        raise ValueError("invalid profile directory")
    return path


def _raw(path: Path) -> bytes:
    raw = _read_regular(path, _MAX_FILE)
    if len(raw) > _MAX_FILE:
        raise ValueError("profile exceeds the stored size limit")
    return raw


def _file_version(path: Path) -> tuple[int, ...]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not info.st_ino or info.st_size > _MAX_FILE:
        raise ValueError("unsafe or oversized profile")
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


@lru_cache(maxsize=32)
def _overview_digest(path: Path, version: tuple[int, ...]) -> str:
    digest = hashlib.sha256(_raw(path)).hexdigest()
    if _file_version(path) != version:
        raise ValueError("profile changed during verification")
    return digest


def _entries(root: Path) -> list:
    try:
        raw = _read_regular(root / _INDEX, 128 << 10)
    except FileNotFoundError:
        return []
    lines = raw.splitlines()
    if len(raw) > 128 << 10 or len(lines) > 16:
        raise ValueError("profile index exceeds its limit")
    return [json.loads(line) for line in lines]


def _kind(cat: str) -> str:
    if "user_annotation" in cat:
        return "stage"
    return "gpu" if cat == "kernel" or cat.startswith("gpu_") else "cpu"


def _duration(e: object) -> bool:
    if not isinstance(e, dict) or e.get("ph") != "X":
        return False
    t, d = e.get("ts"), e.get("dur")
    return (type(t) in (float, int) and type(d) in (float, int)
            and -1e18 < t < 1e18 and 0 < d < 1e18 and t + d > t)


def _lane(e: dict) -> tuple:
    # pid/tid may be strings in Chrome traces; do not retain arbitrary nested metadata.
    return (_kind(str(e.get("cat", ""))), str(e.get("pid", "?"))[:48], str(e.get("tid", "?"))[:48])


class _TraceReader:
    """Incremental JSON reader. Decode one top-level field or trace event at a time."""

    def __init__(self, stream):
        self.stream = stream
        self.buf = ""
        self.pos = 0
        self.read_chars = 0
        self.decoder = json.JSONDecoder()

    def more(self):
        self.buf = self.buf[self.pos:]
        self.pos = 0
        chunk = self.stream.read(65536)
        self.read_chars += len(chunk)
        if self.read_chars > 1 << 30 or len(self.buf) > 8 << 20:
            raise ValueError("decoded profile or single entry exceeds its limit")
        self.buf += chunk
        return bool(chunk)

    def peek(self):
        while True:
            while self.pos < len(self.buf) and self.buf[self.pos].isspace():
                self.pos += 1
            if self.pos < len(self.buf):
                return self.buf[self.pos]
            if not self.more():
                return ""

    def token(self, expected):
        if self.peek() != expected:
            raise ValueError("invalid Chrome trace JSON")
        self.pos += 1

    def value(self):
        if not self.peek():
            raise ValueError("truncated profile")
        while True:
            try:
                value, stop = self.decoder.raw_decode(self.buf, self.pos)
                if stop < len(self.buf) or not isinstance(value, (int, float)):
                    self.pos = stop
                    return value
            except json.JSONDecodeError:
                pass
            if not self.more():
                value, self.pos = self.decoder.raw_decode(self.buf, 0)
                return value


def _events(stream):
    r = _TraceReader(stream)
    wrapped = r.peek() == "{"
    if wrapped:
        r.token("{")
        while r.peek() != "}":
            key = r.value()
            r.token(":")
            if key == "traceEvents":
                break
            r.value()
            if r.peek() == "}":
                break
            r.token(",")
    r.token("[")
    count = 0
    while r.peek() != "]":
        count += 1
        if count > 2_000_000:
            raise ValueError("profile exceeds two million trace events")
        yield r.value()
        if r.peek() == "]":
            break
        r.token(",")
        if r.peek() == "]":
            raise ValueError("trailing comma in trace event array")
    r.token("]")
    if wrapped:
        while r.peek() == ",":
            r.token(",")
            r.value()
            r.token(":")
            r.value()
        r.token("}")
    if r.peek():
        raise ValueError("unexpected trailing profile data")


def _compile(raw: bytes, compressed: bool) -> tuple[dict, bytes]:
    source = io.BytesIO(raw)
    binary = gzip.GzipFile(fileobj=source) if compressed else source
    names, lanes, rows = {}, {}, []
    with io.TextIOWrapper(binary, encoding="utf-8-sig") as stream:
        for e in _events(stream):
            if not _duration(e):
                continue
            identity = _lane(e)
            if identity not in lanes and len(lanes) >= _MAX_LANES:
                raise ValueError("profile exceeds 512 lanes")
            name = str(e.get("name", "unnamed"))
            rows.append((lanes.setdefault(identity, len(lanes)), names.setdefault(name, len(names)),
                         e["ts"], e["dur"]))
    if not rows:
        raise ValueError("trace has no complete duration events")
    start = min(t for _, _, t, _ in rows)
    end = max(t + d for _, _, t, d in rows)
    span = end - start
    lane_names, event_names = list(lanes), list(names)

    # Only sampled events and the top GPU statistics need overview labels.
    @lru_cache(maxsize=None)
    def overview_name(index: int) -> dict:
        name = event_names[index]
        if len(name) <= 220:
            return {"name": name}
        digest = hashlib.sha256(name.encode("utf-8", errors="surrogatepass")).hexdigest()
        return {"name": name[:145] + "…" + name[-60:] + " · " + digest[:10], "name_sha256": digest}

    counts = Counter(row[0] for row in rows)
    keep = {i for kind in ("stage", "gpu", "cpu")
            for i in sorted((j for j in counts if lane_names[j][0] == kind),
                            key=lambda j: (-counts[j], j))[:7]}
    tracks = {}
    gpu_time, gpu_calls = Counter(), Counter()
    for i, (lane_idx, name_idx, ts, dur) in enumerate(rows):
        kind, pid, tid = lane_names[lane_idx]
        lane = (kind, pid, tid) if lane_idx in keep else (kind, "*", "*")
        if lane not in tracks:
            tracks[lane] = ([0] * (_BINS + 1), [])
        bins, longest = tracks[lane]
        lo = max(0, min(_BINS - 1, int((ts - start) / span * _BINS)))
        hi = max(lo + 1, min(_BINS, math.ceil((ts + dur - start) / span * _BINS)))
        bins[lo] += 1
        bins[hi] -= 1
        item = (dur, i, ts, name_idx)
        if len(longest) < 80:
            heapq.heappush(longest, item)
        elif item > longest[0]:
            heapq.heapreplace(longest, item)
        if kind == "gpu":
            gpu_time[name_idx] += dur
            gpu_calls[name_idx] += 1
    overview = []
    for (kind, pid, tid), (bins, longest) in sorted(tracks.items()):
        running = 0
        for j in range(_BINS):
            running += bins[j]
            bins[j] = running
        overview.append({"name": f"{kind} {pid}:{tid}" if pid != "*" else f"{kind} (other lanes)",
                         "kind": kind, "bins": bins[:-1],
                         "events": [{**overview_name(k), "ts_us": t, "dur_us": d}
                                    for d, _, t, k in sorted(longest, key=lambda x: x[2])]})
    summary = {"start_us": start, "duration_us": span, "event_count": len(rows),
               "displayed_event_count": sum(len(t["events"]) for t in overview), "tracks": overview,
               "stats": [{**overview_name(k), "total_us": us, "count": gpu_calls[k]}
                         for k, us in gpu_time.most_common(10)]}
    full = {"names": event_names, "lanes": [{"name": f"{k} {p}:{t}", "kind": k}
                                            for k, p, t in lane_names], "events": rows}
    payload = json.dumps(full, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    if len(payload) > 128 << 20:
        raise ValueError("compiled event table exceeds its limit")
    return summary, gzip.compress(payload, compresslevel=3, mtime=0)


def _put(path, data):
    # Content-addressed artifacts are never replaced. Publish by hard link.
    tmp = path.with_name("." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("xb") as f:
            f.write(data)
        try:
            os.link(tmp, path)
        except FileExistsError:
            if _read_regular(path, len(data)) != data:
                raise ValueError("existing profile artifact does not match its digest") from None
    finally:
        tmp.unlink(missing_ok=True)


def attach_profile(root: Path, *, capture_id: str, source: str, review: Path) -> dict:
    root = Path(root).resolve()
    if not (root / "campaign.json").is_file() or not _ID.fullmatch(capture_id):
        raise ValueError("expected a campaign and a safe profile ID")
    entries = _entries(root)
    if len(entries) >= 16 or any(e.get("id") == capture_id for e in entries):
        raise ValueError("profile limit reached or ID already in use")
    raw_review = _read_regular(review, 16384)
    if len(raw_review) > 16384:
        raise ValueError("profile review exceeds its limit")
    meta = _review(json.loads(raw_review))
    raw = _raw(_profile_path(root, source))
    digest = hashlib.sha256(raw).hexdigest()
    try:
        summary, full = _compile(raw, source.endswith(".gz"))
    except EOFError as exc:
        raise ValueError("truncated compressed profile") from exc
    compact_hash = hashlib.sha256(full).hexdigest()
    compact = f"profiles/{compact_hash}.events.json.gz"
    _put(root / compact, full)
    details = {**meta, "id": capture_id, **summary,
               "source": {"path": source, "sha256": digest, "events_path": compact,
                          "events_sha256": compact_hash}}
    body = json.dumps(details, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    summary_hash = hashlib.sha256(body).hexdigest()
    _put(root / "profiles" / f"{summary_hash}.summary.json", body)
    entry = {"id": capture_id, "summary_sha256": summary_hash}
    _append_index(root / _INDEX, (json.dumps(entry) + "\n").encode())
    return entry


def _verified_summary(root, entry):
    digest = entry["summary_sha256"]
    if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
        raise ValueError("invalid summary digest")
    if not _ID.fullmatch(entry["id"]) or (root / "profiles").resolve() != root / "profiles":
        raise ValueError("invalid profile reference")
    raw = _read_regular(root / "profiles" / f"{digest}.summary.json", 4 << 20)
    if len(raw) > 4 << 20 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("summary unavailable")
    summary = json.loads(raw)
    if summary["id"] != entry["id"]:
        raise ValueError("profile identity mismatch")
    _review_history(summary)
    ref = summary["source"]
    if (not isinstance(ref["events_sha256"], str)
            or not re.fullmatch("[0-9a-f]{64}", ref["events_sha256"])
            or ref["events_path"] != f"profiles/{ref['events_sha256']}.events.json.gz"):
        raise ValueError("invalid compact trace")
    ref["events_url"] = "/api/profile-events/" + ref["events_sha256"]
    return summary


def read_profiles(root: Path, *, events_digest: str | None = None) -> tuple[list[dict], list[str]]:
    """Verify registered captures. Rehash the selected source when opening its event table."""
    captures, missing = [], []
    root = root.resolve()
    try:
        entries = _entries(root)
    except (OSError, ValueError, TypeError, RecursionError):
        return [], ["profile index unavailable"]
    for entry in entries:
        try:
            summary = _verified_summary(root, entry)
            ref = summary["source"]
            if events_digest is not None and ref["events_sha256"] != events_digest:
                continue
            path = _profile_path(root, ref["path"])
            if events_digest is None:
                actual = _overview_digest(path, _file_version(path))
            else:
                actual = hashlib.sha256(_raw(path)).hexdigest()
            if actual != ref["sha256"]:
                raise ValueError("raw profile hash mismatch")
            captures.append(summary)
            if events_digest is not None:
                break
        except (OSError, ValueError, KeyError, TypeError, EOFError, RecursionError):
            label = entry.get("id") if isinstance(entry, dict) else None
            missing.append(label[:120] if isinstance(label, str) else "invalid profile")
    return captures, missing


def profile_event_table(root: Path, digest: str) -> bytes | None:
    """Only serve the registered, hash-verified projection, never raw trace arguments."""
    profiles, _ = read_profiles(root, events_digest=digest)
    if profiles:
        try:
            raw = _raw(_profile_path(root.resolve(), f"profiles/{digest}.events.json.gz"))
            if hashlib.sha256(raw).hexdigest() == digest:
                return raw
        except (OSError, ValueError):
            pass
    return None
