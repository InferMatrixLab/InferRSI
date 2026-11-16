"""Check the unsealed Apps plan handed to the Harness generation controller."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from inferrsi.apps.api import CandidateProvider
from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness.errors import PublicError
from inferrsi.harness.execution_service import LocalCpuTarget, validate

_FIXTURES = Path(__file__).resolve().parents[1] / "docs/contracts/fixtures/t108-v4"
_ATTEMPT_FIELDS = (
    "request_id", "run_id", "attempt_id", "owner", "target_request", "deadline_utc",
    "resources", "budget", "retry_of", "retry_reason",
)


def _artifact(name):
    body = name.encode()
    return {
        "location": f"stores/test/{name}", "sha256": sha256(body).hexdigest(),
        "media_type": "application/octet-stream", "size_bytes": len(body),
    }


def _fixed_input(role, ref):
    return {
        "role": role, "source": ref["location"], "source_namespace": "artifact",
        "source_ref": ref, "snapshot_format": "file-v1", "expected_sha256": ref["sha256"],
        "materialized_path": f"inputs/{role}",
    }


@pytest.fixture
def generation():
    seed = decode((_FIXTURES / "execution-spec.json").read_bytes())
    prepared = decode((_FIXTURES / "prepared.json").read_bytes())
    context_ref, material, feedback = map(_artifact, ("context", "task", "feedback"))
    candidate_contract = prepared["candidate_contract"]
    return {
        "context": {
            "campaign_id": "campaign-1", "generation_id": "generation-1",
            "candidate": None, "parent": None, "task_materials": [material],
            "delivered_context": {
                "artifact": context_ref, "items": [], "selection": {},
                "omissions": [], "limitations": [],
            },
            "allowed_feedback": [feedback], "output_contract": candidate_contract,
        },
        "attempt": {field: seed[field] for field in _ATTEMPT_FIELDS},
        "provider": {"name": "cpu-example", "revision": "1"},
        "output_contract": {
            "manifest_role": "generation-manifest", "candidate_role": "candidate",
            "format_schema": candidate_contract["format_schema"],
            "required_input_roles": ["candidate"], "parser_revision": "1",
        },
        "inputs": [
            _fixed_input("knowledge", context_ref),
            _fixed_input("task", material),
            _fixed_input("feedback", feedback),
        ],
        "steps": [{
            "step_id": "generate", "runtime_role": "local-python",
            "entrypoint_kind": "python_module", "entrypoint": "fixture_generation",
            "entrypoint_revision": "1", "expected_code_sha256": None,
            "args": ["inputs/knowledge", "output/candidate.txt"], "cwd": ".",
            "timeout_seconds": None,
            "outputs": [
                {"role": "generation-manifest", "path": "output/manifest.json", "required": True,
                 "media_type": "application/json",
                 "format_schema": {"name": "fixture-generation-manifest", "revision": "1"}},
                {"role": "candidate", "path": "output/candidate.txt", "required": True,
                 "media_type": "text/plain", "format_schema": candidate_contract["format_schema"]},
            ],
        }],
        "required_capabilities": ["local-process-tree"],
    }


def _provider(generation, bind_inputs=None):
    return CandidateProvider(
        provider=generation["provider"], output_contract=generation["output_contract"],
        steps=generation["steps"], required_capabilities=generation["required_capabilities"],
        bind_inputs=bind_inputs or (lambda context: generation["inputs"]),
        output_root_for=lambda attempt_id: f"generation/{attempt_id}",
    )


def test_plan_preserves_attempt_and_keeps_manifest_separate(generation, tmp_path):
    original = deepcopy(generation)
    provider = _provider(generation)
    result = provider.plan_generation(generation["context"], generation["attempt"])
    spec, manifest = result["spec"], result["manifest"]

    assert {key: spec[key] for key in _ATTEMPT_FIELDS} == generation["attempt"]
    assert all(spec[field] is None for field in (
        "generation_record_ref", "prepared_ref", "protocol_digest", "operation",
        "validation_scope", "candidate",
    ))
    assert spec["inputs"] == generation["inputs"]
    assert spec["steps"] == generation["steps"]
    assert spec["output_root"] == f"generation/{generation['attempt']['attempt_id']}"
    assert manifest == {
        "schema_version": 1, "provider": generation["provider"],
        "output_contract": generation["output_contract"],
        "context_refs": [generation["context"]["delivered_context"]["artifact"]],
        "attempt_id": generation["attempt"]["attempt_id"],
    }
    target_request = spec["target_request"]
    validate(spec, LocalCpuTarget(
        target_request["target_id"], target_request["config_revision"], tmp_path,
    ))
    assert encode(provider.plan_generation(generation["context"], generation["attempt"])) == encode(
        result,
    )
    spec["inputs"][0]["source_ref"]["location"] = "other"
    manifest["output_contract"]["required_input_roles"].clear()
    assert generation == original


def test_provider_binds_each_context_with_the_same_worker_configuration(generation):
    def bind_context(context):
        return [
            _fixed_input("knowledge", context["delivered_context"]["artifact"]),
            _fixed_input("task", context["task_materials"][0]),
            _fixed_input("feedback", context["allowed_feedback"][0]),
        ]

    context, attempt = generation["context"], generation["attempt"]
    provider = _provider(generation, bind_context)
    first = provider.plan_generation(context, attempt)
    next_context = deepcopy(context)
    next_context["delivered_context"]["artifact"] = _artifact("another-context")
    next_context["allowed_feedback"] = [_artifact("another-feedback")]
    next_attempt = {**attempt, "attempt_id": "next-attempt", "request_id": "next-attempt"}
    generation["steps"][0]["entrypoint"] = "altered-after-configuration"

    second = provider.plan_generation(next_context, next_attempt)

    assert second["spec"]["steps"] == first["spec"]["steps"]
    assert second["spec"]["output_root"] == "generation/next-attempt"
    assert second["manifest"]["attempt_id"] == "next-attempt"
    assert second["manifest"]["context_refs"] == [next_context["delivered_context"]["artifact"]]
    assert second["spec"]["inputs"] == bind_context(next_context)


@pytest.mark.parametrize(("path", "value"), (
    pytest.param(("context", "delivered_context"), {"content": b"unsealed"}, id="draft"),
    pytest.param(("inputs",), [], id="missing-delivery"),
    pytest.param(("inputs", 2), _fixed_input("feedback", _artifact("foreign")),
                 id="foreign-feedback"),
    pytest.param(("inputs", 0, "role"), "generation_plan", id="reserved-role"),
    pytest.param(("steps", 0, "outputs"), [], id="missing-outputs"),
    pytest.param(("steps", 0, "outputs", 1, "required"), False, id="optional-candidate"),
    pytest.param(("steps", 0, "outputs", 1, "format_schema"), {"name": "other", "revision": "1"},
                 id="wrong-format"),
    pytest.param(("steps", 0, "expected_code_sha256"), "0" * 64, id="worker-digest"),
    pytest.param(("attempt", "request_id"), "different-attempt", id="new-request-id"),
))
def test_plan_rejects_invalid_handoff(generation, path, value):
    target = generation
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(PublicError) as caught:
        _provider(generation).plan_generation(generation["context"], generation["attempt"])
    assert (caught.value.code, caught.value.stage) == ("InvalidExecutionSpec", "generation_plan")
