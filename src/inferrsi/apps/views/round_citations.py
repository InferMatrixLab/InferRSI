"""Bind explicit citations in a retained round reason to the Codex rollout."""

import hashlib
import json
import re

from inferrsi.harness.records.evidence import read_object, relative_location, sanitized_text
from inferrsi.harness.records.optimization_log import (
    MAX_LOG_BYTES,
    parse_optimization_log,
    read_latest_log,
    read_regular,
)

from .codex_knowledge import _ArgumentError, _parser, cli_arguments
from .codex_search import _recorded_argv
from .codex_tool_returns import _MAX_JOIN_CHARS, _path, correlate_window

_CITATION = re.compile(r"\[use ([^\s|\]]+) \| ([^\]\n]+)\]")


def _citations(reasons):
    for reason in reasons:
        for line in reason.split("\n"):
            if not _CITATION.sub("", line).strip(" .\t"):
                continue
            for match in _CITATION.finditer(line):
                ref, quote = match[1], match[2].strip()
                if quote and relative_location(ref) == ref:
                    yield ref, quote, line.strip()


def _managed_citations(root, number):
    state, status = read_object(root / "state.json", root)
    rounds = state.get("rounds", []) if status == "present" else []
    if not isinstance(rounds, list) or len(rounds) < number:
        return None
    record = rounds[number - 1]
    reason = record.get("hypothesis") if isinstance(record, dict) else None
    citations = list(_citations([reason])) if isinstance(reason, str) else []
    if not citations:
        return None
    from inferrsi.harness.optimization import read_records

    notes = {"citations": citations, "receipts": [], "hypothesis": reason}
    try:
        plan, verified, _ = read_records(root)
        observation = verified["rounds"][number - 1]
        if observation["hypothesis"] == reason:
            notes["command"] = (("campaign", "round") if plan["task_source"] == "project"
                                else ("benchmarks", "session", "round"))
            notes["receipts"] = [{
                "session": str(root), "completed_rounds": number,
                "latest_observation": {key: observation[key] for key in (
                    "path", "hypothesis", "observation_sha256",
                )},
            }]
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        pass
    return notes


def _receipt_matches(expected, actual):
    return isinstance(actual, dict) and all(
        _receipt_matches(value, actual.get(key)) if isinstance(value, dict)
        else actual.get(key) == value for key, value in expected.items()
    )


def _submission(item, root, notes):
    argv, compound = _recorded_argv(item)
    if not argv or compound or item.get("exit_code") != 0:
        return None
    command = notes["command"]
    args = cli_arguments(argv)
    output = item.get("aggregated_output")
    if (not args or tuple(args[:len(command)]) != command or not isinstance(output, str)
            or len(output) > _MAX_JOIN_CHARS):
        return None
    try:
        parsed = _parser().parse_args(args)
        response = json.loads(output)
    except (_ArgumentError, ValueError, RecursionError):
        return None
    cwd = _path(item.get("cwd"))
    directory = parsed.directory if command[-1] == "log" else parsed.session
    if cwd is None or getattr(parsed, "hypothesis", None) != notes.get("hypothesis"):
        return None
    receipt = next((value for value in notes["receipts"] if _receipt_matches(value, response)),
                   None)
    return receipt if receipt and (cwd / directory).resolve() == root else None


def _submissions(trace, lines, root, notes):
    """Locate each authored command and its recorded receipt in the window."""
    if not trace or not notes["receipts"]:
        return {}
    commands, receipts = [], {}
    first, last = lines
    with trace.open("rb") as stream:
        cwd = _path(json.loads(stream.readline())["payload"].get("cwd"))
        for number, raw in enumerate(stream, 2):
            if number > last:
                break
            if number < first:
                continue
            row = json.loads(raw)
            payload = row.get("payload", {})
            if (row.get("type") != "event_msg" or not isinstance(payload, dict)
                    or payload.get("type") != "item_completed"):
                continue
            item = payload.get("item")
            if (isinstance(item, dict) and item.get("type") == "CommandExecution"
                    and isinstance(item.get("id"), str)
                    and (receipt := _submission(item, root, notes))):
                commands.append((number, item, item["id"]))
                receipts[item["id"]] = receipt
    joins = correlate_window(trace, commands, cwd, lines) if commands else {}
    # The persisted round and command stdout establish acceptance. The join
    # locates the authored input even when the host summarized its response.
    return {join["call_line"]: receipts[key] for key, join in joins.items() if "call_line" in join}


def retained_round_citations(root, campaign, number, trace, lines):
    """Find the reason submitted for this round, with its authored trace position."""
    if campaign.get("managed_optimization"):
        notes = _managed_citations(root, number)
        submitted = _submissions(trace, lines, root, notes) if notes else {}
        return notes, next(iter(submitted)) if len(submitted) == 1 else None

    log, versions, _ = read_latest_log(root)
    receipts = [{"log": item["path"], "sha256": item["sha256"]}
                for item in versions if item["state"] == "present"]
    notes = {"command": ("campaign", "log"), "receipts": receipts}
    submitted = _submissions(trace, lines, root, notes)
    line = max(submitted, default=None)
    if line is not None:
        receipt = submitted[line]
        if not log or receipt["log"] != versions[-1]["path"]:
            # Resolve the retained edition from this window, even after a
            # later round appended a new log version.
            try:
                raw = read_regular(root / receipt["log"], MAX_LOG_BYTES)
                log = (parse_optimization_log(raw) if hashlib.sha256(raw).hexdigest()
                       == receipt["sha256"] else None)
            except (OSError, ValueError):
                log = None
    if not log or log["campaign_id"] != campaign["campaign_id"]:
        return None, None
    item = next((row for row in log["iterations"] if row["round"] == number), None)
    citations = list(_citations([item["rationale"], item["decision"]["reason"]])) if item else []
    return ({"citations": citations}, line) if citations else (None, None)


def decision_positions(notes, submitted_at, decisions):
    """Use the authored hypothesis, or the assistant's stated saved-log reason."""
    if submitted_at is None:
        return {}
    reasons = dict.fromkeys(reason for _, _, reason in notes["citations"])
    if "hypothesis" in notes:
        decisions[submitted_at] = notes["hypothesis"]
        return dict.fromkeys(reasons, (submitted_at,))
    # The log command proves which bytes were saved, but its argument
    # does not carry the reason. Keep each statement before the saved log.
    statements = [(line, text) for line, text in sorted(decisions.items()) if line < submitted_at]
    return {reason: tuple(line for line, text in statements if reason in text)
            for reason in reasons}


def round_reviews(citations, positions, events):
    """Return regular archive-review decisions and any unverified declarations."""
    reviews, declarations = [], []
    for ref, quote, reason in dict.fromkeys(citations):
        decision_lines = positions.get(reason, ())
        matches = {}
        if decision_lines and sanitized_text(reason, "", len(reason)) == reason:
            for event in events:
                delivery = event["delivery"]
                if (event["action"] != "read" and "context_id" not in event
                        or delivery["state"] != "visible" or delivery.get("runtime_truncated")):
                    continue
                line = next((at for at in decision_lines if delivery["return_line"] < at), None)
                if line is None:
                    continue
                for p in delivery["passages"]:
                    if (p["ref"] != ref or quote not in p["text"]
                            or p.get("redacted") or p.get("root_normalized")):
                        continue
                    revision = next((m.get("revision") for m in event["materials"]
                                     if m["ref"] == ref), None)
                    path = p.get("path")
                    key = revision, path, p["line"], p["text"]
                    matches[key] = {
                        "ref": ref, "use": "used", "event_line": event["trace_line"],
                        "passage_line": p["line"], "decision_line": line,
                        "decision_quote": reason,
                        **({"passage_path": path} if path else {}),
                    }
        if len(matches) == 1:
            reviews.append(next(iter(matches.values())))
        else:
            reason_code = ("round_submission_unverified" if not decision_lines else
                           "ambiguous_read_excerpt" if matches else "read_excerpt_unverified")
            declarations.append({"ref": ref, "use": "used", "basis": "round_reason_declaration",
                                 "reason": reason_code,
                                 "decision_line": decision_lines[0] if decision_lines else None})
    return reviews, declarations
