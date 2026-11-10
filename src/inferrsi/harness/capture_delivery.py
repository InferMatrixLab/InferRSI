"""Check which prepared Indexer resources also appear in a reviewed tool return."""

import hashlib
import json

from .campaign_records import _identifier
from .dashboard_data import _inside, _relative_location, _text
from .knowledge_capture import MAX_CONTEXT_CAPTURE_BYTES, assemble_context_text, verify_capture


def capture_return_texts(trace, lines, references, context_ids):
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
            output = payload.get("output")
            if isinstance(output, str):
                texts[number] = [output]
            elif isinstance(output, list):
                texts[number] = [
                    part["text"] for part in output if isinstance(part, dict)
                    and part.get("type") == "input_text" and isinstance(part.get("text"), str)
                ]
            else:
                texts[number] = []
            if wanted == texts.keys():
                break
    if wanted != texts.keys():
        raise ValueError("capture return line is missing from the trace")
    return {key: texts[number] for key, number in references.items()}


def visible_capture_resources(doc, texts):
    """Require matching owner, revision, resource path and body in the visible text."""
    visible = []
    if not texts:
        return visible
    chunks = ["\n" + text + "\n" for text in texts]
    for context in doc["contexts"]:
        for resource in context["resources"]:
            block = assemble_context_text([{
                **context, "resources": [resource], "omissions": [],
            }])
            if any("\n" + block in chunk for chunk in chunks):
                visible.append({"ref": context["ref"], "path": resource["path"]})
    return visible


def _archive_capture_metadata(doc):
    request = doc.get("request", {})
    safe_request = {}
    for key in ("query", "relevance", "relevance_method", "kind", "repo", "tier", "backend",
                "scenario"):
        value = request.get(key)
        if isinstance(value, str):
            safe_request[key] = _text(value, "", limit=len(value))
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


def _capture_passages(doc, selections, visible):
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
        lines = resources[0]["content"].splitlines()
        if line > len(lines) or not lines[line - 1]:
            raise ValueError("Indexer review source line is missing or empty")
        text = lines[line - 1]
        if _text(text, "", limit=len(text)) != text:
            raise ValueError("Indexer review source passage is not safe to publish verbatim")
        passages.append({"ref": ref, "path": path, "line": line, "text": text})
    return passages


def capture_event(context_id, captured, *, archive=False, return_chunks=None,
                  return_line=None, selected_passages=()):
    doc, source, digest = captured
    resources = {c["ref"]: [r["path"] for r in c["resources"]] for c in doc["contexts"]}
    materials = []
    for item in doc["items"]:
        ref, revision = item.get("ref"), item.get("revision")
        if not isinstance(ref, str) or not isinstance(revision, str):
            raise ValueError("capture item is missing its ref or revision")
        materials.append({"ref": ref, "revision": revision, "resources": resources.get(ref, [])})
    event = {"action": "search", "tool": "collect", "context_id": context_id,
             "source": source, "sha256": digest, "request": doc["request"],
             "selection": doc.get("selection"), "materials": materials}
    if not archive:
        return event

    omissions = {o["ref"]: o.get("reason") for o in
                 [*doc.get("omissions", []), *doc.get("context_omissions", [])]
                 if isinstance(o, dict) and isinstance(o.get("ref"), str)}
    visible = [r for r in visible_capture_resources(doc, return_chunks)
               if _relative_location(r["ref"]) == r["ref"]
               and _relative_location(r["path"]) == r["path"]]
    visible_keys = {(r["ref"], r["path"]) for r in visible}
    for material in materials:
        ref, revision = material["ref"], material["revision"]
        if _relative_location(ref) != ref or _text(revision, "", len(revision)) != revision:
            raise ValueError("capture contains a nonportable material ref or revision")
        paths = material["resources"]
        material["preparation_state"] = "prepared" if paths else "not_recorded"
        if ref in omissions:
            if not paths:
                material["preparation_state"] = "omitted"
            material["omission_reason"] = _text(omissions[ref])
        material["resources"] = [p for p in paths if _relative_location(p) == p]
        material["delivery_state"] = ("visible" if any((ref, p) in visible_keys for p in paths)
                                      else "unknown")
    event["id"] = f"capture:{context_id}"
    event["request"], event["selection"] = _archive_capture_metadata(doc)
    event["capture"] = {"state": "verified", "source": source, "sha256": digest}
    event["delivery"] = {"state": "visible" if visible else "unknown",
                         "output_state": "verified" if return_line is not None else "unknown",
                         "visible_resources": visible,
                         "passages": _capture_passages(doc, selected_passages, visible_keys)}
    if return_line is not None:
        event["trace_line"] = return_line
        if visible:
            event["delivery"]["return_line"] = return_line
    return event
