"""Replay a retained Find ranking from its frozen rule over a pinned corpus.

Two checks are kept apart. Archival verification (``verify_capture``) proves the
retained bytes are intact; it still passes when an undelivered corpus entry
changes. Exact replay, here, reproduces the returned, delivered and omitted
order, which requires the same query, filters, limits, byte budget, frozen rule,
scoring version and the identical corpus. A changed corpus or a missing binding
is never reported as a reproduced ranking.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping

from .knowledge_find import Corpus, find
from .ranking_policy import RANKING_VERSION, RankingPolicy

BINDING_FIELDS = (
    "query", "limit", "backend", "context_bytes", "ranking_policy", "scoring_version",
    "corpus_sha256",
)


def corpus_digest(corpus: Corpus) -> str:
    """Identify the scoring inputs of every eligible document, in a stable order."""
    rows = sorted(
        [doc.qualified or doc.identity, doc.kind, doc.state, getattr(doc, "backend", None),
         doc.fields]
        for doc in corpus.documents
    )
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def replay_binding(*, query: str, limit: int, ranking_policy: Mapping, corpus: Corpus,
                   backend: str | None = None, context_bytes: int | None = None) -> dict:
    """Record everything an exact replay of one Find and delivery depends on."""
    policy = RankingPolicy.from_configuration(ranking_policy)
    return {
        "query": query, "limit": limit, "backend": backend, "context_bytes": context_bytes,
        "ranking_policy": policy.receipt(), "scoring_version": RANKING_VERSION,
        "corpus_sha256": corpus_digest(corpus),
    }


def ranked_items(items: Iterable[Mapping]) -> list[dict]:
    """Project hits to the fields a replay must reproduce, in rank order."""
    return [
        {"ref": item.get("material_ref") or item["ref"], "revision": item["revision"],
         "score": item["score"]}
        for item in items
    ]


def replay_find(binding: Mapping, corpus: Corpus, *,
                pack: Callable[[list, RankingPolicy, int], Mapping] | None = None) -> dict:
    """Recompute the ranking, and optionally the delivery, bound in ``binding``.

    ``pack(hits, policy, context_bytes)`` assembles the delivery the same way the
    original call did and returns its ``contexts`` and ``context_omissions``.
    """
    missing = [name for name in BINDING_FIELDS if name not in binding]
    if missing:
        raise ValueError(f"Replay binding lacks {', '.join(missing)}")
    policy = RankingPolicy.from_configuration(binding["ranking_policy"])
    result = find(binding["query"], corpus, limit=binding["limit"], pin_material=True,
                  ranking_policy=policy, backend=binding["backend"])
    replayed = {
        "scoring_matches": binding["scoring_version"] == RANKING_VERSION,
        "corpus_matches": binding["corpus_sha256"] == corpus_digest(corpus),
        "ranking_policy": policy.receipt(),
        "items": ranked_items(result["items"]),
    }
    if pack is not None:
        if binding["context_bytes"] is None:
            raise ValueError("Replay binding lacks the delivery byte budget")
        delivery = pack(result["items"], policy, binding["context_bytes"])
        replayed["delivered"] = [context["ref"] for context in delivery["contexts"]]
        replayed["omitted"] = [omission["ref"] for omission in delivery["context_omissions"]]
    return replayed


def verify_replay(binding: Mapping, retained: Mapping, corpus: Corpus, *,
                  pack: Callable[[list, RankingPolicy, int], Mapping] | None = None) -> dict:
    """Compare a retained ranking with its replay.

    ``retained`` holds ``items`` and, when ``pack`` is given, ``delivered`` and
    ``omitted`` refs. The state is ``reproduced`` only when the scoring version
    and corpus match and every rank, delivery and omission is identical.
    """
    replayed = replay_find(binding, corpus, pack=pack)
    if not replayed["scoring_matches"]:
        state = "scoring_changed"
    elif not replayed["corpus_matches"]:
        state = "corpus_changed"
    else:
        state = None
    mismatches = _rank_mismatches(ranked_items(retained["items"]), replayed["items"])
    for key in ("delivered", "omitted") if pack is not None else ():
        if list(retained[key]) != replayed[key]:
            mismatches.append({key: {"retained": list(retained[key]),
                                     "replayed": replayed[key]}})
    return {"state": state or ("differs" if mismatches else "reproduced"),
            "mismatches": mismatches, "replayed": replayed}


def _rank_mismatches(retained: list[dict], replayed: list[dict]) -> list[dict]:
    mismatches = []
    for rank in range(max(len(retained), len(replayed))):
        before = retained[rank] if rank < len(retained) else None
        after = replayed[rank] if rank < len(replayed) else None
        if before != after:
            mismatches.append({"rank": rank + 1, "retained": before, "replayed": after})
    return mismatches


def delivery_difference(first: Iterable[Mapping], second: Iterable[Mapping]) -> dict:
    """Compare two rankings by which refs each returns and whether shared refs reorder."""
    first_refs = [item["ref"] for item in first]
    second_refs = [item["ref"] for item in second]
    shared = [ref for ref in first_refs if ref in second_refs]
    return {
        "only_first": [ref for ref in first_refs if ref not in second_refs],
        "only_second": [ref for ref in second_refs if ref not in first_refs],
        "reordered": shared != [ref for ref in second_refs if ref in first_refs],
    }
