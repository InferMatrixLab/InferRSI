"""Apps assembles and reads offline assessments from fixed records."""

import json
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pytest

from inferrsi.apps.api import EvaluationPort, read_attempt_view
from inferrsi.apps.api import assess as run_assess
from inferrsi.apps.cli import main
from inferrsi.apps.storage import archive
from inferrsi.apps.storage.artifact_reader import ArtifactReader
from inferrsi.apps.views.dashboard_live import DashboardServer
from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness.errors import PublicError
from inferrsi.harness.run_store import RunStore

_FIXTURES = Path(__file__).resolve().parents[2] / "docs/contracts/fixtures/t108-v4"


def _fixture(name):
    return decode((_FIXTURES / f"{name}.json").read_bytes())


@pytest.fixture
def offline(tmp_path):
    directory = tmp_path / "export"
    directory.mkdir()
    for name in ("record-payload.json", "prepared.json", "protocol.json"):
        (directory / name).write_bytes((_FIXTURES / name).read_bytes())
    config = _fixture("storage-config")
    config["mounts"][0]["root"] = str(directory)
    config["mounts"][1]["root"] = str(tmp_path / "unused-store")
    return _fixture("apps-assess-request"), config, directory


def _validate_assessment(assessment):
    for claim in assessment["claims"]:
        if claim["verdict"] not in {"PASS", "FAIL", "INCONCLUSIVE"}:
            raise ValueError("invalid verdict")


def assess(request, **options):
    options.setdefault("encode_assessment", encode)
    return run_assess(request, validate_assessment=_validate_assessment, **options)


def _never_assess(*args, **kwargs):
    pytest.fail("the assessor must not be called")


def _golden_assessor(prepared, evidence, *, artifacts):
    assert prepared == _fixture("prepared")
    assert evidence == _fixture("evidence-input")
    with artifacts.open(prepared["protocol"]) as stream:
        assert stream.read() == (_FIXTURES / "protocol.json").read_bytes()
    return _fixture("assessment")


def _sign_assessment(assessment):
    projection = deepcopy(assessment)
    del projection["assessment_id"], projection["assessed_at"]
    for field in ("prepared_ref", "record_ref"):
        del projection[field]["artifact"]["location"]
    assessment["assessment_id"] = "sha256:" + sha256(encode(projection)).hexdigest()


def _write_export(directory, name, data):
    (directory / name).write_bytes(data)
    return {
        "location": f"fixtures/{name}", "media_type": "application/json",
        "sha256": sha256(data).hexdigest(), "size_bytes": len(data),
    }


def _loop_port(config, *, assess_benchmark=_golden_assessor):
    return EvaluationPort(
        storage_config=config, output_root_for=lambda attempt_id: f"evaluation/{attempt_id}",
        assess_benchmark=assess_benchmark, validate_assessment=_validate_assessment,
        encode_assessment=encode,
    )


def _loop_receipt(request):
    return {
        **_fixture("record-payload"), "record_ref": request["record_ref"],
        "observed_at": "2026-01-01T00:00:00Z", "controller_observation": {"status": "unknown"},
    }


def test_loop_binds_the_original_attempt_and_requires_the_frozen_scope(offline):
    _, config, _ = offline
    golden = _fixture("execution-spec")
    attempt = {key: golden[key] for key in (
        "request_id", "run_id", "attempt_id", "owner", "target_request", "deadline_utc",
        "resources", "budget", "retry_of", "retry_reason",
    )}
    proposal = {key: golden[key] for key in ("candidate", "inputs", "generation_record_ref")}
    port = _loop_port(config, assess_benchmark=_never_assess)

    spec = port.execution_for(golden["prepared_ref"], proposal, attempt, scope="p1")
    assert {key: spec[key] for key in attempt} == attempt
    assert spec["output_root"] == f"evaluation/{attempt['attempt_id']}"
    assert spec["steps"][0]["expected_code_sha256"] == _fixture("prepared")["recipe"]["code_sha256"]
    assert spec["steps"][0]["timeout_seconds"] is None
    with pytest.raises(PublicError, match="IdentityMismatch"):
        port.execution_for(golden["prepared_ref"], proposal, attempt, scope="final")


def test_loop_assessment_returns_the_archived_summary_for_all_claims(offline):
    request, config, directory = offline
    before = set(directory.iterdir())
    summary = _loop_port(config).assess(_loop_receipt(request))
    saved = archive.read_assessment(config, summary["assessment_ref"])
    fields = ("candidate", "attempt_id", "protocol_digest", "claims", "metrics",
              "eligibility", "comparison")
    assert summary == {
        **{key: saved[key] for key in fields}, "evidence": saved["evidence_artifacts"],
        "assessment_ref": summary["assessment_ref"],
    }
    assert saved == _fixture("assessment")
    assert set(directory.iterdir()) - before == {
        directory / Path(summary["assessment_ref"]["artifact"]["location"]).parent.name
    }


def test_loop_rejects_changed_receipt_before_assessing(offline):
    request, config, _ = offline
    receipt = _loop_receipt(request)
    receipt["phase"] = "running"
    with pytest.raises(PublicError) as caught:
        _loop_port(config, assess_benchmark=_never_assess).assess(receipt)
    assert (caught.value.code, caught.value.stage) == ("IdentityMismatch", "assessment_binding")


@pytest.mark.parametrize("raises", (True, False), ids=("raised", "returned"))
def test_loop_propagates_benchmark_rejection_without_archiving(offline, raises):
    request, config, directory = offline
    before = set(directory.iterdir())
    rejection = PublicError(
        "UnsupportedRuleVersion", stage="assess", message="Unsupported frozen rule revision.",
        attempt_id=request["record_ref"]["attempt_id"], field_errors=["claim_definitions[0]"],
    )

    def reject(prepared, evidence, *, artifacts):
        if raises:
            raise rejection
        return rejection.to_json()

    with pytest.raises(PublicError) as caught:
        _loop_port(config, assess_benchmark=reject).assess(_loop_receipt(request))

    assert caught.value.to_json() == rejection.to_json()
    assert set(directory.iterdir()) == before


def test_loop_archive_failure_does_not_return_an_assessment_ref(offline, monkeypatch):
    request, config, _ = offline

    def fail(*args, **kwargs):
        raise PublicError(
            "ArchivePersistenceError", stage="assessment_archive", message="archive failed",
        )

    monkeypatch.setattr("inferrsi.apps.api.archive_assessment", fail)
    with pytest.raises(PublicError) as caught:
        _loop_port(config).assess(_loop_receipt(request))
    assert (caught.value.code, caught.value.stage) == (
        "ArchivePersistenceError", "assessment_archive",
    )


@pytest.mark.parametrize(("primary", "exit_code"), [("F", 0), ("C", 8), ("M", 9)])
def test_primary_claim_controls_exit_without_dropping_other_claims(tmp_path, offline, primary,
                                                               exit_code):
    request, config, _ = offline
    request["primary_claim_id"] = primary
    decision = _fixture("assessment")
    decision["claims"][0]["verdict"] = "PASS"
    decision["claims"][1]["verdict"] = "FAIL"
    _sign_assessment(decision)

    def assessor(prepared, evidence, *, artifacts):
        _golden_assessor(prepared, evidence, artifacts=artifacts)
        return decision

    output = assess(request, workspace=tmp_path, storage_config=config,
                    assess_benchmark=assessor, output_id="offline")

    assert output.result["exit_code"] == exit_code
    assert output.result["assessment"] == decision
    assert output.result["record_ref"] == request["record_ref"]
    assert output.result["execution"] is None
    assert archive.read_result(tmp_path, "offline").result == output.result
    ref = output.result["assessment_ref"]
    assert archive.read_assessment(config, ref) == decision
    with ArtifactReader(config).open(ref["artifact"]) as stream:
        assert stream.read() == encode(decision)


@pytest.mark.parametrize(("field", "value"), [("primary_claim_id", "other"),
                                             ("primary_scope", "other")])
def test_unknown_primary_claim_does_not_invoke_assessor(tmp_path, offline, field, value):
    request, config, directory = offline
    request[field] = value
    output = assess(request, workspace=tmp_path, storage_config=config,
                    assess_benchmark=_never_assess)
    assert output.result["exit_code"] == 2
    assert output.result["error"]["code"] == "InvalidRequest"
    assert output.result["error"]["stage"] == "primary_claim"
    assert not list(directory.glob("*/assessment.json"))


@pytest.mark.parametrize("fault", [
    "omitted_claim", "omitted_non_primary_claim", "duplicate_claim", "reordered_claims",
    "identity", "foreign_error",
    "invalid_verdict", "encoding",
])
def test_invalid_assessor_response_does_not_create_archive(tmp_path, offline, fault):
    request, config, directory = offline
    decision = _fixture("assessment")
    if fault == "omitted_claim":
        del decision["claims"][1]
        _sign_assessment(decision)
    elif fault == "omitted_non_primary_claim":
        del decision["claims"][0]
        _sign_assessment(decision)
    elif fault == "duplicate_claim":
        decision["claims"].append(decision["claims"][0])
        _sign_assessment(decision)
    elif fault == "reordered_claims":
        decision["claims"].reverse()
        _sign_assessment(decision)
    elif fault == "identity":
        decision["assessment_id"] = "sha256:" + "0" * 64
    elif fault == "invalid_verdict":
        decision["claims"][0]["verdict"] = "other"
        _sign_assessment(decision)

    def assessor(*args, **kwargs):
        if fault == "foreign_error":
            raise PublicError("AssessorError", stage="assess", message="test", attempt_id="foreign")
        return decision

    encoder = (lambda assessment: b"{}") if fault == "encoding" else encode
    output = assess(request, workspace=tmp_path, storage_config=config,
                    assess_benchmark=assessor, encode_assessment=encoder)
    assert output.result["exit_code"] == 2
    assert output.result["error"]["code"] == "AssessorError"
    assert output.result["error"]["stage"] == "assessor_response_validation"
    assert output.result["assessment_ref"] is None
    assert not list(directory.glob("*/assessment.json"))


def test_assessor_cannot_read_unrelated_or_foreign_attempt_artifacts(tmp_path, offline):
    request, config, directory = offline
    record = _fixture("record-payload")
    present = _write_export(directory, "retained.json", b"{}")
    foreign = _write_export(directory, "foreign.json", b"{}")
    unrelated = _write_export(directory, "unrelated.json", b"{}")
    missing = {**present, "location": "fixtures/missing.json"}
    record["checks"][0]["evidence_refs"] = [present, missing]
    record["checks"].append({
        **record["checks"][0], "attempt_id": "other", "evidence_refs": [foreign],
    })
    request["record_ref"]["artifact"] = _write_export(
        directory, "record-payload.json", encode(record),
    )

    def assessor(prepared, evidence, *, artifacts):
        assert evidence["record"] == record
        with artifacts.open(present) as stream:
            assert stream.read() == b"{}"
        for ref in (missing, foreign, unrelated):
            with pytest.raises(PublicError, match="ArtifactUnavailable"):
                artifacts.open(ref)
        decision = _fixture("assessment")
        decision["record_ref"] = evidence["record_ref"]
        _sign_assessment(decision)
        return decision

    output = assess(request, workspace=tmp_path, storage_config=config, assess_benchmark=assessor)
    assert output.result["exit_code"] == 9
    assert output.result["assessment_ref"] is not None


def test_wrong_record_version_is_rejected_before_assessing(tmp_path, offline):
    request, config, _ = offline
    request["record_ref"]["record_version"] += 1
    output = assess(request, workspace=tmp_path, storage_config=config,
                    assess_benchmark=_never_assess)
    assert output.result["error"]["code"] == "IdentityMismatch"
    assert output.result["assessment"] is None


def test_assessor_programming_error_reaches_the_host(tmp_path, offline):
    request, config, directory = offline

    def broken_assessor(*args, **kwargs):
        raise TypeError("fixture programming error")

    with pytest.raises(TypeError, match="fixture programming error"):
        assess(request, workspace=tmp_path, storage_config=config, assess_benchmark=broken_assessor)
    assert not list(directory.glob("*/assessment.json"))


def test_read_assessment_rejects_the_wrong_identity_even_if_bytes_match(offline):
    _, config, directory = offline
    data = (_FIXTURES / "assessment.json").read_bytes()
    ref = _fixture("fixed-refs")["assessment_ref"]
    ref["artifact"] = _write_export(directory, "assessment.json", data)
    ref["assessment_id"] = "sha256:" + "0" * 64
    with pytest.raises(PublicError, match="IdentityMismatch"):
        archive.read_assessment(config, ref)


def test_fixed_attempt_view_keeps_process_facts_and_claim_outcomes_separate(offline):
    request, config, directory = offline
    record_ref = request["record_ref"]
    record = _fixture("record-payload")
    ref = _fixture("fixed-refs")["assessment_ref"]
    ref["artifact"] = _write_export(directory, "assessment.json", encode(_fixture("assessment")))

    assert read_attempt_view(record_ref, storage_config=config)["assessment"] is None
    view = read_attempt_view(record_ref, storage_config=config, assessment_ref=ref)
    assert view["record_ref"] == record_ref
    assert view["assessment_ref"] == ref
    assert view["execution"] == {
        **{key: record[key] for key in (
            "run_id", "attempt_id", "record_version", "phase", "started", "side_effect_unknown",
            "process_outcome", "exit_code", "recorded_at", "prepared_ref",
            "generation_record_ref",
        )},
        "candidate_id": record["candidate"]["candidate_id"],
        "cleanup_status": record["cleanup"]["status"],
    }
    assert [(c["claim_id"], c["validation_scope"], c["verdict"])
            for c in view["assessment"]["claims"]] == [
        (c["claim_id"], c["validation_scope"], c["verdict"])
        for c in _fixture("assessment")["claims"]
    ]
    assert view["assessment"]["claims"][0]["missing_evidence"] == ["format"]
    view["record_ref"]["record_version"] = 42
    assert record_ref["record_version"] == 1


def test_fixed_attempt_view_rejects_a_swapped_record_identity(offline):
    request, config, _ = offline
    ref = {**request["record_ref"], "record_version": 2}
    with pytest.raises(PublicError, match="IdentityMismatch"):
        read_attempt_view(ref, storage_config=config)


def test_fixed_attempt_view_rejects_an_assessment_of_another_revision(offline):
    request, config, directory = offline
    decision = _fixture("assessment")
    decision["record_ref"]["record_version"] = 2
    _sign_assessment(decision)
    ref = {
        "assessment_id": decision["assessment_id"], "schema_version": 1,
        "artifact": _write_export(directory, "assessment.json", encode(decision)),
    }
    with pytest.raises(PublicError, match="IdentityMismatch"):
        read_attempt_view(request["record_ref"], storage_config=config, assessment_ref=ref)


def test_fixed_attempt_view_rechecks_assessment_semantic_identity(offline):
    request, config, directory = offline
    decision = _fixture("assessment")
    decision["claims"][0]["verdict"] = "PASS"
    ref = {
        "assessment_id": decision["assessment_id"], "schema_version": 1,
        "artifact": _write_export(directory, "assessment.json", encode(decision)),
    }
    with pytest.raises(PublicError, match="ArtifactIntegrityError"):
        read_attempt_view(request["record_ref"], storage_config=config, assessment_ref=ref)


def test_fixed_surfaces_read_the_same_record_and_assessment(tmp_path, offline, capsys):
    request, config, directory = offline
    record_ref = request["record_ref"]
    assessment_ref = _fixture("fixed-refs")["assessment_ref"]
    assessment_ref["artifact"] = _write_export(
        directory, "assessment.json", encode(_fixture("assessment")),
    )
    flags = []
    for name, value in (
        ("record-ref", record_ref), ("storage-config", config), ("assessment-ref", assessment_ref),
    ):
        path = tmp_path / f"{name}.json"
        path.write_bytes(encode(value))
        flags.extend((f"--{name}", str(path)))
    assert main(["status", *flags]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status == read_attempt_view(
        record_ref, storage_config=config, assessment_ref=assessment_ref,
    )
    assert main(["trace", *flags]) == 0
    fixed = json.loads(capsys.readouterr().out)
    assert fixed == read_attempt_view(
        record_ref, storage_config=config, assessment_ref=assessment_ref, include_trace=True,
    )
    assert {key: fixed[key] for key in status} == status
    assert fixed["trace"]["steps"][0]["started_at"] is None
    assert fixed["trace"]["checks"][0]["check_id"] == "input_identity"
    assert fixed["trace"]["errors"][0] == {
        "code": "capacity_unavailable", "stage": "admission", "retryable": False,
    }
    reports = {}
    for command in ("report", "dashboard"):
        output = tmp_path / f"{command}.html"
        assert main([command, *flags, "--output", str(output)]) == 0
        assert json.loads(capsys.readouterr().out) == {command: str(output.resolve())}
        document = output.read_text(encoding="utf-8")
        assert record_ref["artifact"]["sha256"] in document
        assert assessment_ref["artifact"]["sha256"] in document
        assert "input_identity" in document
        assert "INCONCLUSIVE" in document
        assert "documentation fixture; not actual execution" not in document
        reports[command] = document
    with DashboardServer(None, None, 0, fixed_attempt=fixed) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(f"{url}/api/state", timeout=5) as response:
                assert json.load(response)["data"]["fixed_attempt"] == fixed
            with urlopen(f"{url}/", timeout=5) as response:
                assert response.read().decode("utf-8") == reports["dashboard"]
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.mark.parametrize(("args", "message"), [
    (["--record-ref", "record.json"], "--record-ref requires --storage-config"),
    (["--run-id", "legacy", "--storage-config", "storage.json"], "require --record-ref"),
    (["--run-id", "legacy", "--record-ref", "record.json"], "not allowed with argument"),
])
def test_fixed_status_requires_its_own_flag_combination(args, message, capsys):
    with pytest.raises(SystemExit) as error:
        main(["status", *args])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err


def test_new_process_reassesses_the_requested_sqlite_revision(tmp_path, offline):
    request, config, _ = offline
    store = RunStore(config["mounts"][1]["root"], config["harness_namespace"])
    spec = _fixture("execution-spec")
    attempt = {field: spec[field] for field in (
        "request_id", "run_id", "attempt_id", "owner", "target_request", "deadline_utc",
        "resources", "budget", "retry_of", "retry_reason",
    )}
    payload = _fixture("record-payload")
    with store.claim(attempt, payload["request_digest"]) as claim:
        first = claim.commit({**payload, "phase": "running", "started": True,
                              "process_outcome": None})
        latest = claim.commit({**payload, "record_version": 2})
    request["record_ref"] = first.record_ref
    decision = _fixture("assessment")
    decision["record_ref"] = first.record_ref
    _sign_assessment(decision)
    receipt = store.read(attempt["attempt_id"], record_version=first.record_ref["record_version"])
    (tmp_path / "offline.json").write_bytes(encode([request, config, decision, receipt]))

    subprocess.run(
        [sys.executable, "-c", """
from pathlib import Path
from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.apps.api import EvaluationPort, assess as run_assess, read_attempt_view
from inferrsi.apps.storage.archive import read_assessment

workspace = Path.cwd()
request, config, decision, receipt = decode((workspace / 'offline.json').read_bytes())

def assessor(prepared, evidence, *, artifacts):
    assert evidence['record_ref'] == request['record_ref']
    assert evidence['record']['phase'] == 'running'
    return decision

output = run_assess(request, workspace=workspace, storage_config=config,
                    assess_benchmark=assessor, validate_assessment=lambda value: None,
                    encode_assessment=encode,
                    output_id='reassessed')
assert output.result['exit_code'] == 9
view = read_attempt_view(request['record_ref'], storage_config=config,
                         assessment_ref=output.result['assessment_ref'], include_trace=True)
assert view['execution']['record_version'] == 1
assert view['execution']['phase'] == 'running'
assert view['assessment']['claims'][0]['verdict'] == 'INCONCLUSIVE'
assert view['trace']['checks'][0]['check_id'] == 'input_identity'
port = EvaluationPort(storage_config=config, output_root_for=lambda attempt: attempt,
                      assess_benchmark=assessor, validate_assessment=lambda value: None,
                      encode_assessment=encode)
summary = port.assess(receipt)
assert summary['claims'] == decision['claims']
assert read_assessment(config, summary['assessment_ref']) == decision
"""],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    result = archive.read_result(tmp_path, "reassessed").result
    assert result["record_ref"] == first.record_ref
    assert store.read(attempt["attempt_id"])["record_ref"] == latest.record_ref


@pytest.mark.parametrize("stage", ["assessment_archive", "output_publication"])
def test_publication_failure_preserves_only_committed_references(tmp_path, offline, monkeypatch,
                                                                stage):
    request, config, directory = offline
    destination_root = directory if stage == "assessment_archive" else tmp_path / "output"
    original_publish = archive._publish_directory

    def fail_at_stage(staging, destination):
        if destination.parent == destination_root:
            raise OSError("test failure")
        original_publish(staging, destination)

    monkeypatch.setattr(archive, "_publish_directory", fail_at_stage)
    output = assess(request, workspace=tmp_path, storage_config=config,
                    assess_benchmark=_golden_assessor, output_id="offline")
    result = output.result
    assert result["exit_code"] == 6
    assert result["error"]["code"] == "ArchivePersistenceError"
    assert result["error"]["stage"] == stage
    assert result["assessment"] == _fixture("assessment")
    assert result["record_ref"] == request["record_ref"]
    if stage == "assessment_archive":
        assert result["assessment_ref"] is None
        assert archive.read_result(tmp_path, "offline").result == result
    else:
        assert output.directory is None
        with ArtifactReader(config).open(result["assessment_ref"]["artifact"]) as stream:
            assert stream.read() == (_FIXTURES / "assessment.json").read_bytes()
