"""Project one round's observed knowledge events into its local campaign."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .campaign_records import _identifier, _round_records
from .codex_search import read_window
from .dashboard_data import _inside, _object
from .knowledge_capture import MAX_CONTEXT_CAPTURE_BYTES, verify_capture
from .optimization_log import STAGES, read_latest_log


def _capture(root, campaign_id, context_id):
    _identifier(context_id, "context ID")
    path = root / "knowledge" / f"{context_id}.json"
    if not _inside(root, path):
        raise ValueError("capture escapes the campaign")
    with path.open("rb") as stream:
        raw = stream.read(MAX_CONTEXT_CAPTURE_BYTES + 1)
    doc, state = verify_capture(raw)
    if not doc or doc["campaign_id"] != campaign_id or doc["context_id"] != context_id:
        raise ValueError(f"invalid or mismatched campaign capture ({state})")
    resources = {c["ref"]: [r["path"] for r in c["resources"]] for c in doc["contexts"]}
    if any(not isinstance(item.get("ref"), str) or not isinstance(item.get("revision"), str)
           for item in doc["items"]):
        raise ValueError("capture item is missing its ref or revision")
    materials = [{"ref": item["ref"], "revision": item["revision"],
                  "resources": resources.get(item["ref"], [])} for item in doc["items"]]
    return {"action": "search", "tool": "collect", "context_id": context_id,
            "source": path.relative_to(root).as_posix(), "request": doc["request"],
            "selection": doc.get("selection"), "materials": materials,
            "sha256": hashlib.sha256(raw).hexdigest()}


def _use(materials, ref, status, evidence):
    if ref not in materials:
        raise ValueError("use evidence must name a material observed in this round")
    item = materials[ref]
    evidence = {"use": status, **evidence}
    history = item.setdefault("evidence", [])
    if evidence not in history:
        history.append(evidence)
    states = {entry["use"] for entry in history}
    item["use"] = status if len(states) == 1 else "used_and_rejected"


def _log_uses(root, campaign_id, number, captures, materials):
    if not captures:
        return
    log, versions, state = read_latest_log(root)
    if state == "not_recorded":
        return
    if not log or log["campaign_id"] != campaign_id:
        raise ValueError(f"cannot correlate campaign optimization log ({state})")
    iteration = next((i for i in log["iterations"] if i["round"] == number), {})
    for index, entry in enumerate(log["knowledge"]):
        key = entry["context_id"]
        if key not in iteration.get("context_ids", []) or key not in captures:
            continue
        capture = captures[key]
        if capture["sha256"] != entry["sha256"].lower():
            raise ValueError("optimization log and selected capture revisions differ")
        valid = {m["ref"] for m in capture["materials"]}
        source = f"{versions[-1]['path']}#/knowledge/{index}"
        for status, refs in (("used", entry["used_refs"]),
                             ("rejected", [r["ref"] for r in entry.get("rejected_refs", [])])):
            for ref in refs:
                if ref not in valid:
                    raise ValueError("optimization log cites a material absent from its capture")
                _use(materials, ref, status, {"source": source, "context_id": key,
                                              "stage": entry["stage"]})


def _write(root, record):
    directory = root / "search"
    if not _inside(root, directory):
        raise ValueError("search directory escapes the campaign")
    directory.mkdir(exist_ok=True)
    target = directory / f"round-{record['round']}.json"
    window, contexts = record["trace"], set(record["context_ids"])
    # As with campaign record, callers serialize writes to a campaign.
    for path in directory.glob("round-*.json"):
        old, state = _object(path, root)
        if state != "present":
            raise ValueError("existing search record is unreadable")
        previous = old["trace"]
        if path == target:
            if previous and (not window or previous["session"] != window["session"]
                             or previous["lines"][0] != window["lines"][0]
                             or previous["lines"][1] > window["lines"][1]):
                raise ValueError("reimport must preserve the original round window")
            if not set(old["context_ids"]) <= contexts:
                raise ValueError("reimport must preserve the round's captures")
            # A closing import may add the final reply or a run to an earlier
            # snapshot. Keep previously reviewed decisions for this same window.
            for ref, material in old["materials"].items():
                for evidence in material.get("evidence", []):
                    if evidence.get("basis") != "caller_reviewed":
                        continue
                    current = record["materials"].get(ref, {})
                    if evidence not in current.get("evidence", []):
                        _use(record["materials"], ref, evidence["use"], evidence)
            record["observed"]["used"] = sum(
                m["use"] in ("used", "used_and_rejected") for m in record["materials"].values()
            )
            if old == record:
                return target
            continue
        if contexts.intersection(old["context_ids"]):
            raise ValueError("capture is already associated with another round")
        if window and previous and window["session"] == previous["session"]:
            lo, hi = previous["lines"]
            if max(lo, window["lines"][0]) <= min(hi, window["lines"][1]):
                raise ValueError("trace window overlaps another round")
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.close()
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return target


def _round_candidates(root, number):
    rounds_path = root / "rounds.jsonl"
    if not _inside(root, rounds_path):
        raise ValueError("rounds file escapes the campaign")
    candidates = next((r["candidates"] for r in _round_records(rounds_path)
                       if r["round"] == number), [])
    runs = []
    for candidate in candidates:
        _identifier(candidate, "candidate")
        path = root / "candidates" / candidate / "candidate.json"
        data, status = _object(path, root)
        if (status != "present" or data.get("round") != number
                or data.get("candidate_id") != candidate):
            raise ValueError("invalid candidate association for the round")
        run_id = _identifier(data.get("run_id"), "run ID")
        evaluation_path = root / "runs" / run_id / "evaluation.json"
        evaluation, result_state = _object(evaluation_path, root)
        verdict = evaluation.get("verdict")
        runs.append({"candidate": candidate, "run_id": run_id,
                     "source": path.relative_to(root).as_posix(),
                     "evaluation": evaluation_path.relative_to(root).as_posix()
                     if result_state == "present" else None,
                     "verdict": verdict if verdict in ("PASS", "FAIL", "INCONCLUSIVE") else None})
    return runs


def import_search(root: Path, *, number: int, trace=None, lines=None, knowledge_root=None,
                  context_ids=(), used=(), rejected=(), complete=False, stage=None):
    root = root.resolve()
    campaign, state = _object(root / "campaign.json", root)
    if state != "present" or number < 1:
        raise ValueError("expected an existing campaign and a positive round number")
    campaign_id = _identifier(campaign.get("campaign_id"), "campaign ID")
    trace_inputs = (trace is not None, lines is not None, knowledge_root is not None)
    if any(trace_inputs) and not all(trace_inputs):
        raise ValueError("--trace, --lines and --knowledge-root must be supplied together")
    if stage is not None and stage not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    if complete and not trace and not context_ids:
        raise ValueError("complete coverage needs a trace window or a capture")
    window, events, decisions, uncertain = None, [], set(), []
    if trace:
        window, events, decisions, uncertain = read_window(trace, lines, knowledge_root)
    captures = {key: _capture(root, campaign_id, key) for key in dict.fromkeys(context_ids)}
    events.extend(captures.values())
    materials = {}
    hits = set()
    searches = hit_count = 0
    for event in events:
        refs = {m["ref"] for m in event["materials"]}
        if event["action"] == "search":
            searches += 1
            hit_count += len(refs)
            hits.update(refs)
        for ref in sorted(refs):
            materials.setdefault(ref, {"use": "unknown"})
    _log_uses(root, campaign_id, number, captures, materials)
    for status, entries in (("used", used), ("rejected", rejected)):
        for ref, line in entries:
            if int(line) not in decisions:
                raise ValueError("decision line must reference an assistant message in this round")
            _use(materials, ref, status, {"decision_line": int(line), "basis": "caller_reviewed"})
    observed = {"searches": searches, "hits": hit_count, "unique_hits": len(hits),
                "used": sum(m["use"] in ("used", "used_and_rejected") for m in materials.values())}
    coverage = "complete" if complete and not uncertain else "partial"
    if not window and not captures:
        coverage = "missing"
    record = {"schema_version": 1, "campaign_id": campaign_id, "round": number,
              "stage": stage, "trace": window, "context_ids": list(captures), "coverage": coverage,
              "unresolved_command_lines": uncertain, "events": events, "materials": materials,
              "observed": observed, "counts": observed if coverage == "complete" else None,
              "candidates": _round_candidates(root, number)}
    return _write(root, record)
