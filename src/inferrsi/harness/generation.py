"""Seal the inputs of one generation attempt before execution registration."""

from copy import deepcopy
from hashlib import sha256
from pathlib import PurePosixPath

from inferrsi.contracts.json_v1 import encode
from inferrsi.harness import run_store
from inferrsi.harness.errors import PublicError
from inferrsi.harness.execution_service import LocalCpuTarget, validate

_MANIFEST_FIELDS = {"schema_version", "provider", "output_contract", "context_refs", "attempt_id"}
_MANIFEST_PATH = PurePosixPath("inputs/generation-plan.json")


def prepare_generation(
    store: run_store.RunStore, target: LocalCpuTarget, *, context_provider, candidate_provider,
    context_request: dict, candidate_context: dict, attempt: dict,
) -> dict:
    """Collect and seal the approved context, then return the final ordinary ExecutionSpec.

    A retry with the same preparation request uses the committed delivery and the same
    provider configuration. A changed request requires a new attempt.
    The caller saves and replays this spec through Harness.execute. Preparation does not
    register an execution or allocate a new attempt.
    """
    errors = run_store._attempt_errors(attempt)
    if errors:
        raise PublicError(
            "InvalidRequest", stage="generation-seal", message="illegal generation attempt",
            field_errors=errors,
        )
    attempt_id = attempt["attempt_id"]
    try:
        context = deepcopy(candidate_context)
        context.pop("delivered_context", None)
        preparation = {"attempt": attempt, "context_request": context_request,
                       "candidate_context": context}
        digest = "sha256:" + sha256(encode(preparation)).hexdigest()
        delivery = store._find_delivery(attempt_id, preparation_digest=digest)
        if delivery is None:
            delivery = _collect_delivery(
                store, context_provider, attempt_id, context_request, digest,
            )
        context["delivered_context"] = delivery
        ref = deepcopy(delivery["artifact"])
        plan = candidate_provider.plan_generation(context, deepcopy(attempt))
        spec = _bind_generation_plan(store, target, attempt, plan, ref)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise PublicError(
            "InvalidRequest", stage="generation-seal", attempt_id=attempt_id, started=False,
            message="invalid delivery or candidate generation plan",
        ) from exc
    return spec


def _collect_delivery(store, context_provider, attempt_id, context_request, preparation_digest):
    draft = context_provider.collect(deepcopy(context_request))
    content = draft.content
    if (
        not isinstance(content, bytes) or sha256(content).hexdigest() != draft.sha256
        or len(content) > context_request["max_bytes"]
        or sum(item["delivered_bytes"] for item in draft.items) != len(content)
    ):
        raise ValueError("invalid generation delivery bytes")
    descriptor = {"items": draft.items, "selection": draft.selection, "omissions": draft.omissions,
                  "limitations": draft.limitations}
    return store._seal_delivered_context(attempt_id, preparation_digest, content, descriptor)


def _bind_generation_plan(store, target, attempt, plan, delivery_ref):
    attempt_id = attempt["attempt_id"]
    manifest = plan["manifest"]
    spec = deepcopy(plan["spec"])
    if (
        manifest.keys() != _MANIFEST_FIELDS or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1 or manifest["attempt_id"] != attempt_id
        or manifest["context_refs"] != [delivery_ref]
        or {key: spec[key] for key in attempt} != attempt
        or any(item["role"] == "generation_plan" for item in spec["inputs"])
        or not any(item["source_ref"] == delivery_ref for item in spec["inputs"])
    ):
        raise ValueError("generation plan does not match its sealed context and attempt")
    paths = [item["materialized_path"] for item in spec["inputs"]]
    paths.extend(output["path"] for step in spec["steps"] for output in step["outputs"])
    for source in paths:
        path = PurePosixPath(source.casefold())
        if path.is_relative_to(_MANIFEST_PATH) or _MANIFEST_PATH.is_relative_to(path):
            raise ValueError("a generation input or output occupies the reserved plan path")
    data = encode(manifest)
    # The expected address is internal until the commit succeeds.
    ref = run_store._generation_ref(
        store.namespace, run_store.attempt_hash(attempt_id), "generation-plan", data,
    )
    spec["inputs"].append({
        "role": "generation_plan", "source": ref["location"], "source_namespace": "artifact",
        "source_ref": ref, "snapshot_format": "file-v1", "expected_sha256": ref["sha256"],
        "materialized_path": _MANIFEST_PATH.as_posix(),
    })
    validate(spec, target)
    store._seal_generation_input(attempt_id, "generation-plan", data)
    return spec
