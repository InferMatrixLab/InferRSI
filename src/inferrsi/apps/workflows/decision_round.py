"""Bound a decision round to local Find results and the native pinned reader."""

from __future__ import annotations

import hashlib
from copy import deepcopy

from inferrsi.knowledge.conditions import APPLICABILITY_VERDICTS
from inferrsi.knowledge.knowledge_operations import (
    PageBudgetTooSmall,
    UnavailableResource,
    UnavailableRevision,
    safe_path,
)

from .session_knowledge import scoped_operation


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


def _strings(value, name):
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return [_text(v, name) for v in value]


def _budget(request, name, default):
    n = request.get("budget", {}).get(name, default)
    if type(n) is not int or n < 1:
        raise ValueError(f"{name} must be a positive integer")
    return n


def _find(reader, query, limit, session, number):
    if session is None:
        return reader.find(query, limit=limit, explain=True, pin_material=True)["items"], None
    saved = scoped_operation(
        session,
        reader,
        "find",
        {
            "query": query,
            "backend": None,
            "scenario": None,
            "limit": limit,
            "kinds": "case,skill,record",
            "repo": None,
            "tier": None,
            "explain": True,
            "revisions": {},
            "no_external": True,
            "expected_round": number,
        },
    )
    return saved["context"]["items"], saved["reference"]


def _page(reader, hit, resource, span, session, search, number):
    if session is None:
        view, _ = reader.read_hit(hit, resource=resource, byte_range=span)
        return view, view["content"], None
    saved = scoped_operation(
        session,
        reader,
        "read",
        {
            "expected_round": number,
            "ref": hit["material_ref"],
            "revision": hit["revision"],
            "source_flags": [
                flag
                for flag in ("--skill-root", "--store", "--installed-library")
                if flag in hit["material_read_args"]
            ],
            "byte_range": span,
            "resource": resource,
            "search_ref": search["path"],
        },
    )
    context = saved["context"]
    content = context["contexts"][0]["resources"][0]["content"] if context["contexts"] else ""
    return context["retrieval"]["display"], content, saved["reference"]


def _read(reader, hit, resource, available, session, search, number):
    parts, receipts = [], []
    start = 0
    omission = None
    while start < available:
        try:
            view, text, receipt = _page(
                reader, hit, resource, (start, available - start), session, search, number
            )
        except (
            PageBudgetTooSmall,
            UnavailableRevision,
            UnavailableResource,
            FileNotFoundError,
        ) as exc:
            if not parts:
                raise
            omission = "byte_budget" if isinstance(exc, PageBudgetTooSmall) else str(exc)
            break
        parts.append(text)
        if receipt is not None:
            receipts.append(receipt)
        start += len(text.encode())
        if not text or not view.get("next_byte_range"):
            break
    content = "".join(parts)
    return {
        "ref": hit["material_ref"],
        "revision": hit["revision"],
        "path": view["content_resource"],
        "content": content,
        "bytes": start,
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "partial": bool(view.get("next_byte_range")),
        "receipts": receipts,
        **({"omission": omission} if omission else {}),
    }


def _assessment(assessment, purpose, content):
    if not isinstance(assessment, dict):
        raise ValueError("assessment must be an object")
    quote = _text(assessment.get("quote"), "quote")
    claim = _text(assessment.get("claim"), "claim")
    verdict = assessment.get("verdict")
    adopted = assessment.get("adopted", False)
    if type(adopted) is not bool:
        raise ValueError("adopted must be boolean")
    if verdict not in APPLICABILITY_VERDICTS:
        raise ValueError("unknown applicability verdict")
    if quote in content:
        return {
            "quote": quote,
            "claim": claim,
            "verdict": verdict,
            "purpose": purpose,
            "adopted": adopted,
            "basis": "caller assessment of delivered quote",
        }
    return None


def _unanswered(answers):
    return [
        q
        for q, entries in answers.items()
        if not any(entry["verdict"] != "unknown" for entry in entries)
    ]


def decision_round(reader, request, *, session=None, select=None, assess=None):
    """Run bounded Find/Read. Callbacks see ranked hits, then the actual delivered resource."""
    if not isinstance(request, dict):
        raise ValueError("round request must be an object")
    task = _text(request.get("task"), "task")
    decision = _text(request.get("decision"), "decision")
    original = _text(request.get("query"), "query")
    next_action = _text(request.get("next_action"), "next_action")
    questions = _strings(request.get("questions"), "questions")
    if not questions or len(set(questions)) != len(questions):
        raise ValueError("questions must be nonempty and unique")
    number = request.get("round")
    if type(number) is not int or number < 1:
        raise ValueError("round must be a positive integer")
    signals = request.get("signals", [])
    if not isinstance(signals, list) or any(not isinstance(s, dict) for s in signals):
        raise ValueError("signals must be a list of sourced observations")
    for signal in signals:
        for key in ("observation", "source"):
            _text(signal.get(key), key)
    gaps = _strings(request.get("missing_measurements", []), "missing_measurements")
    attempts = _strings(request.get("tried", []), "tried")
    plan = request.get("queries", [{"query": original}])
    if not isinstance(plan, list) or not plan or any(not isinstance(q, dict) for q in plan):
        raise ValueError("queries must be a nonempty list of objects")
    if plan[0].get("query") != original:
        raise ValueError("first query must preserve the original wording")
    if not isinstance(request.get("budget", {}), dict):
        raise ValueError("budget must be an object")
    if not isinstance(request.get("environment", {}), dict):
        raise ValueError("environment must be an object")
    nqueries = _budget(request, "queries", 2)
    limit = _budget(request, "limit", 5)
    budget = _budget(request, "bytes", 65536)
    results = {q: [] for q in questions}
    delivered, resources, searches, seen = {}, [], [], set()
    used = 0
    stop = "query_plan_exhausted"
    for query in plan:
        text = _text(query.get("query"), "query")
        if not _unanswered(results) or used >= budget:
            break
        query_key = " ".join(text.casefold().split())
        if query_key in seen:
            searches.append({"query": text, "status": "duplicate_query"})
            continue
        if len(seen) >= nqueries:
            stop = "query_budget"
            break
        seen.add(query_key)
        hits, receipt = _find(reader, text, limit, session, number)
        listed = [
            {
                k: h[k]
                for k in (
                    "material_ref",
                    "ref",
                    "id",
                    "revision",
                    "body_resource",
                    "kind",
                    "title",
                    "score",
                    "summary",
                    "matched",
                    "unreadable",
                    "applicability",
                    "limitations",
                )
                if k in h
            }
            for h in hits
        ]
        trace = {
            "query": text,
            "receipt": receipt,
            "listed": listed,
            "selections": [],
            "status": "listed" if hits else "no_hits",
        }
        searches.append(trace)
        choices = (
            select(text, deepcopy(listed), deepcopy(results))
            if select
            else query.get("selections", [])
        )
        if not isinstance(choices, list):
            raise ValueError("selections must be a list")
        for choice in choices:
            if not isinstance(choice, dict):
                raise ValueError("each selection must be an object")
            q = _text(choice.get("question"), "question")
            if q not in results or choice.get("purpose") not in ("method", "conclusion"):
                raise ValueError("select a declared question and purpose")
            _text(choice.get("reason"), "reason")
            ref = _text(choice.get("ref"), "ref")
            selection = {k: choice[k] for k in ("ref", "question", "reason", "purpose")}
            trace["selections"].append(selection)
            hit = next((h for h in hits if (h.get("material_ref") or h.get("ref")) == ref), None)
            if not hit:
                selection["status"] = "outside_results"
                continue
            if not hit.get("revision") or not hit.get("body_resource"):
                selection["status"] = "unreadable"
                continue
            revision = hit["revision"]
            selection["revision"] = choice.get("revision", revision)
            if selection["revision"] != revision:
                selection.update(status="unavailable_revision", listed_revision=revision)
                continue
            resource = safe_path(_text(choice.get("resource", hit["body_resource"]), "resource"))
            selection["resource"] = resource
            key = (ref, revision, resource)
            index = delivered.get(key)
            if index is None:
                if used >= budget:
                    selection["status"] = "byte_budget"
                    continue
                try:
                    body = _read(reader, hit, resource, budget - used, session, receipt, number)
                except UnavailableRevision:
                    selection["status"] = "unavailable_revision"
                    continue
                except (UnavailableResource, FileNotFoundError):
                    selection["status"] = "unavailable_resource"
                    continue
                except PageBudgetTooSmall:
                    selection["status"] = "byte_budget"
                    continue
                index = len(resources)
                resources.append(body)
                delivered[key] = delivered[ref, revision, body["path"]] = index
                used += body["bytes"]
                selection["status"] = "delivered"
            else:
                selection["status"] = "reused"
            selection.update(resource_index=index, adopted=False)
            assessment = (
                assess(deepcopy(choice), deepcopy(resources[index]))
                if assess
                else choice.get("assessment")
            )
            if assessment is not None:
                entry = _assessment(assessment, choice["purpose"], resources[index]["content"])
                if entry is None:
                    selection["assessment_error"] = "quote_not_delivered"
                else:
                    results[q].append({"resource_index": index, **entry})
                    selection["adopted"] = entry["adopted"]
    unresolved = _unanswered(results)
    if not unresolved:
        stop = "questions_addressed"
    elif used >= budget or any(
        body["partial"] and body.get("omission", "byte_budget") == "byte_budget"
        for body in resources
    ):
        stop = "byte_budget"
    elif stop == "query_plan_exhausted" and all(
        s["status"] in ("no_hits", "duplicate_query") for s in searches
    ):
        stop = "no_hits"
    return {
        "task": task,
        "round": number,
        "decision": decision,
        "query": original,
        "environment": request.get("environment", {}),
        "signals": signals,
        "tried": attempts,
        "scope": "session local Find" if session else "local Find",
        "attempts": searches,
        "budget": {"queries": nqueries, "limit": limit, "bytes": budget},
        "bytes_used": used,
        "resources": resources,
        "questions": results,
        "missing_measurements": gaps,
        "unanswered": unresolved,
        "unanswered_verdict": {q: "unknown" for q in unresolved},
        "next_action": next_action,
        "stop": "awaiting_measurement" if gaps else stop,
        "retrieval_stop": stop,
    }
