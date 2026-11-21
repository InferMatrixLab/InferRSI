"""The production offline port over retained P1 fixtures; no evaluation worker is run."""

import json
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from itertools import count
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from inferrsi.apps import api as apps_api
from inferrsi.apps.handoff.bridge import check_assessment_identity, to_evidence
from inferrsi.apps.storage.archive import read_prepared
from inferrsi.apps.storage.artifact_reader import ArtifactReader
from inferrsi.benchmark import assessment
from inferrsi.benchmark import preparation as preparation_port
from inferrsi.contracts.json_v1 import CanonicalError, decode, encode
from inferrsi.harness.errors import PublicError
from tests.test_benchmark_preparation import preparation as preparation

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs/contracts/fixtures/t108-v4"
NOW = "2099-01-01T00:00:00Z"


def test_pure_codec_preserves_the_frozen_documentary_result(monkeypatch):
    data = (GOLDEN / "assessment.json").read_bytes()
    result = decode(data)
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("pure codec opened a file"))
    assert assessment.encode(result) == data
    assert assessment.decode(data) == result
    assessment.validate_assessment(result)
    check_assessment_identity(result)


@pytest.fixture
def retained(preparation, tmp_path):
    service, request, _, _, _, config, directory = preparation
    output = apps_api.prepare(
        {"schema_version": 1, "request": request}, workspace=tmp_path,
        storage_config=config, prepare_benchmark=service.prepare,
        encode_prepared=preparation_port.encode,
        validate_prepared=preparation_port.validate_prepared,
    )
    assert output.result["exit_code"] == 0, output.result
    prepared_ref = output.result["prepared_ref"]
    prepared = read_prepared(config, prepared_ref)
    record = decode((GOLDEN / "record-payload.json").read_bytes())
    record.update(
        prepared_ref=prepared_ref, protocol_digest=prepared["protocol_digest"],
        started=True, phase="finished", process_outcome="exited", exit_code=0,
        elapsed_seconds="1", checks=[], artifacts=[], errors=[],
        cleanup={"status": "confirmed", "process_exit_confirmed": True,
                 "termination_requested": False, "reasons": []},
    )
    record["steps"][0].update(status="exited", started_at=NOW, ended_at=NOW,
                               elapsed_seconds="1", exit_code=0, reasons=[])
    record["target_binding"] = {
        "target_id": record["target_request"]["target_id"], "config_revision": "1",
        "executor_version": "1", "control_domain": "fixture-domain", "capability_checks": [],
        "runtime_bindings_by_step": [{
            "step_id": "main", "runtime_role": "local-python", "executable": "python",
            "entrypoint": prepared["recipe"]["entrypoint"], "entrypoint_revision": "1",
            "code_sha256": prepared["recipe"]["code_sha256"], "argv": [],
            "environment_identity": None,
        }],
    }
    serial = count()

    def put(label, data):
        name = f"retained/{next(serial)}-{label}"
        path = directory / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        return {"location": "archives/local/" + name, "sha256": sha256(data).hexdigest(),
                "size_bytes": len(data), "media_type": "application/json"}

    candidate = put("candidate.txt", b"retained software-test candidate\n")
    record["bound_inputs"] = [{
        "role": "candidate", "retained_ref": candidate, "actual_sha256": candidate["sha256"],
        "snapshot_format": "file-v1", "captured_at": NOW, "attempt_id": record["attempt_id"],
        "step_ids": ["main"], "materialized_path": "inputs/candidate.txt",
        "expected_sha256": candidate["sha256"], "identity_status": "matched", "reasons": [],
    }]

    def add(key, status="passed", **changes):
        requirement = next(x for x in prepared["required_evidence"] if x["check_id"] == key)
        proof = {"schema_version": 1, "attempt_id": record["attempt_id"],
                 "operation": "evaluate", "validation_scope": "p1"}
        if key != "cleanup":
            proof.update(candidate_id=record["candidate"]["candidate_id"],
                         actual_sha256=candidate["sha256"])
        if key in {"format", "grader"}:
            proof.update(claim_id=requirement["for_claims"][0], checker_revision="1",
                         status=status, reasons=[] if status == "passed" else ["fixture_rejection"])
        elif key == "samples":
            proof["samples"] = [
                {"sample_id": name, "role": role, "round": round_, "value": "1", "unit": "ms"}
                for name, role, round_ in [("A1", "baseline", 1), ("B1", "candidate", 1),
                                           ("B2", "candidate", 2), ("A2", "baseline", 2)]
            ]
        else:
            proof["confirmed"] = True
        proof.update(changes)
        ref = put(key + ".json", encode(proof))
        kind = requirement["allowed_producer_kinds"][0]
        check = {
            **{k: requirement[k] for k in ("check_id", "checker_revision", "subject", "phase",
                                          "artifact_schema")},
            "attempt_id": record["attempt_id"], "operation": "evaluate", "validation_scope": "p1",
            "producer": {"kind": kind, "identity": "fixture_worker" if kind == "task_worker"
                         else "fixture-harness", "revision": "1",
                         "control_domain": "fixture-domain",
                         "capture_route": "retained-software-fixture"},
            "status": status, "evidence_refs": [ref], "reasons": [],
        }
        record["checks"].append(check)
        return check, proof

    for key in ("format", "grader", "samples", "cleanup"):
        add(key)

    def seal():
        ref = {"attempt_id": record["attempt_id"], "record_version": record["record_version"],
               "artifact": put("record.json", encode(record))}
        return ref, to_evidence(prepared, prepared_ref, ref, record)

    return {"prepared": prepared, "record": record, "config": config, "directory": directory,
            "put": put, "add": add, "seal": seal, "workspace": tmp_path}


def run(case, *, reader=None, clock=lambda: NOW):
    _, evidence = case["seal"]()
    result = assessment.AssessmentService(clock=clock).assess(
        case["prepared"], evidence, artifacts=reader or ArtifactReader(case["config"]),
    )
    return result


def remove(case, *keys):
    case["record"]["checks"] = [c for c in case["record"]["checks"] if c["check_id"] not in keys]


def test_all_positive_proofs_are_validated_against_captured_bytes(retained):
    result = run(retained)
    assert "code" not in result, result
    assert [c["verdict"] for c in result["claims"]] == ["PASS"] * 3
    assert result["eligibility"][0]["status"] == "eligible"
    assessment.validate_assessment(result)
    check_assessment_identity(result)
    assert assessment.decode(assessment.encode(result)) == result
    schema = json.loads((ROOT / "docs/contracts/schemas/contract-v1.schema.json").read_text(
        encoding="utf-8",
    ))
    Draft202012Validator({**schema, "$ref": "#/$defs/EvaluationResult"}).validate(result)
    _, evidence = retained["seal"]()
    Draft202012Validator({**schema, "$ref": "#/$defs/EvidenceInput"}).validate(evidence)


def test_t35_three_independent_claims_and_apps_exit_codes(retained):
    remove(retained, "grader", "samples", "cleanup")
    retained["add"]("grader", "failed")
    ref, _ = retained["seal"]()
    service = assessment.AssessmentService(clock=lambda: NOW)
    for claim, exit_code in (("F", 0), ("C", 8), ("M", 9)):
        workspace = retained["workspace"] / claim
        workspace.mkdir()
        output = apps_api.assess(
            {"schema_version": 1, "record_ref": ref,
             "primary_scope": "p1", "primary_claim_id": claim},
            workspace=workspace, storage_config=retained["config"],
            assess_benchmark=service.assess, validate_assessment=assessment.validate_assessment,
            encode_assessment=assessment.encode,
        )
        assert output.result["exit_code"] == exit_code, output.result
        assert output.result["assessment_ref"] is not None
        assert [c["verdict"] for c in output.result["assessment"]["claims"]] == [
            "PASS", "FAIL", "INCONCLUSIVE",
        ]


@pytest.mark.parametrize("kind", ["UnsafeArtifactPath", "ArtifactUnavailable",
                                  "ArtifactIntegrityError", "bad_bytes"])
def test_each_read_failure_is_only_a_claim_gap(retained, kind):
    target = retained["record"]["checks"][0]["evidence_refs"][0]
    reader = ArtifactReader(retained["config"])

    class Fault:
        def open(self, ref):
            if ref == target:
                if kind == "bad_bytes":
                    return BytesIO(b"not the retained bytes")
                raise PublicError(kind, stage="open", message="fixture rejection")
            return reader.open(ref)

    result = run(retained, reader=Fault())
    assert [c["verdict"] for c in result["claims"]] == ["INCONCLUSIVE", "PASS", "PASS"]
    assert result["claims"][0]["missing_evidence"] == ["format"]


@pytest.mark.parametrize("error", [TypeError("broken host adapter"),
                                  CanonicalError("host_adapter", "broken host adapter")],
                         ids=["type", "canonical"])
def test_host_programming_errors_are_not_disguised_as_missing_evidence(retained, error):
    class Broken:
        def open(self, ref):
            raise error

    with pytest.raises(type(error), match="broken host"):
        run(retained, reader=Broken())


@pytest.mark.parametrize("field,value", [("kind", "caller_assertion"),
                                         ("control_domain", "untrusted-domain")])
def test_untrusted_self_assertions_cannot_pass(retained, field, value):
    retained["record"]["checks"][0]["producer"][field] = value
    assert run(retained)["claims"][0]["verdict"] == "INCONCLUSIVE"


def test_proof_candidate_hash_is_not_its_own_identity_authority(retained):
    remove(retained, "format")
    retained["add"]("format", actual_sha256="0" * 64)
    assert run(retained)["claims"][0]["verdict"] == "INCONCLUSIVE"


def test_v21_conflicting_proofs_are_aggregated_once(retained):
    retained["add"]("format", "failed")
    result = run(retained)
    assert len(result["claims"]) == 3
    assert result["claims"][0]["verdict"] == "INCONCLUSIVE"
    assert "conflicting_evidence" in result["claims"][0]["reasons"]
    assert result["eligibility"][0]["status"] == "ineligible"


def test_running_snapshot_keeps_missing_terminal_evidence_inconclusive(retained):
    remove(retained, "grader", "samples", "cleanup")
    retained["record"].update(phase="running", process_outcome="unknown", exit_code=None)
    retained["record"]["cleanup"].update(status="unknown", process_exit_confirmed=None)
    before = encode(retained["record"])
    result = run(retained)
    assert [c["verdict"] for c in result["claims"]] == ["PASS", "INCONCLUSIVE", "INCONCLUSIVE"]
    assert result["claims"][1]["missing_evidence"] == ["grader"]
    assert "completed_measurement" in result["claims"][2]["missing_evidence"]
    assert encode(retained["record"]) == before


@pytest.mark.parametrize("mutation", ["order", "zero", "unit", "missing", "cleanup", "lease"])
def test_measurement_requires_complete_sampling_cleanup_and_release(retained, mutation):
    if mutation in {"order", "zero", "unit", "missing"}:
        old = next(c for c in retained["record"]["checks"] if c["check_id"] == "samples")
        with ArtifactReader(retained["config"]).open(old["evidence_refs"][0]) as stream:
            samples = decode(stream.read())["samples"]
        remove(retained, "samples")
        if mutation == "order":
            samples.reverse()
        elif mutation == "zero":
            samples[0]["value"] = "0"
        elif mutation == "unit":
            samples[0]["unit"] = "second"
        else:
            samples.pop()
        retained["add"]("samples", samples=samples)
    elif mutation == "cleanup":
        retained["record"]["cleanup"]["process_exit_confirmed"] = None
    else:
        retained["record"]["resource_leases"] = {
            "applicability": "applicable", "reasons": [], "leases": [{
                "lease_id": "lease-1", "resource_id": "cpu", "control_domain": "fixture-domain",
                "owner": "fixture", "acquired_at": NOW, "release_requested_at": NOW,
                "release_confirmed": False, "release_confirmed_at": None, "reasons": [],
            }],
        }
    assert run(retained)["claims"][2]["verdict"] == "INCONCLUSIVE"


def test_binding_mismatch_is_refused_before_any_artifact_open(retained):
    _, evidence = retained["seal"]()
    evidence["record_digest"] = "0" * 64

    class Never:
        def open(self, ref):
            pytest.fail("identity mismatch reached artifact IO")

    result = assessment.assess(retained["prepared"], evidence, artifacts=Never())
    assert result["code"] == "IdentityMismatch"
    assert result["stage"] == "assessment_binding"
    assert "assessment_id" not in result


@pytest.mark.parametrize("revision", ["grader", "claim-rule"])
def test_v22_unsupported_same_family_rule_revision_is_refused(retained, revision):
    prepared = retained["prepared"]
    reader = ArtifactReader(retained["config"])
    with reader.open(prepared["protocol"]) as stream:
        protocol = decode(stream.read())
    if revision == "grader":
        protocol["grader"]["revision"] = "2"
        prepared["grader"]["revision"] = "2"
    else:
        protocol["claim_definitions"][0]["decision_rule"]["revision"] = "2"
    prepared["protocol"] = retained["put"]("unsupported-protocol.json", encode(protocol))
    prepared["protocol_digest"] = preparation_port.protocol_digest(protocol)
    prepared["prepared_id"] = preparation_port.prepared_id(prepared)
    record = retained["record"]
    record["protocol_digest"] = prepared["protocol_digest"]
    record["prepared_ref"]["prepared_id"] = prepared["prepared_id"]
    record["prepared_ref"]["artifact"] = retained["put"](
        "unsupported-prepared.json", encode(prepared),
    )
    result = run(retained)
    assert result["code"] == "UnsupportedRuleVersion"


def test_outer_prepared_relocation_keeps_semantic_binding(retained):
    before = retained["prepared"]["prepared_id"]
    reader = ArtifactReader(retained["config"])
    ref = retained["prepared"]["protocol"]
    with reader.open(ref) as stream:
        ref["location"] = retained["put"]("relocated-protocol.json", stream.read())["location"]
    assert preparation_port.prepared_id(retained["prepared"]) == before
    retained["record"]["prepared_ref"]["artifact"] = retained["put"](
        "relocated-prepared.json", encode(retained["prepared"]),
    )
    assert all(c["verdict"] == "PASS" for c in run(retained)["claims"])


def test_v23_clock_and_typed_location_projection(retained):
    result = run(retained)
    later = run(retained, clock=lambda: "2099-01-01T00:00:01Z")
    # Each seal creates a new locator but has identical fixed payload bytes.
    assert result["assessment_id"] == later["assessment_id"]
    assert assessment.encode(result) != assessment.encode(later)
    changed = deepcopy(result)
    changed["record_ref"]["artifact"]["location"] = "elsewhere/record.json"
    check_assessment_identity(changed)
    assessment.validate_assessment(changed)
    changed["claims"][0]["verdict"] = "FAIL"
    with pytest.raises(ValueError):
        assessment.validate_assessment(changed)


def test_v23_fixed_clock_is_byte_identical_in_an_isolated_process(retained, tmp_path):
    _, evidence = retained["seal"]()
    reader = ArtifactReader(retained["config"])
    expected = assessment.AssessmentService(clock=lambda: NOW).assess(
        retained["prepared"], evidence, artifacts=reader,
    )
    blobs = {}
    for ref in expected["evidence_artifacts"]:
        with reader.open(ref) as stream:
            blobs[ref["location"]] = stream.read().hex()
    case = tmp_path / "case.json"
    case.write_bytes(encode({
        "prepared": retained["prepared"], "evidence": evidence, "blobs": blobs,
    }))
    child = """
import sys
from io import BytesIO
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from inferrsi.benchmark.assessment import AssessmentService, encode
from inferrsi.contracts.json_v1 import decode
value = decode(Path(sys.argv[2]).read_bytes())
class Reader:
    def open(self, ref):
        return BytesIO(bytes.fromhex(value['blobs'][ref['location']]))
result = AssessmentService(clock=lambda: '2099-01-01T00:00:00Z').assess(
    value['prepared'], value['evidence'], artifacts=Reader())
sys.stdout.buffer.write(encode(result))
"""
    done = subprocess.run([sys.executable, "-I", "-c", child, str(ROOT / "src"), str(case)],
                          cwd=tmp_path, capture_output=True, check=True, timeout=30)
    assert done.stdout == assessment.encode(expected)


@pytest.mark.parametrize("primary", [None, "unknown", "missing"])
def test_t39_bad_primary_is_rejected_before_the_assessor(retained, primary):
    ref, _ = retained["seal"]()

    def never(*args, **kwargs):
        pytest.fail("bad primary reached Benchmark")

    request = {"schema_version": 1, "record_ref": ref,
               "primary_scope": "p1", "primary_claim_id": primary}
    if primary == "missing":
        del request["primary_claim_id"]
    result = apps_api.assess(
        request,
        workspace=retained["workspace"], storage_config=retained["config"],
        assess_benchmark=never, validate_assessment=assessment.validate_assessment,
        encode_assessment=assessment.encode,
    ).result
    assert result["exit_code"] == 2 and result["reason_code"] == "InvalidRequest"


def test_t39_missing_known_claim_and_failed_archive(retained, monkeypatch):
    ref, _ = retained["seal"]()
    request = {"schema_version": 1, "record_ref": ref,
               "primary_scope": "p1", "primary_claim_id": "F"}
    service = assessment.AssessmentService(clock=lambda: NOW)

    def omitted(*args, **kwargs):
        result = service.assess(*args, **kwargs)
        result["claims"].pop(0)
        return result

    options = {"workspace": retained["workspace"], "storage_config": retained["config"],
               "validate_assessment": assessment.validate_assessment,
               "encode_assessment": assessment.encode}
    result = apps_api.assess(request, assess_benchmark=omitted, **options).result
    assert result["exit_code"] == 2 and result["reason_code"] == "AssessorError"
    assert result["assessment_ref"] is None

    def failed(*args, **kwargs):
        raise PublicError(
            "ArchivePersistenceError", stage="assessment_archive", message="fixture IO",
        )

    monkeypatch.setattr(apps_api, "archive_assessment", failed)
    result = apps_api.assess(request, assess_benchmark=service.assess, **options).result
    assert result["exit_code"] == 6 and result["assessment_ref"] is None
    assert result["assessment"] is not None


def test_assessment_does_not_launch_workers_or_access_the_network(retained, monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        pytest.fail("offline assessor attempted execution or network access")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    assert all(c["verdict"] == "PASS" for c in run(retained)["claims"])


@pytest.mark.parametrize("source", ["wrong-code", "foreign-check", "uncaptured", "not-started"])
def test_evidence_cannot_override_actual_runtime_and_input_capture(retained, source):
    record = retained["record"]
    if source == "wrong-code":
        record["target_binding"]["runtime_bindings_by_step"][0]["code_sha256"] = "0" * 64
        expected = ["PASS", "INCONCLUSIVE", "INCONCLUSIVE"]
    elif source == "foreign-check":
        record["checks"][0]["attempt_id"] = "foreign-attempt"
        expected = ["INCONCLUSIVE", "PASS", "PASS"]
    elif source == "uncaptured":
        record["bound_inputs"][0]["actual_sha256"] = "0" * 64
        expected = ["INCONCLUSIVE"] * 3
    else:
        record.update(started=False, process_outcome="not_started", exit_code=None)
        record["steps"][0].update(status="not_started", started_at=None, ended_at=None,
                                   exit_code=None, elapsed_seconds=None)
        expected = ["PASS", "INCONCLUSIVE", "INCONCLUSIVE"]
    assert [c["verdict"] for c in run(retained)["claims"]] == expected


def test_conflicting_measurements_are_not_first_or_last_wins(retained):
    first = next(c for c in retained["record"]["checks"] if c["check_id"] == "samples")
    with ArtifactReader(retained["config"]).open(first["evidence_refs"][0]) as stream:
        samples = decode(stream.read())["samples"]
    samples[0]["value"] = "2"
    retained["add"]("samples", samples=samples)
    result = run(retained)
    assert result["claims"][2]["verdict"] == "INCONCLUSIVE"
    assert "conflicting_evidence" in result["claims"][2]["reasons"]
    assert result["eligibility"][0]["status"] == "ineligible"


def test_typed_projection_is_independent_of_python_object_aliasing(retained):
    result = run(retained)
    shared = result["claims"][0]["evidence"][0]
    result["evidence_artifacts"].append(shared)
    result["candidate"]["context_refs"] = [shared]
    result["assessment_id"] = assessment.assessment_id(result)
    assessment.validate_assessment(result)
    check_assessment_identity(result)


@pytest.mark.parametrize("mutation", ["duplicate", "unknown-claim", "extra-field", "metric"])
def test_pure_validator_rejects_invalid_results_even_with_recomputed_identity(retained, mutation):
    result = run(retained)
    if mutation == "duplicate":
        result["claims"][1] = deepcopy(result["claims"][0])
    elif mutation == "unknown-claim":
        result["claims"][0]["claim_id"] = "unknown"
    elif mutation == "extra-field":
        result["claims"][0]["overall"] = "PASS"
    else:
        result["metrics"] = [{"raw_samples": []}]
    result["assessment_id"] = assessment.assessment_id(result)
    with pytest.raises(ValueError):
        assessment.validate_assessment(result)


def test_pure_timestamp_validation_checks_calendar_and_preserves_fractional_precision(retained):
    result = run(retained)
    result["assessed_at"] = "2099-02-29T00:00:00Z"
    with pytest.raises(ValueError):
        assessment.validate_assessment(result)
    result["assessed_at"] = "2096-02-29T00:00:00.123456789Z"
    assert assessment.decode(assessment.encode(result)) == result


@pytest.mark.parametrize("duplicate", [False, True])
def test_raw_evidence_keeps_original_bytes_and_rejects_duplicate_json_keys(retained, duplicate):
    check = retained["record"]["checks"][0]
    with ArtifactReader(retained["config"]).open(check["evidence_refs"][0]) as stream:
        proof = decode(stream.read())
    text = json.dumps(proof, indent=2)
    if duplicate:
        text = text[:-1] + ', "status": "passed"}'
    raw = text.encode("utf-8")
    check["evidence_refs"] = [retained["put"]("noncanonical-proof.json", raw)]
    result = run(retained)
    assert result["claims"][0]["verdict"] == ("INCONCLUSIVE" if duplicate else "PASS")


@pytest.mark.parametrize("character", ["\x00", "\x1f", "\x7f"])
def test_pure_codec_rejects_control_characters_in_typed_paths(retained, character):
    result = run(retained)
    result["record_ref"]["artifact"]["location"] = "invalid/" + character + "/record.json"
    with pytest.raises(ValueError):
        assessment.encode(result)


def test_host_reader_cannot_change_the_snapshotted_input_during_assessment(retained):
    _, evidence = retained["seal"]()
    reader = ArtifactReader(retained["config"])
    digest = retained["prepared"]["protocol_digest"]

    class Mutating:
        def open(self, ref):
            retained["prepared"]["protocol_digest"] = "sha256:" + "0" * 64
            evidence["record"]["phase"] = "running"
            return reader.open(ref)

    result = assessment.AssessmentService(clock=lambda: NOW).assess(
        retained["prepared"], evidence, artifacts=Mutating(),
    )
    assert result["protocol_digest"] == digest
    assert all(c["verdict"] == "PASS" for c in result["claims"])


def test_confirmed_execution_does_not_require_fabricating_unknown_clock_facts(retained):
    retained["record"]["steps"][0].update(started_at=None, ended_at=None)
    assert all(c["verdict"] == "PASS" for c in run(retained)["claims"])
    assert retained["record"]["steps"][0]["started_at"] is None


def test_invalid_prepared_resource_path_is_rejected_without_reading(retained):
    _, evidence = retained["seal"]()
    retained["prepared"]["resources"][0]["artifact"]["location"] = "invalid/\x00/resource"

    class Never:
        def open(self, ref):
            pytest.fail("invalid input reached artifact IO")

    result = assessment.assess(retained["prepared"], evidence, artifacts=Never())
    assert result["code"] == "InvalidRequest"


def test_conflicting_declared_candidate_expectation_is_a_binding_error(retained):
    prepared, record = retained["prepared"], retained["record"]
    prepared["expected_candidate"] = {
        "candidate_id": record["candidate"]["candidate_id"], "sha256": "0" * 64,
        "format_schema": deepcopy(prepared["candidate_contract"]["format_schema"]),
    }
    prepared["prepared_id"] = preparation_port.prepared_id(prepared)
    record["prepared_ref"].update(prepared_id=prepared["prepared_id"], artifact=retained["put"](
        "different-expectation.json", preparation_port.encode(prepared),
    ))
    assert run(retained)["code"] == "IdentityMismatch"
