"""Check the knowledge delivered for a managed request against its frozen policy."""

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
    source = plan.get("ranking_policy_source")
    if source is None:
        policy = ranking_policy_for(recorded["id"])
    elif source == "configuration":
        try:
            policy = ranking_policy_for(recorded)
        except ValueError as error:
            raise ValueError(
                "Frozen ranking policy changed or is incomplete, use its original runtime"
            ) from error
    else:
        raise ValueError("Unknown frozen ranking policy source, use the original runtime")
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


def check_find_return(plan, result, *, query, limit):
    """Check the reader's Find result before retaining a search receipt."""
    if (not isinstance(result, dict) or result.get("query") != query
            or not isinstance(result.get("items"), list) or len(result["items"]) > limit):
        raise ValueError("Find receipt differs from its dispatched request")
    check_context_ranking(plan, {"request": result})
