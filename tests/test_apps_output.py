"""Apps output publication and replay through the v1 Harness port."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from threading import Barrier

import pytest

from inferrsi._json_v1 import decode, encode
from inferrsi.apps import archive
from inferrsi.apps.api import execute
from inferrsi.apps.archive import publish_result, read_result
from inferrsi.harness.errors import PublicError
from inferrsi.harness.run_store import Claim, RunStore, flatten, request_digest, utc_now

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _ROOT / "docs/contracts/fixtures"
_V4 = _FIXTURES / "t108-v4"
_ATTEMPT_FIELDS = (
    "request_id", "run_id", "attempt_id", "owner", "target_request", "deadline_utc",
    "resources", "budget", "retry_of", "retry_reason",
)
_PROPOSAL_FIELDS = ("candidate", "inputs", "generation_record_ref")


def _fixture(name: str) -> dict:
    return json.loads((_V4 / f"{name}.json").read_bytes())


def _spec() -> dict:
    return json.loads((_FIXTURES / "execution-spec-d023.json").read_bytes())


def _request() -> dict:
    spec = _spec()
    return {
        "schema_version": 1,
        "prepared_ref": spec["prepared_ref"],
        "proposal": {field: spec[field] for field in _PROPOSAL_FIELDS},
        "attempt": {field: spec[field] for field in _ATTEMPT_FIELDS},
        "output_root": spec["output_root"],
    }


def _bind(request: dict) -> dict:
    return {
        **_spec(),
        **request["attempt"],
        **request["proposal"],
        "prepared_ref": request["prepared_ref"],
        "output_root": request["output_root"],
    }


def _submit_to_run_store(workspace: Path, spec: dict) -> dict:
    """Inject the record-producing port using the H01 store and a fixed terminal payload."""
    assert encode(spec) == (_FIXTURES / "execution-spec-d023.json").read_bytes()
    store = RunStore(workspace / "run-store", "apps-test")
    attempt = {field: spec[field] for field in _ATTEMPT_FIELDS}
    digest = request_digest(spec)
    committed = store.claim(attempt, digest)
    if isinstance(committed, Claim):
        with committed as claim:
            payload = _fixture("record-payload")
            payload["request_digest"] = digest
            committed = claim.commit(payload)
    return flatten(committed, utc_now())


def _run_saved_request(workspace: Path, output_id: str):
    request = decode((workspace / "execute-request.json").read_bytes())
    return execute(
        request,
        workspace=workspace,
        output_id=output_id,
        bind_execution=_bind,
        execute_harness=lambda spec: _submit_to_run_store(workspace, spec),
    )


@pytest.mark.parametrize("fixture", ["apps-not-started", "apps-assessment"])
def test_publish_matches_canonical_result_and_manifest(tmp_path, fixture):
    result = _fixture(fixture)
    published = publish_result(tmp_path, result)
    assert published.directory == tmp_path / "output" / published.output_id
    assert {path.name for path in published.directory.iterdir()} == {
        "manifest.json", "result.json",
    }
    data = (published.directory / "result.json").read_bytes()
    assert data == (_V4 / f"{fixture}.json").read_bytes()
    manifest = decode((published.directory / "manifest.json").read_bytes())
    assert manifest == {
        "schema_version": 1,
        "output_id": published.output_id,
        "created_at": manifest["created_at"],
        "operation": result["operation"],
        "run_id": result["execution"]["run_id"],
        "attempt_id": result["attempt_id"],
        "result": {
            "path": "result.json",
            "sha256": sha256(data).hexdigest(),
            "size_bytes": len(data),
            "media_type": "application/json",
        },
    }
    assert manifest["created_at"].endswith("Z")
    assert read_result(tmp_path, published.output_id) == published


def test_failed_publication_preserves_commit_and_replay_reuses_attempt(tmp_path, monkeypatch):
    saved = encode(_request())
    (tmp_path / "execute-request.json").write_bytes(saved)

    def refuse_rename(staging, destination):
        assert {file.name for file in staging.iterdir()} == {"manifest.json", "result.json"}
        assert destination == tmp_path / "output" / "first"
        raise PermissionError("test publication failure")

    with monkeypatch.context() as patch:
        patch.setattr(archive, "_publish_directory", refuse_rename)
        failed = _run_saved_request(tmp_path, "first")

    store = RunStore(tmp_path / "run-store", "apps-test")
    attempt_id = _request()["attempt"]["attempt_id"]
    committed = store.committed(attempt_id, 1)
    record = failed.result["execution"]
    golden = json.loads((_FIXTURES / "MANIFEST-d023.json").read_bytes())
    assert record["request_digest"] == golden["files"][0]["request_digest"]
    assert failed.directory is None
    assert list((tmp_path / "output").iterdir()) == []
    assert failed.result["exit_code"] == 6
    assert failed.result["reason_code"] == failed.result["error"]["code"] == (
        "ArchivePersistenceError"
    )
    assert committed.record_ref == record["record_ref"]
    assert failed.result["prepared_ref"] == record["prepared_ref"]
    assert failed.result["record_ref"] == record["record_ref"]
    assert failed.result["error"]["latest_record_ref"] == record["record_ref"]
    original_bytes = store.open(committed.record_ref["artifact"]).read()
    assert original_bytes == committed.payload_bytes

    subprocess.run(
        [
            sys.executable, "-c",
            "import runpy, sys; from pathlib import Path; "
            "runpy.run_path(sys.argv[1])['_run_saved_request'](Path(sys.argv[2]), 'replay')",
            __file__, str(tmp_path),
        ],
        check=True,
        env={**os.environ, "PYTHONPATH": str(_ROOT / "src")},
        capture_output=True,
        text=True,
    )
    replayed = read_result(tmp_path, "replay")
    assert replayed.result["outcome"] == "not_started"
    assert replayed.result["record_ref"] == failed.result["record_ref"]
    assert replayed.result["attempt_id"] == attempt_id
    assert replayed.result["execution"]["request_digest"] == record["request_digest"]
    assert store.committed(attempt_id).payload["record_version"] == 1
    assert store.open(committed.record_ref["artifact"]).read() == original_bytes
    assert (tmp_path / "execute-request.json").read_bytes() == saved


def test_typed_harness_error_is_published(tmp_path):
    error = PublicError("RecoveryRequired", stage="claim", message="owner state unknown")

    def submit(spec):
        raise error

    output = execute(_request(), workspace=tmp_path, bind_execution=_bind, execute_harness=submit)
    assert output.result["error"] == error.to_json()
    assert output.result["exit_code"] == 5


def test_a_code_key_on_a_bound_spec_does_not_discriminate_a_public_error(tmp_path):
    error = PublicError("RecoveryRequired", stage="claim", message="owner state unknown")
    submitted = []

    def submit(spec):
        submitted.append(spec["code"])
        raise error

    output = execute(
        _request(), workspace=tmp_path,
        bind_execution=lambda request: {**_bind(request), "code": "extra-metadata"},
        execute_harness=submit,
    )
    assert submitted == ["extra-metadata"]
    assert output.result["error"] == error.to_json()


@pytest.mark.parametrize(
    ("code", "outcome", "exit_code"),
    [
        ("AttemptInProgress", "in_progress", 4),
        ("RecoveryRequired", "recovery_required", 5),
        ("ExecutionPersistenceError", "persistence_error", 6),
    ],
)
def test_harness_error_keeps_only_prior_record_ref(tmp_path, code, outcome, exit_code):
    refs = _fixture("fixed-refs")
    error = {**_fixture("public-error"), "code": code, "latest_record_ref": refs["record_ref"]}
    if code == "ExecutionPersistenceError":
        record = _fixture("record-api-envelope")
        fields = (
            "request_id", "run_id", "attempt_id", "request_digest", "phase", "started",
            "side_effect_unknown", "steps", "checks", "artifacts", "budget_admission",
            "usage", "resource_leases", "errors",
        )
        error["partial_record"] = {
            **{field: record[field] for field in fields},
            "proposed_record_version": 2,
        }
        error["retained_refs"] = [refs["record_ref"]["artifact"]]
    output = execute(
        _request(), workspace=tmp_path, output_id="error",
        bind_execution=_bind, execute_harness=lambda spec: error,
    )
    assert output.result["outcome"] == outcome
    assert output.result["exit_code"] == exit_code
    assert output.result["error"] == error
    assert output.result["record_ref"] is output.result["execution"] is None
    manifest = decode((output.directory / "manifest.json").read_bytes())
    assert manifest["run_id"] is manifest["attempt_id"] is None
    assert read_result(tmp_path, "error") == output

    publication_failed = publish_result(tmp_path, output.result, output_id="error")
    assert publication_failed.directory is None
    assert publication_failed.result["reason_code"] == "ArchivePersistenceError"
    assert publication_failed.result["record_ref"] is None
    assert publication_failed.result["error"]["latest_record_ref"] == refs["record_ref"]
    assert publication_failed.result["error"]["partial_record"] == error["partial_record"]
    assert publication_failed.result["error"]["retained_refs"] == error["retained_refs"]
    assert read_result(tmp_path, "error") == output


@pytest.mark.parametrize(
    "field",
    ["attempt_id", "deadline_utc", "budget", "output_root", "candidate",
     "generation_record_ref", "inputs"],
)
def test_binding_cannot_change_saved_request(tmp_path, field):
    def unexpected_submit(spec):
        pytest.fail("changed spec must be rejected before submission")

    output = execute(
        _request(), workspace=tmp_path,
        bind_execution=lambda request: {**_bind(request), field: "changed"},
        execute_harness=unexpected_submit,
    )
    assert output.result["exit_code"] == 2
    assert output.result["reason_code"] == "InvalidExecutionSpec"
    assert read_result(tmp_path, output.output_id) == output


def test_binding_cannot_change_pinned_input(tmp_path):
    def change_pin(request):
        spec = _bind(request)
        spec["inputs"][0]["expected_sha256"] = "0" * 64
        return spec

    output = execute(
        _request(), workspace=tmp_path, bind_execution=change_pin,
        execute_harness=lambda spec: pytest.fail("changed input must not reach Harness"),
    )
    assert output.result["reason_code"] == "InvalidExecutionSpec"


def test_execute_rejects_record_from_different_spec_with_same_attempt(tmp_path):
    stale_record = _fixture("record-api-envelope")
    assert stale_record["attempt_id"] == _request()["attempt"]["attempt_id"]
    output = execute(
        _request(), workspace=tmp_path, bind_execution=_bind,
        execute_harness=lambda spec: stale_record,
    )
    assert output.result["reason_code"] == "IdentityMismatch"
    assert output.result["record_ref"] is output.result["execution"] is None
    assert read_result(tmp_path, output.output_id) == output


@pytest.mark.parametrize("operation", ["prepare", "assess"])
def test_failed_publication_preserves_archive_refs(tmp_path, operation):
    result = _fixture("apps-assessment")
    if operation == "prepare":
        result = dict.fromkeys(result)
        result.update(
            schema_version=1, operation="prepare", outcome="success", exit_code=0,
            prepared_ref=_fixture("fixed-refs")["prepared_ref"],
        )
    output = publish_result(tmp_path, result, output_id=operation)
    failed = publish_result(tmp_path, result, output_id=operation)
    assert failed.directory is None
    assert failed.result["exit_code"] == 6
    assert failed.result["reason_code"] == "ArchivePersistenceError"
    for key in ("prepared_ref", "record_ref", "assessment_ref", "assessment"):
        assert failed.result[key] == result[key]
    assert read_result(tmp_path, operation) == output


@pytest.mark.parametrize("change", ["version", "path", "digest", "size", "run_id"])
def test_reader_rejects_inconsistent_manifest(tmp_path, change):
    output = publish_result(tmp_path, _fixture("apps-not-started"))
    path = output.directory / "manifest.json"
    manifest = decode(path.read_bytes())
    if change == "version":
        manifest["schema_version"] = 2
    elif change == "run_id":
        manifest["run_id"] = "wrong-run"
    else:
        field, value = {
            "path": ("path", "../result.json"),
            "digest": ("sha256", "0" * 64),
            "size": ("size_bytes", 0),
        }[change]
        manifest["result"][field] = value
    path.write_bytes(encode(manifest))
    with pytest.raises(ValueError):
        read_result(tmp_path, output.output_id)


@pytest.mark.parametrize("change", ["record", "assessment", "claim", "ref_digest"])
def test_envelope_requires_consistent_commits(tmp_path, change):
    fixture = "apps-not-started" if change in ("record", "ref_digest") else "apps-assessment"
    result = _fixture(fixture)
    if change == "record":
        result.update(
            execution=None, record_ref=None, prepared_ref=None, admission=None, attempt_id=None,
            outcome="success", exit_code=0,
        )
    elif change == "assessment":
        result.update(assessment=None, assessment_ref=None)
    elif change == "claim":
        result.update(outcome="fail", exit_code=8)
    else:
        result["record_ref"]["artifact"]["sha256"] = "0" * 64
        result["execution"]["record_ref"] = result["record_ref"]
    with pytest.raises(ValueError):
        publish_result(tmp_path, result)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("output_id", ["../other", "a/b", "a\\b", ".pending-x", "NUL.txt", "x."])
def test_output_ids_are_portable_and_cannot_select_other_paths(tmp_path, output_id):
    with pytest.raises(ValueError, match="output_id"):
        publish_result(tmp_path, _fixture("apps-not-started"), output_id=output_id)
    with pytest.raises(ValueError, match="output_id"):
        read_result(tmp_path, output_id)
    assert not (tmp_path / "output").exists()


def test_concurrent_publications_with_same_id_do_not_replace(tmp_path):
    start = Barrier(2)

    def publish(name):
        start.wait(timeout=10)
        return publish_result(tmp_path, _fixture(name), output_id="same")

    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(publish, ["apps-not-started", "apps-assessment"]))
    published, = (output for output in outputs if output.directory is not None)
    rejected, = (output for output in outputs if output.directory is None)
    assert read_result(tmp_path, "same") == published
    assert rejected.result["reason_code"] == "ArchivePersistenceError"
    assert list((tmp_path / "output").iterdir()) == [published.directory]


def test_empty_directory_created_at_publication_is_never_replaced(tmp_path, monkeypatch):
    result = _fixture("apps-not-started")
    publish = archive._publish_directory

    def racing_publish(staging, destination):
        assert not destination.exists()
        destination.mkdir()
        publish(staging, destination)

    monkeypatch.setattr(archive, "_publish_directory", racing_publish)
    output = publish_result(tmp_path, result, output_id="race")
    assert output.directory is None
    assert output.result["reason_code"] == "ArchivePersistenceError"
    assert output.result["record_ref"] == result["record_ref"]
    destination = tmp_path / "output" / "race"
    assert destination.is_dir() and list(destination.iterdir()) == []
    assert list(destination.parent.iterdir()) == [destination]
