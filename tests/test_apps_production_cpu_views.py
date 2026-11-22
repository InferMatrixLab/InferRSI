"""Production CPU records and assessments shared by every read-only Apps surface."""

import json
import sqlite3
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.request import urlopen

import pytest

from inferrsi.apps import api
from inferrsi.apps.cli import main
from inferrsi.apps.storage import archive
from inferrsi.apps.storage.artifact_reader import ArtifactReader
from inferrsi.apps.views.dashboard_live import DashboardServer
from inferrsi.benchmark import assessment, cpu_smoke, preparation, proofs
from inferrsi.benchmark.workers import fixture_worker as worker
from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness import execution_service
from inferrsi.harness.api import Harness, LocalCpuTarget
from inferrsi.harness.run_store import Claim, RunStore

ROOT = Path(__file__).resolve().parents[1]


class TableRows(HTMLParser):
    """Read displayed cells without depending on the renderer's HTML whitespace."""

    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], [], None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td":
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td":
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row:
            self.rows.append(tuple(self.row))


@pytest.fixture(params=["correct", "wrong", "invalid-utf8", "missing"])
def production_attempt(tmp_path, request):
    kind = request.param
    directory = tmp_path / "archive"
    directory.mkdir()
    config = {
        "schema_version": 1, "archive_namespace": "apps", "harness_namespace": "test",
        "mounts": [
            {"kind": "directory", "namespace": "apps", "prefix": "archives/local",
             "root": str(directory)},
            {"kind": "harness_sqlite", "namespace": "test", "prefix": "stores/test",
             "root": str(tmp_path / "store")},
        ],
    }
    service = cpu_smoke.prepare_service(control_domain=execution_service._CONTROL_DOMAIN)
    prepared_output = api.prepare(
        {"schema_version": 1, "request": cpu_smoke.default_request()},
        workspace=tmp_path, storage_config=config, prepare_benchmark=service.prepare,
        encode_prepared=preparation.encode, validate_prepared=preparation.validate_prepared,
        output_id="prepare",
    )
    assert prepared_output.result["exit_code"] == 0
    prepared_ref = prepared_output.result["prepared_ref"]
    prepared = archive.read_prepared(config, prepared_ref)
    candidate = {
        "correct": str(sum(worker.INPUT_BYTES)).encode("ascii") + b"\n",
        "wrong": b"wrong\n", "invalid-utf8": b"\xff\n", "missing": b"wrong\n",
    }[kind]
    if kind != "missing":
        (directory / "candidate.txt").write_bytes(candidate)
    source = {
        "location": "archives/local/candidate.txt", "media_type": "text/plain",
        "sha256": sha256(candidate).hexdigest(), "size_bytes": len(candidate),
    }
    vector = decode((ROOT / "tests/fixtures/harness-prepared-binding/d023-null-timeout.json")
                    .read_bytes())
    proposal = {key: deepcopy(vector[key])
                for key in ("candidate", "inputs", "generation_record_ref")}
    proposal["inputs"][0].update(source=source["location"], source_ref=source,
                                 expected_sha256=source["sha256"])
    reader = ArtifactReader(config)
    with reader.open(prepared["protocol"]) as stream:
        projector = proofs.ProofProjector(prepared, stream.read())
    store = RunStore(tmp_path / "store", "test")
    target = LocalCpuTarget("fixture-cpu", "1", work_root=tmp_path / "work",
                            module_root=Path(worker.__file__).parent)
    harness = Harness(
        store, target, artifact_reader=reader,
        evidence_capture=api.EvidenceCapture(
            projector.project, candidate_role="candidate", report_role="grader",
        ),
    )
    attempt = harness.allocate(**{key: vector[key] for key in (
        "run_id", "owner", "target_request", "deadline_utc", "resources", "budget",
        "retry_of", "retry_reason",
    )})
    execute_request = {
        "schema_version": 1, "prepared_ref": prepared_ref, "attempt": attempt,
        "proposal": proposal, "output_root": "attempts/" + attempt["attempt_id"],
    }
    # Persist the complete request before handing it to Apps, as a host must.
    request_file = tmp_path / "execute-request.json"
    request_file.write_bytes(encode(execute_request))
    executed = api.execute(
        decode(request_file.read_bytes()), workspace=tmp_path, storage_config=config,
        execute_harness=harness.execute, output_id="execute",
    )
    assert executed.result["exit_code"] == (3 if kind == "missing" else 0)
    record_ref = executed.result["record_ref"]
    assessed = api.assess(
        {"schema_version": 1, "record_ref": record_ref, "primary_scope": "p1",
         "primary_claim_id": "C"}, workspace=tmp_path, storage_config=config,
        assess_benchmark=assessment.assess, encode_assessment=assessment.encode,
        validate_assessment=assessment.validate_assessment, output_id="assess",
    )
    expected = (["INCONCLUSIVE"] * 3 if kind == "missing" else
                ["FAIL" if kind == "invalid-utf8" else "PASS",
                 "PASS" if kind == "correct" else "FAIL", "PASS"])
    assert [claim["verdict"] for claim in assessed.result["assessment"]["claims"]] == expected
    return config, store, prepared_output, executed, assessed, expected


def test_production_pair_is_fixed_across_all_views_and_a_new_process(
    production_attempt, tmp_path, capsys,
):
    config, store, prepared, executed, assessed, verdicts = production_attempt
    record = executed.result["execution"]
    record_ref, assessment_ref = executed.result["record_ref"], assessed.result["assessment_ref"]
    before = store.committed(record["attempt_id"])
    flags = []
    for name, value in (
        ("record-ref", record_ref), ("assessment-ref", assessment_ref),
        ("storage-config", config),
    ):
        path = tmp_path / f"{name}.json"
        path.write_bytes(encode(value))
        flags.extend((f"--{name}", str(path)))

    def forbidden(*args, **kwargs):
        raise AssertionError("read-only production view attempted execution, assessment or commit")

    with (
        patch.object(Harness, "execute", forbidden), patch.object(Harness, "allocate", forbidden),
        patch.object(RunStore, "claim", forbidden), patch.object(Claim, "commit", forbidden),
        patch.object(api, "assess", forbidden), patch.object(assessment, "assess", forbidden),
        patch.object(subprocess, "Popen", forbidden),
    ):
        expected = api.read_attempt_view(
            record_ref, storage_config=config, assessment_ref=assessment_ref,
        )
        assert expected["record_ref"] == record_ref
        assert expected["assessment_ref"] == assessment_ref
        assert expected["execution"]["exit_code"] == record["exit_code"]
        assert [claim["verdict"] for claim in expected["assessment"]["claims"]] == verdicts
        assert main(["status", *flags]) == 0
        assert json.loads(capsys.readouterr().out) == expected
        assert main(["trace", *flags]) == 0
        traced = json.loads(capsys.readouterr().out)
        assert {key: traced[key] for key in expected} == expected
        assert traced["trace"]["checks"]
        documents = {}
        for command in ("report", "dashboard"):
            output = tmp_path / f"{command}.html"
            assert main([command, *flags, "--output", str(output)]) == 0
            assert json.loads(capsys.readouterr().out) == {command: str(output.resolve())}
            document = output.read_text(encoding="utf-8")
            assert record_ref["artifact"]["sha256"] in document
            assert assessment_ref["artifact"]["sha256"] in document
            assert record["attempt_id"] in document
            cells = TableRows()
            cells.feed(document)
            for claim in expected["assessment"]["claims"]:
                assert any(row[:3] == (
                    claim["claim_id"], claim["validation_scope"], claim["verdict"],
                ) for row in cells.rows)
            documents[command] = document
        with DashboardServer(None, None, 0, fixed_attempt=traced) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                address = f"http://127.0.0.1:{server.server_port}"
                with urlopen(address + "/api/state", timeout=5) as response:
                    assert json.load(response)["data"]["fixed_attempt"] == traced
                with urlopen(address + "/", timeout=5) as response:
                    assert response.read().decode("utf-8") == documents["dashboard"]
            finally:
                server.shutdown()
                thread.join(timeout=5)
                assert not thread.is_alive()

    child = """
import json, subprocess, sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from inferrsi.apps import api
from inferrsi.apps.storage import archive
from inferrsi.benchmark import assessment
from inferrsi.harness.api import Harness
from inferrsi.harness.run_store import Claim, RunStore
def forbidden(*args, **kwargs):
    raise AssertionError('read-only child attempted execution, assessment or commit')
root = Path(sys.argv[2])
load = lambda name: json.loads((root / (name + '.json')).read_text(encoding='utf-8'))
with patch.object(Harness, 'execute', forbidden), patch.object(Harness, 'allocate', forbidden), \
     patch.object(RunStore, 'claim', forbidden), patch.object(Claim, 'commit', forbidden), \
     patch.object(api, 'assess', forbidden), patch.object(assessment, 'assess', forbidden), \
     patch.object(subprocess, 'Popen', forbidden):
    view = api.read_attempt_view(load('record-ref'), storage_config=load('storage-config'),
                                assessment_ref=load('assessment-ref'), include_trace=True)
    outputs = {name: archive.read_result(root, name).result
               for name in ('prepare', 'execute', 'assess')}
print(json.dumps({'view': view, 'outputs': outputs}))
"""
    child_result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", child, str(ROOT / "src"), str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert child_result.returncode == 0, child_result.stderr
    fresh = json.loads(child_result.stdout)
    assert fresh["view"] == traced
    for output in (prepared, executed, assessed):
        assert fresh["outputs"][output.output_id] == output.result
        result_bytes = (output.directory / "result.json").read_bytes()
        assert result_bytes == encode(output.result)
        manifest = decode((output.directory / "manifest.json").read_bytes())
        assert manifest["output_id"] == output.output_id
        assert manifest["operation"] == output.result["operation"]
        assert manifest["result"] == {
            "path": "result.json", "sha256": sha256(result_bytes).hexdigest(),
            "size_bytes": len(result_bytes), "media_type": "application/json",
        }
    after = store.committed(record["attempt_id"])
    assert after.record_ref == before.record_ref == record_ref
    assert after.payload_bytes == before.payload_bytes


def test_production_publication_failure_keeps_refs_and_replays_in_a_new_process(
    production_attempt, tmp_path, monkeypatch,
):
    config, store, _, executed, assessed, _ = production_attempt
    record_ref = executed.result["record_ref"]
    request_path = tmp_path / "execute-request.json"
    saved_bytes = request_path.read_bytes()
    saved = decode(saved_bytes)
    before = store.committed(record_ref["attempt_id"])
    # A changed/missing original source must not turn replay into a fresh attempt.
    (tmp_path / "archive" / "candidate.txt").write_bytes(b"changed after original attempt\n")
    retired = Harness(
        store, LocalCpuTarget("retired", "2", work_root=tmp_path / "retired"),
        artifact_reader=object(), evidence_capture=object(),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("replay attempted a process or a new committed record")

    def publication_failure(*args, **kwargs):
        raise OSError("synthetic replay publication failure")

    with (
        monkeypatch.context() as fault,
        patch.object(subprocess, "Popen", forbidden), patch.object(Claim, "commit", forbidden),
    ):
        fault.setattr(archive, "_publish_directory", publication_failure)
        failed = api.execute(
            decode(saved_bytes), workspace=tmp_path, storage_config=config,
            execute_harness=retired.execute, output_id="failed-replay",
        )
    assert failed.directory is None
    assert failed.result["exit_code"] == 6
    assert failed.result["record_ref"] == record_ref
    assert failed.result["error"]["latest_record_ref"] == record_ref
    assert not (tmp_path / "output" / "failed-replay").exists()
    (tmp_path / "storage-config.json").write_bytes(encode(config))
    child = """
import json, subprocess, sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from inferrsi.apps import api
from inferrsi.apps.storage import archive
from inferrsi.harness.api import Harness, LocalCpuTarget
from inferrsi.harness.run_store import Claim, RunStore
root = Path(sys.argv[2])
load = lambda name: json.loads((root / (name + '.json')).read_text(encoding='utf-8'))
store = RunStore(root / 'store', 'test')
harness = Harness(store, LocalCpuTarget('retired', '2', work_root=root / 'retired'),
                  artifact_reader=object(), evidence_capture=object())
def forbidden(*args, **kwargs):
    raise AssertionError('replay child attempted a process, allocation or commit')
with patch.object(subprocess, 'Popen', forbidden), patch.object(Claim, 'commit', forbidden), \
     patch.object(Harness, 'allocate', forbidden):
    output = api.execute(load('execute-request'), workspace=root,
                         storage_config=load('storage-config'),
                         execute_harness=harness.execute, output_id='child-replay')
    assert archive.read_result(root, 'child-replay').result == output.result
print(json.dumps(output.result))
"""
    replay = subprocess.run(
        [sys.executable, "-I", "-B", "-c", child, str(ROOT / "src"), str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert replay.returncode == 0, replay.stderr
    result = json.loads(replay.stdout)
    assert result["record_ref"] == record_ref
    # V15 adds a fresh observation envelope; only the committed facts are fixed.
    execution = result["execution"]
    assert execution.keys() == before.payload.keys() | {
        "record_ref", "observed_at", "controller_observation",
    }
    assert {key: execution[key] for key in before.payload} == before.payload
    assert execution["controller_observation"] == {
        "status": "unavailable", "source": "harness-run-store",
        "observed_at": execution["observed_at"], "facts": {},
    }
    assert result["attempt_id"] == saved["attempt"]["attempt_id"]
    assert result["exit_code"] == executed.result["exit_code"]
    assert request_path.read_bytes() == saved_bytes
    after = store.committed(record_ref["attempt_id"])
    assert after.record_ref == before.record_ref
    assert after.payload_bytes == before.payload_bytes
    assert archive.read_assessment(config, assessed.result["assessment_ref"]) == (
        assessed.result["assessment"]
    )
    with sqlite3.connect(store.root / "index.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM records").fetchone()[0] == 1
