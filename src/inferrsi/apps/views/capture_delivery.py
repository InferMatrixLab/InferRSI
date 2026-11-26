"""Check which prepared Indexer resources also appear in a reviewed tool return."""

import hashlib
import json
import re

from inferrsi.apps.workflows.campaign import verify_capture
from inferrsi.harness.records.campaign_records import _identifier
from inferrsi.harness.records.evidence import (
    inside as _inside,
)
from inferrsi.harness.records.evidence import (
    relative_location as _relative_location,
)
from inferrsi.harness.records.evidence import (
    sanitized_text as _text,
)
from inferrsi.harness.records.knowledge_capture import (
    MAX_CONTEXT_CAPTURE_BYTES,
    ranking_identity,
    scoped_response,
)
from inferrsi.harness.records.optimization_log import _unique
from inferrsi.knowledge.context_projection import assemble_context_text

from .codex_knowledge import external_hit_refs
from .codex_tool_returns import _output_lines, _response_chunks, _response_text

_EXTERNAL_SUFFIX = ',\n  "external": '


def capture_return_texts(trace, lines, references, context_ids, *, exec_returns=None):
    """Read only tool-return text at the caller's line references in this round."""
    if not isinstance(references, dict):
        raise ValueError("capture_returns must map capture IDs to tool-return lines")
    if not references:
        return {}
    if trace is None or lines is None or not set(references).issubset(context_ids):
        raise ValueError("capture_returns requires a trace and a selected capture for each ID")
    first, last = lines
    wanted = set()
    for number in references.values():
        if type(number) is not int or not first <= number <= last:
            raise ValueError("capture return line is outside the round")
        wanted.add(number)
    texts = {}
    with trace.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            if number not in wanted:
                continue
            row = json.loads(raw)
            payload = row.get("payload", {})
            if row.get("type") != "response_item" or payload.get("type") not in (
                "function_call_output", "custom_tool_call_output"
            ):
                raise ValueError("capture return must reference a model-facing tool response")
            verified = exec_returns.get(number) if exec_returns else None
            texts[number] = _response_chunks(row, verified) or []
            if wanted == texts.keys():
                break
    if wanted != texts.keys():
        raise ValueError("capture return line is missing from the trace")
    return {key: texts[number] for key, number in references.items()}


def _managed_envelope(doc, reference):
    action = (doc.get("retrieval") or {}).get("entrypoint")
    if action in ("find", "read") and "display" in doc["retrieval"]:
        kind = doc["retrieval"].get(
            "receipt_kind", "knowledge_search" if action == "find" else "delivered_context",
        )
        ref = {"path": reference["path"], "kind": kind, "sha256": reference["sha256"]}
        return json.dumps(scoped_response(doc, ref, "."), ensure_ascii=False, indent=2)
    return json.dumps({"reference": reference, "context": doc}, ensure_ascii=False, indent=2)


def portable_find_return(text):
    """Compare scoped read commands after relocating their local CLI argument paths."""
    if ('"kind": "knowledge_search"' not in text
            and not ('"kind": "delivered_context"' in text and '"next_read_args"' in text)):
        return text
    markers = {"session": ".", "skill-root": "SKILL_ROOT", "store": "STORE"}
    return re.sub(r'(^\s*"--(session|skill-root|store)",\n\s*)"(?:(?:\\.)|[^"\\])*"',
                  lambda m: m[1] + json.dumps(markers[m[2]]), text, flags=re.MULTILINE)


def capture_receipts(captures):
    """Render the manual CLI's capture receipts without material bodies."""
    return {key: json.dumps({"context": source, "sha256": digest}, ensure_ascii=False, indent=2)
            for key, (_, source, digest) in captures.items()}


def managed_envelopes(captures):
    return {key: _managed_envelope(doc, {
        "path": source, "sha256": digest, "kind": "delivered_context",
    }) for key, (doc, source, digest) in captures.items()}


def _joint_output(chunk, start):
    try:
        external, end = json.JSONDecoder(object_pairs_hook=_unique).raw_decode(chunk, start)
    except (ValueError, RecursionError):
        return None, None
    if (isinstance(external, dict) and external.get("channel") == "cannbot-knowledge"
            and chunk.startswith("\n}", end)):
        return end + 2, external
    return None, None


def managed_local_output(output):
    """Return the exact local envelope from a complete joint CLI response."""
    prefix, separator, _ = output.rpartition(_EXTERNAL_SUFFIX)
    if separator and _joint_output(output, len(prefix) + len(separator))[0] == len(output):
        return prefix + "\n}"
    return output


def _matched_envelope(chunk, body):
    chunk = "\n" + chunk.replace("\r\n", "\n") + "\n"
    if '"kind": "knowledge_search"' in body or '"next_read_args"' in body:
        chunk = portable_find_return(chunk)
    if f"\n{body}\n" in chunk:
        return True, None
    prefix = f"\n{body[:-2]}{_EXTERNAL_SUFFIX}"
    start = chunk.find(prefix)
    if start < 0:
        return False, None
    end, external = _joint_output(chunk, start + len(prefix))
    return (True, external) if end is not None and chunk[end:end + 1] == "\n" else (False, None)


def managed_return_lines(trace, lines, envelopes, *, reserved, exec_returns=None):
    """Locate exact tool returns for selected managed captures in the round."""
    if not envelopes:
        return {}
    found = {}
    first, last = lines
    with trace.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            if number > last or len(found) == len(envelopes):
                break
            if number < first or number in reserved:
                continue
            row = json.loads(raw)
            payload = row.get("payload", {})
            if (row.get("type") != "response_item" or not isinstance(payload, dict)
                    or payload.get("type") not in (
                        "function_call_output", "custom_tool_call_output",
                    )):
                continue
            text = _response_text(row, exec_returns.get(number) if exec_returns else None)
            if text is None:
                continue
            keys = [key for key, body in envelopes.items() if _matched_envelope(text, body)[0]]
            if len(keys) == 1:
                found.setdefault(keys[0], number)
    return found


def visible_capture_resources(doc, texts):
    """Require matching owner, revision, resource path and body in the visible text."""
    visible = []
    if not texts:
        return visible
    chunks = ["\n" + text + "\n" for text in texts]
    for context in doc["contexts"]:
        for resource in context["resources"]:
            if not resource["content"]:
                continue
            block = assemble_context_text([{
                **context, "resources": [resource], "omissions": [],
            }])
            if any("\n" + block in chunk for chunk in chunks):
                item = {"ref": context["ref"], "path": resource["path"]}
                if "content_range" in resource:
                    item["content_range"] = resource["content_range"]
                visible.append(item)
    return visible


def _archive_capture_metadata(doc):
    request = doc.get("request", {})
    safe_request = {}
    for key in ("query", "relevance", "relevance_method", "kind", "repo", "tier", "backend",
                "scenario"):
        value = request.get(key)
        if isinstance(value, str):
            safe_request[key] = _text(value, "", limit=len(value))
    if "display" in (doc.get("retrieval") or {}):
        if policy := ranking_identity(request.get("ranking_policy")):
            safe_request["ranking_policy"] = policy
        if isinstance(kinds := request.get("kinds"), str):
            safe_request["kinds"] = _text(kinds, "", limit=len(kinds))
        for key in ("resource", "search_ref"):
            value = request.get(key)
            if isinstance(value, str) and _relative_location(value) == value:
                safe_request[key] = value
    ids = request.get("ids")
    if isinstance(ids, list):
        safe_request["ids"] = [value for value in ids if isinstance(value, str)
                               and _relative_location(value) == value]
    sources = request.get("sources")
    if isinstance(sources, list):
        safe_request["sources"] = [_text(value, "", limit=len(value))
                                   for value in sources if isinstance(value, str)]
    for key in ("limit", "context_bytes"):
        value = request.get(key)
        if type(value) is int and value >= 0:
            safe_request[key] = value
    selection = doc.get("selection")
    safe_selection = {}
    if isinstance(selection, dict):
        for key in ("method", "cue", "scope"):
            value = selection.get(key)
            if isinstance(value, str):
                safe_selection[key] = _text(value, "", limit=len(value))
        if type(selection.get("ranking_applied")) is bool:
            safe_selection["ranking_applied"] = selection["ranking_applied"]
    return safe_request, safe_selection


def load_campaign_capture(root, campaign_id, context_id):
    _identifier(context_id, "context ID")
    path = root / "knowledge" / f"{context_id}.json"
    if not _inside(root, path):
        raise ValueError("capture escapes the campaign")
    with path.open("rb") as stream:
        raw = stream.read(MAX_CONTEXT_CAPTURE_BYTES + 1)
    doc, state = verify_capture(raw)
    if not doc or doc["campaign_id"] != campaign_id or doc["context_id"] != context_id:
        raise ValueError(f"invalid or mismatched campaign capture ({state})")
    return doc, path.relative_to(root).as_posix(), hashlib.sha256(raw).hexdigest()


def citation_excerpts(text, quotes):
    """Keep exact quoted bytes that are still present after sanitizing the source line."""
    requested = [quote for quote in quotes if quote and quote in text]
    if not requested:
        return []
    public = _text(text, "", limit=None)
    return sorted((q for q in requested if q in public and _text(q, "", limit=None) == q),
                  key=lambda q: (text.index(q), q))


def _capture_passages(doc, selections, visible, excerpts):
    locators = dict.fromkeys((item["ref"], item["passage_path"], item["passage_line"])
                             for item in selections)
    passages = []
    for ref, path, line in locators:
        if (ref, path) not in visible:
            raise ValueError("Indexer review needs a matching visible captured resource")
        if line is None:
            raise ValueError("Indexer review needs a positive source line")
        resources = [resource for context in doc["contexts"] if context["ref"] == ref
                     for resource in context["resources"] if resource["path"] == path]
        if len(resources) != 1:
            raise ValueError("Indexer review must name one exact captured resource")
        lines = _output_lines(resources[0]["content"])
        offset = line - resources[0].get("content_range", {}).get("first_line", 1)
        if not 0 <= offset < len(lines) or not lines[offset]:
            raise ValueError("Indexer review source line is missing or empty")
        text = lines[offset]
        if _text(text, "", limit=len(text)) != text:
            raise ValueError("Indexer review source passage is not safe to publish verbatim")
        passages.append({"ref": ref, "path": path, "line": line, "text": text})
    for context in doc["contexts"]:
        ref = context["ref"]
        if ref not in excerpts:
            continue
        for resource in context["resources"]:
            path = resource["path"]
            if (ref, path) not in visible:
                continue
            first_line = resource.get("content_range", {}).get("first_line", 1)
            for line, text in enumerate(_output_lines(resource["content"]), first_line):
                if (ref, path, line) in locators:
                    continue
                quoted = citation_excerpts(text, excerpts[ref])
                if not quoted:
                    continue
                source = {"ref": ref, "path": path, "line": line}
                passages.extend({**source, "text": quote, "quoted": True,
                                 **({"truncated": True} if quote != text else {})}
                                for quote in quoted)
    return passages


def capture_event(context_id, captured, *, archive=False, return_chunks=None,
                  return_line=None, selected_passages=(), excerpts=None):
    doc, source, digest = captured
    resources = {c["ref"]: [r["path"] for r in c["resources"]] for c in doc["contexts"]}
    ranges = {c["ref"]: r["content_range"] for c in doc["contexts"]
              for r in c["resources"] if "content_range" in r}
    materials = []
    scoped_find = (doc.get("retrieval") or {}).get("entrypoint") == "find"
    for item in doc["items"]:
        ref, revision = item.get("ref"), item.get("revision")
        if not isinstance(ref, str) or (not isinstance(revision, str) and not scoped_find):
            raise ValueError("capture item is missing its ref or revision")
        materials.append({"ref": ref, **({"revision": revision} if revision else {}),
                          "resources": resources.get(ref, []),
                          **({"content_range": ranges[ref]} if ref in ranges else {})})
    observation = doc.get("retrieval") or {}
    calls = observation.get("calls", [])
    if "knowledge search" in calls:
        tool = "knowledge search"
    else:
        recorded_tool = calls[-1] if calls else None
        tool = recorded_tool if recorded_tool in ("collect", "find", "read") else "collect"
    action = "search"
    recorded_selection = observation.get("selection")
    request = observation.get("request")
    if observation.get("schema_version") == 1 and isinstance(recorded_selection, dict):
        state = recorded_selection.get("state")
        if state == "explicit_ids":
            action = "read"
        elif (
            state == "not_requested" and isinstance(request, dict)
            and "query" in request and not request.get("relevance")
        ):
            query = request["query"]
            # Earlier Collect versions could filter by query without ranking.
            if query is None or (isinstance(query, str) and not query.strip()):
                action = "inventory"
    event = {"action": action, "tool": tool, "context_id": context_id,
             "source": source, "sha256": digest, "request": doc["request"],
             "selection": doc.get("selection"), "materials": materials}
    exact_return, external = _matched_envelope(
        "".join(return_chunks or []),
        _managed_envelope(doc, {"path": source, "sha256": digest, "kind": "delivered_context"}),
    )
    if scoped_find and external and external.get("context_ref") == source:
        materials.extend({"ref": ref, "resources": []} for ref in external_hit_refs(external))
    visible = [r for r in visible_capture_resources(
        doc, [doc["assembled_text"]] if exact_return else return_chunks,
    ) if _relative_location(r["ref"]) == r["ref"] and _relative_location(r["path"]) == r["path"]]
    visible_refs = [item["ref"] for item in materials] if exact_return and scoped_find else []
    if not archive:
        if visible or visible_refs:
            event["delivery"] = {"state": "visible", "return_line": return_line,
                                 "visible_resources": visible}
            if visible_refs:
                event["delivery"]["visible_refs"] = visible_refs
        return event

    omissions = {o["ref"]: o.get("reason") for o in
                 [*doc.get("omissions", []), *doc.get("context_omissions", [])]
                 if isinstance(o, dict) and isinstance(o.get("ref"), str)}
    visible_keys = {(r["ref"], r["path"]) for r in visible}
    for material in materials:
        ref, revision = material["ref"], material.get("revision")
        if (_relative_location(ref) != ref
                or (revision and _text(revision, "", len(revision)) != revision)):
            raise ValueError("capture contains a nonportable material ref or revision")
        paths = material["resources"]
        material["preparation_state"] = "prepared" if paths else "not_recorded"
        if ref in omissions:
            if not paths:
                material["preparation_state"] = "omitted"
            material["omission_reason"] = _text(omissions[ref])
        material["resources"] = [p for p in paths if _relative_location(p) == p]
        material["delivery_state"] = ("visible" if any((ref, p) in visible_keys for p in paths)
                                      else "ref_visible" if ref in visible_refs else "unknown")
    event["id"] = f"capture:{context_id}"
    event["request"], event["selection"] = _archive_capture_metadata(doc)
    event["capture"] = {"state": "verified", "source": source, "sha256": digest}
    event["delivery"] = {"state": "visible" if visible or visible_refs else "unknown",
                         "output_state": "verified" if exact_return or visible else "unknown",
                         "visible_resources": visible,
                         "passages": _capture_passages(
                             doc, selected_passages, visible_keys, excerpts or {})}
    if visible_refs:
        event["delivery"]["visible_refs"] = visible_refs
    if return_line is not None:
        event["trace_line"] = return_line
        if visible or visible_refs:
            event["delivery"]["return_line"] = return_line
    return event
