"""Connect Knowledge values to the campaign records that Harness keeps.

Harness records never import Knowledge. This module supplies the backend
vocabulary, the selection default, the context projection and the capture
orchestration they need: it calls the reader, keeps the retrieval envelope
the reader returned and hands Harness only the bytes to store.
"""

from __future__ import annotations

from pathlib import Path

from inferrsi import __version__
from inferrsi.harness.records import campaign_records, knowledge_capture
from inferrsi.knowledge._skill_selection import TASK_RELEVANCE
from inferrsi.knowledge.catalog import BACKENDS
from inferrsi.knowledge.context_projection import (
    PROVENANCE_FIELDS,
    assemble_context_text,
    context_item,
)


def create_campaign(root: Path, campaign_id: str, *, target: float | None = None,
                    noise: float | None = None, synthetic: bool = False,
                    backend: str | None = None, profile_first: bool = False) -> Path:
    """Create a campaign manifest that accepts the Knowledge backend names."""
    return campaign_records.create_campaign(
        root, campaign_id, target=target, noise=noise, synthetic=synthetic, backend=backend,
        profile_first=profile_first, backends=BACKENDS,
    )


def capture_context(root: Path, *, context_id: str, reader, query: str = "",
                    relevance: str | None = None,
                    relevance_method: str | None = None,
                    ids: list[str] | None = None, kind: str | None = None,
                    repo: str | None = None, tier: str | None = None,
                    backend: str | None = None, scenario: str | None = None,
                    limit: int = 5, context_bytes: int = 65536,
                    sources: tuple[str, ...] = ("package",)) -> tuple[Path, str]:
    """Run ``collect`` with a context budget and keep its complete envelope.

    The capture is produced by the same ``collect`` operation the agent uses,
    not by a caller narrative. Returns the new campaign-relative file and its
    SHA-256.
    """
    campaign = knowledge_capture.capture_campaign(root, context_id)
    if relevance_method is None:
        relevance_method = TASK_RELEVANCE if relevance and ids is None else "weighted-lexical-v1"
    if relevance_method == TASK_RELEVANCE and ids is None and backend is None:
        backend = campaign.get("backend")
    result = reader.collect(
        query, ids=ids, kind=kind, repo=repo, tier=tier, backend=backend,
        scenario=scenario, limit=limit, relevance=relevance,
        relevance_method=relevance_method, context_bytes=context_bytes,
    )
    request = {
        "query": query, "relevance": relevance,
        "relevance_method": relevance_method if relevance else None,
        "ids": ids, "kind": kind, "repo": repo, "tier": tier,
        "backend": backend, "scenario": scenario, "limit": limit,
        "context_bytes": context_bytes, "sources": list(sources),
    }
    if _supplies_no_observation(result):
        # Such a reader gets the record this entry wrote before observations
        # existed: the same fields, order and bytes, with no empty provenance.
        contexts = _contexts(result)
        return knowledge_capture.store_capture(
            root, campaign_id=campaign["campaign_id"], context_id=context_id,
            # Only the source categories are kept; store and checkout paths can be private.
            request={**request, "ids": ids or []},
            selection=result.get("selection"),
            items=[context_item(view) for view in result.get("items", [])],
            omissions=result.get("omissions", []),
            context_omissions=result.get("context_omissions", []),
            context_budget=result.get("context_budget"),
            context_bytes_used=result.get("context_bytes"),
            contexts=contexts,
            assembled_text=assemble_context_text(contexts),
        )
    return save_retrieval(root, context_id=context_id, result=result, request=request,
                          wrapper="campaign capture-context")


def _supplies_no_observation(result: dict) -> bool:
    """Whether a result has neither a retrieval observation nor any item provenance."""
    return not isinstance(result.get("retrieval"), dict) and not any(
        key in view for view in result.get("items", []) for key in PROVENANCE_FIELDS)


def _contexts(result: dict) -> list[dict]:
    return [{
        "ref": context["ref"], "revision": context["revision"],
        "content_bytes": context["content_bytes"],
        "resources": [{key: resource[key] for key in ("path", "role", "sha256", "content")}
                      for resource in context["resources"]],
        "omissions": context["omissions"],
        "sources": context.get("sources", []),
    } for context in result.get("contexts", [])]


def save_retrieval(root: Path, *, context_id: str, result: dict,
                   request: dict | None = None, wrapper: str | None = None) -> tuple[Path, str]:
    """Explicitly retain a search/collect result without executing another search.

    The caller owns this local capture. Review/redact the bundle before sharing;
    hashes attest bytes, not publication permission or actual model use.
    """
    campaign = knowledge_capture.capture_campaign(root, context_id)
    retrieval = result.get("retrieval")
    if isinstance(retrieval, dict):
        retrieval = {**retrieval}
        if wrapper:
            retrieval.update(entrypoint=wrapper, calls=[wrapper, *retrieval["calls"]])
    request = request if request is not None else (retrieval or {}).get("request", {})
    observations = {item["ref"]: item for item in (retrieval or {}).get("items", [])}
    items = []
    for view in result.get("items", []):
        ref = view.get("ref") or "package:" + view["id"]
        items.append({**context_item({**view, "ref": ref}, provenance=True),
                      "revision": view.get("revision")
                      or observations.get(ref, {}).get("revision")})
    contexts = _contexts(result)
    return knowledge_capture.store_capture(
        root, campaign_id=campaign["campaign_id"], context_id=context_id,
        # Only the source categories are kept; store and checkout paths can be private.
        request=request,
        selection=result.get("selection"),
        items=items,
        omissions=result.get("omissions", []),
        context_omissions=result.get("context_omissions", []),
        context_budget=result.get("context_budget"),
        context_bytes_used=result.get("context_bytes"),
        contexts=contexts,
        assembled_text=assemble_context_text(contexts),
        retrieval=retrieval,
        # A result without an observation has no recorded entry point. It is
        # labelled unknown; a plausible current default is not evidence.
        captured_by=f"inferrsi {(retrieval or {}).get('entrypoint', 'unknown')} {__version__}",
    )


def verify_capture(raw: bytes) -> tuple[dict | None, str]:
    """Return the capture and ``verified``, or ``None`` and a fixed reason code.

    Harness checks the stored bytes. This adds that the assembled text is the
    Knowledge projection of the listed resources, so a reader sees exactly the
    text those resources produce.
    """
    document, state = knowledge_capture.verify_capture(raw)
    if document is None:
        return None, state
    if assemble_context_text(document["contexts"]) != document["assembled_text"]:
        return None, "assembly_mismatch"
    return document, "verified"
