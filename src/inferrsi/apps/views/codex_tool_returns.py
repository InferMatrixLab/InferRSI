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
_JS_STRING = r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`'''
_TOOL_HEADER = re.compile(r"^(?:Script completed\nWall time[^\n]*\n)?Output:\n")


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


def _literal_powershell_argv(argv):
    """Decode one recorded PowerShell command with only literal bare words."""
    if (len(argv) != 3 or argv[1].lower() != "-command"
            or re.split(r"[\\/]", argv[0])[-1].lower().removesuffix(".exe")
            not in ("pwsh", "powershell")):
        return None
    script = argv[2].strip(" \t")
    if not re.fullmatch(r"[A-Za-z0-9_./:\\+=-]+(?:[ \t]+[A-Za-z0-9_./:\\+=-]+)*", script):
        return None
    return script.split()


def _command_key(item):
    argv = item.get("command")
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
        return None
    if (Path(argv[0]).name in _SHELLS and len(argv) == 3
            and argv[1] in ("-c", "-lc", "-ic", "-ilc")):
        return "shell", argv[2]
    if _literal_powershell_argv(argv) is not None:
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
    key = rf'''(?:{re.escape(name)}|"{re.escape(name)}"|'{re.escape(name)}')'''
    pattern = (r"(?:\{\s*|,\s*)" + key
               + rf"\s*:\s*({_JS_STRING})(?=\s*[,}}])")
    matches = re.findall(pattern, source)
    if len(matches) != 1:
        return None, False
    literal = matches[0]
    delimiter = literal[0]

    # Normalize delimiters and multiline templates to JSON string syntax.
    # Interpolation and expressions cannot identify an authored command.
    def json_escape(match):
        token = match[0]
        if token == "${" and delimiter == "`":
            raise ValueError("dynamic template")
        if token in (r"\'", r"\`", r"\$"):
            return token[1:]
        return json.dumps(token)[1:-1] if token in ('"', "\n", "\r") else token

    try:
        if delimiter != '"':
            literal = '"' + re.sub(r'\\.|[\r\n"]|\$\{', json_escape, literal[1:-1]) + '"'
        value = json.loads(literal)
    except ValueError:
        return None, False
    return (value, True) if isinstance(value, str) else (None, False)


def _emits_exec_result(source):
    """Recognize code-mode calls that print one complete exec_command result."""
    # A quoted shell command can contain braces, JS-looking text and semicolons.
    source = re.sub(_JS_STRING, '""', source).strip()
    invocation = r"await\s+tools\.exec_command\s*\(\s*\{[^{}();]*\}\s*\)"
    binding = re.match(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*" + invocation, source)
    if binding:
        value = re.escape(binding[1])
        source = source[binding.end():].lstrip().removeprefix(";").lstrip()
    else:
        value = invocation
    value = rf"(?:{value}|\(\s*{value}\s*\))"
    return re.fullmatch(rf"text\(\s*(?:{value}|JSON\.stringify\(\s*{value}\s*\))\s*\)\s*;?",
                        source) is not None


def _outer_call_spec(row, meta_cwd):
    payload = row.get("payload", {})
    if not isinstance(payload, dict):
        return None
    payload_type, name = payload.get("type"), payload.get("name")
    command = workdir = None
    emits_exec_result = False
    if payload_type == "custom_tool_call" and name in ("exec", "exec_command"):
        source = payload.get("input")
        if not isinstance(source, str):
            return None
        emits_exec_result = name == "exec" and _emits_exec_result(source)
        command, valid = _js_string_property(source, "cmd")
        if not valid:
            command, valid = _js_string_property(source, "command")
        if not valid:
            return None
        workdir, workdir_set = _js_string_property(source, "workdir")
        if not workdir_set and re.search(
                r'''(?:\{\s*|,\s*)(?:workdir|"workdir"|'workdir')\s*:''', source):
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
    return {"call_id": call_id, "cwd": cwd.as_posix(), "keys": keys,
            "emits_exec_result": emits_exec_result}


def _batch_launch_spec(row, meta_cwd):
    """Identify one directly printed launch result among separate JS statements."""
    payload = row.get("payload", {})
    source = payload.get("input")
    if (payload.get("type") != "custom_tool_call" or payload.get("name") != "exec"
            or not isinstance(source, str)):
        return None
    statements, start = [], 0
    # Semicolons inside shell commands and other string values are not JS boundaries.
    for token in re.finditer(_JS_STRING + "|;", source):
        if token[0] == ";":
            statements.append(source[start:token.start()])
            start = token.end()
    statements.append(source[start:])
    matches = []
    for statement in statements:
        call = _outer_call_spec({**row, "payload": {**payload, "input": statement}}, meta_cwd)
        if call and call["emits_exec_result"]:
            matches.append({**call, "batched_launch": True})
    return matches[0] if len(matches) == 1 else None


def _response_chunks(row, verified_text=None):
    if verified_text is not None:
        return [verified_text]
    payload = row.get("payload", {})
    value = payload.get("output") if isinstance(payload, dict) else None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [
            part["text"] for part in value
            if isinstance(part, dict) and part.get("type") == "input_text"
            and isinstance(part.get("text"), str)
        ]
    return None


def _response_text(row, verified_text=None):
    chunks = _response_chunks(row, verified_text)
    return None if chunks is None else "".join(chunks)


def _exec_result(row):
    """Read the separate code-mode header and one serialized command result."""
    payload = row["payload"]
    blocks = payload.get("output")
    if (payload["type"] != "custom_tool_call_output" or not isinstance(blocks, list)
            or len(blocks) != 2):
        return None
    chunks = _response_chunks(row)
    if len(chunks) != 2 or not _TOOL_HEADER.fullmatch(chunks[0]):
        return None
    try:
        result = json.loads(chunks[1])
    except (ValueError, RecursionError):
        return None
    if (not isinstance(result, dict) or not isinstance(result.get("chunk_id"), str)
            or type(result.get("wall_time_seconds")) not in (int, float)
            or not isinstance(result.get("output"), str)):
        return None
    return result


def _exec_result_text(row, exit_code):
    result = _exec_result(row)
    if (not result or type(result.get("exit_code")) is not int or result["exit_code"] != exit_code
            or result.get("session_id") is not None):
        return None
    return result["output"]


def _started_process(row, item, *, batched=False):
    if batched:
        blocks = row.get("payload", {}).get("output")
        results = []
        if isinstance(blocks, list) and len(blocks) > 1:
            for block in blocks[1:]:
                candidate = {"payload": {**row["payload"], "output": [blocks[0], block]}}
                result = _exec_result(candidate)
                if result and str(result.get("session_id")) == str(item.get("process_id")):
                    results.append(result)
        result = results[0] if len(results) == 1 else None
    else:
        result = _exec_result(row)
    return (result is not None and "exit_code" not in result
            and type(result.get("session_id")) is int
            and str(result["session_id"]) == str(item.get("process_id"))
            and item.get("source") == "unified_exec_startup"
            and (item.get("status") == "completed"
                 or (item.get("status") == "failed" and item.get("exit_code") == 2)))


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


def _match_output_lines(aggregate, response, *, tool_header=True):
    """Map only exact aggregate lines present in the outer call result."""
    # Some producers prepend a tool header. Only remove a known envelope,
    # and leave an exact source body containing its own "Output:" intact.
    if tool_header and response != aggregate:
        header = _TOOL_HEADER.match(response)
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


def correlate_window(trace, commands, meta_cwd, window_lines, *, exec_returns=None,
                     submissions=False):
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
            call = (_outer_call_spec(row, meta_cwd)
                    or (_batch_launch_spec(row, meta_cwd) if submissions else None))
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
            pending = return_line < event_line
            if pending and not (submissions and call["emits_exec_result"]
                                and _started_process(output_row, item,
                                                     batched=call.get("batched_launch", False))):
                continue
            covered = []
            for line, candidate in command_rows:
                cwd = _path(candidate.get("cwd"))
                in_call = (line > return_line and candidate.get("process_id") == item["process_id"]
                           if pending else call["line"] <= line <= return_line)
                if (in_call and cwd is not None and cwd.as_posix() == signature[0]
                        and _command_key(candidate) == signature[1]):
                    covered.append(line)
            if len(covered) == 1 and covered[0] == event_line:
                matching.append((call, return_line, output_row))
            elif event_line in covered:
                ambiguous_command = True
        if len(matching) != 1:
            reason = "command_not_unique" if ambiguous_command else "outer_call_not_unique"
            joins[event_id] = {"state": "unknown", "runtime_truncated": None,
                               "reason": reason}
            continue
        call, return_line, output_row = matching[0]
        call_line = call["line"]
        if return_line < event_line:
            # The process ID proves who started this command, not its output.
            joins[event_id] = {"state": "unknown", "runtime_truncated": None,
                               "launch_line": call_line, "reason": "process_running_at_return"}
            continue
        structured = call["emits_exec_result"]
        response = (_exec_result_text(output_row, signature[2]) if structured
                    else _response_text(output_row))
        if response is None:
            joins[event_id] = {"state": "unknown", "runtime_truncated": None,
                               "call_line": call_line,
                               "reason": ("exec_result_unverified" if structured
                                          else "outer_result_has_no_text")}
            continue
        indexes, truncated, reason = _match_output_lines(signature[3], response,
                                                         tool_header=not structured)
        if reason is not None:
            joins[event_id] = {"state": "unknown", "runtime_truncated": truncated,
                               "call_line": call_line,
                               "reason": reason}
            if submissions and reason == "output_bytes_do_not_match":
                joins[event_id]["returned_text"] = (_TOOL_HEADER.sub("", response, count=1)
                                                    if not structured else response)
            continue
        joins[event_id] = {
            "state": "visible", "runtime_truncated": truncated,
            "line_indexes": indexes, "aggregate_lines": _output_lines(signature[3], keepends=True),
            "call_line": call_line, "return_line": return_line,
        }
        if exec_returns is not None and structured and not truncated and signature[2] == 0:
            exec_returns[return_line] = response
    return joins
