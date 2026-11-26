"""Keep the knowledge context that was delivered to an optimization campaign.

A capture holds what the caller delivered: every resource body with its
SHA-256 and the assembled text with its SHA-256. It records what InferRSI
prepared, not that a model read it. Hashes establish internal consistency,
not an authenticated capture origin.

This module stores bytes and record facts only. Callers project items and
assemble text; Harness does not interpret ranking, selection or publication.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from inferrsi import __version__

MAX_CONTEXT_CAPTURE_BYTES = 4 * 1024 * 1024
CAPTURE_KIND = "inferrsi.knowledge_context"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def capture_campaign(root: Path, context_id: str) -> dict:
    """Check a new capture's identifier and return the campaign manifest."""
    if not isinstance(context_id, str) or not _IDENTIFIER.fullmatch(context_id):
        raise ValueError("context id must be a safe single identifier")
    try:
        campaign = json.loads((Path(root).resolve() / "campaign.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("campaign.json is missing or invalid") from exc
    if not isinstance(campaign, dict) or not isinstance(campaign.get("campaign_id"), str):
        raise ValueError("campaign.json is missing or invalid")
    return campaign


def ranking_identity(policy) -> dict | None:
    """Project the recorded ranking identity without resolving its policy in this runtime."""
    if (not isinstance(policy, dict) or not isinstance(policy.get("id"), str)
            or not _IDENTIFIER.fullmatch(policy["id"]) or type(policy.get("version")) is not int):
        return None
    identity = {"id": policy["id"], "version": policy["version"]}
    if "config_sha256" in policy:
        digest = policy["config_sha256"]
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            return None
        identity["config_sha256"] = digest
    return identity


def scoped_response(document: dict, reference: dict, session: str, *, skill_root=None,
                    store=None) -> dict:
    """Render the Find or Read response from a retained session operation."""
    observation = document["retrieval"]
    display = observation["display"]
    if observation["entrypoint"] == "find":
        hits = []
        for item in document["items"]:
            hit = {key: value for key, value in item.items() if key != "material_read_args"}
            if argv := item.get("material_read_args"):
                argv = list(argv)
                for flag, value in (("--skill-root", skill_root), ("--store", store)):
                    if value is not None and flag in argv:
                        argv[argv.index(flag) + 1] = str(value)
                hit["read_args"] = [*argv, "--session", session, "--search-ref", reference["path"]]
            hits.append(hit)
        summary = {}
        if "context_bytes_used" in display:
            summary = {"hits": len(hits), "context_bytes_used": display["context_bytes_used"]}
        return {**summary, "reference": reference, **display, "items": hits}
    response = {"reference": reference}
    if "next_read_args" in display:
        continuation = list(display["next_read_args"])
        for flag, value in (("--session", session), ("--skill-root", skill_root),
                            ("--store", store)):
            if value is not None and flag in continuation:
                continuation[continuation.index(flag) + 1] = str(value)
        response["next_read_args"] = continuation
    for key in ("ref", "revision", "content_resource"):
        response[key] = display[key]
    for key in ("content_range", "next_byte_range"):
        if key in display:
            response[key] = display[key]
    if document["contexts"]:
        resource, = document["contexts"][0]["resources"]
        response["content"] = resource["content"]
    else:
        response["context_omissions"] = document["context_omissions"]
    response.update(display)
    if "next_read_args" in display:
        response["next_read_args"] = continuation
    response["search_ref"] = document["request"]["search_ref"]
    response["ranking_policy"] = ranking_identity(document["request"]["ranking_policy"])
    return response


def store_capture(root: Path, *, campaign_id: str, context_id: str, request: dict,
                  selection: object, items: list[dict], omissions: list[dict],
                  context_omissions: list[dict], context_budget: object,
                  context_bytes_used: object, contexts: list[dict],
                  assembled_text: str, retrieval: dict | None = None,
                  captured_by: str | None = None,
                  diagnosis_binding: dict | None = None) -> tuple[Path, str]:
    """Write the delivered context as one new capture.

    Optional record facts include retrieval provenance and the managed diagnosis
    in effect when lookup began. Omitted facts preserve the earlier capture format.

    Returns the new campaign-relative file and its SHA-256. An existing capture
    is never overwritten, so a trace can pin the exact bytes it cites.
    """
    root = Path(root).resolve()
    document = {
        "schema_version": 1, "kind": CAPTURE_KIND,
        "campaign_id": campaign_id, "context_id": context_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_by": captured_by or f"inferrsi collect {__version__}",
        # Only the source categories are kept; store and checkout paths can be private.
        "request": request,
    }
    if retrieval is not None:
        document["retrieval"] = retrieval
    if diagnosis_binding is not None:
        document["diagnosis_binding"] = diagnosis_binding
    document.update({
        "selection": selection,
        "items": items,
        "omissions": omissions,
        "context_omissions": context_omissions,
        "context_budget": context_budget,
        "context_bytes_used": context_bytes_used,
        "contexts": contexts,
        "assembled_text": assembled_text,
        "assembled_sha256": hashlib.sha256(assembled_text.encode("utf-8")).hexdigest(),
    })
    payload = (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)
               + "\n").encode("utf-8")
    if len(payload) > MAX_CONTEXT_CAPTURE_BYTES:
        if retrieval and retrieval.get("entrypoint") in ("find", "read"):
            raise ValueError("captured context exceeds 4 MiB for one serialized record")
        raise ValueError("captured context exceeds 4 MiB; lower --context-bytes or --limit")
    directory = root / "knowledge"
    if directory.is_symlink() or directory.resolve() != directory:
        raise ValueError("knowledge directory must not be a symbolic link")
    directory.mkdir(exist_ok=True)
    if directory.is_symlink() or directory.resolve() != directory:
        raise ValueError("knowledge directory must not be a symbolic link")
    target = directory / f"{context_id}.json"
    temporary = directory / f".capture-{os.getpid()}-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
        os.link(temporary, target)
    except FileExistsError as exc:
        raise ValueError("a context capture with this id already exists") from exc
    finally:
        if temporary.exists():
            temporary.unlink()
    return target, hashlib.sha256(payload).hexdigest()


def valid_content_range(bounds, content):
    """A returned interval describes exactly these bytes of the pinned UTF-8 view."""
    fields = ("start", "end", "total_bytes", "first_line")
    if not isinstance(bounds, dict) or bounds.keys() != set(fields):
        return False
    start, end, total, line = (bounds[key] for key in fields)
    return (all(type(i) is int for i in (start, end, total, line))
            and 0 <= start <= end <= total and (start < end or total == 0)
            and 1 <= line <= start + 1 and end - start == len(content.encode("utf-8")))


def delivered_contexts(capture):
    """Yield contexts with returned resource content."""
    return (context for context in capture["contexts"]
            if any(resource["content"] for resource in context["resources"]))


def verify_capture(raw: bytes) -> tuple[dict | None, str]:
    """Check the stored bytes of a capture.

    Returns the capture and ``verified``, or ``None`` and a fixed reason code.
    This covers the format, every resource hash and the assembled-text hash.
    It does not re-derive the assembled text from the resources.
    """
    if len(raw) > MAX_CONTEXT_CAPTURE_BYTES:
        return None, "too_large"
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        return None, "invalid_format"
    if (not isinstance(document, dict) or document.get("kind") != CAPTURE_KIND
            or type(document.get("schema_version")) is not int
            or document["schema_version"] != 1
            or not isinstance(document.get("campaign_id"), str)
            or not isinstance(document.get("context_id"), str)
            or not isinstance(document.get("contexts"), list)
            or not isinstance(document.get("request"), dict)
            or any(not isinstance(document.get(key), list) for key in
                   ("items", "omissions", "context_omissions"))
            or any(not isinstance(item, dict) for key in
                   ("items", "omissions", "context_omissions") for item in document[key])
            or not isinstance(document.get("assembled_text"), str)):
        return None, "invalid_format"
    try:
        for context in document["contexts"]:
            for key in ("ref", "revision"):
                if not isinstance(context[key], str):
                    return None, "invalid_format"
            if (not isinstance(context["omissions"], list)
                    or not isinstance(context["resources"], list)):
                return None, "invalid_format"
            for resource in context["resources"]:
                if not all(isinstance(resource.get(key), str)
                           for key in ("path", "sha256", "content")):
                    return None, "invalid_format"
                actual = hashlib.sha256(resource["content"].encode("utf-8")).hexdigest()
                if resource["sha256"].lower() != actual:
                    return None, "resource_hash_mismatch"
                if "content_range" in resource and not valid_content_range(
                    resource["content_range"], resource["content"]
                ):
                    return None, "invalid_format"
            for omission in context["omissions"]:
                if not isinstance(omission, dict) or not all(
                        isinstance(omission.get(key), str) for key in ("path", "reason")):
                    return None, "invalid_format"
        # Resource bodies were encoded above. The labels around them must be
        # valid Unicode too, checked only after every resource hash.
        for context in document["contexts"]:
            labels = [context["ref"], context["revision"]]
            labels += [resource["path"] for resource in context["resources"]]
            for omission in context["omissions"]:
                labels += [omission["path"], omission["reason"]]
            for label in labels:
                label.encode("utf-8")
    except (KeyError, TypeError, AttributeError, UnicodeError):
        return None, "invalid_format"
    try:
        digest = hashlib.sha256(document["assembled_text"].encode("utf-8")).hexdigest()
    except UnicodeError:
        return None, "invalid_format"
    if digest != document.get("assembled_sha256"):
        return None, "assembly_mismatch"
    return document, "verified"
