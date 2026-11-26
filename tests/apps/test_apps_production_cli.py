"""Exercise opt-in evidence capture through the saved-request CLI on a real CPU task."""

import json
import sqlite3
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from inferrsi.apps import api
from inferrsi.apps.cli import main
from inferrsi.apps.handoff.bridge import bind_execution
from inferrsi.apps.handoff.production_capture import PreparedCapture
from inferrsi.apps.storage import archive
from inferrsi.apps.storage.archive import read_prepared, read_result
from inferrsi.benchmark import cpu_smoke, proofs
from inferrsi.benchmark.workers import fixture_worker as worker
from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness import execution_service, run_store
from inferrsi.harness.executor import request_digest
from tests.apps.test_apps_evaluate_cli import arguments, save

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["correct", "wrong", "invalid-utf8", "missing"])
def production_cli(tmp_path, request, capsys):
    for name in ("archive", "controller", "modules"):
        (tmp_path / name).mkdir()
    code = tmp_path / "modules/fixture_worker.py"
    code.write_bytes(cpu_smoke.worker_source())
    protocol = cpu_smoke.protocol(code.read_bytes(),
                                  control_domain=execution_service._CONTROL_DOMAIN)
    config = {"schema_version": 1, "archive_namespace": "apps", "harness_namespace": "test",
              "mounts": [{"kind": "directory", "namespace": "apps", "prefix": "archives/local",
                          "root": str(tmp_path / "archive")},
                         {"kind": "harness_sqlite", "namespace": "test", "prefix": "stores/test",
                          "root": str(tmp_path / "store")}]}
    runtime = {"schema_version": 1, "benchmark": {
        "protocol": str(save(tmp_path, "protocol.json", protocol)), "worker_role": "worker-code",
        "resources": {"worker-code": str(code), "baseline-code": str(code)},
    }, "target": {"target_id": "fixture-cpu", "config_revision": "1",
                  "work_root": str(tmp_path / "work"), "module_root": str(tmp_path / "modules"),
                  "controller_root": str(tmp_path / "controller")}}
    prepare_request = {"schema_version": 1, "request": cpu_smoke.default_request()}
    assert main(arguments(tmp_path, "prepare", prepare_request, config, runtime,
                          output="prepare")) == 0
    capsys.readouterr()
    prepared = read_result(tmp_path, "prepare")
    assert not (tmp_path / "store").exists()
    kind = request.param
    candidate = {"correct": str(sum(worker.INPUT_BYTES)).encode("ascii") + b"\n",
                 "wrong": b"wrong\n", "invalid-utf8": b"\xff\n", "missing": b"wrong\n"}[kind]
    if kind != "missing":
        (tmp_path / "controller/candidate.txt").write_bytes(candidate)
    seed = decode((ROOT / "tests/fixtures/harness-prepared-binding/d023-null-timeout.json")
                  .read_bytes())
    attempt = run_store.allocate_attempt(**{key: seed[key] for key in (
        "run_id", "owner", "target_request", "deadline_utc", "resources", "budget",
        "retry_of", "retry_reason",
    )})
    proposal = {key: deepcopy(seed[key])
                for key in ("candidate", "inputs", "generation_record_ref")}
    proposal["inputs"][0].update(source="candidate.txt", source_namespace="controller",
                                 source_ref=None, expected_sha256=sha256(candidate).hexdigest())
    saved = {"schema_version": 1, "prepared_ref": prepared.result["prepared_ref"],
             "attempt": attempt, "proposal": proposal,
             "output_root": "evaluation/" + attempt["attempt_id"]}
    (tmp_path / "original-execute.json").write_bytes(encode(saved))
    command = arguments(tmp_path, "execute", saved, config, runtime, output="execute")
    assert main(command + ["--capture-evidence"]) == (3 if kind == "missing" else 0)
    capsys.readouterr()
    executed = read_result(tmp_path, "execute")
    assessment = {"schema_version": 1, "record_ref": executed.result["record_ref"],
                  "primary_scope": "p1", "primary_claim_id": "C"}
    expected = (["INCONCLUSIVE"] * 3 if kind == "missing" else
                ["FAIL" if kind == "invalid-utf8" else "PASS",
                 "PASS" if kind == "correct" else "FAIL", "PASS"])
    expected_exit = {"PASS": 0, "FAIL": 8, "INCONCLUSIVE": 9}[expected[1]]
    assert main(arguments(tmp_path, "assess", assessment, config, output="assess")) == expected_exit
    capsys.readouterr()
    assessed = read_result(tmp_path, "assess")
    assert [claim["verdict"] for claim in assessed.result["assessment"]["claims"]] == expected
    return {"pair": (config, run_store.RunStore(tmp_path / "store", "test"), prepared, executed,
                     assessed, expected), "saved": saved, "runtime": runtime, "kind": kind}


def test_real_cli_claims_and_views_share_the_fixed_pair(production_cli, tmp_path, capsys):
    config, store, _, executed, assessed, verdicts = production_cli["pair"]
    ref, decision = executed.result["record_ref"], assessed.result["assessment_ref"]
    flags = ["--record-ref", str(save(tmp_path, "record-ref.json", ref)),
             "--assessment-ref", str(save(tmp_path, "assessment-ref.json", decision)),
             "--storage-config", str(save(tmp_path, "views-storage.json", config))]
    before = store.committed(ref["attempt_id"])
    expected = api.read_attempt_view(ref, storage_config=config, assessment_ref=decision)
    for command in ("status", "trace"):
        assert main([command, *flags]) == 0
        view = json.loads(capsys.readouterr().out)
        assert view["record_ref"] == expected["record_ref"] == ref
        assert view["assessment_ref"] == decision
        assert view["execution"]["attempt_id"] == ref["attempt_id"]
        assert [claim["verdict"] for claim in view["assessment"]["claims"]] == verdicts
    for command in ("report", "dashboard"):
        path = tmp_path / (command + ".html")
        assert main([command, *flags, "--output", str(path)]) == 0
        capsys.readouterr()
        document = path.read_text(encoding="utf-8")
        assert ref["artifact"]["sha256"] in document
        assert decision["artifact"]["sha256"] in document
    after = store.committed(ref["attempt_id"])
    assert before.payload_bytes == after.payload_bytes
    assert decode((tmp_path / "original-execute.json").read_bytes()) == production_cli["saved"]


def test_registered_cli_replay_never_builds_projection_or_recaptures(
    production_cli, tmp_path, capsys, monkeypatch,
):
    case = production_cli
    config, store, _, executed, _, _ = case["pair"]
    count_before = store.committed(executed.result["attempt_id"])
    runtime = deepcopy(case["runtime"])
    runtime["target"].update(target_id="retired", config_revision="2", module_root=None)

    def never(*args, **kwargs):
        pytest.fail("registered replay built a projection, recaptured evidence or started a worker")

    monkeypatch.setattr(PreparedCapture, "capture", never)
    monkeypatch.setattr(proofs.ProofProjector, "__init__", never)
    monkeypatch.setattr(execution_service.local_process, "_supervise", never)
    assert main(arguments(tmp_path, "execute", case["saved"], config, runtime,
                          output="replay") + ["--capture-evidence"]) == executed.result["exit_code"]
    result = json.loads(capsys.readouterr().out)
    assert result["record_ref"] == executed.result["record_ref"]
    after = store.committed(executed.result["attempt_id"])
    assert after.payload_bytes == count_before.payload_bytes
    with sqlite3.connect(store.root / run_store.INDEX_NAME) as connection:
        assert connection.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM records").fetchone()[0] == 1


def new_attempt(case):
    saved = deepcopy(case["saved"])
    original = saved["attempt"]
    saved["attempt"] = run_store.allocate_attempt(**{key: original[key] for key in (
        "run_id", "owner", "target_request", "deadline_utc", "resources", "budget",
        "retry_of", "retry_reason",
    )})
    saved["output_root"] = "evaluation/" + saved["attempt"]["attempt_id"]
    return saved


@pytest.mark.parametrize("production_cli", ["correct"], indirect=True)
@pytest.mark.parametrize("code", ["InvalidRequest", "UnsupportedSchema", "UnsupportedRuleVersion"])
def test_declared_projection_error_keeps_existing_postregistration_refusal(
    production_cli, tmp_path, capsys, monkeypatch, code,
):
    case = production_cli
    config, store, _, _, _, _ = case["pair"]
    saved = new_attempt(case)

    def reject(*args, **kwargs):
        raise proofs.ProofError(code, "controlled declared B projection refusal")

    monkeypatch.setattr(proofs.ProofProjector, "__init__", reject)
    monkeypatch.setattr(execution_service.local_process, "_supervise",
                        lambda *a, **k: pytest.fail("rejected capture started a worker"))
    assert main(arguments(tmp_path, "execute", saved, config, case["runtime"],
                          output="rejected") + ["--capture-evidence"]) == 3
    result = json.loads(capsys.readouterr().out)
    assert result["execution"]["started"] is False
    assert result["execution"]["process_outcome"] == "not_started"
    assert result["record_ref"] == store.read(saved["attempt"]["attempt_id"])["record_ref"]
    assert any(error["code"] == code for error in result["execution"]["errors"])


@pytest.mark.parametrize("production_cli", ["correct"], indirect=True)
def test_enabling_capture_on_registered_attempt_never_retrofits_proofs(
    production_cli, tmp_path, capsys, monkeypatch,
):
    case = production_cli
    config, _, _, _, _, _ = case["pair"]
    saved = new_attempt(case)
    assert main(arguments(tmp_path, "execute", saved, config, case["runtime"],
                          output="uncaptured")) == 0
    original = json.loads(capsys.readouterr().out)
    assert not {"format", "grader", "samples", "cleanup"} & {
        check["check_id"] for check in original["execution"]["checks"]
    }

    def forbidden(*args, **kwargs):
        pytest.fail("changing host assembly attempted to retrofit a registered record")

    monkeypatch.setattr(PreparedCapture, "capture", forbidden)
    monkeypatch.setattr(proofs.ProofProjector, "__init__", forbidden)
    assert main(arguments(tmp_path, "execute", saved, config, case["runtime"],
                          output="late-opt-in") + ["--capture-evidence"]) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["record_ref"] == original["record_ref"]
    assert replay["execution"]["checks"] == original["execution"]["checks"]


@pytest.mark.parametrize("production_cli", ["correct"], indirect=True)
def test_conflict_and_live_attempt_never_invoke_fresh_capture(
    production_cli, tmp_path, capsys, monkeypatch,
):
    case = production_cli
    config, store, _, executed, _, _ = case["pair"]

    def never(*args, **kwargs):
        pytest.fail("registered state invoked fresh capture, projection or worker")

    monkeypatch.setattr(PreparedCapture, "capture", never)
    monkeypatch.setattr(proofs.ProofProjector, "__init__", never)
    monkeypatch.setattr(execution_service.local_process, "_supervise", never)
    changed = deepcopy(case["saved"])
    changed["attempt"]["deadline_utc"] = "2098-01-01T00:00:00Z"
    assert main(arguments(tmp_path, "execute", changed, config, case["runtime"],
                          output="conflict") + ["--capture-evidence"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["reason_code"] == "RequestConflict" and result["error"]["stage"] == "claim"
    saved = new_attempt(case)
    spec = bind_execution(saved, read_prepared(config, saved["prepared_ref"]))
    with store.claim(saved["attempt"], request_digest(spec)):
        assert main(arguments(tmp_path, "execute", saved, config, case["runtime"],
                              output="live") + ["--capture-evidence"]) == 4
    result = json.loads(capsys.readouterr().out)
    assert result["reason_code"] == "AttemptInProgress"
    assert store.read(executed.result["attempt_id"])["record_ref"] == executed.result["record_ref"]


@pytest.mark.parametrize("action", ["prepare", "assess"])
def test_capture_flag_is_execute_only(tmp_path, monkeypatch, action):
    from inferrsi.apps.cli import evaluate as cli

    monkeypatch.setattr(cli, "dispatch", lambda *a: pytest.fail("invalid flag reached a port"))
    command = arguments(tmp_path, action, {}, {}, {"schema_version": 1})
    with pytest.raises(SystemExit) as error:
        main(command + ["--capture-evidence"])
    assert error.value.code == 2


@pytest.mark.parametrize("production_cli", ["correct"], indirect=True)
@pytest.mark.parametrize("after_publication", [False, True])
def test_production_cli_publication_failure_preserves_refs_and_original_attempt(
    production_cli, tmp_path, capsys, monkeypatch, after_publication,
):
    case = production_cli
    config, store, _, _, _, _ = case["pair"]
    saved = new_attempt(case)
    request_bytes = encode(saved)
    output_id = "uncertain" if after_publication else "unpublished"
    command = arguments(tmp_path, "execute", saved, config, case["runtime"], output=output_id)
    output = tmp_path / "output" / output_id
    original_publish = archive._publish_directory
    original_sync = archive._sync_directory

    def fail_publish(source, destination):
        if destination == output:
            raise OSError("controlled pre-publication failure")
        return original_publish(source, destination)

    def fail_durability(directory):
        if directory == output.parent and output.is_dir():
            raise OSError("controlled post-publication durability failure")
        return original_sync(directory)

    with monkeypatch.context() as fault:
        if after_publication:
            fault.setattr(archive, "_sync_directory", fail_durability)
        else:
            fault.setattr(archive, "_publish_directory", fail_publish)
        assert main(command + ["--capture-evidence"]) == 6
    failed = json.loads(capsys.readouterr().out)
    ref = failed["record_ref"]
    committed = store.committed(saved["attempt"]["attempt_id"])
    assert ref == committed.record_ref == failed["error"]["latest_record_ref"]
    assert failed["execution"]["started"] is True
    assert {"format", "grader", "samples", "cleanup"} <= {
        check["check_id"] for check in failed["execution"]["checks"]
    }
    assert output.exists() is after_publication
    published_bytes = None
    if after_publication:
        assert "uncertain" in failed["error"]["message"].lower()
        published = read_result(tmp_path, output_id)
        assert published.result["exit_code"] == 0
        assert published.result["record_ref"] == ref
        published_bytes = {name: (output / name).read_bytes()
                           for name in ("result.json", "manifest.json")}

    # Once committed, a failed output publication cannot re-run the task, even
    # with its source gone and the configured target retired.
    (tmp_path / "controller/candidate.txt").unlink()
    runtime = deepcopy(case["runtime"])
    runtime["target"].update(target_id="retired", config_revision="2", module_root=None)

    def never(*args, **kwargs):
        pytest.fail("publication recovery recaptured evidence, allocated or ran a worker")

    monkeypatch.setattr(PreparedCapture, "capture", never)
    monkeypatch.setattr(proofs.ProofProjector, "__init__", never)
    monkeypatch.setattr(run_store, "allocate_attempt", never)
    monkeypatch.setattr(execution_service.local_process, "_supervise", never)
    retry = arguments(tmp_path, "execute", saved, config, runtime, output=output_id)
    assert main(retry + ["--capture-evidence"]) == (6 if after_publication else 0)
    retried = json.loads(capsys.readouterr().out)
    assert retried["record_ref"] == ref
    if after_publication:
        assert published_bytes == {name: (output / name).read_bytes()
                                   for name in ("result.json", "manifest.json")}
        retry = arguments(tmp_path, "execute", saved, config, runtime, output="recovered")
        assert main(retry + ["--capture-evidence"]) == 0
        assert json.loads(capsys.readouterr().out)["record_ref"] == ref
    assert encode(saved) == request_bytes
    assert store.committed(ref["attempt_id"]).payload_bytes == committed.payload_bytes
    with sqlite3.connect(store.root / run_store.INDEX_NAME) as connection:
        assert connection.execute("SELECT count(*) FROM attempts").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM records").fetchone()[0] == 2
