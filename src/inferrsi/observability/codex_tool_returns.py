"""Correlate Codex command events with exact outer tool call/result envelopes."""

from __future__ import annotations

import json
import os
import re
import shlex
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

_SHELLS = ("sh", "bash", "zsh", "dash")
_MAX_JOIN_CHARS = 1_000_000
_MAX_JOIN_LINES = 8_000


def _output_lines(text, *, keepends=False):
    """Split source/tool output on LF, preserving other control characters."""
    lines = text.split("\n")
    tail = lines.pop()
    result = [line + "\n" if keepends else line.removesuffix("\r") for line in lines]
    if tail:
        result.append(tail)
    return result


def _path(value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    if value.startswith("file://"):
        uri = urlsplit(value)
        if uri.netloc not in ("", "localhost"):
            return None
        value = url2pathname(uri.path)
    path = Path(os.path.normpath(value))
    return path if path.is_absolute() else None


def _command_key(item):
    argv = item.get("command")
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
        return None
    if (Path(argv[0]).name in _SHELLS and len(argv) == 3
            and argv[1] in ("-c", "-lc", "-ic", "-ilc")):
        return "shell", argv[2]
    return "argv", tuple(argv)


def _signature(item):
    cwd = _path(item.get("cwd"))
    key = _command_key(item)
    code, output = item.get("exit_code"), item.get("aggregated_output")
    if cwd is None or key is None or type(code) is not int or not isinstance(output, str):
        return None
    return cwd.as_posix(), key, code, output


def _js_string_property(source, name):
    pattern = (r"(?:\{\s*|,\s*)" + re.escape(name)
               + r"\s*:\s*(\"(?:\\.|[^\"\\])*\")")
    matches = re.findall(pattern, source)
    if len(matches) != 1:
        return None, False
    try:
        value = json.loads(matches[0])
    except json.JSONDecodeError:
        return None, False
    return (value, True) if isinstance(value, str) else (None, False)


def _outer_call_spec(row, meta_cwd):
    payload = row.get("payload", {})
    if not isinstance(payload, dict):
        return None
    payload_type, name = payload.get("type"), payload.get("name")
    command = workdir = None
    if payload_type == "custom_tool_call" and name in ("exec", "exec_command"):
        source = payload.get("input")
        if not isinstance(source, str):
            return None
        command, valid = _js_string_property(source, "cmd")
        if not valid:
            command, valid = _js_string_property(source, "command")
        if not valid:
            return None
        workdir, workdir_set = _js_string_property(source, "workdir")
        if not workdir_set and re.search(r"(?:\{\s*|,\s*)workdir\s*:", source):
            return None
        if not workdir_set:
            workdir = None
    elif payload_type == "function_call" and name in ("exec", "exec_command"):
        arguments = payload.get("arguments", payload.get("input"))
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return None
        if not isinstance(arguments, dict):
            return None
        command = arguments.get("cmd", arguments.get("command"))
        workdir = arguments.get("workdir", arguments.get("cwd"))
        if not isinstance(command, str):
            if (isinstance(command, list) and command
                    and all(isinstance(arg, str) for arg in command)):
                command = shlex.join(command)
            else:
                return None
    else:
        return None
    cwd = _path(workdir) if workdir is not None else meta_cwd
    call_id = payload.get("call_id")
    if cwd is None or not isinstance(command, str) or not isinstance(call_id, str) or not call_id:
        return None
    keys = {("shell", command)}
    try:
        keys.add(("argv", tuple(shlex.split(command))))
    except ValueError:
        pass
    return {"call_id": call_id, "cwd": cwd.as_posix(), "keys": keys}


def _response_text(row):
    payload = row.get("payload", {})
    value = payload.get("output") if isinstance(payload, dict) else None
    if isinstance(value, str):
        joined = value
    elif isinstance(value, list):
        joined = "".join(
            part.get("text", "") for part in value
            if isinstance(part, dict) and part.get("type") == "input_text"
            and isinstance(part.get("text"), str)
        )
    else:
        return None
    return joined


def _truncation_marker(aggregate, response):
    for line in _output_lines(aggregate):
        if "tokens truncated" in line and ("…" in line or "..." in line):
            return True
    aggregate_lines = set(_output_lines(aggregate))
    for line in _output_lines(response):
        if (re.match(r"^\s*(?:Warning:\s*)?truncated output\b", line, re.I)
                and line not in aggregate_lines):
            return True
        if re.match(r"^\s*\[output truncated\b", line, re.I):
            return True
    return False


def _match_output_lines(aggregate, response):
    """Map only exact aggregate lines present in the outer call result."""
    # Some producers prepend a tool header. Only remove a known envelope,
    # and leave an exact source body containing its own "Output:" intact.
    if response != aggregate:
        header = re.match(r"^(?:Script completed\nWall time[^\n]*\n)?Output:\n", response)
        if header:
            response = response[header.end():]
    if max(len(aggregate), len(response)) > _MAX_JOIN_CHARS:
        return {}, None, "output_missing_or_too_large"
    source = _output_lines(aggregate, keepends=True)
    returned = _output_lines(response, keepends=True)
    if max(len(source), len(returned)) > _MAX_JOIN_LINES:
        return {}, None, "output_has_too_many_lines"
    truncated = _truncation_marker(aggregate, response)
    if aggregate == response:
        return {i: i for i, line in enumerate(source) if line.strip()}, truncated, None
    if not truncated:
        return {}, None, "output_bytes_do_not_match"

    # A truncated read can contain identical paragraphs from different
    # positions. Only a unique complete row can identify its source line.
    source_counts, return_counts = Counter(source), Counter(returned)
    positions = {line: i for i, line in enumerate(returned) if return_counts[line] == 1}
    indices = {i: positions[line] for i, line in enumerate(source)
               if line.strip() and source_counts[line] == 1 and line in positions}
    return indices, True, None if indices else "no_exact_output_lines"


def correlate_window(trace, commands, meta_cwd, window_lines):
    """Join each command to one exact enclosing call/result pair in this window."""
    first, last = window_lines
    command_rows, calls, outputs = [], [], {}
    scan_complete = True
    with trace.open("rb") as stream:
        stream.readline()
        for line_number, raw in enumerate(stream, 2):
            if line_number < first:
                continue
            if line_number > last:
                break
            try:
                row = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                scan_complete = False
                continue
            payload = row.get("payload", {})
            if (row.get("type") == "event_msg" and isinstance(payload, dict)
                    and payload.get("type") == "item_completed"):
                item = payload.get("item", {})
                if isinstance(item, dict) and item.get("type") == "CommandExecution":
                    command_rows.append((line_number, item))
            if row.get("type") != "response_item" or not isinstance(payload, dict):
                continue
            call = _outer_call_spec(row, meta_cwd)
            if call:
                call["line"] = line_number
                calls.append(call)
                outputs.setdefault(call["call_id"], [])
            if (payload.get("type") in ("custom_tool_call_output", "function_call_output")
                    and payload.get("call_id") in outputs):
                outputs[payload["call_id"]].append((line_number, row))
    calls_by_id = {}
    for call in calls:
        calls_by_id.setdefault(call["call_id"], []).append(call)
    joins = {}
    for event_line, item, event_id in commands:
        signature = _signature(item)
        if signature is None or not scan_complete:
            joins[event_id] = {"state": "unknown", "runtime_truncated": None,
                               "reason": "trace_scan_incomplete"}
            continue
        matching, ambiguous_command = [], False
        for call in calls:
            if (call["line"] > event_line or call["cwd"] != signature[0]
                    or signature[1] not in call["keys"]):
                continue
            if len(calls_by_id.get(call["call_id"], [])) != 1:
                continue
            call_outputs = outputs.get(call["call_id"], [])
            if len(call_outputs) != 1:
                continue
            return_line, output_row = call_outputs[0]
            if return_line < event_line:
                continue
            covered = []
            for line, candidate in command_rows:
                cwd = _path(candidate.get("cwd"))
                if (call["line"] <= line <= return_line and cwd is not None
                        and cwd.as_posix() == signature[0]
                        and _command_key(candidate) == signature[1]):
                    covered.append(line)
            if len(covered) == 1 and covered[0] == event_line:
                matching.append((return_line, output_row))
            elif event_line in covered:
                ambiguous_command = True
        if len(matching) != 1:
            reason = "command_not_unique" if ambiguous_command else "outer_call_not_unique"
            joins[event_id] = {"state": "unknown", "runtime_truncated": None,
                               "reason": reason}
            continue
        return_line, output_row = matching[0]
        response = _response_text(output_row)
        if response is None:
            joins[event_id] = {"state": "unknown", "runtime_truncated": None,
                               "reason": "outer_result_has_no_text"}
            continue
        indexes, truncated, reason = _match_output_lines(signature[3], response)
        if reason is not None:
            joins[event_id] = {"state": "unknown", "runtime_truncated": truncated,
                               "reason": reason}
            continue
        joins[event_id] = {
            "state": "visible", "runtime_truncated": truncated,
            "line_indexes": indexes, "aggregate_lines": _output_lines(signature[3], keepends=True),
            "return_line": return_line,
        }
    return joins
