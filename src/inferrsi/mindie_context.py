"""Export explicitly supplied MindIE reads for a caller-reviewed campaign trace.

This CLI host adapter never activates MindIE, reads a session or calls a model.
Retained responses establish supplied bytes, not their authenticity or consumption.
It stays with the current flat CLI; it does not instantiate the proposed Apps package.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_REF = re.compile(r"mindie://([A-Za-z0-9_.-]+)/units/([A-Za-z0-9_.-]+)@([1-9][0-9]*)")


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("MindIE evidence contains duplicate JSON keys")
        value[key] = item
    return value


def _invalid_constant(_):
    raise ValueError("MindIE evidence contains a non-finite JSON value")


def _parse(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_object, parse_constant=_invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("MindIE evidence is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("MindIE evidence must contain a JSON object")
    return value


def _payload(value, required, locator=""):
    status = value.get("status")
    if (value.get("isError") is True or value.get("error")
            or isinstance(status, str) and status in {"error", "failed", "inactive", "denied"}):
        raise ValueError("MindIE call failed or knowledge was not enabled")
    if required <= value.keys():
        return value, locator
    structured = value.get("structuredContent")
    if isinstance(structured, dict):
        return _payload(structured, required, locator + "/structuredContent")
    blocks = value.get("content")
    if isinstance(blocks, list) and len(blocks) == 1 and isinstance(blocks[0], dict):
        block = blocks[0]
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            return _payload(_parse(block["text"]), required,
                            locator + "/content/0/text (decoded JSON)")
    raise ValueError("Unsupported or missing MindIE business payload")


def export_context(root: Path, *, context_id: str, query_input: Path, query_result: Path,
                   explain_input: Path, explain_result: Path, query_exit_code: int,
                   explain_exit_code: int) -> Path:
    """Keep a new read receipt and a trace context fragment without marking review."""
    if not isinstance(context_id, str) or not _ID.fullmatch(context_id):
        raise ValueError("MindIE context id must be a safe identifier")
    if query_exit_code != 0 or explain_exit_code != 0:
        raise ValueError("MindIE calls must both exit successfully")
    root = Path(root).resolve()
    campaign = _parse((root / "campaign.json").read_bytes())
    if not isinstance(campaign.get("campaign_id"), str):
        raise ValueError("campaign.json is missing an identity")
    originals, documents = {}, {}
    for name, path in (("query-input", query_input), ("query-result", query_result),
                       ("explain-input", explain_input), ("explain-result", explain_result)):
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("MindIE evidence exceeds 2 MiB")
        originals[name + ".json"] = raw
        documents[name] = _parse(raw)
    query = documents["query-input"].get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("MindIE query input has no query")
    found, _ = _payload(documents["query-result"], {"results"})
    if not isinstance(found["results"], list):
        raise ValueError("MindIE query results must be a list")
    hits = set()
    for key in ("results", "cards", "foundation_cards"):
        rows = found.get(key, [])
        if not isinstance(rows, list):
            raise ValueError("MindIE navigation must contain lists")
        hits.update(row["ref"] for row in rows if isinstance(row, dict)
                    and isinstance(row.get("ref"), str) and _REF.fullmatch(row["ref"]))
    requested = documents["explain-input"].get("refs")
    if requested is None:
        requested = [documents["explain-input"].get("ref")]
    if (not isinstance(requested, list) or not requested
            or any(not isinstance(ref, str) or ref not in hits for ref in requested)):
        raise ValueError("MindIE explain refs must be exact revision-bound query hits")
    domains = {_REF.fullmatch(ref).group(1) for ref in requested}
    if len(domains) != 1:
        raise ValueError("MindIE explain refs must share one domain")
    domain = next(iter(domains))
    delivered, pointer = _payload(documents["explain-result"], {"units", "requires", "unresolved"})
    if any(not isinstance(delivered[key], list) for key in ("units", "requires", "unresolved")):
        raise ValueError("MindIE delivery must contain units, requires and unresolved lists")
    sources, sections, seen = [], [], set()
    relative = f"mindie/{context_id}"
    response_hash = hashlib.sha256(originals["explain-result.json"]).hexdigest()
    for key in ("requires", "units"):
        for index, row in enumerate(delivered[key]):
            if not isinstance(row, dict):
                raise ValueError("Invalid MindIE delivered unit")
            identity, revision, content = row.get("id"), row.get("revision"), row.get("content")
            if (not isinstance(identity, str) or not _ID.fullmatch(identity)
                    or type(revision) is not int or revision < 1
                    or not isinstance(content, str) or not content.strip()):
                raise ValueError("MindIE delivered unit needs id, revision and full content")
            ref = f"mindie://{domain}/units/{identity}@{revision}"
            if row.get("ref", ref) != ref or ref in seen:
                raise ValueError("MindIE delivered unit reference is inconsistent or duplicated")
            if key == "units" and ref not in requested:
                raise ValueError("MindIE delivered unit does not match the explain request")
            seen.add(ref)
            locator = (f"{relative}/explain-result.json (sha256:{response_hash})"
                       f"#{pointer}/{key}/{index}/content")
            sources.append({"ref": ref, "revision": str(revision), "locator": locator})
            sections.append(f"## {ref} ({key})\n\n{content}\n")
    if not sources:
        raise ValueError("MindIE explain delivered no full bodies")
    omitted = bool(delivered["unresolved"]) or not set(requested) <= seen
    text = "\n".join(sections)
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("MindIE context exceeds 2 MiB")
    fragment = {"state": "partial" if omitted else "complete", "text": "",
                "queries": [query], "sources": sources,
                "missing_reason": ("Requested material was not delivered; inspect the retained "
                                   "explain request and unresolved list." if omitted else "")}
    receipt = {"schema_version": 1, "campaign_id": campaign["campaign_id"],
               "context_id": context_id, "query_exit_code": query_exit_code,
               "explain_exit_code": explain_exit_code, "requested_refs": requested,
               "delivered_refs": [source["ref"] for source in sources],
               "unresolved": delivered["unresolved"],
               "attribution": "caller_supplied_tool_responses_not_authenticated",
               "sha256": {name: hashlib.sha256(raw).hexdigest()
                          for name, raw in originals.items()}}
    originals["reviewed-context.txt"] = text.encode("utf-8")
    receipt["sha256"]["reviewed-context.txt"] = hashlib.sha256(originals[
        "reviewed-context.txt"]).hexdigest()
    for name, value in (("context.json", fragment), ("receipt.json", receipt)):
        originals[name] = (json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n").encode("utf-8")
    target = root / "mindie" / context_id
    if not target.resolve().is_relative_to(root):
        raise ValueError("MindIE context directory escapes the campaign")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(exist_ok=False)
    # Keep partial writes on I/O failure for inspection, never silently replace them.
    for name, raw in originals.items():
        (target / name).write_bytes(raw)
    return target
