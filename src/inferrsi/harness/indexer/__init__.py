"""Check the knowledge delivered for a managed request against its frozen policy."""

import hashlib

from ..records import atomic_capture, knowledge_capture


def require_ranking_policy(recorded, effective):
    if (not isinstance(recorded, dict) or not isinstance(effective, dict)
            or type(recorded.get("version")) is not int
            or not isinstance(recorded.get("weights"), dict)
            or any(type(value) not in (int, float) for value in recorded["weights"].values())
            or recorded != effective):
        raise ValueError("Frozen ranking policy changed or is incomplete, use its original runtime")


def resolve_frozen_ranking(plan, ranking_policy_for, *, read_only=False):
    if read_only and "ranking_policy" not in plan:
        return None
    recorded = plan.get("ranking_policy")
    if not isinstance(recorded, dict) or not isinstance(recorded.get("id"), str):
        raise ValueError("Missing frozen ranking policy, use the original runtime to resume")
    if ranking_policy_for is None:
        raise ValueError("A resolver for the frozen ranking policy is required")
    policy = ranking_policy_for(recorded["id"])
    effective = (policy.configuration() if plan.get("evaluation_mode") == "service_reuse"
                 else policy.receipt())
    require_ranking_policy(recorded, effective)
    return policy


def check_context_ranking(plan, context):
    if "ranking_policy" in plan:
        request = context.get("request") if isinstance(context, dict) else None
        recorded = request.get("ranking_policy") if isinstance(request, dict) else None
        require_ranking_policy(recorded, plan["ranking_policy"])


def check_returned_ranking(observation, effective):
    selection = observation.get("selection") if isinstance(observation, dict) else None
    recorded = selection.get("ranking_policy") if isinstance(selection, dict) else None
    try:
        require_ranking_policy(recorded, effective)
    except ValueError as error:
        raise ValueError("Delivered ranking policy differs from the frozen session") from error


def _check_dispatched_request(recorded, expected, lane):
    if not isinstance(recorded, dict) or any(
        key not in recorded or type(recorded[key]) is not type(value) or recorded[key] != value
        for key, value in expected.items()
    ):
        raise ValueError(f"{lane} knowledge receipt differs from its dispatched request")


def ordinary_delivery(root, plan, *, context_id, binding, reader, prepare_context, **request):
    """Validate the prepared capture and its underlying retrieval before Manager retains it."""
    context = prepare_context(root, context_id=context_id, reader=reader,
                              diagnosis_binding=binding, **request)
    if (not isinstance(context, dict) or context.get("context_id") != context_id
            or context.get("diagnosis_binding") != binding):
        raise ValueError("Knowledge capture differs from its dispatched request")
    expected = {key: request[key] for key in ("query", "relevance", "scenario", "limit",
                                             "context_bytes")}
    expected["relevance_method"] = request["relevance_method"] or "find-lexical-v1"
    _check_dispatched_request(context.get("request"), expected, "Ordinary")
    observation = context.get("retrieval")
    _check_dispatched_request(observation.get("request") if isinstance(observation, dict) else None,
                              expected, "Ordinary")
    check_context_ranking(plan, context)
    if "ranking_policy" in plan:
        check_returned_ranking(observation, plan["ranking_policy"])
    return _capture_delivery(context_id, context, "delivered_context")


def pinned_delivery(root, plan, *, context_id, binding, reader, assemble_text, **request):
    """Verify the exact bodies and record refusals against the frozen session policy."""
    context = atomic_capture.prepare_selection(
        root, context_id=context_id, reader=reader, assemble_text=assemble_text,
        diagnosis_binding=binding, ranking_policy=plan.get("ranking_policy"), **request,
    )
    check_context_ranking(plan, context)
    delivered = context["selection"]["status"] == "delivered"
    return _capture_delivery(context_id, context,
                             "delivered_context" if delivered else "knowledge_refusal")


def _capture_delivery(context_id, context, kind):
    reference = {"path": f"knowledge/{context_id}.json",
                 "sha256": hashlib.sha256(knowledge_capture.capture_bytes(context)).hexdigest(),
                 "kind": kind}
    return {"reference": reference, "context": context}


def service_delivery(plan, *, context_id, binding, reader, query, relevance_method, limit,
                     context_bytes, ranking_policy):
    """Validate a fingerprint-free service receipt from the injected reader."""
    method = "find-lexical-v1" if relevance_method is None else relevance_method
    context = reader.collect_service_context(
        query, relevance_method=method, limit=limit, context_bytes=context_bytes,
        ranking_policy=ranking_policy,
    )
    check_context_ranking(plan, context)
    expected = {"relevance": query, "relevance_method": method, "limit": limit,
                "context_bytes": context_bytes}
    recorded = context.get("request") if isinstance(context, dict) else None
    _check_dispatched_request(recorded, expected, "Service")
    if "diagnosis_binding" in context and context["diagnosis_binding"] != binding:
        raise ValueError("Knowledge capture differs from its dispatched request")
    if context.get("prepared_not_consumed") is not True:
        raise ValueError("Service knowledge delivery requires a prepared context")
    if binding:
        context = {**context, "diagnosis_binding": binding}
    return {"reference": {"path": f"knowledge/{context_id}.json", "kind": "delivered_context",
                          "prepared_not_consumed": True}, "context": context}
