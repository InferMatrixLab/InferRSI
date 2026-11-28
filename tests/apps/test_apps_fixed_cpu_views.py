"""Keep real CPU facts fixed across the Apps read-only views."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.request import urlopen

import pytest

from inferrsi.apps import api as apps_api
from inferrsi.apps.cli import main
from inferrsi.apps.views.dashboard_live import DashboardServer
from inferrsi.contracts.json_v1 import encode
from inferrsi.harness.executor import prepare_generation
from inferrsi.harness.records import RunStore, RunStoreReader, allocate_attempt
from inferrsi.harness.records._run_store import Claim
from tests.apps.test_apps_generation_plan import generation as generation
from tests.harness import test_harness_generation_seal as seal_tests
from tests.harness.test_harness_generation_seal import cpu_generation as cpu_generation


@pytest.mark.parametrize("linked", [False, True], ids=["unlinked", "controlled-link"])
def test_real_cpu_record_is_shared_by_all_read_only_surfaces(
    cpu_generation, tmp_path, capsys, linked,
):
    store, target, harness, _, inputs = cpu_generation
    spec = prepare_generation(store, target, **inputs)
    record = harness(spec)
    assert record["exit_code"] == 0
    generation_ref = None
    if linked:
        generation_ref = deepcopy(record["record_ref"])
        following = deepcopy(spec)
        following.update(allocate_attempt(**{key: inputs["attempt"][key] for key in (
            "run_id", "owner", "target_request", "deadline_utc", "resources", "budget",
            "retry_of", "retry_reason",
        )}))
        following["output_root"] = "linked-view/" + following["attempt_id"]
        commit = Claim.commit

        def controlled_link(claim, payload, artifacts=()):
            # Read-side metadata control, not production lineage admission. Both CPU runs are real.
            return commit(claim, {**payload, "generation_record_ref": generation_ref}, artifacts)

        with patch.object(Claim, "commit", controlled_link):
            record = harness(following)
        assert record["exit_code"] == 0
    record_ref = record["record_ref"]
    before = store.committed(record["attempt_id"])
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    config = {
        "schema_version": 1,
        "archive_namespace": "fixtures",
        "harness_namespace": "generation",
        "mounts": [
            {"kind": "directory", "namespace": "fixtures", "prefix": "fixtures",
             "root": str(archive_root)},
            {"kind": "harness_sqlite", "namespace": "generation", "prefix": "stores/generation",
             "root": str(store.root)},
        ],
    }
    flags = []
    for name, value in (("record-ref", record_ref), ("storage-config", config)):
        path = tmp_path / (name + ".json")
        path.write_bytes(encode(value))
        flags.extend(("--" + name, str(path)))

    def forbidden(*args, **kwargs):
        raise AssertionError("a read-only surface attempted execution, assessment or a write")

    committed = RunStoreReader.committed

    def fixed_revision_only(reader, attempt_id, record_version=None):
        assert (attempt_id, record_version) == (
            record_ref["attempt_id"], record_ref["record_version"],
        )
        return committed(reader, attempt_id, record_version)

    with (
        patch("inferrsi.harness.executor.execute_attempt", forbidden),
        patch("inferrsi.harness.records.allocate_attempt", forbidden),
        patch.object(RunStore, "claim", forbidden),
        patch.object(Claim, "commit", forbidden),
        patch.object(apps_api, "assess", forbidden),
        patch.object(subprocess, "Popen", forbidden),
        patch.object(RunStoreReader, "committed", fixed_revision_only),
    ):
        expected = apps_api.read_attempt_view(record_ref, storage_config=config)
        assert expected["assessment"] is None
        assert expected["assessment_ref"] is None
        assert expected["execution"]["attempt_id"] == record["attempt_id"]
        assert expected["execution"]["exit_code"] == 0
        assert expected["execution"]["generation_record_ref"] == generation_ref

        assert main(["status", *flags]) == 0
        assert json.loads(capsys.readouterr().out) == expected
        assert main(["trace", *flags]) == 0
        traced = json.loads(capsys.readouterr().out)
        assert traced == apps_api.read_attempt_view(
            record_ref, storage_config=config, include_trace=True,
        )
        assert {key: traced[key] for key in expected} == expected
        assert traced["trace"]["steps"]

        documents = {}
        for command in ("report", "dashboard"):
            output = tmp_path / (command + ".html")
            assert main([command, *flags, "--output", str(output)]) == 0
            assert json.loads(capsys.readouterr().out) == {command: str(output.resolve())}
            document = output.read_text(encoding="utf-8")
            assert record_ref["artifact"]["sha256"] in document
            assert record["attempt_id"] in document
            if generation_ref is not None:
                assert generation_ref["attempt_id"] in document
                assert generation_ref["artifact"]["sha256"] in document
                assert generation_ref["artifact"]["location"] not in document
            else:
                assert "Not linked" in document
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
import json, sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from unittest.mock import patch
from inferrsi.apps import api
from inferrsi.harness import executor, records
from inferrsi.harness.records import RunStore
from inferrsi.harness.records._run_store import Claim
def forbidden(*args, **kwargs):
    raise AssertionError('read-only child attempted execution, assessment or a write')
with patch.object(executor, 'execute_attempt', forbidden), \
     patch.object(records, 'allocate_attempt', forbidden), \
     patch.object(RunStore, 'claim', forbidden), \
     patch.object(Claim, 'commit', forbidden), patch.object(api, 'assess', forbidden):
    view = api.read_attempt_view(
        json.loads(Path(sys.argv[2]).read_text()),
        storage_config=json.loads(Path(sys.argv[3]).read_text()),
        include_trace=True,
    )
print(json.dumps(view))
"""
    source = str(Path(seal_tests.__file__).resolve().parents[2] / "src")
    result = subprocess.run(
        [sys.executable, "-I", "-c", child, source,
         str(tmp_path / "record-ref.json"), str(tmp_path / "storage-config.json")],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == traced
    after = store.committed(record["attempt_id"])
    assert after.record_ref == before.record_ref == record_ref
    assert after.payload_bytes == before.payload_bytes
