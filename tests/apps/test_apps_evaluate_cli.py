"""Saved requests reach production ports, with CLI-only checks before effects."""

import json
import os
import sqlite3
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pytest

from inferrsi.apps.cli import evaluate as cli
from inferrsi.apps.cli import main
from inferrsi.apps.storage import archive
from inferrsi.apps.storage.archive import read_result
from inferrsi.benchmark import cpu_smoke
from inferrsi.benchmark.workers import fixture_worker as worker
from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness import execution_service
from inferrsi.harness.records import RunStore
from inferrsi.harness.records import _run_store as run_store
from tests.apps.test_apps_generation_plan import generation as generation
from tests.benchmark.test_benchmark_assessment import remove
from tests.benchmark.test_benchmark_assessment import retained as retained
from tests.benchmark.test_benchmark_preparation import preparation as preparation
from tests.harness.test_harness_entry_verification import evaluation as evaluation
from tests.harness.test_harness_generation_lineage import lineage as lineage
from tests.harness.test_harness_generation_seal import cpu_generation as cpu_generation


def save(tmp_path, name, value):
    path = tmp_path / name
    # Human-readable inputs are allowed; persisted outputs remain canonical.
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path


def arguments(tmp_path, action, request, config, runtime=None, output="call"):
    values = ["evaluate", action, "--request", "@" + str(save(tmp_path, "request.json", request)),
              "--storage-config", str(save(tmp_path, "storage.json", config)),
              "--workspace", str(tmp_path), "--output-id", output]
    if runtime is not None:
        values += ["--runtime-config", str(save(tmp_path, "runtime.json", runtime))]
    return values


def execute_request(case):
    spec = case["spec"]
    proposal = {key: deepcopy(spec[key]) for key in ("candidate", "generation_record_ref")}
    proposal["inputs"] = [deepcopy(item) for item in spec["inputs"]
                          if item["role"] == spec["candidate"]["input_role"]]
    return {"schema_version": 1, "prepared_ref": spec["prepared_ref"],
            "attempt": {key: deepcopy(spec[key]) for key in execution_service.ATTEMPT_FIELDS},
            "proposal": proposal,
            "output_root": spec["output_root"]}


def target_config(case):
    values = asdict(case["target"])
    return {"schema_version": 1, "target": {
        key: str(value) if isinstance(value, Path) else value for key, value in values.items()
    }}


def storage_config(case):
    # The entry-verification fixture already creates its archive beside the Store.
    root = case["store"].root.parent
    return {"schema_version": 1, "archive_namespace": "apps", "harness_namespace": "test",
            "mounts": [{"prefix": "archives/local", "namespace": "apps",
                        "root": str(root / "archive"), "kind": "directory"},
                       {"prefix": "stores/test", "namespace": "test",
                        "root": str(case["store"].root), "kind": "harness_sqlite"}]}


def test_prepare_uses_real_benchmark_and_publishes_standard_output(preparation, tmp_path, capsys):
    _, request, sources, protocol, _, config, _ = preparation
    runtime = {"schema_version": 1, "benchmark": {
        "protocol": str(save(tmp_path, "protocol.json", protocol)), "worker_role": "worker-code",
        "resources": {role: str(path) for role, path in sources.items()},
    }}
    command = arguments(tmp_path, "prepare", {"schema_version": 1, "request": request},
                        config, runtime)
    assert main(command + ["--scope", "p1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == read_result(tmp_path, "call").result
    assert result["prepared_ref"] is not None
    assert not (tmp_path / "store").exists()
    manifest = decode((tmp_path / "output/call/manifest.json").read_bytes())
    assert manifest["result"]["size_bytes"] == len(encode(result))


def test_execute_and_cross_process_replay_keep_original_attempt(evaluation, tmp_path, capsys,
                                                              monkeypatch):
    case = evaluation
    request, config, runtime = execute_request(case), storage_config(case), target_config(case)
    command = arguments(tmp_path, "execute", request, config, runtime)
    ref_file = save(tmp_path, "prepared-ref.json", request["prepared_ref"])
    assert main(command + ["--prepared-ref", "@" + str(ref_file), "--scope", "p1"]) == 0
    original = json.loads(capsys.readouterr().out)
    assert original["execution"]["started"] is True
    assert original["record_ref"] == read_result(tmp_path, "call").result["record_ref"]
    (case["modules"] / "fixture_worker.py").unlink()
    runtime["target"].update(target_id="retired", config_revision="2", module_root=None)
    command = arguments(tmp_path, "execute", request, config, runtime, output="replay")
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")}
    child = subprocess.run([sys.executable, "-m", "inferrsi", *command], cwd=tmp_path,
                           env=env, capture_output=True, text=True, timeout=30)
    assert child.returncode == 0, child.stderr
    replay = json.loads(child.stdout)
    assert replay["record_ref"] == original["record_ref"]
    assert request == execute_request(case)
    with sqlite3.connect(case["store"].root / run_store.INDEX_NAME) as conn:
        assert conn.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM records").fetchone()[0] == 1


@pytest.mark.parametrize(("claim", "code"), [("F", 0), ("C", 8), ("M", 9)])
def test_assess_offline_claim_exits_preserve_all_claims(retained, tmp_path, capsys, monkeypatch,
                                                     claim, code):
    remove(retained, "grader", "samples", "cleanup")
    retained["add"]("grader", "failed")
    ref, _ = retained["seal"]()
    request = {"schema_version": 1, "record_ref": ref,
               "primary_scope": "p1", "primary_claim_id": claim}

    def never(*args):
        pytest.fail("offline assessment constructed an execution/prepare runtime")

    monkeypatch.setattr(cli, "_execute_ports", never)
    monkeypatch.setattr(cli, "_prepare_ports", never)
    command = arguments(tmp_path, "assess", request, retained["config"])
    command += ["--runtime-config", str(tmp_path / "absent-runtime.json"),
                "--record-ref", "@" + str(save(tmp_path, "ref.json", ref)),
                "--scope", "p1", "--primary-claim", claim]
    assert main(command) == code
    result = json.loads(capsys.readouterr().out)
    assert result["assessment_ref"] is not None
    assert result == read_result(tmp_path, "call").result
    assert [row["verdict"] for row in result["assessment"]["claims"]] == [
        "PASS", "FAIL", "INCONCLUSIVE",
    ]


@pytest.mark.parametrize("check_id", ["samples", "cleanup"])
@pytest.mark.parametrize(
    "status", ["failed", pytest.param([], id="array"), pytest.param({}, id="object")],
)
def test_assess_archives_inconclusive_measurement_for_unusable_check(
    retained, tmp_path, capsys, check_id, status,
):
    check = next(row for row in retained["record"]["checks"] if row["check_id"] == check_id)
    check["status"] = status
    ref, _ = retained["seal"]()
    config = retained["config"]
    request = {"schema_version": 1, "record_ref": ref,
               "primary_scope": "p1", "primary_claim_id": "M"}
    record_path = retained["directory"] / ref["artifact"]["location"].removeprefix(
        "archives/local/",
    )
    original_bytes = record_path.read_bytes()

    command = arguments(tmp_path, "assess", request, config)
    assert main(command) == 9
    result = json.loads(capsys.readouterr().out)

    assert result == read_result(tmp_path, "call").result
    assessment = archive.read_assessment(config, result["assessment_ref"])
    assert assessment == result["assessment"]
    assert assessment["record_ref"] == ref
    assert [claim["verdict"] for claim in assessment["claims"]] == [
        "PASS", "PASS", "INCONCLUSIVE",
    ]
    assert assessment["claims"][2]["missing_evidence"] == [check_id]
    assert assessment["eligibility"][0]["status"] == "unknown"

    replay = arguments(tmp_path, "assess", request, config, output="reassessed")
    assert main(replay) == 9
    reassessed = json.loads(capsys.readouterr().out)["assessment"]
    assert reassessed["assessment_id"] == assessment["assessment_id"]
    assert record_path.read_bytes() == original_bytes


@pytest.mark.parametrize("option", ["--output-id", "--request", "--workspace", "--storage-config",
                                   "--runtime-config"])
def test_missing_cli_arguments_never_reach_a_port(tmp_path, monkeypatch, option):
    monkeypatch.setattr(cli, "dispatch", lambda args: pytest.fail("parser invoked a port"))
    command = arguments(tmp_path, "execute", {}, {}, {"schema_version": 1})
    index = command.index(option)
    del command[index:index + 2]
    with pytest.raises(SystemExit) as error:
        main(command)
    assert error.value.code == 2
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("extra", [
    ["--scope", "foreign"], ["--primary-claim", "foreign"],
    ["--prepared-ref", "@foreign.json"], ["--record-ref", "@foreign.json"],
])
def test_conflicting_options_fail_before_configuration_or_effects(retained, tmp_path, monkeypatch,
                                                                extra):
    ref, _ = retained["seal"]()
    request = {"schema_version": 1, "record_ref": ref,
               "primary_scope": "p1", "primary_claim_id": "F"}
    monkeypatch.setattr(cli, "_assess_ports", lambda: pytest.fail("configured a port"))
    command = arguments(tmp_path, "assess", request, retained["config"])
    with pytest.raises(SystemExit) as error:
        main(command + extra)
    assert error.value.code == 2
    assert not (tmp_path / "output/call").exists()


@pytest.mark.parametrize("bad", [b'{"schema_version":1,"schema_version":1}', b'[]', b'{"x":NaN}',
                                 b'{"x":1.5}', b'{"x":9007199254740992}', b'\xff',
                                 pytest.param(b'{"x":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}',
                                              id="excessive-nesting")])
def test_malformed_saved_json_is_refused_before_ports(tmp_path, monkeypatch, capsys, bad):
    command = arguments(tmp_path, "assess", {}, {})
    (tmp_path / "request.json").write_bytes(bad)
    monkeypatch.setattr(cli, "_assess_ports", lambda: pytest.fail("configured a port"))
    with pytest.raises(SystemExit) as error:
        main(command)
    assert error.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_publication_failure_keeps_committed_execution_reference(evaluation, tmp_path, capsys,
                                                               monkeypatch):
    case = evaluation
    command = arguments(tmp_path, "execute", execute_request(case), storage_config(case),
                        target_config(case))
    original = archive._publish_directory

    def fail(source, target):
        if target.name == "call":
            raise OSError("controlled output publication failure")
        return original(source, target)

    monkeypatch.setattr(archive, "_publish_directory", fail)
    assert main(command) == 6
    result = json.loads(capsys.readouterr().out)
    assert result["record_ref"] == case["store"].read(result["attempt_id"])["record_ref"]
    assert result["execution"]["started"] is True
    assert not (tmp_path / "output/call").exists()
    monkeypatch.setattr(archive, "_publish_directory", original)
    assert main(command) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["record_ref"] == result["record_ref"]
    with sqlite3.connect(case["store"].root / run_store.INDEX_NAME) as conn:
        assert conn.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM records").fetchone()[0] == 1


@pytest.mark.parametrize("path", ["relative/path", "//remote/share/path", "", None])
def test_runtime_never_infers_local_authority(tmp_path, path):
    runtime = {"schema_version": 1, "benchmark": {
        "protocol": path, "worker_role": "worker-code", "resources": {"code": path},
    }}
    command = arguments(tmp_path, "prepare", {"schema_version": 1, "request": {}}, {}, runtime)
    with pytest.raises(SystemExit) as error:
        main(command)
    assert error.value.code == 2
    assert not (tmp_path / "store").exists()


def test_parser_and_unrelated_commands_do_not_load_new_ports(tmp_path):
    script = """
import sys
from inferrsi.apps.cli.arguments import parser
parser()
assert not any(name in sys.modules for name in (
    'inferrsi.apps.api', 'inferrsi.harness.api', 'inferrsi.harness.records._run_store',
    'inferrsi.benchmark.preparation', 'inferrsi.benchmark.assessment'))
"""
    child = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                           timeout=30)
    assert child.returncode == 0, child.stderr


@pytest.mark.parametrize("change", ["version", "unknown", "null-root", "relative-root"])
def test_invalid_runtime_does_not_open_a_writable_store(evaluation, tmp_path, change):
    case = evaluation
    config = storage_config(case)
    config["mounts"][1]["root"] = str(tmp_path / "never-opened-store")
    runtime = target_config(case)
    if change == "version":
        runtime["schema_version"] = True
    elif change == "unknown":
        runtime["import"] = "untrusted_module"
    else:
        runtime["target"]["work_root"] = None if change == "null-root" else "relative"
    command = arguments(tmp_path, "execute", execute_request(case), config, runtime)
    with pytest.raises(SystemExit) as error:
        main(command)
    assert error.value.code == 2
    assert not (tmp_path / "never-opened-store").exists()


def test_changed_saved_attempt_digest_is_a_persisted_conflict(evaluation, tmp_path, capsys):
    case = evaluation
    request, config, runtime = execute_request(case), storage_config(case), target_config(case)
    assert main(arguments(tmp_path, "execute", request, config, runtime)) == 0
    first = json.loads(capsys.readouterr().out)
    request["attempt"]["deadline_utc"] = "2098-01-01T00:00:00Z"
    assert main(arguments(tmp_path, "execute", request, config, runtime, output="conflict")) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["reason_code"] == "RequestConflict"
    assert result["error"]["stage"] == "claim"
    assert result == read_result(tmp_path, "conflict").result
    assert case["store"].read(first["attempt_id"])["record_ref"] == first["record_ref"]


def test_request_tag_is_required_before_runtime_configuration(tmp_path, monkeypatch):
    command = arguments(tmp_path, "assess", {}, {})
    index = command.index("--request") + 1
    command[index] = command[index].removeprefix("@")
    monkeypatch.setattr(cli, "_assess_ports", lambda: pytest.fail("configured a port"))
    with pytest.raises(SystemExit) as error:
        main(command)
    assert error.value.code == 2


@pytest.mark.parametrize("field", ["runtime_config", "storage_config", "target", "import"])
def test_request_cannot_supply_runtime_authority(evaluation, tmp_path, capsys, monkeypatch, field):
    case = evaluation
    request, config, runtime = execute_request(case), storage_config(case), target_config(case)
    config["mounts"][1]["root"] = str(tmp_path / "unopened-store")
    request[field] = {"work_root": str(tmp_path / "request-selected-root"),
                      "module_root": str(tmp_path / "request-selected-modules")}
    configured = []
    original = cli._execute_ports

    def observe(trusted, storage, **options):
        configured.append(deepcopy(trusted))
        return original(trusted, storage, **options)

    monkeypatch.setattr(cli, "_execute_ports", observe)
    command = arguments(tmp_path, "execute", request, config, runtime)
    assert main(command) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["reason_code"] == "InvalidRequest"
    assert configured == [runtime]
    assert not (tmp_path / "unopened-store").exists()
    assert not (tmp_path / "request-selected-root").exists()
    assert not (tmp_path / "request-selected-modules").exists()


def test_entry_refusal_is_a_committed_exit_three(evaluation, tmp_path, capsys):
    case = evaluation
    (case["modules"] / "fixture_worker.py").write_bytes(b"raise RuntimeError('changed code')\n")
    command = arguments(tmp_path, "execute", execute_request(case), storage_config(case),
                        target_config(case))
    assert main(command) == 3
    result = json.loads(capsys.readouterr().out)
    assert result["execution"]["started"] is False
    assert result["execution"]["process_outcome"] == "not_started"
    assert result["record_ref"] is not None


@pytest.mark.parametrize("evaluation", [{"worker_code": b"raise SystemExit(3)\n"}], indirect=True)
def test_recorded_worker_failure_returns_exit_seven(evaluation, tmp_path, capsys):
    case = evaluation
    command = arguments(tmp_path, "execute", execute_request(case), storage_config(case),
                        target_config(case))
    assert main(command) == 7
    result = json.loads(capsys.readouterr().out)
    assert result["execution"]["started"] is True
    assert result["execution"]["exit_code"] == 3
    assert result["record_ref"] is not None


@pytest.mark.parametrize("fault", ["missing", "null-mounts", "missing-namespace",
                                   "list-namespace", "directory-store"])
def test_malformed_storage_is_exit_two_before_store_open(evaluation, tmp_path, monkeypatch,
                                                       fault, capsys):
    case = evaluation
    config = storage_config(case)
    if fault == "missing":
        config = {}
    elif fault == "null-mounts":
        config["mounts"] = None
    elif fault == "missing-namespace":
        del config["mounts"][1]["namespace"]
    elif fault == "list-namespace":
        config["harness_namespace"] = []
    else:
        config["mounts"][1]["kind"] = "directory"

    def forbidden(*args, **kwargs):
        pytest.fail("malformed storage reached a writable Store")

    monkeypatch.setattr(RunStore, "from_mount", forbidden)
    command = arguments(tmp_path, "execute", execute_request(case), config, target_config(case))
    with pytest.raises(SystemExit) as error:
        main(command)
    assert error.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_generated_candidate_through_saved_commands(lineage, tmp_path, capsys):
    config = lineage["config"]
    runtime = target_config({"target": lineage["evaluation_target"]})
    code = Path(worker.__file__)
    protocol = cpu_smoke.protocol(
        code.read_bytes(), control_domain=execution_service._CONTROL_DOMAIN,
    )
    runtime["benchmark"] = {
        "protocol": str(save(tmp_path, "protocol.json", protocol)), "worker_role": "worker-code",
        "resources": {"worker-code": str(code), "baseline-code": str(code)},
    }
    prepare = {"schema_version": 1, "request": cpu_smoke.default_request()}
    assert main(arguments(tmp_path, "prepare", prepare, config, runtime, output="cli-prepare")) == 0
    request = execute_request(lineage)
    request["prepared_ref"] = json.loads(capsys.readouterr().out)["prepared_ref"]
    generation_ref = lineage["generated"]["record_ref"]
    assert request["attempt"]["attempt_id"] != generation_ref["attempt_id"]

    assert main(arguments(tmp_path, "execute", request, config, runtime, output="cli-execute")
                + ["--capture-evidence"]) == 0
    executed = json.loads(capsys.readouterr().out)
    assert executed["execution"]["generation_record_ref"] == generation_ref
    assert executed["record_ref"]["attempt_id"] == request["attempt"]["attempt_id"]
    assessment = {"schema_version": 1, "record_ref": executed["record_ref"],
                  "primary_scope": "p1", "primary_claim_id": "C"}
    assert main(arguments(tmp_path, "assess", assessment, config, output="cli-assess")) == 8
    assessed = json.loads(capsys.readouterr().out)["assessment"]
    assert assessed["record_ref"] == executed["record_ref"]
    assert [(item["claim_id"], item["verdict"]) for item in assessed["claims"]] == [
        ("F", "PASS"), ("C", "FAIL"), ("M", "PASS"),
    ]
