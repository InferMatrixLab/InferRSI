"""Decode recorded InferRSI CLI results without reopening the corpus."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from functools import lru_cache
from pathlib import Path

from inferrsi.harness.records.evidence import relative_location, sanitized_text
from inferrsi.harness.records.knowledge_capture import ranking_identity, valid_content_range

from .codex_tool_returns import _output_lines

_SEARCHES = ("find", "knowledge search", "knowledge research", "context", "cannbot search")
_READS = ("read", "knowledge show", "cannbot read")
_CAPTURE_SEARCHES = (
    "campaign capture-context", "campaign knowledge", "benchmarks session knowledge",
)
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

    return parser(parser_class=_QuietParser, historical=True)


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
    if not args:
        return None
    length = {"knowledge": 2, "cannbot": 2, "campaign": 2, "benchmarks": 3}.get(args[0], 1)
    tool = " ".join(args[:length])
    if tool in (*_SEARCHES, *_READS, *_CAPTURE_SEARCHES, "collect"):
        return tool, args
    return None


def _ref(value):
    return (value if isinstance(value, str) and _QUALIFIED.fullmatch(value)
            and relative_location(value) == value else None)


def _external_ref(channel, locator):
    if channel == "mindie-agent":
        return _mindie_locator(locator)[0]
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
        elif opened and "--revision" in read_args:
            revision = read_args[read_args.index("--revision") + 1:]
            if not revision or not _REVISION.fullmatch(revision[0]):
                raise ValueError("invalid revision in Find read arguments")
            row["revision"] = revision[0]
    return row


def external_hit_refs(channels):
    for channel in [channels] if isinstance(channels, dict) else channels:
        if channel["state"] == "ok":
            hits = channel.get("items", [])
            if channel["count"] != len(hits):
                raise ValueError("incomplete external Find result")
            for hit in hits:
                yield _external_ref(channel["channel"], hit["locator"])


def mindie_unit_from_key(ref):
    """Parse the archive's versioned unit key without admitting it as a filesystem location."""
    from ..integrations.mindie.context import UNIT_REFERENCE

    prefix = "mindie-agent:"
    if (isinstance(ref, str) and len(ref) <= 240 and ref.startswith(prefix)
            and sanitized_text(ref, "") == ref):
        return UNIT_REFERENCE.fullmatch("mindie://" + ref[len(prefix):])
    return None


def _mindie_locator(locator):
    if isinstance(locator, str) and locator.startswith("mindie://"):
        key = "mindie-agent:" + locator.removeprefix("mindie://")
        if unit := mindie_unit_from_key(key):
            return key, unit
    raise ValueError("invalid native navigation reference")


def _external_material(ref):
    if ref.startswith("mindie-agent:"):
        return {"ref": ref, "revision": ref.rsplit("@", 1)[1]}
    return {"ref": ref}


def _native_mindie_find(text):
    from ..integrations.mindie.context import _payload

    envelope = json.loads(text)
    if not isinstance(envelope.get("receipt_directory"), str) or not envelope["receipt_directory"]:
        raise ValueError("missing native query receipt")
    page, _ = _payload(envelope["result"], {"results"})
    if "retrieval" in page and (
        page["retrieval"] != "graded-bm25" or not {"cards", "foundation_cards"} <= page.keys()
    ):
        raise ValueError("incomplete graded navigation page")
    domain = page.get("domain")
    if domain is not None and (not isinstance(domain, str)
                               or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", domain)):
        raise ValueError("invalid native query domain")
    materials = {}
    for name in ("cards", "foundation_cards", "unverified_cards", "results"):
        rows = page.get(name, [])
        if not isinstance(rows, list):
            raise ValueError("invalid native navigation list")
        for row in rows:
            key, unit = _mindie_locator(row["ref"])
            if domain is not None and unit["domain"] != domain:
                raise ValueError("invalid native navigation domain")
            domain = unit["domain"]
            if (row.get("id", unit["id"]) != unit["id"]
                    or "revision" in row and (type(row["revision"]) is not int
                                              or str(row["revision"]) != unit["revision"])):
                raise ValueError("invalid native navigation identity")
            material = materials.setdefault(key, {"ref": key, "revision": unit["revision"],
                                                  "navigation": []})
            observed = {"list": name}
            if "match_status" in row:
                if row["match_status"] not in ("matched", "mismatched", "condition_unknown"):
                    raise ValueError("invalid native navigation status")
                observed["match_status"] = row["match_status"]
            if "ready_to_apply" in row:
                if type(row["ready_to_apply"]) is not bool:
                    raise ValueError("invalid native navigation applicability")
                observed["ready_to_apply"] = row["ready_to_apply"]
            if observed not in material["navigation"]:
                material["navigation"].append(observed)
    request = {"external_source": "mindie-agent"}
    if domain is not None:
        request["domain"] = domain
    event = {"materials": list(materials.values()), "request": request}
    if query := sanitized_text(envelope.get("query"), ""):
        event["query"] = query
    if type(page.get("usage", {}).get("has_more")) is bool:
        event["has_more"] = page["usage"]["has_more"]
    return event


def _find_json(args, text):
    from ...knowledge.channels import no_match_across_sources

    result = json.loads(text)
    items, matched, no_match = result["items"], result["matched"], result["no_match"]
    query = args.query or getattr(args, "model", None)
    external = result.get("external", [])
    if external and (args.no_external or args.external_source == "none"):
        raise ValueError("An offline Find has no external return")
    if (args.session is not None and isinstance(external, dict)
            and external.get("channel") == "cannbot-knowledge"):
        # Session Find sends the same redacted query to its local and frozen external sources.
        query = sanitized_text(query, "", limit=None)
    if (result["query"] != query or not isinstance(items, list)
            or type(matched) is not int or matched < 0
            or len(items) != min(args.limit, matched)):
        raise ValueError("invalid Find result")
    channels = [external] if isinstance(external, dict) else external
    # Earlier transcripts used no_match for the local corpus alone.
    if (no_match is not (matched == 0)
            and no_match is not no_match_across_sources(matched, channels)):
        raise ValueError("Find match status disagrees with its results")
    materials = []
    for row in items:
        if getattr(args, "session", None) and row.get("material_ref"):
            material = _item(row["material_ref"])
            if isinstance(row.get("revision"), str):
                material["revision"] = row["revision"]
        else:
            material = _item(f"{row['authority']}:{row['id']}", row.get("read_args", []))
            if ("revision" in material
                    and row.get("revision", material["revision"]) != material["revision"]):
                raise ValueError("Find result and read revision disagree")
        materials.append(material)
    materials.extend(_external_material(ref) for ref in external_hit_refs(external))
    return materials


def _legacy_model_materials(args, text):
    """The original model command returned package records without bundle revision pins."""
    result = json.loads(text)
    items, queries = result["items"], result["queries"]
    scope = {"repo": args.repo_type, "tier": args.tier,
             "backend": args.backend, "scenario": args.scenario}
    if (result["model"] != args.model.strip() or result["filters"] != scope
            or not isinstance(items, list) or not isinstance(queries, list) or not queries
            or result["no_match"] is not (not items) or args.limit < 1):
        raise ValueError("invalid historical model result")
    counts = [q["matches"] for q in queries]
    if (any(type(n) is not int or n < 0 for n in counts)
            or not min(args.limit, max(counts)) <= len(items) <= min(args.limit, sum(counts))):
        raise ValueError("incomplete historical model result")
    materials = [_item("package:" + row["record"]["id"]) for row in items]
    if len({row["ref"] for row in materials}) != len(materials):
        raise ValueError("duplicate historical model result")
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
            heading = re.fullmatch(
                r"  ([a-z0-9-]+)(?: @ [^\t]+\t\[[^\t]+\])?\t(\d+) hit\(s\)\t\d+ ms", line,
            )
            if heading:
                if remaining:
                    raise ValueError("incomplete external hits")
                channel, remaining = heading[1], int(heading[2])
            elif remaining:
                row = r"     [^\t]*\t([^\t]+)" if channel == "mindie-agent" else (
                    r"     [\d.-]+\t[^\t]*\t([^\t]+)")
                if hit := re.fullmatch(row, line):
                    external.append(_external_material(_external_ref(channel, hit[1])))
                    remaining -= 1
                else:
                    raise ValueError("incomplete external hit")
            elif not line.startswith("  "):
                raise ValueError("unrecognized external Find result")
        elif line.startswith(("no_match\t", "local_no_match\t")) and " entries searched;" in line:
            no_match = True
        elif match := _FIND_ROW.fullmatch(line):
            authority = "package" if match[2] == "record" else "checkout"
            local.append(_item(f"{authority}:{match[1]}"))
        elif local and line.startswith("     material: "):
            ref = line.removeprefix("     material: ")
            if ref.partition(":")[2] != local[-1]["ref"].partition(":")[2]:
                raise ValueError("Find material does not identify the displayed item")
            local[-1] = _item(ref)
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
    scoped = getattr(args, "session", None) is not None
    revision_known = _REVISION.fullmatch(revision) or (
        scoped and re.fullmatch("[0-9a-f]{40}", revision))
    if (not _ref(ref) or identity != ref.partition(":")[2]
            or args.id not in (ref, identity) or not revision_known
            or (args.revision is not None and args.revision != revision)):
        raise ValueError("read result does not identify the requested material")
    material = {"ref": ref, "revision": revision}
    if scoped and any(item["ref"] == ref for item in view.get("context_omissions", [])):
        return material, None
    if not scoped and args.resource is None and not args.material:
        return material, None
    path = view["content_resource"] if args.resource is not None or scoped else view["entrypoint"]
    body = view["content"]
    if (relative_location(path) != path or not isinstance(path, str)
            or not isinstance(body, str)):
        raise ValueError("read result does not contain the requested resource")
    if args.resource is not None and args.resource != path:
        from inferrsi.knowledge.knowledge_operations import resolve_resource_key

        base = view["body_resource"]
        if not isinstance(base, str) or relative_location(base) != base:
            raise ValueError("read result does not identify the source of its resource link")
        resolve_resource_key(args.resource, base, (path,))
    bounds = view.get("content_range")
    if bounds is not None or args.byte_range is not None:
        if not valid_content_range(bounds, body):
            raise ValueError("read returned inconsistent byte range")
        start, end = bounds["start"], bounds["end"]
        if (args.byte_range is None and start != 0
                or args.byte_range is not None and (start != args.byte_range[0]
                                                     or end - start > args.byte_range[1])):
            raise ValueError("read returned inconsistent byte range")
        material["content_range"] = bounds
    return material, (path, body)


def decode(call, code, output):
    tool, argv = call
    if argv[-1] in ("--help", "-h") and "--" not in argv:
        return None, True, None
    try:
        args = _parser().parse_args(argv)
        if tool == "find" and not any(
                arg == "--limit" or arg.startswith("--limit=") for arg in argv):
            args.limit = 10 if getattr(args, "model", None) else 5
    except _ArgumentError:
        args = None

    if tool in _CAPTURE_SEARCHES:
        manual = tool == "campaign capture-context"
        if (manual and args is not None
                and (args.ids is not None or not (args.query.strip() or args.relevance))):
            return None, True, None  # Inventory and exact assembly do not search.
        directory = context_id = None
        if args is not None and code == 0:
            directory = args.directory if manual else args.session
            context_id = args.id if manual else None
        # The retained capture supplies the event and counts. The trace join
        # determines whether this command is accounted for by that capture.
        return None, False, {"kind": "captured_search", "tool": tool,
                             "directory": directory, "context_id": context_id}

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
        if tool == "find" and args.input is not None:
            if (args.external_source not in (None, "mindie-agent") or args.session is not None
                    or args.query is not None or args.model is not None):
                raise ValueError("unsupported native Find arguments")
            event.update(_native_mindie_find(output))
        elif tool == "find":
            structured = args.json or args.session or args.model or args.input
            event["materials"] = _find_json(args, output) if structured else _find_text(output)
        elif tool == "knowledge research":
            event["materials"] = _legacy_model_materials(args, output)
        elif tool == "read":
            material, spec["resource"] = _read_result(args, output)
            event["materials"] = [material]
        else:
            # Compatibility tools have separate output shapes. A recognized
            # invocation must not pass a complete-coverage check as zero.
            return event, False, spec
        if getattr(args, "session", None) is not None and tool in ("find", "read"):
            returned = json.loads(output)
            reference = returned["reference"]
            kind = "knowledge_search" if tool == "find" else "delivered_context"
            if (reference["kind"] != kind or not isinstance(reference["path"], str)
                    or relative_location(reference["path"]) != reference["path"]):
                raise ValueError("invalid scoped receipt")
            if "sha256" in reference:
                if not re.fullmatch("[0-9a-f]{64}", reference["sha256"]):
                    raise ValueError("invalid scoped receipt digest")
                spec["capture"] = (reference["path"], reference["sha256"])
                spec["directory"] = args.session
                spec["context_id"] = getattr(args, "capture_id", None)
            request = {}
            if policy := ranking_identity(returned.get("ranking_policy")):
                request["ranking_policy"] = policy
            if tool == "find":
                request["kinds"] = sanitized_text(args.kinds, "")
            else:
                if relative_location(args.search_ref) == args.search_ref and args.search_ref:
                    request["search_ref"] = args.search_ref
                path = returned.get("content_resource")
                if isinstance(path, str) and relative_location(path) == path:
                    request["resource"] = path
            event["request"] = request
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return event, False, spec
    spec["decoded"] = True
    return event, True, spec
