"""Read-only retrieval and round-search projection; never rerun historical ranking."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from .dashboard_data import _inside, _relative_location, _text
from .optimization_log import _IDENTIFIER, _unique

_MAX_BYTES = 4 * 1024 * 1024


def public_value(value):
    """Sanitize even verified records. Verification does not authorize publication."""
    if isinstance(value, str):
        # Keep public source locators without credentials, queries or fragments.
        if re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+/(?:blob|tree|commit)/[\w./-]+",
                        value):
            return value
        return _text(value, "", limit=None)
    if isinstance(value, list):
        return [public_value(item) for item in value]
    if isinstance(value, dict):
        return {public_value(key): public_value(item) for key, item in value.items()}
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def retrieval_view(capture):
    """Explain only recorded facts, including unknown historical entry points."""
    observation = capture.get("retrieval")
    valid = (isinstance(observation, dict) and observation.get("schema_version") == 1
             and isinstance(observation.get("request"), dict)
             and isinstance(observation.get("selection"), dict)
             and isinstance(observation.get("counts"), dict)
             and isinstance(observation.get("calls"), list)
             and all(isinstance(call, str) for call in observation["calls"])
             and isinstance(observation.get("items"), list)
             and all(isinstance(item, dict) and isinstance(item.get("ref"), str)
                     for item in observation["items"]))
    if valid:
        result = public_value(observation)
        result["state"] = "recorded"
        return result
    selection = capture.get("selection")
    selection = selection if isinstance(selection, dict) else {}
    request = capture.get("request")
    request = request if isinstance(request, dict) else {}
    # These fields record behavior; method defaults alone are not evidence of execution.
    applied = selection.get("ranking_applied")
    state = ("applied" if applied is True else
             "explicit_ids" if applied is False and request.get("ids") else
             "not_requested" if "relevance" in request and request["relevance"] is None else
             "unknown")
    return public_value({
        "state": "unsupported_version" if observation else "not_recorded",
        "entrypoint": "unknown", "calls": [], "request": request,
        "selection": {**selection, "state": state},
        "counts": {"matched": selection.get("matched_count"),
                   "returned": len(capture.get("items", []))},
        "items": [], "candidate_details": "not_recorded",
        "assembly": ("performed" if capture.get("context_budget") is not None else
                     "not_requested" if "context_bytes" in request
                     and request["context_bytes"] is None else "unknown"),
    })


def _read(root, path):
    if not _inside(root, path) or path.is_symlink():
        return None, "unsafe_path", None
    try:
        with path.open("rb") as stream:
            raw = stream.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            return None, "too_large", None
        document = json.loads(raw, object_pairs_hook=_unique)
        if not isinstance(document, dict):
            return None, "invalid_format", None
        return document, "present", hashlib.sha256(raw).hexdigest()
    except FileNotFoundError:
        return None, "file_absent", None
    except (OSError, ValueError, RecursionError):
        return None, "invalid_format", None


def _validate(record, campaign_id, number, version):
    if type(record.get("schema_version")) is not int or record["schema_version"] != version:
        return "unsupported_version"
    if (record.get("campaign_id") != campaign_id or type(record.get("round")) is not int
            or record["round"] != number):
        return "identity_mismatch"
    if record.get("coverage") not in ("complete", "partial", "missing"):
        return "invalid_coverage"
    for key in ("events", "context_ids", "candidates"):
        if not isinstance(record.get(key), list):
            return "invalid_format"
    if (any(not isinstance(value, str) for value in record["context_ids"])
            or len(set(record["context_ids"])) != len(record["context_ids"])
            or not isinstance(record.get("materials"), dict)):
        return "invalid_format"
    for key in ("counts", "observed"):
        counts = record.get(key)
        if counts is None and key == "counts" and record["coverage"] != "complete":
            continue
        if not isinstance(counts, dict) or any(
                type(counts.get(k)) is not int or counts[k] < 0
                for k in ("searches", "hits", "unique_hits", "used")):
            return "invalid_counts"
    if record["coverage"] != "complete" and record.get("counts") is not None:
        return "invalid_counts"
    if any(not isinstance(m, dict) or m.get("use") not in
           ("unknown", "used", "rejected", "used_and_rejected")
           for m in record["materials"].values()):
        return "invalid_materials"
    for material in record["materials"].values():
        for key in ("evidence", "declarations", "conflicts"):
            if not isinstance(material.get(key, []), list) or any(
                    not isinstance(e, dict) for e in material.get(key, [])):
                return "invalid_materials"
    if any(not isinstance(e, dict) or not isinstance(e.get("materials"), list)
           or any(not isinstance(m, dict) or not isinstance(m.get("ref"), str)
                  for m in e["materials"]) for e in record["events"]):
        return "invalid_events"
    for event in record["events"]:
        delivery = event.get("delivery", {})
        if (not isinstance(delivery, dict)
                or not isinstance(delivery.get("passages", []), list)
                or any(not isinstance(p, dict) for p in delivery.get("passages", []))
                or ("context_id" in event and (
                    not isinstance(event["context_id"], str)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",
                                        event["context_id"])
                    or not isinstance(event.get("sha256"), str)
                    or not re.fullmatch(r"[a-f0-9]{64}", event["sha256"])))):
            return "invalid_events"
    if version == 2:
        from .search_archive import _REVISION

        corpus = record.get("corpus")
        if (not isinstance(corpus, dict)
                or not isinstance(corpus.get("revision"), str)
                or not _REVISION.fullmatch(corpus["revision"])
                or not re.fullmatch(r"[\w.-]+/[\w.-]+", str(corpus.get("repository", "")))
                or (corpus.get("root") != "." and not _relative_location(corpus.get("root")))
                or not isinstance(record.get("declarations"), list)):
            return "invalid_source"
        if any(not isinstance(d, dict) or not isinstance(d.get("ref"), str)
               for d in record["declarations"]):
            return "invalid_declarations"
    return "recorded"


def _evidence_state(ref, evidence, events, version):
    if version == 1:
        return "local_v1"  # The old use field is never upgraded to archive-reviewed use.
    if evidence.get("basis") != "archive_reviewed":
        return "unsupported_basis"
    matches = [e for e in events if e.get("id") == evidence.get("event_id")]
    if len(matches) != 1:
        return "event_identity_mismatch"
    event = matches[0]
    delivery = event.get("delivery", {})
    passages = delivery.get("passages", [])
    if not any(p.get("ref") == ref and p.get("line") == evidence.get("passage_line")
               and p.get("text") == evidence.get("passage_text")
               and p.get("path") == evidence.get("passage_path") for p in passages):
        return "passage_mismatch"
    # Reuse the importer's association checks. This verifies the saved relationship,
    # not the unavailable original conversation or authenticity of caller review.
    from .search_archive import reviewed_uses

    decision = {"ref": ref, "use": evidence.get("use"), "event_line": event.get("trace_line"),
                "passage_line": evidence.get("passage_line"),
                "decision_line": evidence.get("decision_line"),
                "decision_quote": evidence.get("decision_quote")}
    if "passage_path" in evidence:
        decision["passage_path"] = evidence["passage_path"]
    try:
        list(reviewed_uses({"decisions": [decision]}, events,
                           {decision["decision_line"]: decision["decision_quote"]}))
    except (ValueError, TypeError, KeyError, AttributeError):
        return "invalid_association"
    return "archive_reviewed"


def read_searches(root: Path, campaign_id, rows, retrievals):
    """Read v1/v2 side by side; do not sum alternative projections of one round."""
    results = []
    directories = [(root / "search", 1), (root / "search/archive", 2)]
    for directory, version in directories:
        if not _inside(root, directory) or directory.is_symlink():
            results.append({"path": "search", "state": "unsafe_path", "schema_version": version})
            continue
        for path in sorted(directory.glob("round-*.json")):
            match = re.fullmatch(r"round-([1-9]\d*)\.json", path.name)
            if not match:
                continue
            number = int(match[1])
            record, state, digest = _read(root, path)
            view = {"round": number, "schema_version": version,
                    "path": path.relative_to(root).as_posix(), "sha256": digest}
            state = _validate(record, campaign_id, number, version) if record else state
            if state != "recorded":
                results.append({**view, "state": state})
                continue
            issues, events, materials = [], [], []
            captures = {c["context_id"]: c for c in retrievals}
            for event in record["events"]:
                context_id = event.get("context_id")
                event_state = "recorded"
                if context_id:
                    capture = captures.get(context_id)
                    if not capture:
                        from .optimization_story import _capture

                        capture = _capture(root, {
                            "context_id": context_id, "sha256": event.get("sha256", ""),
                            "stage": "knowledge", "purpose": "", "used_refs": [], "takeaways": [],
                        }, campaign_id) if re.fullmatch(r"[\w.-]{1,128}", context_id) else None
                        if capture:
                            retrievals.append(capture)
                            captures[context_id] = capture
                    if (not capture or capture.get("state") != "verified"
                            or capture.get("expected_sha256") != event.get("sha256")
                            or event.get("source") != f"knowledge/{context_id}.json"
                            or context_id not in record["context_ids"]):
                        event_state = "capture_mismatch"
                    else:
                        revisions = {m["ref"]: m.get("revision") for m in capture["items"]}
                        if any(revisions.get(m["ref"]) != m.get("revision")
                               for m in event["materials"]):
                            event_state = "revision_mismatch"
                events.append(public_value({key: event[key] for key in (
                    "id", "action", "tool", "context_id", "source", "sha256", "request",
                    "selection", "materials", "delivery", "trace_line") if key in event})
                              | {"state": event_state})
                if event_state != "recorded":
                    issues.append(event_state)
            for ref, material in record["materials"].items():
                evidence = [{**public_value(e), "state": _evidence_state(
                    ref, e, record["events"], version)} for e in material.get("evidence", [])
                            if isinstance(e, dict)]
                for entry in evidence:
                    invalid_event = next((event for event in events if event.get("id") == entry.get(
                        "event_id") and event["state"] != "recorded"), None)
                    if invalid_event:
                        entry["state"] = invalid_event["state"]
                issues.extend(e["state"] for e in evidence
                              if e["state"] not in ("local_v1", "archive_reviewed"))
                materials.append({"ref": public_value(ref), **public_value(material),
                                  "evidence": evidence})
            links = []
            for candidate in record["candidates"]:
                if not isinstance(candidate, dict):
                    issues.append("invalid_candidate")
                    continue
                matches = [row for row in rows if row.get("run_id")
                    and row.get("candidate_id") == candidate.get(
                    "candidate") and row.get("run_id") == candidate.get("run_id")
                    and row.get("round") == number]
                if len(matches) == 1 and candidate.get("source") != matches[0].get(
                        "artifacts", {}).get("candidate_metadata", {}).get("path"):
                    matches = []
                link = {"candidate_id": public_value(candidate.get("candidate")),
                        "run_id": public_value(candidate.get("run_id")), "round": number,
                        "state": "linked" if len(matches) == 1 else "identity_mismatch"}
                if len(matches) == 1:
                    link["experiment_id"] = matches[0].get("experiment_id")
                else:
                    issues.append("candidate_run_mismatch")
                links.append(link)
            declarations = []
            # Top-level declarations belong to v2; v1 records use material evidence.
            for declaration in record["declarations"] if version == 2 else []:
                declaration_state = "caller_declaration"
                if declaration.get("basis") == "optimization_log_declaration":
                    locator = declaration.get("source")
                    source = locator.partition("#")[0] if isinstance(locator, str) else ""
                    context_id = declaration.get("context_id")
                    if (not re.fullmatch(r"optimization-log-v[1-9]\d*\.json", source)
                            or not isinstance(context_id, str)
                            or not _IDENTIFIER.fullmatch(context_id)):
                        declaration_state = "source_mismatch"
                    else:
                        _, source_state, source_hash = _read(root, root / source)
                        capture = captures.get(context_id)
                        if (source_state != "present"
                                or source_hash != declaration.get("log_sha256")
                                or not capture or capture.get("state") != "verified"
                                or capture["expected_sha256"] != declaration.get("capture_sha256")
                                or capture["path"] != declaration.get("capture_source")):
                            declaration_state = "source_mismatch"
                elif declaration.get("basis") != "caller_flag_declaration":
                    declaration_state = "unsupported_basis"
                if declaration_state != "caller_declaration":
                    issues.append(declaration_state)
                declarations.append({**public_value(declaration), "state": declaration_state})
            results.append({**view, "state": "recorded", "issues": sorted(set(issues)),
                            **public_value({k: record.get(k) for k in (
                                "coverage", "counts", "observed", "context_ids", "corpus",
                                "unresolved_details")}), "declarations": declarations,
                            "materials": materials, "events": events, "links": links})
    return results


def project_knowledge(root, data):
    """One projection for both layouts, offline export and live refresh."""
    story = data.get("story") or {}
    retrievals = list(story.get("retrievals", []))
    rows = data.get("candidates", [])
    searches = read_searches(root, data.get("campaign_id"), rows, retrievals)
    for capture in retrievals:
        capture["trace"] = retrieval_view(capture)
        capture["links"] = []
        for iteration in story.get("iterations", []):
            if capture["context_id"] not in iteration.get("context_ids", []):
                continue
            for candidate in iteration["candidates"]:
                matches = [row for row in rows if row.get("candidate_id") == candidate[
                    "candidate_id"] and row.get("round") == iteration["round"]]
                if not matches:
                    capture["links"].append({"round": iteration["round"],
                                             "candidate_id": candidate["candidate_id"],
                                             "state": "not_recorded"})
                for row in matches:
                    unique = sum(r.get("run_id") == row.get("run_id") for r in matches) == 1
                    capture["links"].append({"round": iteration["round"],
                        "candidate_id": row["candidate_id"], "run_id": row.get("run_id"),
                        "experiment_id": row.get("experiment_id") if unique else None,
                        "state": "linked" if unique and row.get("run_id") else "ambiguous"})
        for search in searches:
            if capture["context_id"] in (search.get("context_ids") or []):
                for link in search["links"]:
                    if link not in capture["links"]:
                        capture["links"].append(link)
    # An explicit but conflicting ownership declaration cannot be repaired by timestamps.
    ownership = {}
    for search in searches:
        for context_id in search.get("context_ids") or []:
            ownership.setdefault(context_id, set()).add(search["round"])
    for iteration in story.get("iterations", []):
        for context_id in iteration.get("context_ids", []):
            ownership.setdefault(context_id, set()).add(iteration["round"])
    for capture in retrievals:
        if len(ownership.get(capture["context_id"], [])) > 1:
            capture["association_state"] = "round_conflict"
            for link in capture["links"]:
                link["state"] = "round_conflict"
        capture["display_redacted"] = public_value(capture) != capture
    return {"retrievals": public_value(retrievals), "searches": searches}
