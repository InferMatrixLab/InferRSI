"""Capture the knowledge context InferRSI assembled for an optimization campaign.

The capture is produced by the same ``collect`` operation the agent uses, not by
a caller narrative: every resource body keeps its recorded SHA-256 and the
assembled text is re-derived from those resources when the dashboard loads it.
It proves what InferRSI prepared, not that a model read it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

MAX_CONTEXT_CAPTURE_BYTES = 4 * 1024 * 1024
CAPTURE_KIND = "inferrsi.knowledge_context"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SHA256 = re.compile(r"[a-f0-9]{64}")


def assemble_context_text(contexts: list[dict]) -> str:
    """Render context views exactly as ``inferrsi collect`` prints them."""
    lines = []
    for context in contexts:
        for resource in context["resources"]:
            content = resource["content"]
            lines.append(
                f"--- begin context {context['ref']} @ {context['revision']} "
                f"{resource['path']} ---\n"
            )
            lines.append(content if content.endswith("\n") else content + "\n")
            lines.append(f"--- end context {resource['path']} ---\n")
        for omission in context["omissions"]:
            lines.append(f"{omission['path']}\tcontext_omitted\t{omission['reason']}\n")
    return "".join(lines)


def _item(view: dict) -> dict:
    return {key: view.get(key) for key in ("ref", "revision", "title", "kind", "backend")}


def capture_context(root: Path, *, context_id: str, reader, query: str = "",
                    relevance: str | None = None,
                    relevance_method: str = "weighted-lexical-v1",
                    ids: list[str] | None = None, kind: str | None = None,
                    repo: str | None = None, tier: str | None = None,
                    backend: str | None = None, scenario: str | None = None,
                    limit: int = 5, context_bytes: int = 65536,
                    sources: tuple[str, ...] = ("package",)) -> tuple[Path, str]:
    """Run ``collect`` with a context budget and keep its complete envelope.

    Returns the new campaign-relative file and its SHA-256. An existing capture
    is never overwritten, so a trace can pin the exact bytes it cites.
    """
    root = Path(root).resolve()
    if not isinstance(context_id, str) or not _IDENTIFIER.fullmatch(context_id):
        raise ValueError("context id must be a safe single identifier")
    manifest_path = root / "campaign.json"
    try:
        campaign = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("campaign.json is missing or invalid") from exc
    if not isinstance(campaign, dict) or not isinstance(campaign.get("campaign_id"), str):
        raise ValueError("campaign.json is missing or invalid")
    result = reader.collect(
        query, ids=ids, kind=kind, repo=repo, tier=tier, backend=backend,
        scenario=scenario, limit=limit, relevance=relevance,
        relevance_method=relevance_method, context_bytes=context_bytes,
    )
    contexts = [{
        "ref": context["ref"], "revision": context["revision"],
        "content_bytes": context["content_bytes"],
        "resources": [{key: resource[key] for key in ("path", "role", "sha256", "content")}
                      for resource in context["resources"]],
        "omissions": context["omissions"],
        "sources": context.get("sources", []),
    } for context in result.get("contexts", [])]
    assembled = assemble_context_text(contexts)
    try:
        from .. import __version__ as version
    except ImportError:  # pragma: no cover - the package always defines it
        version = "unknown"
    document = {
        "schema_version": 1, "kind": CAPTURE_KIND,
        "campaign_id": campaign["campaign_id"], "context_id": context_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_by": f"inferrsi collect {version}",
        # Only the source categories are kept; store and checkout paths can be private.
        "request": {"query": query, "relevance": relevance,
                    "relevance_method": relevance_method if relevance else None,
                    "ids": ids or [], "kind": kind, "repo": repo, "tier": tier,
                    "backend": backend, "scenario": scenario, "limit": limit,
                    "context_bytes": context_bytes, "sources": list(sources)},
        "selection": result.get("selection"),
        "items": [_item(view) for view in result.get("items", [])],
        "omissions": result.get("omissions", []),
        "context_omissions": result.get("context_omissions", []),
        "context_budget": result.get("context_budget"),
        "context_bytes_used": result.get("context_bytes"),
        "contexts": contexts,
        "assembled_text": assembled,
        "assembled_sha256": hashlib.sha256(assembled.encode("utf-8")).hexdigest(),
    }
    payload = (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)
               + "\n").encode("utf-8")
    if len(payload) > MAX_CONTEXT_CAPTURE_BYTES:
        raise ValueError("captured context exceeds 4 MiB; lower --context-bytes or --limit")
    directory = root / "knowledge"
    directory.mkdir(parents=True, exist_ok=True)
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
    """Return the capture and ``verified``, or ``None`` and a fixed reason code."""
    if len(raw) > MAX_CONTEXT_CAPTURE_BYTES:
        return None, "too_large"
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        return None, "invalid_format"
    if (not isinstance(document, dict) or document.get("kind") != CAPTURE_KIND
            or document.get("schema_version") != 1
            or not isinstance(document.get("contexts"), list)
            or not isinstance(document.get("assembled_text"), str)):
        return None, "invalid_format"
    try:
        for context in document["contexts"]:
            for key in ("ref", "revision"):
                if not isinstance(context[key], str):
                    return None, "invalid_format"
            if not isinstance(context["omissions"], list):
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
        assembled = assemble_context_text(document["contexts"])
    except (KeyError, TypeError, AttributeError):
        return None, "invalid_format"
    if (assembled != document["assembled_text"]
            or hashlib.sha256(assembled.encode("utf-8")).hexdigest()
            != document.get("assembled_sha256")):
        return None, "assembly_mismatch"
    return document, "verified"
