"""Project one round's observed knowledge events into its local campaign."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .campaign_records import _identifier, _round_records
from .capture_delivery import capture_event, capture_return_texts, load_campaign_capture
from .codex_search import read_window
from .dashboard_data import _inside, _object
from .optimization_log import STAGES, read_latest_log
from .search_archive import read_archive_review, reviewed_uses


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


def _caller_use(materials, events, ref, status, evidence):
    """Count a caller's decision only after an observed material in this window."""
    if ref not in materials:
        raise ValueError("use evidence must name a material observed in this round")
    observed_lines = [
        event["trace_line"] for event in events
        if type(event.get("trace_line")) is int
        and any(material["ref"] == ref for material in event["materials"])
    ]
    if any(line < evidence["decision_line"] for line in observed_lines):
        _use(materials, ref, status, {key: value for key, value in evidence.items()
                                     if key != "reason"})
    elif observed_lines and evidence.get("reason") not in (
        "observation_order_unknown", "no_prior_ordered_observation",
    ):
        raise ValueError("decision must follow an observation of the cited material")
    else:
        # A capture has no trace position. A later observation also cannot
        # settle an already accepted declaration about an earlier decision.
        reason = "no_prior_ordered_observation" if observed_lines else "observation_order_unknown"
        declaration = {"use": status, **evidence, "reason": reason}
        declarations = materials[ref].setdefault("declarations", [])
        if declaration not in declarations:
            declarations.append(declaration)


def _atomic_json(target, record):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.close()
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def _log_uses(root, campaign_id, number, captures, materials, *, archive=False):
    if not captures:
        return []
    log, versions, state = read_latest_log(root)
    if state == "not_recorded":
        return []
    if not log or log["campaign_id"] != campaign_id:
        raise ValueError(f"cannot correlate campaign optimization log ({state})")
    iteration = next((i for i in log["iterations"] if i["round"] == number), {})
    declarations = []
    for index, entry in enumerate(log["knowledge"]):
        key = entry["context_id"]
        if key not in iteration.get("context_ids", []) or key not in captures:
            continue
        capture = captures[key]
        if capture["sha256"] != entry["sha256"].lower():
            raise ValueError("optimization log and selected capture revisions differ")
        material_rows = {m["ref"]: m for m in capture["materials"]}
        resources = {ref: material.get("resources", [])
                     for ref, material in material_rows.items()}
        source = f"{versions[-1]['path']}#/knowledge/{index}"
        for status, refs in (("used", entry["used_refs"]),
                             ("rejected", [r["ref"] for r in entry.get("rejected_refs", [])])):
            for ref in refs:
                if ref not in resources and not archive:
                    raise ValueError("optimization log cites a material absent from its capture")
                material = material_rows.get(ref)
                if archive:
                    delivery = capture.get("delivery", {})
                    visible = any(isinstance(row, dict) and row.get("ref") == ref
                                  for row in delivery.get("visible_resources", []))
                    declarations.append({
                        "ref": ref, "use": status, "basis": "optimization_log_declaration",
                        "source": source, "log_sha256": versions[-1].get("sha256"),
                        "context_id": key, "capture_source": capture["source"],
                        "capture_sha256": capture["sha256"], "stage": entry["stage"],
                        "preparation_state": (material.get("preparation_state", "prepared")
                                               if material else "not_in_capture"),
                        "delivery_state": "visible" if visible else "unknown",
                    })
                    continue
                evidence = {"source": source, "context_id": key, "stage": entry["stage"]}
                if status == "used" and not resources[ref]:
                    conflict = {**evidence, "claimed_use": status, "reason": "context_omitted"}
                    conflicts = materials[ref].setdefault("conflicts", [])
                    if conflict not in conflicts:
                        conflicts.append(conflict)
                else:
                    _use(materials, ref, status, evidence)
    return declarations


def _prepare_record(root, record):
    """Validate round ownership and restore saved claims before either projection is written."""
    directory = root / "search"
    if not _inside(root, directory):
        raise ValueError("search directory escapes the campaign")
    directory.mkdir(exist_ok=True)
    target = directory / f"round-{record['round']}.json"
    window, contexts = record["trace"], set(record["context_ids"])
    supplied_decisions = {
        (ref, evidence["decision_line"])
        for ref, material in record["materials"].items()
        for evidence in [*material.get("evidence", []), *material.get("declarations", [])]
        if evidence.get("basis") == "caller_reviewed"
    }
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
                for evidence in [*material.get("evidence", []), *material.get("declarations", [])]:
                    if evidence.get("basis") != "caller_reviewed":
                        continue
                    if (ref, evidence["decision_line"]) in supplied_decisions:
                        # Explicit flags correct this decision; other decisions remain.
                        continue
                    current = record["materials"].get(ref, {})
                    if evidence not in current.get("evidence", []):
                        _caller_use(record["materials"], record["events"], ref,
                                    evidence["use"], evidence)
            record["observed"]["used"] = _used_count(record["materials"])
            if old == record:
                return target
            continue
        if contexts.intersection(old["context_ids"]):
            raise ValueError("capture is already associated with another round")
        if window and previous and window["session"] == previous["session"]:
            lo, hi = previous["lines"]
            if max(lo, window["lines"][0]) <= min(hi, window["lines"][1]):
                raise ValueError("trace window overlaps another round")
            event_ids = {event["event_id"] for event in record["events"] if "event_id" in event}
            if any(event.get("event_id") in event_ids for event in old["events"]):
                raise ValueError("command event is already associated with another round")
    return target


def _write_archive(root, record):
    """Atomically write a portable v2 projection beside the local v1 ledger."""
    directory = root / "search" / "archive"
    if not _inside(root, directory):
        raise ValueError("search archive directory escapes the campaign")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"round-{record['round']}.json"
    if target.exists():
        old, state = _object(target, root)
        if state != "present" or old.get("schema_version") != 2:
            raise ValueError("existing archive record has invalid content or version")
        if old == record:
            return target
    _atomic_json(target, record)
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
                     "evaluation_state": result_state,
                     "evaluation": evaluation_path.relative_to(root).as_posix()
                     if result_state == "present" else None,
                     "verdict": verdict if verdict in ("PASS", "FAIL", "INCONCLUSIVE") else None})
    return runs


def _observations(events, *, archive=False):
    """Count tool hits separately from what appeared in a model-facing return."""
    materials, hits = {}, set()
    counts = {"searches": 0, "hits": 0, "unique_hits": 0, "used": 0}
    for event in events:
        refs = {row["ref"] for row in event["materials"]}
        if event["action"] == "search":
            counts["searches"] += 1
            counts["hits"] += len(refs)
            hits.update(refs)
        for ref in sorted(refs):
            materials.setdefault(ref, {"use": "unknown"})
        if archive:
            delivery = event["delivery"]
            passages = {row["ref"] for row in delivery.get("passages", [])}
            visible_refs = set(delivery.get("visible_refs", []))
            resources = {row["ref"] for row in delivery.get("visible_resources", [])}
            for ref in refs:
                material = materials[ref]
                state = material.setdefault("delivery_state", "unknown")
                if ref in passages or ref in resources:
                    material["delivery_state"] = "visible"
                elif ref in visible_refs and state == "unknown":
                    material["delivery_state"] = "ref_visible"
    counts["unique_hits"] = len(hits)
    return materials, counts


def _used_count(materials):
    return sum(m["use"] in ("used", "used_and_rejected") for m in materials.values())


def import_search(root: Path, *, number: int, trace=None, lines=None, knowledge_root=None,
                  context_ids=(), used=(), rejected=(), complete=False, stage=None,
                  archive_review=None):
    root = root.resolve()
    campaign, state = _object(root / "campaign.json", root)
    if state != "present" or number < 1:
        raise ValueError("expected an existing campaign and a positive round number")
    campaign_id = _identifier(campaign.get("campaign_id"), "campaign ID")
    trace_inputs = (trace is not None, lines is not None, knowledge_root is not None)
    if any(trace_inputs) and not all(trace_inputs):
        raise ValueError("--trace, --lines and --knowledge-root must be supplied together")
    review = read_archive_review(archive_review) if archive_review is not None else None
    if stage is not None and stage not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    if complete and not trace and not context_ids:
        raise ValueError("complete coverage needs a trace window or a capture")
    capture_ids = list(dict.fromkeys(context_ids))
    if review is not None and not trace and (review["decisions"] or review["capture_returns"]):
        raise ValueError("archive decisions and capture_returns need a trace window")
    if review is not None and not trace and not capture_ids:
        raise ValueError("archive review needs a trace window or a verified capture")
    if review is not None and set(review["capture_returns"]) - set(capture_ids):
        raise ValueError("archive review capture_returns must name selected context IDs")
    capture_return_lines = list(review["capture_returns"].values()) if review else []
    if len(set(capture_return_lines)) != len(capture_return_lines):
        raise ValueError("capture return line is ambiguous across selected contexts")
    indexer_decisions = {key: [] for key in capture_ids}
    command_decisions = []
    if review:
        context_by_return = {line: key for key, line in review["capture_returns"].items()}
        for item in review["decisions"]:
            context_id = context_by_return.get(item["event_line"])
            if context_id is not None:
                if "passage_path" not in item:
                    raise ValueError("Indexer review must name the exact captured resource path")
                indexer_decisions[context_id].append(item)
            else:
                command_decisions.append(item)
                if "passage_path" in item:
                    raise ValueError("passage_path is only valid for a verified Indexer return")

    window, events, decisions, uncertain = None, [], {}, []
    if trace:
        window, events, decisions, uncertain, _ = read_window(
            trace, lines, knowledge_root, archive=False)
    capture_inputs = {key: load_campaign_capture(root, campaign_id, key) for key in capture_ids}
    captures = {key: capture_event(key, capture_inputs[key]) for key in capture_ids}
    events.extend(captures.values())
    materials, observed = _observations(events)
    _log_uses(root, campaign_id, number, captures, materials)
    for status, entries in (("used", used), ("rejected", rejected)):
        for ref, line in entries:
            if int(line) not in decisions:
                raise ValueError("decision line must reference an assistant message in this round")
            _caller_use(materials, events, ref, status,
                        {"decision_line": int(line), "basis": "caller_reviewed"})
    observed["used"] = _used_count(materials)
    coverage = "complete" if complete and not uncertain else "partial"
    if not window and not captures:
        coverage = "missing"
    record = {"schema_version": 1, "campaign_id": campaign_id, "round": number,
              "stage": stage, "trace": window, "context_ids": list(captures), "coverage": coverage,
              "unresolved_command_lines": uncertain, "events": events, "materials": materials,
              "observed": observed, "counts": observed if coverage == "complete" else None,
              "candidates": _round_candidates(root, number)}
    target = _prepare_record(root, record)
    if review is None:
        _atomic_json(target, record)
        return target

    selections = {}
    for item in command_decisions:
        selections.setdefault(item["event_line"], []).append((item["ref"], item["passage_line"]))
    archive_events, archive_decisions, archive_uncertain, unresolved_details = [], {}, [], []
    if trace:
        _, archive_events, archive_decisions, archive_uncertain, unresolved_details = read_window(
            trace, lines, knowledge_root, archive=True, selections=selections)
    return_texts = {}
    if review["capture_returns"]:
        return_texts = capture_return_texts(trace, lines, review["capture_returns"], capture_ids)
    archive_captures = {}
    for key in capture_ids:
        return_line = review["capture_returns"].get(key)
        archive_captures[key] = capture_event(
            key, capture_inputs[key], archive=True,
            return_chunks=return_texts.get(key),
            return_line=return_line,
            selected_passages=indexer_decisions[key])
    archive_events.extend(archive_captures.values())
    archive_materials, archive_observed = _observations(archive_events, archive=True)
    declarations = _log_uses(root, campaign_id, number, archive_captures, archive_materials,
                             archive=True)
    for ref, material in record["materials"].items():
        for claim in [*material.get("evidence", []), *material.get("declarations", [])]:
            if claim.get("basis") != "caller_reviewed":
                continue
            line = claim["decision_line"]
            if line not in archive_decisions:
                raise ValueError("decision line must reference an assistant message in this round")
            if ref not in archive_materials:
                raise ValueError("use declaration must name a material observed in this round")
            declarations.append({
                "ref": ref, "use": claim["use"], "basis": "caller_flag_declaration",
                "decision_line": line,
                "delivery_state": archive_materials[ref].get("delivery_state", "unknown"),
            })
    for ref, status, evidence in reviewed_uses(review, archive_events, archive_decisions):
        _use(archive_materials, ref, status, evidence)
    archive_observed["used"] = _used_count(archive_materials)
    archive_coverage = ("complete" if complete and not archive_uncertain and not unresolved_details
                        else "partial")
    archive_record = {
        "schema_version": 2, "campaign_id": campaign_id, "round": number,
        "stage": stage, "task": review["task"], "corpus": review["corpus"],
        "trace": ({"lines": window["lines"], "archive": True} if window else None),
        "context_ids": list(archive_captures), "coverage": archive_coverage,
        "unresolved_command_lines": archive_uncertain,
        "unresolved_details": unresolved_details,
        "events": archive_events, "materials": archive_materials,
        "declarations": declarations, "observed": archive_observed,
        "counts": archive_observed if archive_coverage == "complete" else None,
        "candidates": record["candidates"],
    }
    if review["result_note"] is not None:
        archive_record["result_note"] = review["result_note"]
        archive_record["result_note_basis"] = "caller_reviewed"
    _atomic_json(target, record)
    return _write_archive(root, archive_record)
