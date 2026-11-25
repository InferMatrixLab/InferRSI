"""Pure capture-draft tests; no worker, process observation or acceptance claim."""

import json
import socket
import subprocess
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from inferrsi.benchmark import assessment, preparation, proofs
from inferrsi.contracts.json_v1 import decode, encode

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "docs/contracts/fixtures/t108-v4"


def report():
    return {
        "schema_version": 1, "grader": {"status": "passed", "reasons": []},
        "samples": [{"sample_id": name, "role": role, "round": round_, "value": "1.25",
                     "unit": "ms"} for name, role, round_ in
                    (("A1", "baseline", 1), ("B1", "candidate", 1),
                     ("B2", "candidate", 2), ("A2", "baseline", 2))],
    }


@pytest.fixture
def case():
    prepared_bytes = (GOLDEN / "prepared.json").read_bytes()
    prepared = decode(prepared_bytes)
    # Derive a new in-memory preparation; historical vector bytes are untouched.
    prepared["expected_candidate"] = None
    prepared["prepared_id"] = preparation.prepared_id(prepared)
    prepared_bytes = preparation.encode(prepared)
    protocol = (GOLDEN / "protocol.json").read_bytes()
    data = b"captured candidate\n"
    ref = {"location": "retained/candidate", "sha256": sha256(data).hexdigest(),
           "size_bytes": len(data), "media_type": "text/plain"}
    source = decode((GOLDEN / "record-payload.json").read_bytes())
    facts = {key: deepcopy(source[key]) for key in proofs.CONTEXT_FIELDS}
    facts.update(
        attempt_id="runtime-attempt-37", request_id="runtime-attempt-37", run_id="runtime-run-37",
        request_digest="sha256:" + "a" * 64,
        prepared_ref={"schema_version": 1, "prepared_id": prepared["prepared_id"],
                      "artifact": {"location": "retained/prepared",
                                   "media_type": "application/json",
                                   "sha256": sha256(prepared_bytes).hexdigest(),
                                   "size_bytes": len(prepared_bytes)}},
        protocol_digest=prepared["protocol_digest"], candidate={
            "candidate_id": "runtime-candidate-37", "kind": "text", "input_role": "candidate",
            "context_refs": [], "parent_id": None, "parent_digest": None,
        },
        bound_inputs=[{"role": "candidate", "attempt_id": "runtime-attempt-37",
                       "retained_ref": ref, "actual_sha256": ref["sha256"],
                       "captured_at": "2099-01-01T00:00:00Z", "snapshot_format": "file-v1",
                       "step_ids": ["main"]}],
        target_binding={"control_domain": "fixture-domain", "runtime_bindings_by_step": [{
            "step_id": "main", **{key: prepared["recipe"][key] for key in
                                   ("runtime_role", "entrypoint", "entrypoint_revision",
                                    "code_sha256")},
        }]},
        steps=[{"step_id": "main", "status": "exited", "started_at": "2099-01-01T00:00:00Z"}],
        started=True, process_outcome="exited", exit_code=0,
        cleanup={"status": "confirmed", "process_exit_confirmed": True},
        resource_leases={"applicability": "applicable", "leases": [{
            "release_confirmed": True, "release_confirmed_at": "2099-01-01T00:00:00Z",
        }]},
    )
    return prepared, protocol, facts, data


def project(case, phase="finalizing", value=None, **kwargs):
    prepared, protocol, facts, data = case
    if phase == "preparing":
        facts = deepcopy(facts)
        facts.update(started=False, steps=[], process_outcome=None, exit_code=None,
                     cleanup=None, resource_leases=None)
    kwargs.setdefault("candidate_bytes", data)
    kwargs.setdefault("report_bytes", proofs.encode_report(report() if value is None else value))
    return proofs.project(prepared, protocol, phase, facts, **kwargs)


def by_id(draft):
    return {check["check_id"]: check for check in draft["checks"]}


def test_report_codec_is_strict_but_preserves_input_whitespace_semantics():
    value = report()
    assert proofs.decode_report(proofs.encode_report(value)) == value
    assert proofs.decode_report(json.dumps(value, indent=2).encode()) == value
    assert proofs.encode_report(value) == encode(value)
    proofs.validate_report(value)


@pytest.mark.parametrize("phase", ["preparing", "finalizing"])
def test_drafts_use_runtime_identity_and_existing_proof_schemas(case, phase):
    prepared, _, facts, data = case
    draft, blobs = project(case, phase)
    assert draft["schema_version"] == 1 and draft["errors"] == []
    assert set(blobs) == ({"format"} if phase == "preparing" else {"grader", "samples", "cleanup"})
    required = {x["check_id"]: x for x in prepared["required_evidence"]}
    for check in draft["checks"]:
        assert "producer" not in check and "attempt_id" not in check
        assert "evidence_refs" not in check and "artifact" not in check
        raw = blobs[check["proof_key"]]
        proof = assessment._proof(raw, required[check["check_id"]], facts, sha256(data).hexdigest())
        assert proof["attempt_id"] == "runtime-attempt-37"
        if check["check_id"] != "cleanup":
            assert proof["candidate_id"] == "runtime-candidate-37"
        assert check["status"] == "passed"


@pytest.mark.parametrize("raw,code", [
    (b"{}", "InvalidRequest"),
    (b'{"schema_version":1,"grader":null,"samples":null,"grader":null}', "InvalidRequest"),
    (b'{"schema_version":2,"grader":null,"samples":null}', "UnsupportedSchema"),
    (b'{"schema_version":true,"grader":null,"samples":null}', "UnsupportedSchema"),
    (b'{"schema_version":1.0,"grader":null,"samples":null}', "InvalidRequest"),
    (b'{"schema_version":1,"grader":NaN,"samples":null}', "InvalidRequest"),
    (b'{"schema_version":1,"grader":"\\ud800","samples":null}', "InvalidRequest"),
    (b"\xff", "InvalidRequest"),
])
def test_bad_report_envelopes_refuse_without_fabricating_proofs(case, raw, code):
    with pytest.raises(proofs.ProofError) as caught:
        proofs.decode_report(raw)
    assert caught.value.code == code
    draft, blobs = project(case, report_bytes=raw)
    assert by_id(draft)["grader"]["status"] == by_id(draft)["samples"]["status"] == "not_performed"
    assert set(blobs) == {"cleanup"}
    assert {x["code"] for x in draft["errors"]} == {code}


@pytest.mark.parametrize("extra", ["producer", "control_domain", "cleanup", "attempt_id",
                                   "candidate_id", "actual_sha256", "record_ref"])
def test_worker_cannot_supply_producer_identity_cleanup_or_references(case, extra):
    value = report()
    value[extra] = "forged"
    draft, blobs = project(case, report_bytes=encode(value))
    assert set(blobs) == {"cleanup"}
    assert all(by_id(draft)[key]["status"] == "not_performed" for key in ("grader", "samples"))
    assert decode(blobs["cleanup"])["confirmed"] is True


@pytest.mark.parametrize("change", ["reversed", "duplicate", "float", "zero", "negative",
                                    "noncanonical", "unit", "bool-round", "wrong-role",
                                    "unknown-field", "missing", "null-item"])
def test_invalid_samples_do_not_hide_an_independent_grader_result(case, change):
    value = report()
    sample = value["samples"][0]
    if change == "reversed":
        value["samples"].reverse()
    elif change == "duplicate":
        value["samples"][1] = deepcopy(sample)
    elif change == "float":
        sample["value"] = 1.25
    elif change == "zero":
        sample["value"] = "0"
    elif change == "negative":
        sample["value"] = "-1"
    elif change == "noncanonical":
        sample["value"] = "1.0"
    elif change == "unit":
        sample["unit"] = "seconds"
    elif change == "bool-round":
        sample["round"] = True
    elif change == "wrong-role":
        sample["role"] = "candidate"
    elif change == "unknown-field":
        sample["producer"] = "forged"
    elif change == "missing":
        value["samples"].pop()
    else:
        value["samples"][0] = None
    raw = json.dumps(value).encode()
    draft, blobs = project(case, report_bytes=raw)
    if change == "float":
        # A forbidden JSON numeric token invalidates the raw envelope itself.
        assert set(blobs) == {"cleanup"}
    else:
        assert set(blobs) == {"grader", "cleanup"}
        assert by_id(draft)["grader"]["status"] == "passed"
    assert by_id(draft)["samples"]["status"] == "not_performed"
    with pytest.raises(proofs.ProofError):
        proofs.decode_report(raw)


@pytest.mark.parametrize("grader", [{"status": "unknown", "reasons": []},
                                    {"status": "passed", "reasons": [None]}, None])
def test_bad_or_incomplete_grader_keeps_valid_samples_and_cleanup(case, grader):
    value = report()
    value["grader"] = grader
    draft, blobs = project(case, report_bytes=encode(value))
    assert set(blobs) == {"samples", "cleanup"}
    assert by_id(draft)["grader"]["status"] == "not_performed"
    assert by_id(draft)["samples"]["status"] == "passed"


@pytest.mark.parametrize("missing", [("grader",), ("samples",), ("grader", "samples")])
def test_explicit_null_families_emit_diagnostics_without_losing_valid_siblings(case, missing):
    value = report()
    for field in missing:
        value[field] = None
    raw = proofs.encode_report(value)
    assert proofs.decode_report(raw) == value

    _, complete_blobs = project(case)
    draft, blobs = project(case, report_bytes=raw)
    assert set(blobs) == {"grader", "samples", "cleanup"} - set(missing)
    for field in missing:
        check = by_id(draft)[field]
        assert check["status"] == "not_performed" and check["proof_key"] is None
        assert check["reasons"] == ["report_family_incomplete"]
    assert {tuple(error["check_ids"]): (error["code"], error["reason"])
            for error in draft["errors"]} == {
                (field,): ("InvalidRequest", "report_family_incomplete") for field in missing
            }
    assert all(raw == complete_blobs[field] for field, raw in blobs.items())


def test_independent_failed_grade_is_not_rewritten_or_overlaid(case):
    value = report()
    value.update(grader={"status": "failed", "reasons": ["actual_grader_rejection"]}, samples=None)
    draft, blobs = project(case, value=value)
    assert by_id(draft)["grader"]["status"] == "failed"
    assert decode(blobs["grader"])["reasons"] == ["actual_grader_rejection"]
    assert by_id(draft)["samples"]["status"] == "not_performed"
    assert draft["errors"] == [{"code": "InvalidRequest", "check_ids": ["samples"],
                                "reason": "report_family_incomplete"}]


@pytest.mark.parametrize("change", ["not-started", "entry-digest", "entry-name", "input-step",
                                    "no-start-time", "bad-runtime-step"])
def test_a_report_without_an_actual_bound_worker_is_not_trusted(case, change):
    facts = case[2]
    runtime = facts["target_binding"]["runtime_bindings_by_step"][0]
    if change == "not-started":
        facts["started"] = False
    elif change == "entry-digest":
        runtime["code_sha256"] = "b" * 64
    elif change == "entry-name":
        runtime["entrypoint"] = "other_worker"
    elif change == "input-step":
        facts["bound_inputs"][0]["step_ids"] = ["other"]
    elif change == "no-start-time":
        facts["steps"][0]["started_at"] = None
    else:
        runtime["step_id"] = {}
    draft, blobs = project(case)
    assert set(blobs) == {"cleanup"}
    assert {x["code"] for x in draft["errors"]} == {"IdentityMismatch"}


@pytest.mark.parametrize("change", ["attempt", "prepared", "protocol", "scope", "actual-sha",
                                    "ref-sha", "ref-size", "capture-time", "duplicate-input"])
def test_foreign_or_corrupt_capture_context_refuses(case, change):
    facts = case[2]
    bound = facts["bound_inputs"][0]
    if change == "attempt":
        bound["attempt_id"] = "foreign-attempt"
    elif change == "prepared":
        facts["prepared_ref"]["prepared_id"] = "sha256:" + "b" * 64
    elif change == "protocol":
        facts["protocol_digest"] = "sha256:" + "b" * 64
    elif change == "scope":
        facts["validation_scope"] = "foreign"
    elif change == "actual-sha":
        bound["actual_sha256"] = "b" * 64
    elif change == "ref-sha":
        bound["retained_ref"]["sha256"] = "b" * 64
    elif change == "ref-size":
        bound["retained_ref"]["size_bytes"] += 1
    elif change == "capture-time":
        bound["captured_at"] = "not-a-time"
    else:
        facts["bound_inputs"].append(deepcopy(bound))
    with pytest.raises(proofs.ProofError) as error:
        project(case)
    assert error.value.code == "IdentityMismatch"


@pytest.mark.parametrize("phase", ["preparing", "finalizing"])
def test_unsupported_actual_control_domain_refuses_each_affected_check(case, phase):
    case[2]["target_binding"]["control_domain"] = "foreign-domain"
    draft, blobs = project(case, phase)
    assert blobs == {} and all(x["status"] == "not_performed" for x in draft["checks"])
    assert {x["code"] for x in draft["errors"]} == {"IdentityMismatch"}


@pytest.mark.parametrize("status,confirmed", [("confirmed", True), ("failed", False),
                                             ("unknown", False)])
def test_cleanup_proof_comes_from_controller_facts(case, status, confirmed):
    case[2]["cleanup"]["status"] = status
    draft, blobs = project(case)
    assert decode(blobs["cleanup"])["confirmed"] is confirmed
    assert by_id(draft)["cleanup"]["status"] == ("passed" if confirmed else "failed")


@pytest.mark.parametrize("change", ["release", "release-time", "process-exit", "unobserved"])
def test_unknown_or_incomplete_cleanup_is_never_confirmed(case, change):
    facts = case[2]
    if change == "release":
        facts["resource_leases"]["leases"][0]["release_confirmed"] = False
    elif change == "release-time":
        facts["resource_leases"]["leases"][0]["release_confirmed_at"] = None
    elif change == "process-exit":
        facts["cleanup"]["process_exit_confirmed"] = None
    else:
        facts["cleanup"] = None
    draft, blobs = project(case)
    if change == "unobserved":
        assert by_id(draft)["cleanup"]["status"] == "not_performed" and "cleanup" not in blobs
    else:
        assert decode(blobs["cleanup"])["confirmed"] is False


def test_format_validation_reads_actual_bytes_and_can_fail_without_a_worker(case):
    bad = b"\xff"
    case[2]["bound_inputs"][0].update(actual_sha256=sha256(bad).hexdigest())
    case[2]["bound_inputs"][0]["retained_ref"].update(sha256=sha256(bad).hexdigest(), size_bytes=1)
    case[2].update(started=False, steps=[], process_outcome=None, exit_code=None,
                   cleanup=None, resource_leases=None)
    draft, blobs = project(case, "preparing", candidate_bytes=bad, report_bytes=None)
    assert by_id(draft)["format"]["status"] == "failed"
    assert decode(blobs["format"])["reasons"] == ["invalid_utf8"]
    assert draft["errors"] == []


@pytest.mark.parametrize("phase", ["preparing", "finalizing"])
def test_missing_candidate_bytes_does_not_invent_a_positive_proof(case, phase):
    draft, blobs = project(case, phase, candidate_bytes=None)
    assert set(blobs) == (set() if phase == "preparing" else {"cleanup"})
    assert all(x["status"] == "not_performed" for x in draft["checks"]
               if x["check_id"] != "cleanup")


def test_configuration_and_drafts_are_snapshotted_and_projection_is_pure(case, monkeypatch):
    prepared, protocol, facts, data = case
    frozen = deepcopy((prepared, facts))
    projector = proofs.ProofProjector(prepared, protocol)
    prepared["required_evidence"].clear()

    def forbidden(*args, **kwargs):
        pytest.fail("pure proof projection performed host I/O or execution")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    kwargs = {"candidate_bytes": data, "report_bytes": proofs.encode_report(report())}
    first = projector.project("finalizing", facts, **kwargs)
    clean = deepcopy(first)
    first[0]["checks"][0]["artifact_schema"]["revision"] = "99"
    first[1]["grader"] = b"mutated"
    assert projector.project("finalizing", facts, **kwargs) == clean
    assert facts == frozen[1]


@pytest.mark.parametrize("field", ["schema_version", "operation", "validation_scope", "grader"])
def test_unsupported_frozen_configuration_refuses_before_projection(case, field):
    prepared, protocol, _, _ = case
    if field == "schema_version":
        prepared[field] = 2
    elif field == "grader":
        prepared[field]["revision"] = "2"
    else:
        prepared[field] = "other"
    with pytest.raises(proofs.ProofError):
        proofs.ProofProjector(prepared, protocol)


@pytest.mark.parametrize("argument", ["candidate_bytes", "report_bytes"])
def test_unknown_host_content_types_propagate_as_programming_errors(case, argument):
    with pytest.raises(TypeError):
        project(case, **{argument: object()})


@pytest.mark.parametrize("key", ["started", "process_outcome", "exit_code", "cleanup",
                                 "resource_leases"])
def test_a_late_context_cannot_be_relabelled_as_preparing(case, key):
    prepared, protocol, facts, data = case
    value = deepcopy(facts[key])
    facts.update(started=False, process_outcome=None, exit_code=None, cleanup=None,
                 resource_leases=None)
    facts[key] = value
    with pytest.raises(proofs.ProofError) as caught:
        proofs.project(prepared, protocol, "preparing", facts,
                       candidate_bytes=data, report_bytes=None)
    assert caught.value.code == "IdentityMismatch"


def test_a_frozen_expected_candidate_is_enforced(case):
    prepared, protocol, facts, data = case
    prepared["expected_candidate"] = {
        "candidate_id": facts["candidate"]["candidate_id"],
        "format_schema": {"name": "utf8-text", "revision": "1"},
        "sha256": sha256(data).hexdigest(),
    }
    prepared["prepared_id"] = preparation.prepared_id(prepared)
    facts["prepared_ref"]["prepared_id"] = prepared["prepared_id"]
    frozen_bytes = preparation.encode(prepared)
    facts["prepared_ref"]["artifact"].update(
        sha256=sha256(frozen_bytes).hexdigest(), size_bytes=len(frozen_bytes),
    )
    projector = proofs.ProofProjector(prepared, protocol)
    projector.project("finalizing", facts, candidate_bytes=data, report_bytes=encode(report()))
    facts["candidate"]["candidate_id"] = "foreign-candidate"
    with pytest.raises(proofs.ProofError) as caught:
        projector.project("finalizing", facts, candidate_bytes=data, report_bytes=encode(report()))
    assert caught.value.code == "IdentityMismatch"
