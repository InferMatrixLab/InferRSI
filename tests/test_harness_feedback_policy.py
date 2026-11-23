"""Frozen feedback authorization controls, distinct from production-worker evidence."""

import io
import sqlite3
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness import run_store
from inferrsi.harness.errors import PublicError
from inferrsi.harness.generation import prepare_generation
from tests.test_apps_generation_plan import _fixed_input, _provider
from tests.test_apps_generation_plan import generation as generation
from tests.test_harness_generation_seal import cpu_generation as cpu_generation

FIXTURES = Path(__file__).resolve().parents[1] / "docs/contracts/fixtures/t108-v4"


class Reader:
    def __init__(self, values):
        self.values = values

    def open(self, ref):
        if ref["location"] not in self.values:
            raise PublicError("ArtifactUnavailable", stage="open", message="control bytes absent")
        return io.BytesIO(self.values[ref["location"]])


def document(reader, location, value):
    data = encode(value)
    reader.values[location] = data
    return {"location": location, "sha256": sha256(data).hexdigest(),
            "size_bytes": len(data), "media_type": "application/json"}


@pytest.fixture
def authorized(cpu_generation, generation, request):
    store, target, harness, draft, inputs = cpu_generation
    control = getattr(request, "param", None)
    original = decode((FIXTURES / "execution-spec.json").read_bytes())
    attempt = {key: deepcopy(original[key]) for key in inputs["attempt"]}
    for key in ("run_id", "owner", "deadline_utc", "resources", "budget", "target_request"):
        attempt[key] = deepcopy(inputs["attempt"][key])
    if control == "owner":
        attempt["owner"] = "another-owner"
    spec = {**original, **attempt}
    payload = decode((FIXTURES / "record-payload.json").read_bytes())
    for key in attempt.keys() & payload.keys():
        payload[key] = deepcopy(attempt[key])
    payload["request_digest"] = run_store.request_digest(spec)
    prepared = decode((FIXTURES / "prepared.json").read_bytes())
    protocol_bytes, prepared_bytes = ((FIXTURES / name).read_bytes()
                                      for name in ("protocol.json", "prepared.json"))
    if control in ("matching-rule", "protocol-version", "semantic"):
        # Pure fixture identity calculations; no production prepare/worker claim.
        from inferrsi.benchmark import preparation

        protocol = decode(protocol_bytes)
        if control == "matching-rule":
            protocol["required_evidence"][0]["matching_rule_revision"] = "2"
            prepared["required_evidence"] = deepcopy(protocol["required_evidence"])
        elif control == "protocol-version":
            protocol["schema_version"] = 2
        else:
            protocol["task_parameters"]["label"] += " changed semantic parameter"
        if control != "semantic":
            prepared["protocol_digest"] = preparation.protocol_digest(protocol)
        protocol_bytes = encode(protocol)
        prepared["protocol"].update(sha256=sha256(protocol_bytes).hexdigest(),
                                     size_bytes=len(protocol_bytes))
        prepared["prepared_id"] = preparation.prepared_id(prepared)
        prepared_bytes = encode(prepared)
        payload["protocol_digest"] = prepared["protocol_digest"]
        payload["prepared_ref"].update(prepared_id=prepared["prepared_id"])
        payload["prepared_ref"]["artifact"].update(sha256=sha256(prepared_bytes).hexdigest(),
                                                    size_bytes=len(prepared_bytes))
    candidate_bytes = (FIXTURES / "candidate.txt").read_bytes()
    candidate = run_store.artifact_ref(store.namespace, candidate_bytes, "application/octet-stream")
    # This is an explicitly controlled proof, not output from a production task worker.
    proof_bytes = encode({"control": "format-check", "candidate_sha256": candidate["sha256"]})
    proof = run_store.artifact_ref(store.namespace, proof_bytes, "application/json")
    payload["bound_inputs"] = [{
        "role": "candidate", "retained_ref": candidate, "actual_sha256": candidate["sha256"],
        "snapshot_format": "file-v1", "captured_at": payload["recorded_at"],
        "attempt_id": attempt["attempt_id"], "step_ids": [payload["steps"][0]["step_id"]],
        "materialized_path": "inputs/candidate", "expected_sha256": candidate["sha256"],
        "identity_status": "matched", "reasons": [],
    }]
    if control == "snapshot":
        payload["bound_inputs"][0]["snapshot_format"] = "unknown-v2"
    check = deepcopy(payload["checks"][0])
    check.update(check_id="format", status="passed", reasons=[], evidence_refs=[proof],
                 artifact_schema={"name": "format-proof", "revision": "1"})
    if control == "producer":
        check["producer"]["kind"] = "task_worker"
    payload["checks"] = [check]
    payload["budget_admission"]["scope_id"] = attempt["budget"]["scope_id"]
    with store.claim(attempt, payload["request_digest"]) as claim:
        record = claim.commit(payload, [(candidate, candidate_bytes), (proof, proof_bytes)])
    context = inputs["candidate_context"]
    context.update(parent=deepcopy(payload["candidate"]), allowed_feedback=[proof])

    def bind(candidate_context):
        return [_fixed_input("knowledge", candidate_context["delivered_context"]["artifact"]),
                *[_fixed_input(f"feedback-{index}", ref)
                  for index, ref in enumerate(candidate_context["allowed_feedback"])]]

    inputs["candidate_provider"] = _provider(generation, bind)
    reader = Reader({prepared["protocol"]["location"]: protocol_bytes,
                     payload["prepared_ref"]["artifact"]["location"]: prepared_bytes})
    policy = {
        "schema_version": 1, "campaign_id": context["campaign_id"], "goal": "software control",
        "starting_point": {"candidate": payload["candidate"],
                           "inputs": [_fixed_input("candidate", candidate)],
                           "generation_record_ref": None},
        "prepared": [{"validation_scope": payload["validation_scope"],
                      "prepared_ref": payload["prepared_ref"],
                      "protocol_digest": payload["protocol_digest"]}],
        "budget_scope": attempt["budget"]["scope_id"], "deadline_utc": attempt["deadline_utc"],
        "advance_rule": {"name": "manual-control", "revision": "1"},
        "stop_rule": {"name": "manual-stop", "revision": "1"},
        "allowed_feedback": [payload["validation_scope"]],
    }
    ref = document(reader, "policies/feedback.json", policy)
    return store, target, harness, inputs, reader, ref, policy, record, proof_bytes


def test_control_record_has_original_retained_proof(authorized):
    store, _, _, _, _, _, _, record, data = authorized
    assert record.payload["started"] is False  # Not called a production worker result.
    with store.open(record.payload["checks"][0]["evidence_refs"][0]) as stream:
        assert stream.read() == data


def prepare(case, **overrides):
    store, target, _, inputs, reader, ref, _, record, _ = case
    options = {"feedback_policy_ref": ref, "feedback_record_refs": [record.record_ref],
               "artifact_reader": reader, **overrides}
    return prepare_generation(store, target, **inputs, **options)


def test_opt_in_retains_policy_and_allowed_proof_for_real_generation(authorized):
    store, _, harness, inputs, reader, ref, _, _, proof_bytes = authorized
    spec = prepare(authorized)
    policy_input = next(item for item in spec["inputs"]
                        if item["role"] == "generation_feedback_policy")
    with store.open(policy_input["source_ref"]) as stream:
        assert stream.read() == reader.values[ref["location"]]
    del reader.values[ref["location"]]  # The original policy archive is no longer needed.
    result = harness.execute(spec)
    assert result["exit_code"] == 0
    bound = next(item for item in result["bound_inputs"] if item["role"] == "feedback-0")
    with store.open(bound["retained_ref"]) as stream:
        assert stream.read() == proof_bytes
    assert prepare(authorized) == spec
    assert result["attempt_id"] == inputs["attempt"]["attempt_id"]


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_registered_policy_generation_replays_before_fresh_authorization(
    authorized, monkeypatch, tmp_path, fault,
):
    from inferrsi.harness import execution_service, generation_feedback
    from inferrsi.harness.api import Harness, LocalCpuTarget

    store, _, harness, _, _, _, _, _, _ = authorized
    spec = prepare(authorized)
    saved = encode(spec)
    original = harness.execute(decode(saved))
    assert original["exit_code"] == 0
    before = store.committed(original["attempt_id"])
    policy = next(item["source_ref"] for item in spec["inputs"]
                  if item["role"] == "generation_feedback_policy")
    path = store.root / "objects" / policy["sha256"][:2] / policy["sha256"]
    assert path.resolve().is_relative_to(tmp_path.resolve())
    data = path.read_bytes()
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(bytes([data[0] ^ 1]) + data[1:])

    def forbidden(*args, **kwargs):
        pytest.fail("registered generation performed fresh authorization or execution")

    class Never:
        open = forbidden

    monkeypatch.setattr(generation_feedback, "verify", forbidden)
    monkeypatch.setattr(execution_service, "_budget", forbidden)
    monkeypatch.setattr(execution_service, "_deadline_seconds", forbidden)
    monkeypatch.setattr(execution_service.local_process, "_supervise", forbidden)
    monkeypatch.setattr(store, "claim", forbidden)
    monkeypatch.setattr(run_store.Claim, "commit", forbidden)
    monkeypatch.setattr(run_store, "utc_now", lambda: "2100-01-01T00:00:00Z")
    retired = Harness(store, LocalCpuTarget("retired", "2", tmp_path / "retired"),
                      artifact_reader=Never())
    replayed = retired.execute(decode(saved))
    assert replayed["record_ref"] == original["record_ref"]
    assert replayed["request_digest"] == original["request_digest"]
    changed = decode(saved)
    changed["deadline_utc"] = "2098-01-01T00:00:00Z"
    with pytest.raises(PublicError) as caught:
        retired.execute(changed)
    assert (caught.value.code, caught.value.stage) == ("RequestConflict", "claim")
    assert store.committed(original["attempt_id"]).payload_bytes == before.payload_bytes
    assert encode(spec) == saved
    with store._connection() as connection:
        assert connection.execute("SELECT count(*) FROM attempts").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM records").fetchone()[0] == 2


@pytest.mark.parametrize("fault,code", [
    ("denied-scope", "InvalidRequest"), ("extra-ref", "InvalidRequest"),
    ("unknown-version", "UnsupportedSchema"), ("wrong-scope", "InvalidRequest"),
    ("wrong-parent", "IdentityMismatch"), ("bad-hash", "ArtifactIntegrityError"),
    ("absent", "ArtifactUnavailable"),
    ("alternate-ref", "InvalidRequest"), ("assessment", "InvalidRequest"),
    ("bad-proof", "ArtifactIntegrityError"), ("absent-proof", "ArtifactUnavailable"),
    ("bad-candidate", "ArtifactIntegrityError"), ("unknown-ref-version", "UnsupportedSchema"),
    ("bool-version", "InvalidRequest"), ("ambiguous", "InvalidRequest"),
    ("bad-binding", "IdentityMismatch"),
])
def test_refusal_precedes_both_providers(authorized, fault, code):
    store, target, _, inputs, reader, ref, policy, record, _ = authorized
    if fault == "denied-scope":
        policy["allowed_feedback"] = []
    elif fault == "unknown-version":
        policy["schema_version"] = 2
    elif fault == "wrong-scope":
        policy["prepared"][0]["validation_scope"] = "development"
        policy["allowed_feedback"] = ["development"]
    elif fault == "extra-ref":
        inputs["candidate_context"]["allowed_feedback"].append(
            {**ref, "location": "unapproved/whole-assessment.json"})
    elif fault == "wrong-parent":
        inputs["candidate_context"]["parent"]["candidate_id"] = "another-parent"
    elif fault == "alternate-ref":
        inputs["candidate_context"]["allowed_feedback"][0] = {
            **inputs["candidate_context"]["allowed_feedback"][0], "location": "other/same-bytes",
        }
    elif fault == "assessment":
        inputs["candidate_context"]["allowed_feedback"] = [document(
            reader, "fixtures/whole-assessment.json",
            decode((FIXTURES / "assessment.json").read_bytes()),
        )]
    elif fault in ("bad-proof", "absent-proof", "bad-candidate"):
        artifact = (record.payload["bound_inputs"][0]["retained_ref"] if fault == "bad-candidate"
                    else record.payload["checks"][0]["evidence_refs"][0])
        path = store.root / "objects" / artifact["sha256"][:2] / artifact["sha256"]
        assert path.resolve().is_relative_to(store.root.resolve())
        if fault == "absent-proof":
            path.unlink()
        else:
            path.write_bytes(b"controlled corruption\n")
    elif fault == "unknown-ref-version":
        policy["prepared"][0]["prepared_ref"]["schema_version"] = 2
    elif fault == "bool-version":
        policy["schema_version"] = True
    elif fault == "ambiguous":
        policy["prepared"].append(deepcopy(policy["prepared"][0]))
    elif fault == "bad-binding":
        policy["prepared"][0]["prepared_ref"]["prepared_id"] = "sha256:" + "0" * 64
    if fault not in ("bad-hash", "absent"):
        ref = document(reader, ref["location"], policy)
    elif fault == "bad-hash":
        reader.values[ref["location"]] = b"changed bytes\n"
    else:
        del reader.values[ref["location"]]

    def forbidden(*args, **kwargs):
        raise AssertionError("refused feedback reached a provider")

    with pytest.raises(PublicError) as error:
        prepare_generation(
            store, target, **{**inputs,
                              "context_provider": SimpleNamespace(collect=forbidden),
                              "candidate_provider": SimpleNamespace(plan_generation=forbidden)},
            feedback_policy_ref=ref, feedback_record_refs=[record.record_ref],
            artifact_reader=reader,
        )
    assert (error.value.code, error.value.stage) == (code, "validate")
    with sqlite3.connect(store.root / "index.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM generation_inputs").fetchone()[0] == 0


@pytest.mark.parametrize("changed", ["policy", "records"])
def test_changed_authorization_does_not_replay_an_old_delivery(authorized, changed):
    prepare(authorized)
    _, _, _, _, reader, ref, _, _, _ = authorized
    if changed == "policy":
        alternate = {**ref, "location": "policies/other.json"}
        reader.values[alternate["location"]] = reader.values[ref["location"]]
        override = {"feedback_policy_ref": alternate}
    else:
        override = {"feedback_record_refs": []}
    with pytest.raises(PublicError) as error:
        prepare(authorized, **override)
    assert (error.value.code, error.value.stage) == ("RequestConflict",
                                                   "delivered-context-retention")


def test_absent_policy_keeps_the_exact_legacy_preparation_identity(cpu_generation):
    store, target, _, _, inputs = cpu_generation
    spec = prepare_generation(store, target, **inputs)
    assert prepare_generation(store, target, **inputs, feedback_policy_ref=None) == spec
    context = deepcopy(inputs["candidate_context"])
    context.pop("delivered_context", None)
    expected = "sha256:" + sha256(encode({
        "attempt": inputs["attempt"], "context_request": inputs["context_request"],
        "candidate_context": context,
    })).hexdigest()
    with sqlite3.connect(store.root / "index.sqlite3") as connection:
        metadata = connection.execute(
            "SELECT descriptor FROM generation_inputs WHERE role='delivered-context'",
        ).fetchone()[0]
    assert decode(metadata)["preparation_digest"] == expected
    assert all(item["role"] != "generation_feedback_policy" for item in spec["inputs"])


@pytest.mark.parametrize("authorized,code", [
    ("owner", "IdentityMismatch"), ("producer", "IdentityMismatch"),
    ("matching-rule", "UnsupportedRuleVersion"), ("protocol-version", "UnsupportedSchema"),
    ("semantic", "ArtifactIntegrityError"), ("snapshot", "UnsupportedRuleVersion"),
], indirect=["authorized"])
def test_record_and_protocol_controls_fail_closed(authorized, code):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid source metadata reached a provider")

    authorized[3].update(context_provider=SimpleNamespace(collect=forbidden),
                         candidate_provider=SimpleNamespace(plan_generation=forbidden))
    with pytest.raises(PublicError) as error:
        prepare(authorized)
    assert (error.value.code, error.value.stage) == (code, "validate")


def test_policy_retention_failure_never_calls_providers(authorized, monkeypatch):
    store, target, _, inputs, reader, ref, _, record, _ = authorized

    def forbidden(*args, **kwargs):
        raise AssertionError("policy retention failure reached a provider")

    def fail(*args, **kwargs):
        raise OSError("controlled policy retention failure")

    monkeypatch.setattr(store, "_retain", fail)
    with pytest.raises(PublicError) as error:
        prepare_generation(
            store, target, **{**inputs,
                              "context_provider": SimpleNamespace(collect=forbidden),
                              "candidate_provider": SimpleNamespace(plan_generation=forbidden)},
            feedback_policy_ref=ref, feedback_record_refs=[record.record_ref],
            artifact_reader=reader,
        )
    assert (error.value.code, error.value.stage, error.value.started) == (
        "ExecutionPersistenceError", "generation-seal", False,
    )
    with sqlite3.connect(store.root / "index.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM generation_inputs").fetchone()[0] == 0


def test_authorization_imports_no_other_business_module_in_a_child(authorized, tmp_path):
    store, _, _, inputs, reader, ref, _, record, _ = authorized
    bundle = {"root": str(store.root), "namespace": store.namespace,
              "attempt": inputs["attempt"], "context": inputs["candidate_context"],
              "policy": ref, "records": [record.record_ref],
              "resources": {name: data.decode("utf-8") for name, data in reader.values.items()}}
    path = tmp_path / "authorization.json"
    path.write_bytes(encode(bundle))
    child = """
import io, json, sys
sys.path.insert(0, sys.argv[1])
from inferrsi.harness.generation_feedback import verify
from inferrsi.harness.run_store import RunStoreReader
data = json.load(open(sys.argv[2], encoding='utf-8'))
class Reader:
    def open(self, ref):
        return io.BytesIO(data['resources'][ref['location']].encode('utf-8'))
store = RunStoreReader(data['root'], data['namespace'])
verify(store, data['attempt'], data['context'], data['policy'], data['records'], Reader())
assert not any(name.startswith(('inferrsi.apps', 'inferrsi.benchmark', 'inferrsi.knowledge'))
               for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", child,
         str(Path(__file__).resolve().parents[1] / "src"), str(path)],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("collision", ["role", "path", "casefold-prefix"])
def test_opt_in_policy_role_and_path_are_reserved(authorized, collision):
    store, _, _, inputs, _, _, _, _, _ = authorized
    provider = inputs["candidate_provider"]

    def plan(context, attempt):
        value = provider.plan_generation(context, attempt)
        extra = _fixed_input("another-input", context["delivered_context"]["artifact"])
        if collision == "role":
            extra["role"] = "generation_feedback_policy"
        else:
            extra["materialized_path"] = ("inputs/generation-feedback-policy.json"
                                           if collision == "path" else
                                           "inputs/GENERATION-FEEDBACK-POLICY.JSON/child")
        value["spec"]["inputs"].append(extra)
        return value

    inputs["candidate_provider"] = SimpleNamespace(plan_generation=plan)
    with pytest.raises(PublicError) as error:
        prepare(authorized)
    assert (error.value.code, error.value.stage) == ("InvalidRequest", "validate")
    # Collision detection needs the provider's plan; no execution/plan commit follows.
    with sqlite3.connect(store.root / "index.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM generation_inputs WHERE role='generation-plan'",
        ).fetchone()[0] == 0
