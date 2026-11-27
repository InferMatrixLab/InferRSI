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
from .codex_search import _SHELL_OPERATORS, _recorded_argv
from .codex_tool_returns import _MAX_JOIN_CHARS, _path, correlate_window

_CITATION = re.compile(r"\[use ([^\s|\]]+) \| ([^\]\n]+)\]")
_PERSISTENCE_CUT = "\n... command output truncated for persistence ...\n"


def _citations(reasons):
    for reason in reasons:
        for line in reason.split("\n"):
            if not _CITATION.sub("", line).strip(" .\t"):
                continue
            for match in _CITATION.finditer(line):
                ref, quote = match[1], match[2].strip()
                if quote and relative_location(ref) == ref:
                    yield ref, quote, line.strip()


def submission_receipt(root, number, observation):
    """Project the original round response to its retained observation identity."""
    return {"session": str(root), "completed_rounds": number,
            "latest_observation": {key: observation[key] for key in (
                "path", "observation_sha256",
            )}}


def read_round_receipt(root, number, *, project):
    from inferrsi.harness.manager import read_session_records

    plan, state, _ = read_session_records(root)
    if plan.get("evaluation_mode") == "service_reuse":
        raise ValueError("Round submission receipts require an AB/BA project or benchmark")
    if plan["task_source"] != ("project" if project else "benchmark"):
        raise ValueError("Use the status command for the session's project or benchmark")
    if not 1 <= number <= len(state["rounds"]):
        raise ValueError("Select a completed round by its one-based number")
    return submission_receipt(root, number, state["rounds"][number - 1])


def _round_args(row):
    return {"hypothesis": row["hypothesis"], "strategy": row.get("strategy"),
            "knowledge_ref": row.get("knowledge_refs") or None,
            "alternative": row.get("alternatives") or None,
            "selection_reason": row.get("selection_reason")}


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
    from inferrsi.harness.manager import read_session_records

    notes = {"citations": citations, "receipts": [], "hypothesis": reason}
    try:
        plan, verified, _ = read_session_records(root)
        observation = verified["rounds"][number - 1]
        if observation["hypothesis"] == reason:
            notes["command"] = (("campaign", "round") if plan["task_source"] == "project"
                                else ("benchmarks", "session", "round"))
            compact = submission_receipt(root, number, observation)
            if plan.get("evaluation_mode") != "service_reuse":
                notes["status_receipt"] = compact
                if observation["assessment"]["status"] == "infrastructure_failure":
                    notes["blocked_observation"] = {
                        key: observation[key] for key in ("candidate_sha256", "assessment")
                    }
            notes["receipts"] = [{**compact, "latest_observation": {
                **compact["latest_observation"], "hypothesis": reason,
            }}]
            notes["round_args"] = _round_args(observation)
            notes["unique_round"] = sum(_round_args(row) == notes["round_args"]
                                        for row in verified["rounds"]) == 1
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        pass
    return notes


def _receipt_matches(expected, actual):
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return all(key in actual and _receipt_matches(value, actual[key])
                   for key, value in expected.items())
    return actual == expected


def _submission(item, root, notes):
    argv, compound = _recorded_argv(item, submission=True)
    code = item.get("exit_code")
    # Unquoted shell boundaries have separator tokens. A quoted multiline hypothesis
    # remains one argument and must still match the stored round byte for byte.
    if (not argv or (compound and any(arg in _SHELL_OPERATORS for arg in argv))
            or type(code) is not int or code not in (0, 2)):
        return None
    command = notes["command"]
    args = cli_arguments(argv)
    output = item.get("aggregated_output")
    if not args or not isinstance(output, str) or not output or len(output) > _MAX_JOIN_CHARS:
        return None
    operation = tuple(args[:len(command)])
    status = command[-1] == "round" and operation == (*command[:-1], "status")
    if operation != command and not status:
        return None
    # The managed CLI returns 2 for a persisted blocked round as well as for
    # argument errors. Only its matching retained observation can identify it.
    if code and (status or command[-1] != "round" or "blocked_observation" not in notes):
        return None
    try:
        parsed = _parser().parse_args(args)
    except _ArgumentError:
        return None
    cwd = _path(item.get("cwd"))
    directory = parsed.directory if command[-1] == "log" else parsed.session
    if cwd is None or (cwd / directory).resolve() != root:
        return None
    if status:
        expected = notes.get("status_receipt")
        if not expected or getattr(parsed, "round_receipt", None) != expected["completed_rounds"]:
            return None
    elif command[-1] == "round" and any(getattr(parsed, name) != value
                                        for name, value in notes["round_args"].items()):
        return None
    try:
        response = json.loads(output)
    except (ValueError, RecursionError):
        # A later verified status can identify the observation whose full
        # command output the host explicitly cut from the persisted rollout.
        return ("round", None) if (not code and operation == command and command[-1] == "round"
                                   and _PERSISTENCE_CUT in output) else None
    if command[-1] == "round" and (not isinstance(response, dict)
                                   or type(response.get("completed_rounds")) is not int):
        return None
    if status:
        return ("status", expected) if response == expected else None
    if code and not _receipt_matches(
        {"state": "blocked", "latest_observation": notes["blocked_observation"]}, response,
    ):
        return None
    receipt = next((value for value in notes["receipts"] if _receipt_matches(value, response)),
                   None)
    return (command[-1], receipt) if receipt else None


def _visible_summary(join, receipt, stdout):
    # Older hosts retained full successful stdout but showed selected
    # confirmation fields in the model-facing response.
    if "returned_text" not in join:
        return False
    try:
        summary = json.loads(join["returned_text"])
        full = json.loads(stdout)
    except (ValueError, RecursionError):
        return False
    return (isinstance(summary, dict) and type(summary.get("completed_rounds")) is int
            and summary["completed_rounds"] == receipt["completed_rounds"]
            and _receipt_matches(summary, full))


def _submissions(trace, lines, root, notes):
    """Locate each authored command and its recorded receipt in the window."""
    if not trace or not notes["receipts"]:
        return {}
    commands, operations = [], {}
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
                    and (operation := _submission(item, root, notes))):
                commands.append((number, item, item["id"]))
                operations[item["id"]] = operation
    if not commands:
        return {}
    managed = notes["command"][-1] == "round"
    joins = correlate_window(trace, commands, cwd, lines, submissions=managed)
    submitted, starts, confirmations = {}, [], []
    for number, item, key in commands:
        kind, receipt = operations[key]
        join = joins[key]
        visible = join["state"] == "visible" and not join["runtime_truncated"]
        if kind == "status":
            if visible:
                confirmations.append(join["call_line"])
        elif kind == "log":
            if "call_line" in join:
                submitted[join["call_line"]] = receipt
        else:
            authored = join.get("launch_line")
            summary = (not visible and receipt is not None
                       and _visible_summary(join, receipt, item["aggregated_output"]))
            if join["state"] == "visible" or summary:
                authored = join["call_line"]
                if receipt and (visible or summary):
                    submitted[authored] = receipt
            starts.append((authored, number))
    if not submitted and len(starts) == 1 and notes.get("unique_round"):
        authored, finished = starts[0]
        if authored is not None and any(at > finished for at in confirmations):
            submitted[authored] = notes["receipts"][0]
    return submitted


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
                        or delivery["state"] != "visible" or delivery.get("runtime_truncated")
                        or not delivery.get("passages")):
                    continue
                line = next((at for at in decision_lines if delivery["return_line"] < at), None)
                if line is None:
                    continue
                for p in delivery["passages"]:
                    matched = quote == p["text"] if p.get("quoted") else quote in p["text"]
                    if (p["ref"] != ref or not matched
                            or p.get("redacted") or p.get("root_normalized")):
                        continue
                    revision = next((m.get("revision") for m in event["materials"]
                                     if m["ref"] == ref), None)
                    path = p.get("path")
                    key = revision, path, p["line"], p["text"]
                    matches[key] = {
                        "ref": ref, "use": "used", "event_line": event["trace_line"],
                        "passage_line": p["line"], "decision_line": line,
                        "decision_quote": reason, "passage_text": p["text"],
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
