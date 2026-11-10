"""Extract bounded, attributable file-search evidence from Codex rollouts."""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

from .campaign_records import _identifier
from .codex_tool_returns import _path, correlate_window
from .dashboard_data import _relative_location, _text

_SHELLS = ("sh", "bash", "zsh", "dash")
_TOOLS = ("rg", "cat", "sed", "nl")
_MAX_PASSAGES = 12
_MAX_PASSAGE_CHARS = 400
_MAX_VISIBLE_REFS = 64
_MAX_UNRESOLVED_PATH_EXCERPTS = 4


def _material(cwd: Path, name: str, corpus: Path) -> str | None:
    # The original tree may be offline; use the recorded working directory.
    path = Path(os.path.normpath(cwd / name))
    if path.is_relative_to(corpus):
        return _relative_location(path.relative_to(corpus).as_posix())
    return None


def _rg_args(args: list[str]) -> tuple[str, list[str], str, list[str]] | None:
    """Decode common text/filename rg output; decline options that change its meaning."""
    patterns, operands, options = [], [], []
    mode = "text"
    context = numbered = False
    it = iter(args)
    for arg in it:
        if arg == "--":
            operands.extend(it)
            break
        if arg == "--files":
            return "", [], "inventory", []
        if arg in ("-e", "--regexp"):
            pattern = next(it, None)
            if pattern is None:
                return None
            patterns.append(pattern)
        elif arg in ("-g", "--glob", "-A", "-B", "-C", "--context", "--max-count", "-m"):
            value = next(it, None)
            if value is None:
                return None
            options.extend([arg, _text(value)])
            if arg in ("-A", "-B", "-C", "--context"):
                context = True
        elif arg in ("--files-with-matches", "-l"):
            mode = "files"
            options.append(arg)
        elif arg in ("--no-heading", "--with-filename", "--line-number", "--ignore-case",
                     "--fixed-strings", "--word-regexp", "--smart-case", "--hidden"):
            options.append(arg)
            if arg == "--line-number":
                numbered = True
        elif arg.startswith("-"):
            if not re.fullmatch(r"-[inSFwHs]+", arg):
                return None
            options.append(arg)
            if "n" in arg:
                numbered = True
        else:
            operands.append(arg)
    if not patterns and operands:
        patterns.append(operands.pop(0))
    if mode == "text" and context:
        mode = "numbered_context" if numbered else "unnumbered_context"
    return (" | ".join(patterns), operands or ["."], mode, options) if patterns else None


def _rg_observations(output, cwd, corpus, scopes, mode):
    """Return parsed rg rows with their aggregate-output line indexes."""
    if mode == "unnumbered_context":
        return [], False
    observations = []
    scope_paths = [Path(os.path.normpath(cwd / scope)) for scope in scopes]
    complete = True
    for index, raw_line in enumerate(output.splitlines()):
        line = raw_line.rstrip("\r")
        if "tokens truncated" in line and ("…" in line or "..." in line):
            complete = False
            continue
        if mode == "files":
            path, number, text = line, None, None
        else:
            if mode == "numbered_context":
                numbered_match = re.match(r"^(?:[^:]+:)?\d+:", line)
                if line == "--":
                    continue
                if re.match(r"^(?:[^:]*-)?\d+-", line):
                    # Context text may itself contain ":42:", and filenames
                    # may contain "-2-". Neither interpretation is certain.
                    if numbered_match:
                        complete = False
                    continue
                if not numbered_match:
                    complete = False
                    continue
            bare = re.match(r"^(\d+):(.*)$", line)
            if bare and len(scope_paths) == 1 and scope_paths[0] != cwd:
                path, number, text = str(scope_paths[0]), int(bare[1]), bare[2]
            else:
                match = re.match(r"^([^:]+):(?:(\d+):)?(.*)$", line)
                if not match:
                    complete = False
                    continue
                path = match[1]
                number = int(match[2]) if match[2] else None
                text = match[3]
        candidate = Path(os.path.normpath(cwd / path))
        if not any(candidate.is_relative_to(scope) for scope in scope_paths):
            complete = False
            continue
        ref = _material(cwd, str(candidate), corpus)
        if ref:
            observations.append({"ref": ref, "line": number, "text": text,
                                 "output_line": index})
        elif candidate.is_relative_to(corpus):
            complete = False
    return observations, complete


def _rg_hits(output, cwd, corpus, scopes, mode):
    observations, complete = _rg_observations(output, cwd, corpus, scopes, mode)
    hits = {}
    for observation in observations:
        hits.setdefault(observation["ref"], observation["line"])
    return [{"ref": ref, "match_line": line} for ref, line in hits.items()], complete


def _command(item, corpus):
    """Decode one simple file command without changing its legacy event fields."""
    original_argv = item.get("command")
    if (not isinstance(original_argv, list) or not original_argv
            or not all(isinstance(arg, str) for arg in original_argv)):
        return None, False, None
    argv = original_argv
    multiline = False
    if (Path(argv[0]).name in _SHELLS and len(argv) == 3
            and argv[1] in ("-c", "-lc", "-ic", "-ilc")):
        multiline = "\n" in argv[2].strip()
        try:
            lexer = shlex.shlex(argv[2], posix=True, punctuation_chars=";&|<>")
            lexer.whitespace_split = True
            argv = list(lexer)
        except ValueError:
            return None, False, None
    if not argv:
        return None, True, None
    tool = Path(argv[0]).name
    if multiline or tool not in _TOOLS:
        # A compound script can run several tools against one shared stdout.
        return None, not any(Path(word).name in _TOOLS for word in argv), None
    cwd = _path(item.get("cwd"))
    if cwd is None:
        return None, False, None
    if any(word in {"|", "||", "&&", ";", ">", ">>", "<"} for word in argv):
        return None, False, None
    code, output = item.get("exit_code"), item.get("aggregated_output")
    if not isinstance(output, str) or type(code) is not int:
        return None, False, None
    if tool == "rg":
        parsed = _rg_args(argv[1:])
        if parsed is None:
            return None, False, None
        query, scopes, mode, options = parsed
        if mode == "inventory":
            return None, True, None
        if any(re.search(r"[$\x60*?~{}\[]", value) for value in scopes):
            return None, False, None
        paths = [Path(os.path.normpath(cwd / value)) for value in scopes]
        scope_refs = ["." if path == corpus or corpus.is_relative_to(path)
                      else _material(cwd, str(path), corpus) for path in paths]
        if not any(scope_refs):
            return None, True, None
        materials, complete = [], code == 1
        if code == 0:
            materials, complete = _rg_hits(output, cwd, corpus, scopes, mode)
        event = {"action": "search", "tool": tool, "query": _text(query),
                 "scope": [scope for scope in scope_refs if scope], "options": options,
                 "exit_code": code, "materials": materials}
        spec = {"kind": "search", "tool": tool, "cwd": cwd, "scopes": scopes,
                "mode": mode}
        return event, complete and (code != 0 or bool(materials)), spec
    if tool == "cat":
        names = argv[2:] if argv[1:2] == ["--"] else argv[1:]
        if any(name.startswith("-") for name in names):
            return None, False, None
    elif len(argv) == 4 and tool == "sed" and argv[1] == "-n" and re.fullmatch(
            r"\d+(?:,\d+)?p", argv[2]):
        names = argv[3:]
    elif tool == "nl" and len(argv) == 3 and argv[1] == "-ba":
        names = argv[2:]
    else:
        return None, False, None
    if any(re.search(r"[$\x60*?~{}\[]", name) for name in names):
        return None, False, None
    refs = [ref for name in names if (ref := _material(cwd, name, corpus))]
    if not refs:
        return None, True, None
    if code != 0:
        return None, False, None
    # Successful cat of multiple files has one joined stdout, so no excerpt
    # can be assigned to an individual source.
    event = {"action": "read", "tool": tool,
             "materials": [{"ref": ref} for ref in dict.fromkeys(refs)]}
    spec = {"kind": "read", "tool": tool, "refs": list(dict.fromkeys(refs))}
    if len(names) == 1 and len(refs) == 1:
        spec["source_ref"] = refs[0]
        if tool == "sed":
            selected = argv[2][:-1].split(",")
            spec["line_start"] = int(selected[0])
            spec["line_end"] = int(selected[-1])
        elif tool == "cat":
            spec["line_start"] = 1
        else:
            spec["line_mode"] = "numbered"
    return event, True, spec


def _archive_text(value, corpus, limit=_MAX_PASSAGE_CHARS):
    text = value if isinstance(value, str) else ""
    normalized_root = False
    placeholder = "NORMALIZEDKNOWLEDGEROOTTOKEN"
    roots = (corpus.as_posix(), str(corpus))
    for root in dict.fromkeys(roots):
        if root and root in text:
            text = text.replace(root, placeholder)
            normalized_root = True
    preview = _text(text, "", limit + 1)
    redacted = preview != text[:limit + 1]
    truncated = len(preview) > limit
    fields = {"text": preview[:limit].replace(placeholder, "<KNOWLEDGE_ROOT>")}
    if redacted:
        fields["redacted"] = True
    if normalized_root:
        fields["root_normalized"] = True
    if truncated:
        fields["truncated"] = True
    return fields


def _passage(ref, line, text, corpus):
    safe = _archive_text(text, corpus)
    return {"ref": ref, "line": line, **safe}


def _unique_candidates(candidates):
    result, seen = [], set()
    for candidate in candidates:
        key = (candidate["ref"], candidate["line"], candidate["text"])
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def _select_passages(candidates, event_line, selections):
    candidates = _unique_candidates(candidates)
    requested = set(selections.get(event_line, ()))
    selected = []
    found = set()
    for index, candidate in enumerate(candidates):
        locator = (candidate["ref"], candidate["line"])
        if locator in requested:
            found.add(locator)
        if index < _MAX_PASSAGES or locator in requested:
            selected.append(candidate)
    missing = [key for key in selections.get(event_line, ()) if key not in found]
    return selected, len(candidates) - len(selected), missing


def _delivery(event, spec, join, corpus, event_line, selections):
    base = {"state": "unknown", "runtime_truncated": join.get("runtime_truncated"),
            "archive_omitted": True, "passages": [], "visible_refs": []}
    issues = []
    if join.get("state") != "visible":
        return base, join.get("reason", "output_not_verified"), issues
    if spec["kind"] == "read" and "source_ref" not in spec:
        base["runtime_truncated"] = join.get("runtime_truncated")
        return base, "read_sources_not_separable", issues
    aggregate_lines = join["aggregate_lines"]
    visible_indexes = set(join["line_indexes"])
    candidates, refs = [], []
    if spec["kind"] == "search":
        observations, _ = _rg_observations(
            "".join(aggregate_lines), spec["cwd"], corpus, spec["scopes"], spec["mode"]
        )
        for observation in observations:
            if observation["output_line"] not in visible_indexes:
                continue
            if observation["ref"] not in refs:
                refs.append(observation["ref"])
            if observation["text"] is None:
                continue
            candidates.append({"ref": observation["ref"], "line": observation["line"],
                               "text": observation["text"]})
    else:
        ref = spec["source_ref"]
        refs.append(ref)
        marker_indexes = [
            index for index, output_line in enumerate(aggregate_lines)
            if ("tokens truncated" in output_line
                and ("…" in output_line or "..." in output_line))
        ]
        truncation_index = min(marker_indexes) if marker_indexes else None
        for index in sorted(visible_indexes):
            if index >= len(aggregate_lines):
                continue
            # A cut marker in a read stream means indexes after it no longer
            # establish source line numbers.
            if truncation_index is not None and index >= truncation_index:
                continue
            text = aggregate_lines[index].rstrip("\r\n")
            if spec.get("line_mode") == "numbered":
                match = re.match(r"^\s*(\d+)\t(.*)$", text)
                if not match:
                    continue
                line_number, text = int(match[1]), match[2]
            else:
                line_number = spec["line_start"] + index
            candidates.append({"ref": ref, "line": line_number, "text": text})
    passages, omitted, unmatched = _select_passages(candidates, event_line, selections)
    safe_passages = [_passage(item["ref"], item["line"], item["text"], corpus)
                     for item in passages]
    visible_refs = refs[:_MAX_VISIBLE_REFS]
    omitted_refs = max(0, len(refs) - len(visible_refs))
    truncated_passages = sum(item.get("truncated", False) for item in safe_passages)
    redacted_passages = sum(item.get("redacted", False) for item in safe_passages)
    normalized_passages = sum(item.get("root_normalized", False) for item in safe_passages)
    base.update({
        "state": "visible",
        "return_line": join["return_line"],
        "archive_omitted": bool(omitted or omitted_refs or truncated_passages),
        "passages": safe_passages,
        "visible_refs": visible_refs,
    })
    for key, count in (
        ("omitted_passages", omitted), ("omitted_refs", omitted_refs),
        ("truncated_passages", truncated_passages),
        ("redacted_passages", redacted_passages),
        ("root_normalized_passages", normalized_passages),
    ):
        if count:
            base[key] = count
    for ref, line in unmatched:
        issues.append({"reason": "requested_passage_not_visible",
                       "selection": {"ref": ref, "line": line}})
    return base, None, issues


def _rough_action(item):
    argv = item.get("command")
    if not isinstance(argv, list) or not argv:
        return "unknown", False
    tokens = argv
    if (isinstance(argv[0], str) and Path(argv[0]).name in _SHELLS
            and len(argv) == 3 and argv[1] in ("-c", "-lc", "-ic", "-ilc")):
        try:
            lexer = shlex.shlex(argv[2], posix=True, punctuation_chars=";&|<>")
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            return "unknown", False
    found = [Path(word).name for word in tokens if isinstance(word, str)
             and Path(word).name in _TOOLS]
    compound = any(word in {"|", "||", "&&", ";", ">", ">>", "<"} for word in tokens)
    if compound:
        return "unknown", True
    if found:
        return ("search" if found[0] == "rg" else "read"), False
    return "unknown", False


def _safe_file_list_pipeline(item, corpus, join):
    """Retain samples only for a simple scoped rg file-list/filter pipeline."""
    if join.get("state") != "visible":
        return None
    argv = item.get("command")
    if (not isinstance(argv, list) or len(argv) != 3
            or Path(argv[0]).name not in ("sh", "bash", "zsh", "dash")
            or argv[1] not in ("-c", "-lc", "-ic", "-ilc")
            or "\n" in argv[2]):
        return None
    try:
        lexer = shlex.shlex(argv[2], posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    if (len(tokens) == 6 and tokens[:2] == ["rg", "--files"]
            and tokens[3:5] == ["|", "rg"]):
        pattern, ignore_case = tokens[5], False
    elif (len(tokens) == 7 and tokens[:2] == ["rg", "--files"]
          and tokens[3:5] == ["|", "rg"] and tokens[5] in ("-i", "--ignore-case")):
        pattern, ignore_case = tokens[6], True
    else:
        return None
    if not pattern or pattern.startswith("-") or len(pattern) > 120:
        return None
    cwd = _path(item.get("cwd"))
    if cwd is None:
        return None
    operand = tokens[2]
    if re.search(r"[$\x60*?~{}\[]", operand):
        return None
    scope = Path(os.path.normpath(cwd / operand))
    if not scope.is_relative_to(corpus):
        return None
    scope_ref = "." if scope == corpus else _material(cwd, str(scope), corpus)
    if scope_ref is None:
        return None
    pattern_text = _text(pattern, "", 120)
    if not pattern_text:
        return None
    display_scope = "<KNOWLEDGE_ROOT>" + (f"/{scope_ref}" if scope_ref != "." else "")
    flag = " -i" if ignore_case else ""
    rendered_command = (
        f"rg --files {display_scope} | rg{flag} {shlex.quote(pattern_text)}"
    )
    command_truncated = len(rendered_command) > 240
    command_excerpt = rendered_command[:237] + "..." if command_truncated else rendered_command
    lines = join["aggregate_lines"]
    visible_indexes = set(join["line_indexes"])
    paths, seen = [], set()
    for index in sorted(visible_indexes):
        if index >= len(lines):
            continue
        text = lines[index].rstrip("\r\n")
        if not text or ("tokens truncated" in text and ("…" in text or "..." in text)):
            continue
        candidate_path = _path(text) or Path(os.path.normpath(cwd / text))
        if not candidate_path.is_relative_to(scope):
            continue
        ref = _material(cwd, str(candidate_path), corpus)
        if ref is None or ref in seen:
            continue
        seen.add(ref)
        paths.append({"ref": ref, "line": None, "text": text})
    excerpts = [_passage(item["ref"], None, item["text"], corpus)
                for item in paths[:_MAX_UNRESOLVED_PATH_EXCERPTS]]
    omitted = max(0, len(paths) - len(excerpts))
    return {
        "scope": scope_ref, "command_excerpt": command_excerpt,
        "excerpts": excerpts, "omitted": omitted,
        "pattern_redacted": pattern_text != pattern,
        "scope_normalized": Path(operand).is_absolute(),
        "command_truncated": command_truncated,
    }


def _operation_skeleton(item, action, event=None):
    if event:
        refs = list(event.get("scope", []))
        refs.extend(material.get("ref") for material in event.get("materials", []))
        return {"tool": event.get("tool"), "action": action,
                "scope": list(dict.fromkeys(refs))[:_MAX_VISIBLE_REFS]}
    argv = item.get("command")
    if not isinstance(argv, list) or not argv:
        return {"action": action}
    tokens = argv
    if (isinstance(argv[0], str) and Path(argv[0]).name in _SHELLS
            and len(argv) == 3 and argv[1] in ("-c", "-lc", "-ic", "-ilc")):
        try:
            lexer = shlex.shlex(argv[2], posix=True, punctuation_chars=";&|<>")
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            return {"action": action}
    tools = list(dict.fromkeys(
        Path(word).name for word in tokens
        if isinstance(word, str) and Path(word).name in _TOOLS
    ))
    compound = any(word in {"|", "||", "&&", ";", ">", ">>", "<"} for word in tokens)
    if compound:
        return {"tools": tools, "action": "unknown", "compound": True}
    if tools:
        return {"tool": tools[0], "action": action, "scope": []}
    return {"action": action}


def _detail(event_id, trace_line, action, reason, event=None, excerpt=None, selection=None,
            command_item=None):
    descriptions = {
        "trace_scan_incomplete": "Trace scan incomplete; verify the selected lines manually.",
        "command_not_unique": "Multiple same-key commands are covered; narrow the selected window.",
        "outer_call_not_unique": "No unique enclosing call; narrow the selected window.",
        "outer_result_not_unique": "No unique result; inspect tool-return rows in the window.",
        "outer_result_has_no_text": "No text is available to verify an excerpt.",
        "output_missing_or_too_large": "Output is absent or exceeds the comparison cap.",
        "output_has_too_many_lines": "Output exceeds the line comparison cap.",
        "output_bytes_do_not_match": "Output differs from the command record; don't quote it.",
        "no_exact_output_lines": "No exact returned lines match the command record.",
        "read_sources_not_separable": "Files were concatenated; source paths cannot be assigned.",
        "requested_passage_not_visible": "Requested line is absent; choose a returned passage.",
        "unsupported_or_compound_command": "Inspect the operation and return rows before citing.",
        "command_output_incomplete": "Output is incomplete; cite only retained lines.",
    }
    detail = {"trace_line": trace_line, "reason": reason,
              "action": action, "description": descriptions.get(
                  reason, "File output could not be attributed safely; inspect the selected trace."
              )}
    if event_id:
        detail["id"] = event_id
    detail["operation"] = _operation_skeleton(command_item or {}, action, event)
    if excerpt:
        detail["excerpt"] = excerpt
    if selection:
        detail["selection"] = selection
    return detail


def read_window(trace: Path, lines: tuple[int, int], corpus: Path, *, archive=False,
                selections=None):
    """Return window, events, full transient decisions, uncertainty and detail.

    In archive mode, selections maps a command event's trace line to
    [(corpus_relative_ref, source_line_or_None), ...]. Requested lines are
    retained alongside the default first 12 passages per event. Each selected
    line must be present in the model-facing tool return.
    """
    first, last = lines
    if first < 1 or last < first or not corpus.is_absolute():
        raise ValueError("expected a positive inclusive line range and absolute knowledge root")
    corpus = Path(os.path.normpath(corpus))
    selected_passages = selections or {}
    events, decisions, uncertain, unresolved_details = [], {}, [], []
    commands, seen = [], set()
    with trace.open("rb") as stream:
        meta = json.loads(stream.readline())
        if not isinstance(meta, dict) or meta.get("type") != "session_meta":
            raise ValueError("expected Codex session_meta in the first trace line")
        meta_payload = meta.get("payload", {})
        if not isinstance(meta_payload, dict):
            raise ValueError("expected Codex session metadata payload")
        session = _identifier(meta_payload.get("id"), "session ID")
        meta_cwd = _path(meta_payload.get("cwd"))
        number = 1
        while number < last:
            raw = stream.readline()
            if not raw:
                raise ValueError("round boundary exceeds the available trace")
            number += 1
            if number < first:
                continue
            row = json.loads(raw)
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                continue
            if (row.get("type") == "response_item" and payload.get("type") == "message"
                    and payload.get("role") == "assistant"
                    and payload.get("phase") in ("commentary", "final_answer")):
                content = payload.get("content", [])
                text = "".join(part.get("text", "") for part in content
                               if isinstance(part, dict) and isinstance(part.get("text"), str))
                if text:
                    # Full strings are transient quote-validation input. Callers
                    # must select a reviewed quote before serialization.
                    decisions[number] = text
            if row.get("type") != "event_msg" or payload.get("type") != "item_completed":
                continue
            item = payload.get("item", {})
            if not isinstance(item, dict) or item.get("type") != "CommandExecution":
                continue
            event_id = _identifier(item.get("id"), "command event ID")
            if event_id in seen:
                continue
            seen.add(event_id)
            event, complete, spec = _command(item, corpus)
            commands.append((number, item, event_id, event, complete, spec))
            if event is not None:
                events.append(dict(event, trace_line=number, event_id=event_id))
            if not complete:
                uncertain.append(number)
    window = {"session": session, "lines": [first, last]}
    if archive:
        window["archive"] = True
        joinable = [(line, item, event_id) for line, item, event_id, _, _, _ in commands]
        joins = correlate_window(trace, joinable, meta_cwd, (first, last))
        event_by_line = {event["trace_line"]: event for event in events}
        for line, item, event_id, event, complete, spec in commands:
            if event is None:
                if not complete:
                    action, compound = _rough_action(item)
                    detail = _detail(f"file-{line}", line, action,
                                     "unsupported_or_compound_command",
                                     command_item=item)
                    if compound:
                        detail["description"] = (
                            "Compound file operation; review its call and result before citing."
                        )
                    safe_list = _safe_file_list_pipeline(
                        item, corpus, joins.get(event_id, {"state": "unknown"})
                    )
                    if safe_list:
                        detail["description"] = (
                            "Samples are filenames only; no content or match count is attributed."
                        )
                        detail["operation"] = {
                            "tools": ["rg", "rg"], "action": "file_list_filter",
                            "scope": [safe_list["scope"]], "compound": True,
                        }
                        detail["command_excerpt"] = safe_list["command_excerpt"]
                        detail["excerpt"] = safe_list["excerpts"]
                        detail["return_line"] = joins[event_id]["return_line"]
                        detail["runtime_truncated"] = joins[event_id]["runtime_truncated"]
                        if safe_list["pattern_redacted"]:
                            detail["command_redacted"] = True
                        if safe_list["scope_normalized"]:
                            detail["command_root_normalized"] = True
                        if safe_list["command_truncated"]:
                            detail["command_excerpt_truncated"] = True
                        excerpt_truncated = sum(
                            passage.get("truncated", False) for passage in safe_list["excerpts"]
                        )
                        if safe_list["omitted"] or excerpt_truncated:
                            detail["archive_omitted"] = True
                    unresolved_details.append(detail)
                continue
            public_event = event_by_line[line]
            public_id = f"file-{line}"
            public_event["id"] = public_id
            public_event["event_id"] = public_id
            join = joins.get(event_id, {"state": "unknown", "runtime_truncated": None,
                                        "reason": "outer_call_not_unique"})
            delivery, problem, selection_issues = _delivery(
                public_event, spec, join, corpus, line, selected_passages
            )
            public_event["delivery"] = delivery
            for issue in selection_issues:
                unresolved_details.append(_detail(
                    public_id, line, public_event["action"], issue["reason"], public_event,
                    selection=issue.get("selection"),
                ))
            reason = None
            if not complete:
                reason = "command_output_incomplete"
            elif problem:
                reason = problem
            elif delivery["runtime_truncated"]:
                reason = "command_output_incomplete"
            elif delivery["state"] == "unknown":
                reason = join.get("reason", "output_missing_or_too_large")
            if (delivery["state"] == "unknown" or not complete
                    or delivery["runtime_truncated"]):
                if line not in uncertain:
                    uncertain.append(line)
            if reason:
                excerpt = delivery["passages"][0] if delivery["passages"] else None
                unresolved_details.append(_detail(
                    public_id, line, public_event["action"], reason, public_event, excerpt
                ))
        event_lines = set(event_by_line)
        for event_line, requested in selected_passages.items():
            if event_line not in event_lines and requested:
                unresolved_details.append(_detail(
                    None, event_line, "unknown", "requested_passage_not_visible"
                ))
    return window, events, decisions, uncertain, unresolved_details
