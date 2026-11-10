"""Extract file search observations from a caller-selected Codex Desktop rollout window."""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

from .campaign_records import _identifier
from .dashboard_data import _relative_location, _text


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
    it = iter(args)
    for arg in it:
        if arg == "--":
            operands.extend(it)
            break
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
        elif arg in ("--files-with-matches", "-l"):
            mode = "files"
            options.append(arg)
        elif arg in ("--no-heading", "--with-filename", "--line-number", "--ignore-case",
                     "--fixed-strings", "--word-regexp", "--smart-case", "--hidden"):
            options.append(arg)
        elif arg.startswith("-"):
            if not re.fullmatch(r"-[inSFwHs]+", arg):
                return None
            options.append(arg)
        else:
            operands.append(arg)
    if not patterns and operands:
        patterns.append(operands.pop(0))
    return (" | ".join(patterns), operands or ["."], mode, options) if patterns else None


def _rg_hits(output, cwd, corpus, scopes, mode, options):
    hits = {}
    scopes = [Path(os.path.normpath(cwd / s)) for s in scopes]
    has_context = any(opt in options for opt in ("-A", "-B", "-C", "--context"))
    complete = True
    for line in output.splitlines():
        if "tokens truncated" in line and ("…" in line or "..." in line):
            complete = False
            continue
        if mode == "files":
            path, number = line, None
        else:
            if has_context and (line == "--" or re.match(r"^(?:[^:]*-)?\d+-", line.split(":")[0])
                                and not re.match(r"^[^:]+:\d+:", line)):
                continue  # context rather than a matching line
            # For a single explicit file, rg -n omits the filename. Do not stat
            # the live corpus: the retained rollout may outlive that checkout.
            bare = re.match(r"^(\d+):", line)
            if bare and len(scopes) == 1 and scopes[0] != cwd:
                path, number = str(scopes[0]), int(bare[1])
            else:
                match = re.match(r"^([^:]+):(?:(\d+):)?", line)
                if not match:
                    complete = False
                    continue
                path, number = match[1], int(match[2]) if match[2] else None
        candidate = Path(os.path.normpath(cwd / path))
        if not any(candidate.is_relative_to(scope) for scope in scopes):
            complete = False
            continue
        ref = _material(cwd, str(candidate), corpus)
        if ref:
            hits.setdefault(ref, number)
        elif candidate.is_relative_to(corpus):
            complete = False
    return [{"ref": ref, "match_line": n} for ref, n in hits.items()], complete


def _command(item, corpus):
    argv = item.get("command")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        return None, False
    if (Path(argv[0]).name in ("sh", "bash", "zsh", "dash") and len(argv) == 3
            and argv[1] in ("-c", "-lc", "-ic", "-ilc")):
        try:
            lexer = shlex.shlex(argv[2], posix=True, punctuation_chars=";&|<>")
            lexer.whitespace_split = True
            argv = list(lexer)
        except ValueError:
            return None, False
    if not argv:
        return None, True
    tool = Path(argv[0]).name
    if tool not in ("rg", "cat", "sed", "nl"):
        # A pipeline or chained directory change may hide an in-scope action.
        return None, not any(Path(word).name in ("rg", "cat", "sed", "nl") for word in argv)
    cwd = item.get("cwd")
    if isinstance(cwd, str) and cwd.startswith("file://"):
        uri = urlsplit(cwd)
        cwd = url2pathname(uri.path) if uri.netloc in ("", "localhost") else None
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return None, False
    cwd = Path(cwd)
    if any(word in {"|", "||", "&&", ";", ">", ">>", "<"} for word in argv):
        return None, False
    code, output = item.get("exit_code"), item.get("aggregated_output")
    if not isinstance(output, str) or type(code) is not int:
        return None, False
    if tool == "rg":
        if "--files" in argv:
            return None, True  # inventory, not a content search
        parsed = _rg_args(argv[1:])
        if parsed is None:
            return None, False
        query, scopes, mode, options = parsed
        if any(re.search(r"[$`*?~{}\[]", value) for value in scopes):
            return None, False  # literal command text cannot resolve expanded operands
        paths = [Path(os.path.normpath(cwd / value)) for value in scopes]
        scope_refs = ["." if p == corpus or corpus.is_relative_to(p)
                      else _material(cwd, str(p), corpus) for p in paths]
        if not any(scope_refs):
            return None, True
        materials, complete = [], code == 1
        if code == 0:
            materials, complete = _rg_hits(output, cwd, corpus, scopes, mode, options)
        event = {"action": "search", "tool": tool, "query": _text(query),
                 "scope": [s for s in scope_refs if s], "options": options,
                 "exit_code": code, "materials": materials}
        return event, complete and (code != 0 or bool(materials))
    if tool == "cat":
        names = argv[2:] if argv[1:2] == ["--"] else argv[1:]
        if any(n.startswith("-") for n in names):
            return None, False
    elif len(argv) == 4 and tool == "sed" and argv[1] == "-n" and re.fullmatch(
            r"\d+(?:,\d+)?p", argv[2]):
        names = argv[3:]
    elif tool == "nl" and len(argv) == 3 and argv[1] == "-ba":
        names = argv[2:]
    else:
        return None, False
    if any(re.search(r"[$`*?~{}\[]", n) for n in names):
        return None, False
    refs = [ref for n in names if (ref := _material(cwd, n, corpus))]
    if not refs or code != 0:
        return None, True
    # Successful cat opened every literal operand. Its shared stdout cannot
    # establish which file supplied a particular passage.
    return {"action": "read", "tool": tool,
            "materials": [{"ref": ref} for ref in dict.fromkeys(refs)]}, True


def read_window(trace: Path, lines: tuple[int, int], corpus: Path):
    """Return only attributed events and decision locators, never the raw transcript."""
    first, last = lines
    if first < 1 or last < first or not corpus.is_absolute():
        raise ValueError("expected a positive inclusive line range and absolute knowledge root")
    events, decisions, seen, uncertain = [], set(), set(), []
    with trace.open("rb") as stream:
        meta = json.loads(stream.readline())
        if not isinstance(meta, dict) or meta.get("type") != "session_meta":
            raise ValueError("expected Codex session_meta in the first trace line")
        session = _identifier(meta.get("payload", {}).get("id"), "session ID")
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
            if (row.get("type") == "response_item" and payload.get("type") == "message"
                    and payload.get("role") == "assistant"
                    and payload.get("phase") in ("commentary", "final_answer")
                    and any(isinstance(part, dict) and part.get("text")
                            for part in payload.get("content", []))):
                decisions.add(number)
            if row.get("type") != "event_msg" or payload.get("type") != "item_completed":
                continue
            item = payload.get("item", {})
            if item.get("type") != "CommandExecution":
                continue
            event_id = _identifier(item.get("id"), "command event ID")
            if event_id in seen:
                continue
            seen.add(event_id)
            event, complete = _command(item, corpus)
            if event:
                events.append(dict(event, trace_line=number, event_id=event_id))
            if not complete:
                uncertain.append(number)
    return {"session": session, "lines": [first, last]}, events, decisions, uncertain
