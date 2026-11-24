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

ROOT = Path(__file__).resolve().parents[2]
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
    monkeypatch.setattr(execution_service.local_process, "_supervise", forbidden)
    monkeypatch.setattr(execution_service, "_argv", forbidden)
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


def replace_prepared(binding, path, value):
    spec, reader, _, _ = binding
    prepared = decode(reader.data)
    parent = prepared
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    reader.data = encode(prepared)
    spec["prepared_ref"]["artifact"].update(
        sha256=sha256(reader.data).hexdigest(), size_bytes=len(reader.data),
    )


@pytest.mark.parametrize("path,value", [
    (("prepared_ref", "prepared_id"), "sha256:" + "0" * 64),
    (("operation",), "different"), (("validation_scope",), "different"),
])
def test_all_preparation_identity_disagreements_precede_registration(binding, path, value):
    spec, reader, store, harness = binding
    parent = spec
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    with pytest.raises(PublicError) as caught:
        harness.execute(spec)
    assert caught.value.code == "IdentityMismatch"
    assert len(reader.opens) == 1
    assert_empty(store)


@pytest.mark.parametrize("field,value", [
    ("runtime_role", "another-python"), ("entrypoint_kind", "executable"),
    ("entrypoint", "another_worker"), ("entrypoint_revision", "2"),
    ("args", ["inputs/candidate.txt", "outputs/other.json"]), ("cwd", "elsewhere"),
    ("outputs", []),
])
def test_worker_declarations_must_preserve_the_frozen_recipe(binding, field, value):
    spec, reader, store, harness = binding
    spec["steps"][0][field] = value
    with pytest.raises(PublicError) as caught:
        harness.execute(spec)
    assert caught.value.code == "InvalidExecutionSpec"
    assert caught.value.stage == "prepared_binding"
    assert len(reader.opens) == 1
    assert_empty(store)


@pytest.mark.parametrize("field,value", [
    ("path", "inputs/candidate.txt"), ("required", False), ("role", "other"),
    ("media_type", "text/plain"), ("format_schema", {"name": "fixture-grader", "revision": "2"}),
])
def test_output_relabeling_cannot_change_the_frozen_worker_contract(binding, field, value):
    spec, _, store, harness = binding
    spec["steps"][0]["outputs"][0][field] = value
    with pytest.raises(PublicError) as caught:
        harness.execute(spec)
    assert caught.value.code == "InvalidExecutionSpec"
    assert_empty(store)


@pytest.mark.parametrize("failure", ["capability", "missing-role", "overlap", "extra-step"])
def test_incomplete_or_ambiguous_worker_binding_is_refused(binding, failure):
    spec, _, store, harness = binding
    if failure == "capability":
        spec["required_capabilities"] = []
    elif failure == "missing-role":
        replace_prepared(binding, ("recipe", "input_roles"), ["candidate", "config"])
    elif failure == "extra-step":
        extra = deepcopy(spec["steps"][0])
        extra["step_id"] = "extra"
        spec["steps"].append(extra)
    else:
        # Keep argument binding internally consistent while overlapping an output.
        spec["inputs"][0]["materialized_path"] = "outputs"
        spec["steps"][0]["args"][0] = "outputs"
    with pytest.raises(PublicError) as caught:
        harness.execute(spec)
    assert caught.value.code == "InvalidExecutionSpec"
    assert_empty(store)


@pytest.mark.parametrize("path,value", [
    (("schema_version",), True), (("schema_version",), 2),
    (("candidate_contract",), None), (("candidate_contract", "identity_rule"), {}),
    (("expected_candidate",), {}), (("expected_candidate", "sha256"), None),
    (("recipe",), None), (("recipe", "code_sha256"), None),
    (("recipe", "runtime_role"), None), (("recipe", "entrypoint_kind"), "unknown"),
    (("recipe", "entrypoint"), None), (("recipe", "entrypoint_revision"), ""),
    (("recipe", "args"), [None]), (("recipe", "args"), ["{input:unknown}"]),
    (("recipe", "args"), ["prefix{input:candidate}"]),
    (("recipe", "input_roles"), ["candidate", "candidate"]),
    (("recipe", "required_capabilities"), [None]),
    (("recipe", "outputs"), [{}]), (("recipe", "outputs", 0, "path"), "../outside"),
    (("recipe", "outputs", 0, "format_schema"), {}),
])
def test_malformed_fixed_projection_is_refused_with_a_declared_error(binding, path, value):
    _, _, store, harness = binding
    replace_prepared(binding, path, value)
    with pytest.raises(PublicError) as caught:
        harness.execute(binding[0])
    assert caught.value.code == ("UnsupportedSchema" if value == 2 else "InvalidExecutionSpec")
    assert_empty(store)


@pytest.mark.parametrize("revision", ["2", "unknown"])
def test_unknown_candidate_identity_revision_is_never_downgraded(binding, revision):
    spec, _, store, harness = binding
    replace_prepared(binding, ("candidate_contract", "identity_rule", "revision"), revision)
    with pytest.raises(PublicError) as caught:
        harness.execute(spec)
    assert caught.value.code == "UnsupportedRuleVersion"
    assert_empty(store)


@pytest.mark.parametrize("rule", ["captured-sha256", "expected-sha256"])
def test_expected_hash_requirement_depends_on_the_frozen_identity_rule(binding, rule):
    spec, _, store, harness = binding
    replace_prepared(binding, ("candidate_contract", "identity_rule", "name"), rule)
    replace_prepared(binding, ("expected_candidate",), None)
    spec["inputs"][0].update(
        expected_sha256=None, source_namespace="controller", source_ref=None,
        source="candidate.txt",
    )
    with pytest.raises(PublicError) as caught:
        harness.execute(spec)
    assert caught.value.code == ("InvalidExecutionSpec" if rule == "expected-sha256"
                                 else "UnsupportedOperation")
    assert_empty(store)


@pytest.mark.parametrize("mode", ["noncanonical", "duplicate-key", "array", "extra-field"])
def test_unparseable_or_unknown_preparation_fields_never_register(binding, mode):
    spec, reader, store, harness = binding
    if mode == "noncanonical":
        reader.data += b"\n"
    elif mode == "duplicate-key":
        reader.data = reader.data[:-1] + b',"schema_version":1}'
    elif mode == "array":
        reader.data = b"[]"
    else:
        replace_prepared(binding, ("unknown",), True)
    spec["prepared_ref"]["artifact"].update(
        sha256=sha256(reader.data).hexdigest(), size_bytes=len(reader.data),
    )
    with pytest.raises(PublicError) as caught:
        harness.execute(spec)
    expected = ("ArtifactIntegrityError" if mode in {"noncanonical", "duplicate-key"}
                else "InvalidExecutionSpec")
    assert caught.value.code == expected
    assert_empty(store)


@pytest.mark.parametrize("path,value", [
    (("schema_version",), True), (("schema_version",), 2), (("unknown",), None),
    (("prepared_ref",), None), (("prepared_ref", "schema_version"), 2),
    (("prepared_ref", "artifact", "location"), "../outside"),
    (("prepared_ref", "artifact", "size_bytes"), True),
    (("prepared_ref", "artifact", "sha256"), "A" * 64),
    (("prepared_ref", "artifact", "media_type"), "text/plain"),
    (("protocol_digest",), "invalid"), (("candidate",), {}),
    (("candidate", "kind"), None), (("candidate", "parent_id"), "parent"),
    (("candidate", "context_refs"), [None]), (("candidate", "input_role"), "absent"),
    (("steps", 0, "expected_code_sha256"), "invalid"),
])
def test_static_shape_errors_never_open_the_preparation(binding, path, value):
    spec, reader, store, harness = binding
    parent = spec
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    with pytest.raises(PublicError) as caught:
        harness.execute(spec)
    assert caught.value.code == ("UnsupportedSchema" if path == ("schema_version",) and value == 2
                                 else "InvalidExecutionSpec")
    assert reader.opens == []
    assert_empty(store)


@pytest.mark.parametrize("mode", ["undersize", "oversize", "wrong-hash", "missing", "os-error"])
def test_fixed_byte_reader_closes_streams_and_bounds_reads(binding, mode):
    spec, reader, store, harness = binding
    original = spec["prepared_ref"]["artifact"]
    sizes = []

    class Tracking(BytesIO):
        def read(self, size=-1):
            sizes.append(size)
            return super().read(size)

    stream = Tracking(reader.data + (b"x" if mode == "oversize" else b""))

    class Tracked:
        def open(self, ref):
            if mode == "os-error":
                raise FileNotFoundError("fixture missing")
            return stream

    if mode == "undersize":
        original["size_bytes"] += 1
    elif mode == "wrong-hash":
        original["sha256"] = "0" * 64
    with pytest.raises(PublicError) as caught:
        prepared_binding.verify(spec, None if mode == "missing" else Tracked())
    assert caught.value.code == ("ArtifactUnavailable" if mode in {"missing", "os-error"}
                                 else "ArtifactIntegrityError")
    if mode not in {"missing", "os-error"}:
        assert stream.closed
        assert max(sizes) <= original["size_bytes"] + 1
    assert_empty(store)


def test_reader_cannot_rewrite_the_ref_it_is_meant_to_verify(binding):
    spec, _, store, _ = binding
    original = deepcopy(spec["prepared_ref"]["artifact"])

    class Mutating:
        def open(self, ref):
            ref.update(sha256=sha256(b"{}").hexdigest(), size_bytes=2)
            return BytesIO(b"{}")

    with pytest.raises(PublicError) as caught:
        prepared_binding.verify(spec, Mutating())
    assert caught.value.code == "ArtifactIntegrityError"
    assert spec["prepared_ref"]["artifact"] == original
    assert_empty(store)


def test_reader_programming_errors_propagate_without_registration(binding):
    spec, _, store, _ = binding

    class Broken:
        def open(self, ref):
            raise TypeError("broken host reader")

    with pytest.raises(TypeError, match="broken host reader"):
        prepared_binding.verify(spec, Broken())
    assert_empty(store)
