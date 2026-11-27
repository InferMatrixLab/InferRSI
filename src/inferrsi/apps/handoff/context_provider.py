"""Project Knowledge selection into the in-process Harness delivery draft."""

import re
from dataclasses import dataclass
from hashlib import sha256

from inferrsi.contracts.json_v1 import MAX_SAFE_INTEGER
from inferrsi.knowledge._skill_selection import FIND_RELEVANCE, validate_relevance_method
from inferrsi.knowledge.catalog import KNOWLEDGE_SCOPES
from inferrsi.knowledge.knowledge_find import (
    Corpus,
    find,
    installed_skill_projection,
    installed_skill_root,
    load_corpus,
)
from inferrsi.knowledge.knowledge_operations import KnowledgeReader

_REQUEST_FIELDS = {"query", "ids", "pins", "selection_limits", "max_bytes", "round_id"}
_TEXT_OPTIONS = {"kind", "repo", "tier", "backend", "scenario", "relevance", "relevance_method"}
_SIZE_OPTIONS = {"limit", "max_bytes"}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}")


@dataclass(frozen=True)
class DeliveredContextDraft:
    """The actual bytes and metadata for Harness to retain and seal."""

    content: bytes
    intended_location: str
    sha256: str
    items: list[dict]
    selection: dict
    omissions: list[dict]
    limitations: list[str]


class ContextProvider:
    """Deliver whole UTF-8 resources in Knowledge's selection order."""

    def __init__(self, reader: KnowledgeReader):
        self.reader = reader

    def collect(self, request: dict) -> DeliveredContextDraft:
        if not isinstance(request, dict) or request.keys() != _REQUEST_FIELDS:
            raise ValueError("expected ContextRequest fields")
        query, ids, pins = request["query"], request["ids"], request["pins"]
        limits, max_bytes, round_id = (
            request["selection_limits"], request["max_bytes"], request["round_id"]
        )
        if query is not None and not isinstance(query, str):
            raise ValueError("expected a string or null query")
        if not isinstance(ids, list) or not all(_identifier(item) for item in ids):
            raise ValueError("expected Knowledge ids")
        if type(max_bytes) is not int or not 0 <= max_bytes <= MAX_SAFE_INTEGER:
            raise ValueError("expected a delivery byte limit in the v1 unsigned integer range")
        if not _identifier(round_id):
            raise ValueError("expected a round_id")
        if not isinstance(limits, dict) or not limits.keys() <= _TEXT_OPTIONS | _SIZE_OPTIONS:
            raise ValueError("unsupported Knowledge selection option")
        if any(not isinstance(limits[key], str) for key in limits.keys() & _TEXT_OPTIONS):
            raise ValueError("invalid Knowledge selection option value")
        if any(
            type(limits[key]) is not int or not 1 <= limits[key] <= MAX_SAFE_INTEGER
            for key in limits.keys() & _SIZE_OPTIONS
        ):
            raise ValueError("invalid Knowledge selection option value")

        revisions = _revisions(pins)
        if ids and query and query.strip():
            raise ValueError("Use explicit IDs or a Find query to select Knowledge")
        cue = (query or "").strip() or limits.get("relevance")
        if not ids and cue is not None:
            if query and query.strip() and limits.get("relevance") is not None:
                raise ValueError("Find takes one query or relevance cue")
            if "relevance" in limits and not re.search(r"\w", cue):
                raise ValueError("Find requires at least one word")
            result, selection = self._find(cue, revisions, limits, max_bytes)
        else:
            reader = self.reader
            if reader.skill_root is None and reader.store is None and any(
                identity.startswith("checkout:") for identity in ids
            ):
                reader = KnowledgeReader(skill_root=installed_skill_root())
            result = reader.collect(ids=ids or None, revisions=revisions,
                                    context_bytes=max_bytes or None, **limits)
            selection = {**result.get("selection", {}), **result["retrieval"]["selection"]}
        selection.update(no_match=result["no_match"], collisions=result["collisions"])
        omissions = [_omission(item, stage="knowledge_selection") for item in result["omissions"]]
        limitations = list(result["limitations"])
        items, payloads = [], []
        if max_bytes == 0 and "contexts" not in result:
            omissions.extend(
                _omission({**item, "reason": "context_limit"}, stage="context_delivery")
                for item in result["items"]
            )
        for item in result.get("context_omissions", ()):
            omissions.append(_omission(item, stage="context_delivery"))
        for context in result.get("contexts", ()):
            reference, revision = context["ref"], context["revision"]
            parts, roles = [], []
            for resource in context["resources"]:
                body = resource["content"].encode("utf-8")
                if sha256(body).hexdigest() != resource["sha256"]:
                    raise ValueError("Knowledge context resource digest mismatch")
                parts.append(body)
                roles.append(resource["role"])
            block = b"".join(parts)
            if len(block) != context["content_bytes"]:
                raise ValueError("Knowledge context byte count mismatch")
            payloads.append(block)
            items.append({
                "pin": {"reference": reference, "revision": revision},
                "delivered_roles": list(dict.fromkeys(roles)),
                "delivered_bytes": len(block),
            })
            omissions.extend(
                _omission({**item, "ref": reference}, stage="context_delivery")
                for item in context["omissions"]
            )
            limitations.extend(context["limitations"])
        content = b"".join(payloads)
        if len(content) > max_bytes:
            raise ValueError("Knowledge context exceeds the delivery byte limit")
        # A round identifier can contain path separators or platform-specific names.
        round_key = sha256(round_id.encode("ascii")).hexdigest()
        return DeliveredContextDraft(
            content=content, intended_location=f"context/{round_key}/delivered.bin",
            sha256=sha256(content).hexdigest(), items=items, selection=selection,
            omissions=omissions, limitations=list(dict.fromkeys(limitations)),
        )

    def _find(self, cue, revisions, limits, max_bytes):
        """Find within the request's scope, then assemble those exact pins for sealing."""
        validate_relevance_method(limits.get("relevance_method"))
        kind = limits.get("kind")
        kinds = {None: ("case", "skill", "record"), "skill": ("skill",),
                 "case": ("case",), "knowledge": ("skill", "record")}
        if kind not in kinds:
            raise ValueError("Unknown content kind")
        if "tier" in limits and limits["tier"] not in KNOWLEDGE_SCOPES:
            raise ValueError(f"Unknown knowledge tier: {limits['tier']}")
        reader = self.reader
        if reader.skill_root is None and reader.store is None:
            reader = KnowledgeReader(skill_root=installed_skill_root())
        fixed = {}
        for name, revision in revisions.items():
            ref = reader.resolve(name)
            if fixed.setdefault(ref, revision) != revision:
                raise ValueError(f"Conflicting revisions for {ref}")
        scope = {key: limits[key] for key in ("repo", "tier", "backend", "scenario")
                 if key in limits}
        catalog_scope = any(key in scope for key in ("repo", "tier", "scenario"))
        store_pins = {ref: rev for ref, rev in fixed.items() if ref.startswith("store:")}
        unavailable = []
        corpus = load_corpus(
            self.reader.skill_root,
            kinds=kinds[kind], store=self.reader.store,
            revisions={} if catalog_scope else store_pins, unavailable_store_revisions=unavailable,
            **scope,
        )
        if kind == "knowledge":
            # This older DTO calls imported records and catalog-projected skills "knowledge".
            corpus = Corpus([doc for doc in corpus.documents if doc.kind == "record"
                             or installed_skill_projection(doc, reader.record) is not None])
        limit = limits.get("limit", 10)
        # A material-size limit or caller pin may exclude a higher-ranked item.
        # Let exact assembly continue down the same ranked list in that case.
        preview_limit = max(1, len(corpus.documents)) if fixed or "max_bytes" in limits else limit
        unreadable = []
        hits = find(cue, corpus, limit=preview_limit, pin_material=True, unreadable_hits=unreadable)
        result = reader.pack_find_hits(hits["items"], cue=cue, revisions=fixed, limit=limit,
                                       max_bytes=limits.get("max_bytes"), context_bytes=max_bytes)
        result["limitations"][:1] = hits["limitations"]
        result["omissions"].extend({"id": ref, "reason": "unavailable_revision"}
                                   for ref in unavailable)
        result["omissions"].extend(
            {"id": f"{hit['authority']}:{hit['id']}", "reason": "invalid"} for hit in unreadable
        )
        selection = {"method": FIND_RELEVANCE, "cue": cue, "ranking_applied": True,
                     "state": "applied", "tie_break": "state_then_id_then_ref",
                     "scope": "package-records-library-and-store" if self.reader.store is not None
                     else "package-records-and-library",
                     "ranking_policy": hits["ranking_policy"], "matched_count": hits["matched"],
                     "returned_count": len(result["items"])}
        return result, selection


def _identifier(value: object) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _revisions(pins: object) -> dict[str, str]:
    if not isinstance(pins, list):
        raise ValueError("expected Knowledge pins")
    revisions = {}
    for pin in pins:
        if (
            not isinstance(pin, dict) or pin.keys() != {"name", "revision"}
            or not _identifier(pin["name"]) or not _identifier(pin["revision"])
        ):
            raise ValueError("expected Knowledge pin name and revision")
        name, revision = pin["name"], pin["revision"]
        if revisions.setdefault(name, revision) != revision:
            raise ValueError("conflicting Knowledge revisions")
    return revisions


def _omission(item: dict, *, stage: str) -> dict:
    reference = item.get("ref", item.get("id"))
    location = "/".join(part for part in (reference, item.get("path")) if part)
    return {
        "code": item["reason"], "stage": stage, "message": f"{location}: {item['reason']}",
        "retryable": False,
    }
