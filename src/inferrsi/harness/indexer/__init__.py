"""Check the knowledge delivered for a managed request against its frozen policy."""

from ..records import knowledge_capture


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


def ordinary_delivery(root, plan, *, context_id, binding, reader, retain_context, **request):
    """Validate the capture returned by the injected Apps callback."""
    path, fingerprint = retain_context(root, context_id=context_id, reader=reader,
                                       diagnosis_binding=binding, **request)
    relative = path.relative_to(root).as_posix()
    if relative != f"knowledge/{context_id}.json":
        raise ValueError("Knowledge capture differs from its dispatched request")
    reference = {"path": relative, "sha256": fingerprint, "kind": "delivered_context"}
    context = knowledge_capture.read_retained(root, reference)
    if context.get("context_id") != context_id or context.get("diagnosis_binding") != binding:
        raise ValueError("Knowledge capture differs from its dispatched request")
    check_context_ranking(plan, context)
    if "ranking_policy" in plan:
        check_returned_ranking(context.get("retrieval"), plan["ranking_policy"])
    return {"reference": reference, "context": context}


def service_delivery(plan, *, context_id, binding, reader, query, **request):
    """Validate a fingerprint-free service receipt from the injected reader."""
    context = reader.collect_service_context(query, **request)
    check_context_ranking(plan, context)
    if "diagnosis_binding" in context and context["diagnosis_binding"] != binding:
        raise ValueError("Knowledge capture differs from its dispatched request")
    if context.get("prepared_not_consumed") is not True:
        raise ValueError("Service knowledge delivery requires a prepared context")
    if binding:
        context = {**context, "diagnosis_binding": binding}
    return {"reference": {"path": f"knowledge/{context_id}.json", "kind": "delivered_context",
                          "prepared_not_consumed": True}, "context": context}
