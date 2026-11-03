"""Join the optimization log with captured knowledge and recorded measurements.

The narrative stays caller-authored. This module only resolves its references
and lists every place where the narrative and the recorded evidence disagree,
so a reviewer sees the disagreement instead of a confident story.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .knowledge_capture import MAX_CONTEXT_CAPTURE_BYTES, verify_capture
from .optimization_log import read_latest_log

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_GOOD = {"improved"}
_MEASURED_BAD = {"failed", "quality_failed", "regressed"}


def _capture(root: Path, entry: dict) -> dict:
    context_id = entry["context_id"]
    view = {"context_id": context_id, "stage": entry["stage"], "purpose": entry["purpose"],
            "used_refs": entry["used_refs"], "takeaways": entry["takeaways"],
            "rejected_refs": entry.get("rejected_refs", []),
            "path": f"knowledge/{context_id}.json", "expected_sha256": entry["sha256"].lower()}
    path = root / "knowledge" / f"{context_id}.json"
    try:
        if path.is_symlink():
            raise OSError
        with path.open("rb") as stream:
            raw = stream.read(MAX_CONTEXT_CAPTURE_BYTES + 1)
    except FileNotFoundError:
        return {**view, "state": "file_absent"}
    except OSError:
        return {**view, "state": "unreadable"}
    if hashlib.sha256(raw).hexdigest() != view["expected_sha256"]:
        return {**view, "state": "hash_mismatch"}
    document, state = verify_capture(raw)
    if document is None:
        return {**view, "state": state}
    contexts = [{"ref": context["ref"], "revision": context["revision"],
                 "resources": [{"path": resource["path"], "role": resource.get("role"),
                                "sha256": resource["sha256"],
                                "bytes": len(resource["content"].encode("utf-8"))}
                               for resource in context["resources"]],
                 "omissions": context["omissions"]} for context in document["contexts"]]
    return {**view, "state": "verified", "request": document.get("request", {}),
            "captured_at": document.get("captured_at"),
            "captured_by": document.get("captured_by"),
            "items": document.get("items", []), "omissions": document.get("omissions", []),
            "context_omissions": document.get("context_omissions", []),
            "context_budget": document.get("context_budget"),
            "context_bytes_used": document.get("context_bytes_used"),
            "contexts": contexts, "assembled_text": document["assembled_text"],
            "assembled_sha256": document["assembled_sha256"]}


def build_story(root: Path, rows: list[dict], decisions: dict) -> dict:
    """Return the dashboard's optimization story, or a not-recorded marker."""
    root = Path(root).resolve()
    log, versions, state = read_latest_log(root)
    if log is None:
        return {"state": state, "versions": versions}
    checks: list[dict] = []

    def check(severity: str, where: str, message: str) -> None:
        checks.append({"severity": severity, "where": where, "message": message})

    retrievals = [_capture(root, entry) for entry in log["knowledge"]]
    captured_refs: dict[str, set[str]] = {}
    for retrieval in retrievals:
        if retrieval["state"] != "verified":
            check("error", f"knowledge {retrieval['context_id']}",
                  f"capture {retrieval['path']} is {retrieval['state'].replace('_', ' ')}; "
                  "its text is not shown")
            continue
        refs = {context["ref"] for context in retrieval["contexts"]}
        selected = {item["ref"] for item in retrieval["items"] if isinstance(item.get("ref"), str)}
        captured_refs[retrieval["context_id"]] = refs | selected
        for ref in retrieval["used_refs"]:
            if ref not in refs:
                reason = ("was selected but its text was omitted from the context"
                          if ref in selected else "was not retrieved by this capture")
                check("warning", f"knowledge {retrieval['context_id']}",
                      f"the log says {ref} was used, but it {reason}")
    every_ref = set().union(*captured_refs.values()) if captured_refs else set()
    # Only these texts were in front of the agent; a selected-but-omitted item was not.
    read_refs = {context["ref"] for retrieval in retrievals if retrieval["state"] == "verified"
                 for context in retrieval["contexts"]}

    def unread(ref: str, scope: set[str] | None = None) -> str | None:
        if ref in (read_refs if scope is None else scope & read_refs):
            return None
        if ref in (every_ref if scope is None else scope):
            return "was selected by search but its text was omitted from the context"
        return "was not retrieved by any capture" if scope is None else \
            "was not retrieved by the captures this round names"

    by_candidate: dict[str, list[dict]] = {}
    for row in rows:
        if isinstance(row.get("candidate_id"), str):
            by_candidate.setdefault(row["candidate_id"], []).append(row)

    def measured(candidate_id: str) -> dict:
        matches = by_candidate.get(candidate_id, [])
        if len(matches) != 1:
            return {"state": "not_recorded" if not matches else "ambiguous"}
        row = matches[0]
        return {"state": "recorded", "run_id": row.get("run_id"), "round": row.get("round"),
                "outcome": row.get("outcome"), "verdict": row.get("verdict"),
                "quality": row.get("quality"), "improvement_pct": row.get("improvement_pct"),
                "decision": row.get("decision"), "title": row.get("title")}

    option_use: dict[str, list[dict]] = {}
    iterations = []
    for iteration in log["iterations"]:
        where = f"round {iteration['round']}"
        allowed = set()
        for context_id in iteration.get("context_ids", []):
            allowed |= captured_refs.get(context_id, set())
        for ref in iteration["knowledge_refs"]:
            problem = unread(ref, allowed or None)
            if problem:
                check("warning", where, f"{ref} is cited, but it {problem}")
        candidates = []
        for candidate in iteration["candidates"]:
            result = measured(candidate["candidate_id"])
            candidates.append({**candidate, "measured": result})
            for option in candidate["option_ids"]:
                option_use.setdefault(option, []).append(
                    {"round": iteration["round"], "candidate_id": candidate["candidate_id"],
                     "outcome": result.get("outcome")})
            if result["state"] != "recorded":
                check("warning", where, f"candidate {candidate['candidate_id']} has no "
                      f"{'unique ' if result['state'] == 'ambiguous' else ''}recorded run")
            elif result.get("round") not in (None, iteration["round"]):
                check("warning", where, f"candidate {candidate['candidate_id']} is recorded "
                      f"in round {result['round']}")
        decision = iteration["decision"]
        chosen = decision.get("candidate_id")
        recorded = decisions.get((iteration["round"], chosen)) if chosen else None
        if chosen and chosen not in {item["candidate_id"] for item in iteration["candidates"]}:
            check("error", where, f"the decision names {chosen}, which is not a candidate "
                  "of this round")
        if recorded and recorded != decision["outcome"]:
            check("error", where, f"the log says {decision['outcome'].replace('_', ' ')}, "
                  f"rounds.jsonl records {recorded.replace('_', ' ')}")
        if chosen and decision["outcome"] == "adopted":
            result = measured(chosen)
            if result["state"] == "recorded" and result.get("outcome") not in _GOOD:
                check("error", where, f"{chosen} is adopted but its recorded outcome is "
                      f"{str(result.get('outcome')).replace('_', ' ')}")
        iterations.append({**iteration, "candidates": candidates})

    space = log["search_space"]
    dimensions = []
    for dimension in space["dimensions"]:
        options = []
        for option in dimension["options"]:
            qualified = f"{dimension['id']}.{option['id']}"
            uses = option_use.get(qualified, [])
            if option["status"] == "tried" and not uses:
                check("warning", f"search space {qualified}",
                      "marked tried, but no iteration lists a candidate for it")
            if option["status"] != "tried" and uses:
                check("warning", f"search space {qualified}",
                      f"marked {option['status']}, but round {uses[0]['round']} tried it")
            for ref in option.get("source_refs", []):
                problem = unread(ref)
                if problem:
                    check("warning", f"search space {qualified}", f"cites {ref}, which {problem}")
            options.append({**option, "qualified_id": qualified, "uses": uses})
        dimensions.append({**dimension, "options": options})

    summary = log["summary"]

    def resolve(entries: list[dict], kind: str) -> list[dict]:
        resolved = []
        for index, entry in enumerate(entries):
            links = []
            for evidence in entry["evidence"]:
                if evidence.startswith("candidate:"):
                    candidate_id = evidence.partition(":")[2]
                    result = measured(candidate_id)
                    links.append({"ref": evidence, **result})
                    outcome = result.get("outcome")
                    if result["state"] != "recorded":
                        check("warning", f"{kind} {index + 1}",
                              f"evidence {evidence} has no recorded run")
                    elif kind == "success" and outcome not in _GOOD:
                        check("error", f"{kind} {index + 1}",
                              f"evidence {evidence} recorded {str(outcome).replace('_', ' ')}, "
                              "not an improvement")
                else:
                    problem = unread(evidence)
                    links.append({"ref": evidence, "state": "recorded" if not problem
                                  else "not_retrieved"})
                    if problem:
                        check("warning", f"{kind} {index + 1}", f"evidence {evidence} {problem}")
            if not entry["evidence"]:
                check("warning", f"{kind} {index + 1}", "states a conclusion without evidence")
            resolved.append({**entry, "links": links})
        return resolved

    successes = resolve(summary["successes"], "success")
    failures = resolve(summary["failures"], "failure")
    for row in rows:
        if row.get("outcome") in _MEASURED_BAD or row.get("decision") == "rolled_back":
            mentioned = any(link["ref"] == f"candidate:{row.get('candidate_id')}"
                            for entry in failures for link in entry["links"])
            if not mentioned:
                check("warning", "failure summary",
                      f"{row.get('candidate_id') or row.get('run_id')} recorded "
                      f"{str(row.get('outcome')).replace('_', ' ')}, but no failure cites it")
    return {"state": "present", "versions": versions, "goal": log["goal"],
            "retrievals": retrievals,
            "search_space": {"state": space["state"], "missing_reason": space["missing_reason"],
                             "dimensions": dimensions},
            "iterations": iterations,
            "summary": {"state": summary["state"], "missing_reason": summary["missing_reason"],
                        "successes": successes, "failures": failures,
                        "lessons": summary["lessons"], "limitations": summary["limitations"]},
            "checks": checks}
