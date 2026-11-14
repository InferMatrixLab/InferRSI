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


def store_capture(root: Path, *, campaign_id: str, context_id: str, request: dict,
                  selection: object, items: list[dict], omissions: list[dict],
                  context_omissions: list[dict], context_budget: object,
                  context_bytes_used: object, contexts: list[dict],
                  assembled_text: str, retrieval: dict | None = None,
                  captured_by: str | None = None) -> tuple[Path, str]:
    """Write the delivered context as one new capture.

    ``retrieval`` and ``captured_by`` are optional record facts supplied by the
    caller. Omitting them leaves the stored fields, their order and their bytes
    exactly as earlier captures wrote them, so old records keep verifying.

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
