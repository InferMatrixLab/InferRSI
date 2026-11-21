"""PR-1: bind frozen preparation before registration; never perform T37 entry checks."""

import sqlite3
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest

from inferrsi.apps.handoff.bridge import bind_execution, verify_protocol
from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness import execution_service, prepared_binding, run_store
from inferrsi.harness.api import Harness, LocalCpuTarget
from inferrsi.harness.errors import PublicError

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs/contracts/fixtures/t108-v4"
VECTOR = ROOT / "tests/fixtures/harness-prepared-binding/d023-null-timeout.json"
DIGEST = "sha256:62ce11e6d458b5c581245d0988189e1bd834f2ed1e1880d15242faf70c5b6fe9"


def test_d023_null_timeout_bytes_match_apps_and_harness():
    data = VECTOR.read_bytes()
    spec = decode(data)
    prepared = decode((GOLDEN / "prepared.json").read_bytes())
    verify_protocol(prepared, (GOLDEN / "protocol.json").read_bytes())
    request = {
        "schema_version": 1, "prepared_ref": spec["prepared_ref"],
        "attempt": {key: spec[key] for key in execution_service.ATTEMPT_FIELDS},
        "proposal": {key: spec[key] for key in ("candidate", "inputs", "generation_record_ref")},
        "output_root": spec["output_root"],
    }
    assert len(data) == 2069
    assert "sha256:" + sha256(data).hexdigest() == DIGEST
    assert run_store.request_digest(spec) == DIGEST
    assert encode(bind_execution(request, prepared)) == data
    assert spec["steps"][0]["timeout_seconds"] is None


@pytest.fixture
def binding(tmp_path, monkeypatch):
    spec = decode(VECTOR.read_bytes())
    prepared = (GOLDEN / "prepared.json").read_bytes()

    class Reader:
        def __init__(self):
            self.opens = []
            self.data = prepared

        def open(self, ref):
            assert ref == spec["prepared_ref"]["artifact"]
            self.opens.append(deepcopy(ref))
            return BytesIO(self.data)

    reader = Reader()
    store = run_store.RunStore(tmp_path / "store", "binding-tests")
    target = LocalCpuTarget("fixture-cpu", "1", work_root=tmp_path / "work")
    harness = Harness(store, target, artifact_reader=reader)

    def forbidden(*args, **kwargs):
        pytest.fail("a PR-1 refusal reached registration or process execution")

    monkeypatch.setattr(store, "claim", forbidden)
    monkeypatch.setattr(execution_service.local_process, "execute_command", forbidden)
    return spec, reader, store, harness


def assert_empty(store):
    with sqlite3.connect(store.root / run_store.INDEX_NAME) as connection:
        assert connection.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM records").fetchone()[0] == 0


def test_projection_reads_the_fixed_preparation_without_resolving_an_entry(binding):
    spec, reader, store, harness = binding
    fixed = prepared_binding.verify(spec, reader)
    assert fixed.prepared_id == spec["prepared_ref"]["prepared_id"]
    assert fixed.code_sha256 == spec["steps"][0]["expected_code_sha256"]
    assert len(reader.opens) == 1
    # T37 is a later delivery: valid evaluation bindings still cannot start.
    with pytest.raises(PublicError) as caught:
        harness.execute(spec)
    assert caught.value.code == "UnsupportedOperation"
    assert_empty(store)


@pytest.mark.parametrize("failure", ["null-code", "wrong-code", "protocol", "candidate", "input"])
def test_malformed_or_inconsistent_binding_registers_no_attempt(binding, failure):
    spec, reader, store, harness = binding
    if failure == "null-code":
        spec["steps"][0]["expected_code_sha256"] = None
    elif failure == "wrong-code":
        spec["steps"][0]["expected_code_sha256"] = "0" * 64
    elif failure == "protocol":
        spec["protocol_digest"] = "sha256:" + "0" * 64
    elif failure == "candidate":
        spec["candidate"]["candidate_id"] = "different-candidate"
    else:
        spec["inputs"][0]["expected_sha256"] = "0" * 64
        spec["inputs"][0]["source_ref"]["sha256"] = "0" * 64
    with pytest.raises(PublicError) as caught:
        harness.execute(spec)
    assert caught.value.code == ("IdentityMismatch" if failure == "protocol"
                                 else "InvalidExecutionSpec")
    assert_empty(store)
    assert len(reader.opens) == (0 if failure == "null-code" else 1)


def test_corrupt_preparation_bytes_cannot_reach_registration(binding):
    spec, reader, store, harness = binding
    reader.data = b"corrupt retained preparation"
    with pytest.raises(PublicError) as caught:
        harness.execute(spec)
    assert caught.value.code == "ArtifactIntegrityError"
    assert_empty(store)
