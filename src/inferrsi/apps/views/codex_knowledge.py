"""Decode recorded InferRSI CLI results without reopening the corpus."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from functools import lru_cache
from pathlib import Path

from inferrsi.harness.records.evidence import relative_location, sanitized_text

from .codex_tool_returns import _output_lines

_SEARCHES = ("find", "knowledge search", "knowledge research", "context", "cannbot search")
_READS = ("read", "knowledge show", "cannbot read")
_QUALIFIED = re.compile(r"(?:package|checkout|store):[A-Za-z0-9][A-Za-z0-9_.-]*")
_REVISION = re.compile(r"sha256:[a-f0-9]{64}")
_FIND_ROW = re.compile(r"([^\t]+)\t\[(case|skill|record) · [^\t]+\]\tscore [\d.]+")
_EXTERNAL_HEADING = "external (not locally verified; scores are not comparable across channels)"
_MAX_RESULT = 1_000_000


class _ArgumentError(ValueError):
    pass


class _QuietParser(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        pass  # A historic command must not print help or its private argument values.

    def exit(self, status=0, message=None):
        raise _ArgumentError


@lru_cache(maxsize=1)
def _parser():
    from ..cli.arguments import parser

    return parser(parser_class=_QuietParser)


def cli_arguments(argv):
    """Recognize the installed command, module, and Codex/WorkSwarm launcher."""
    start = 1 if argv and Path(argv[0]).name == "env" else 0
    while start < len(argv) and re.match(r"[A-Za-z_][A-Za-z0-9_]*=", argv[start]):
        start += 1
    if start >= len(argv):
        return None
    program = Path(argv[start]).stem.lower()
    args = argv[start + 1:]
    if re.fullmatch(r"python(?:\d+(?:\.\d+)?)?", Path(argv[start]).name.removesuffix(".exe")):
        while args and args[0] in ("-B", "-I", "-S", "-s", "-E", "-u", "-X", "-P"):
            args = args[2:] if args[0] == "-X" else args[1:]
        if args[:2] == ["-m", "inferrsi"]:
            args = args[2:]
        elif args and Path(args[0]).name == "inferrsi.py":
            args = args[1:]
        else:
            return None
    elif program != "inferrsi":
        return None
    return args


def invocation(argv):
    args = cli_arguments(argv)
    tool = " ".join(args[:2]) if args and args[0] in ("knowledge", "cannbot") else (
        args[0] if args else "")
    if tool in (*_SEARCHES, *_READS, "collect"):
        return tool, args
    return None


def _ref(value):
    return (value if isinstance(value, str) and _QUALIFIED.fullmatch(value)
            and relative_location(value) == value else None)


def _external_ref(channel, locator):
    if (isinstance(channel, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", channel)
            and isinstance(locator, str) and relative_location(locator) == locator):
        ref = f"{channel}:{locator}"
        if relative_location(ref) == ref:
            return ref
    raise ValueError("external locator is not portable")


def _item(ref, read_args=()):
    if _ref(ref) is None:
        raise ValueError("missing qualified Find result")
    row = {"ref": ref}
    if len(read_args) >= 2 and read_args[0] == "read":
        opened = _ref(read_args[1])
        if opened and opened != ref:
            row["read_ref"] = opened
    return row


def _find_json(args, text):
    result = json.loads(text)
    items, matched, no_match = result["items"], result["matched"], result["no_match"]
    if (result["query"] != args.query or not isinstance(items, list)
            or type(matched) is not int or matched < 0 or type(no_match) is not bool
            or len(items) != min(args.limit, matched) or no_match != (matched == 0)):
        raise ValueError("invalid Find result")
    materials = [_item(f"{row['authority']}:{row['id']}", row.get("read_args", []))
                 for row in items]
    for channel in result.get("external", []):
        if channel["state"] != "ok":
            continue
        hits = channel.get("items", [])
        if channel["count"] != len(hits):
            raise ValueError("incomplete external Find result")
        materials.extend({"ref": _external_ref(channel["channel"], hit["locator"])}
                         for hit in hits)
    return materials


def _find_text(text):
    local, external = [], []
    no_match = False
    channel, remaining = None, 0
    for line in _output_lines(text):
        if not line:
            continue
        if line == _EXTERNAL_HEADING:
            channel = ""
        elif channel is not None:
            heading = re.fullmatch(r"  ([a-z0-9-]+) @ [^\t]+\t\[[^\t]+\]\t(\d+) hit\(s\)\t\d+ ms",
                                   line)
            if heading:
                if remaining:
                    raise ValueError("incomplete external hits")
                channel, remaining = heading[1], int(heading[2])
            elif remaining and (hit := re.fullmatch(r"     [\d.-]+\t[^\t]*\t([^\t]+)", line)):
                external.append({"ref": _external_ref(channel, hit[1])})
                remaining -= 1
            elif not line.startswith("  "):
                raise ValueError("unrecognized external Find result")
        elif line.startswith("no_match\t") and " entries searched;" in line:
            no_match = True
        elif match := _FIND_ROW.fullmatch(line):
            authority = "package" if match[2] == "record" else "checkout"
            local.append(_item(f"{authority}:{match[1]}"))
        elif local and (opening := re.fullmatch(r"     open(?: \(PowerShell\))?: (.+)", line)):
            candidate = invocation(shlex.split(opening[1].removeprefix("& ")))
            if candidate and candidate[0] == "read":
                local[-1] = _item(local[-1]["ref"], candidate[1])
        elif not (local and line.startswith("  ")):
            raise ValueError("unrecognized local Find result")
    if bool(local) == no_match or remaining:
        raise ValueError("incomplete Find result")
    return [*local, *external]


def _read_result(args, output):
    view = json.loads(output)
    revision = view["revision"]
    identity = view["id"]
    ref = view.get("ref") or args.id  # Older qualified commands already record the authority.
    if (not _ref(ref) or identity != ref.partition(":")[2]
            or args.id not in (ref, identity) or not _REVISION.fullmatch(revision)
            or (args.revision is not None and args.revision != revision)):
        raise ValueError("read result does not identify the requested material")
    material = {"ref": ref, "revision": revision}
    if args.resource is None and not args.material:
        return material, None
    path = view["content_resource"] if args.resource is not None else view["entrypoint"]
    body = view["content"]
    if (relative_location(path) != path or not isinstance(path, str)
            or (args.resource is not None and args.resource != path)
            or not isinstance(body, str)):
        raise ValueError("read result does not contain the requested resource")
    return material, (path, body)


def decode(call, code, output):
    tool, argv = call
    if argv[-1] in ("--help", "-h") and "--" not in argv:
        return None, True, None
    try:
        args = _parser().parse_args(argv)
    except _ArgumentError:
        args = None

    action = "search" if tool in _SEARCHES or tool == "collect" else "read"
    if args is not None:
        if tool == "collect" and args.ids:
            action = "read"
        if tool in ("collect", "knowledge search", "context") and action == "search":
            if not (args.query.strip() or getattr(args, "relevance", None)):
                return None, True, None  # A queryless listing is inventory.
    event = {"tool": tool, "action": action, "materials": []}
    if type(code) is int:
        event["exit_code"] = code
    if args is not None and action == "search":
        query = (getattr(args, "query", None) or getattr(args, "relevance", None)
                 or getattr(args, "model", None))
        if query:
            event["query"] = sanitized_text(query, "")
    spec = {"kind": "knowledge", "decoded": False}
    if (args is None or type(code) is not int or code != 0 or not isinstance(output, str)
            or not output.strip() or len(output) > _MAX_RESULT):
        return event, False, spec
    try:
        if tool == "find":
            event["materials"] = _find_json(args, output) if args.json else _find_text(output)
        elif tool == "read":
            material, spec["resource"] = _read_result(args, output)
            event["materials"] = [material]
        else:
            # Compatibility tools have separate output shapes. A recognized
            # invocation must not pass a complete-coverage check as zero.
            return event, False, spec
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return event, False, spec
    spec["decoded"] = True
    return event, True, spec
