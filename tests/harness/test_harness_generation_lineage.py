"""Carry a genuinely generated, retained candidate into the production CPU task."""

import sqlite3
import subprocess
import sys
import threading
from copy import deepcopy
from dataclasses import replace
from functools import partial
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest

from inferrsi.apps import api
from inferrsi.apps.storage import archive
from inferrsi.apps.storage.artifact_reader import ArtifactReader
from inferrsi.benchmark import assessment, cpu_smoke, preparation, proofs
from inferrsi.benchmark.workers import fixture_worker as worker
from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness.api import PublicError
from inferrsi.harness.executor import _execution as execution_service
from inferrsi.harness.executor import _generation_lineage as generation_lineage
from inferrsi.harness.executor import execute_attempt, prepare_generation, request_digest
from inferrsi.harness.records import _run_store as run_store
from inferrsi.harness.records import allocate_attempt
from tests.apps.test_apps_generation_plan import _fixed_input
from tests.apps.test_apps_generation_plan import generation as generation
from tests.harness.test_harness_generation_seal import cpu_generation as cpu_generation


@pytest.fixture
def lineage(
    cpu_generation, tmp_path, request, monkeypatch,
):
    store, target, generation_harness, draft, inputs = cpu_generation
    variant = getattr(request, "param", None)
    if variant in ("failed", "missing-candidate", "missing-role"):
        original_plan = inputs["candidate_provider"].plan_generation

        def changed_plan(context, attempt):
            value = original_plan(context, attempt)
            if variant == "failed":
                value["spec"]["steps"][0]["args"] = ["-c", "raise SystemExit(7)"]
            elif variant == "missing-candidate":
                value["spec"]["steps"][0]["args"] = [
                    "-c", "from pathlib import Path; Path('output').mkdir(); "
                    "Path('output/manifest.json').write_bytes(b'{}')",
                ]
            else:
                value["manifest"]["output_contract"]["candidate_role"] = "absent-candidate"
            return value

        monkeypatch.setattr(inputs["candidate_provider"], "plan_generation", changed_plan)
    with monkeypatch.context() as patch:
        if variant == "legacy":
            original_seal = store._seal_generation_input

            def old_writer(*args, **kwargs):
                # A real pre-bounds writer calls the unchanged seal without this new option.
                kwargs.pop("original_bounds", None)
                return original_seal(*args, **kwargs)

            patch.setattr(store, "_seal_generation_input", old_writer)
        generation_spec = prepare_generation(store, target, **inputs)
    with monkeypatch.context() as patch:
        if variant in ("history", "ambiguous"):
            original_commit = run_store.Claim.commit

            def controlled_commit(claim, payload, artifacts=()):
                # Controlled record metadata/history; the generator and capture remain real.
                artifacts = tuple(artifacts)
                if variant == "history":
                    original_commit(claim, {**payload, "phase": "finalizing"}, artifacts)
                    payload = {**payload, "record_version": claim.next_record_version}
                else:
                    payload = deepcopy(payload)
                    candidate = next(item for item in payload["artifacts"]
                                     if item["role"] == "candidate")
                    payload["artifacts"].append(deepcopy(candidate))
                return original_commit(claim, payload, artifacts)

            patch.setattr(run_store.Claim, "commit", controlled_commit)
        generated = generation_harness(generation_spec)
    assert generated["exit_code"] == (7 if variant == "failed" else 0)
    generation_ref = generated["record_ref"]
    generation_before = store.committed(generated["attempt_id"])
    context_ref = store.read_delivered_context(generated["attempt_id"])["artifact"]
    with store.open(context_ref) as stream:
        context_bytes = stream.read()
    assert context_bytes == draft.content
    if variant in ("failed", "missing-candidate", "missing-role", "ambiguous"):
        # Explicitly declared negative input; no successful collection or task result is claimed.
        source = next((item["artifact"] for item in generated["artifacts"]
                       if item["role"] == "candidate" and item["status"] == "available"),
                      context_ref)
        proposal = {
            "candidate": {"candidate_id": "negative-declaration", "kind": "text",
                          "input_role": "candidate", "parent_id": None, "parent_digest": None,
                          "context_refs": [context_ref]},
            "inputs": [_fixed_input("candidate", source)], "generation_record_ref": generation_ref,
        }
    else:
        proposal = inputs["candidate_provider"].collect_candidate(generated, artifacts=store)
    assert proposal["generation_record_ref"] == generation_ref

    directory = tmp_path / "archive"
    directory.mkdir()
    config = {
        "schema_version": 1, "archive_namespace": "apps", "harness_namespace": "generation",
        "mounts": [
            {"kind": "directory", "namespace": "apps", "prefix": "archives/local",
             "root": str(directory)},
            {"kind": "harness_sqlite", "namespace": "generation", "prefix": "stores/generation",
             "root": str(store.root)},
        ],
    }
    service = cpu_smoke.prepare_service(control_domain=execution_service._CONTROL_DOMAIN)
    prepared_output = api.prepare(
        {"schema_version": 1, "request": cpu_smoke.default_request()},
        workspace=tmp_path, storage_config=config, prepare_benchmark=service.prepare,
        encode_prepared=preparation.encode, validate_prepared=preparation.validate_prepared,
        output_id="generated-prepare",
    )
    assert prepared_output.result["exit_code"] == 0
    prepared_ref = prepared_output.result["prepared_ref"]
    prepared = archive.read_prepared(config, prepared_ref)
    reader = ArtifactReader(config)
    with reader.open(prepared["protocol"]) as stream:
        projector = proofs.ProofProjector(prepared, stream.read())
    evaluation_target = replace(target, module_root=Path(worker.__file__).parent)
    harness = partial(
        execute_attempt,
        store, evaluation_target, artifact_reader=reader,
        evidence_capture=api.EvidenceCapture(
            projector.project, candidate_role="candidate", report_role="grader",
        ),
    )
    attempt = allocate_attempt(**{key: inputs["attempt"][key] for key in (
        "run_id", "owner", "target_request", "deadline_utc", "resources", "budget",
        "retry_of", "retry_reason",
    )})
    assert attempt["attempt_id"] != generated["attempt_id"]
    assert attempt["deadline_utc"] == inputs["attempt"]["deadline_utc"]
    assert attempt["budget"] == inputs["attempt"]["budget"]
    port = api.EvaluationPort(
        storage_config=config, output_root_for=lambda attempt_id: "evaluation/" + attempt_id,
        assess_benchmark=assessment.assess, encode_assessment=assessment.encode,
        validate_assessment=assessment.validate_assessment,
    )
    spec = port.execution_for(prepared_ref, proposal, attempt, scope="p1")
    assert spec["generation_record_ref"] == generation_ref
    return {
        "store": store, "target": target, "harness": harness, "inputs": inputs,
        "generated": generated, "generation_spec": generation_spec, "proposal": proposal,
        "config": config, "reader": reader, "port": port, "spec": spec,
        "evaluation_target": evaluation_target,
        "generation_before": generation_before, "context_ref": context_ref,
        "context_bytes": context_bytes,
    }


def test_large_candidate_integrity_check_does_not_collect_content():
    payload = b"x" * (3 * 1024 * 1024 + 17)
    ref = {
        "location": "stores/test/objects/large-candidate",
        "sha256": sha256(payload).hexdigest(),
        "size_bytes": len(payload),
        "media_type": "application/octet-stream",
    }

    class Store:
        def open(self, actual):
            assert actual == ref
            return BytesIO(payload)

    assert generation_lineage._read(Store(), ref, collect=False) is None


def test_generated_candidate_uses_a_separate_production_evaluation_attempt(lineage):
    store, harness, spec, port = (lineage[key] for key in ("store", "harness", "spec", "port"))
    generated = lineage["generated"]
    generation_ref = generated["record_ref"]
    evaluated = harness(spec)
    assert evaluated["exit_code"] == 0
    assert evaluated["generation_record_ref"] == generation_ref
    assert evaluated["attempt_id"] == spec["attempt_id"]
    summary = port.assess(evaluated)
    assert summary["attempt_id"] == spec["attempt_id"]
    # The generator emits UTF-8 context, deliberately not this task's correct sum.
    assert [(claim["claim_id"], claim["verdict"]) for claim in summary["claims"]] == [
        ("F", "PASS"), ("C", "FAIL"), ("M", "PASS"),
    ]
    decision = archive.read_assessment(lineage["config"], summary["assessment_ref"])
    assert decision["record_ref"] == evaluated["record_ref"]
    assert decision["record_ref"] != generation_ref
    assert decision["candidate"] == lineage["proposal"]["candidate"]
    view = api.read_attempt_view(
        evaluated["record_ref"], storage_config=lineage["config"],
        assessment_ref=summary["assessment_ref"], include_trace=True,
    )
    assert view["execution"]["exit_code"] == 0
    assert view["assessment"]["claims"][1]["verdict"] == "FAIL"
    generation_after = store.committed(generated["attempt_id"])
    assert generation_after.record_ref == lineage["generation_before"].record_ref
    assert generation_after.payload_bytes == lineage["generation_before"].payload_bytes
    with store.open(lineage["context_ref"]) as stream:
        assert stream.read() == lineage["context_bytes"]


def _forbid_claim(monkeypatch, store):
    def forbidden(*args, **kwargs):
        pytest.fail("fresh lineage refusal registered an attempt")
    monkeypatch.setattr(store, "claim", forbidden)


@pytest.mark.parametrize("change,code", [
    ("owner", "IdentityMismatch"), ("run", "IdentityMismatch"),
    ("foreign-store", "UnsupportedOperation"), ("missing-record", "RecordNotFound"),
    ("missing-version", "RecordNotFound"), ("ref-checksum", "IdentityMismatch"),
    ("ref-size", "IdentityMismatch"), ("budget-scope", "IdentityMismatch"),
    ("unregistered-self", "IdentityMismatch"),
    ("budget-policy", "IdentityMismatch"), ("later-deadline", "IdentityMismatch"),
    ("later-fraction", "IdentityMismatch"),
    ("source-alias", "IdentityMismatch"), ("source-path", "IdentityMismatch"),
    ("unverified-input", "InvalidExecutionSpec"), ("invalid-ref", "InvalidExecutionSpec"),
    ("boolean-version", "InvalidExecutionSpec"), ("zero-version", "InvalidExecutionSpec"),
])
def test_fresh_lineage_refusals_register_nothing(lineage, monkeypatch, change, code):
    store = lineage["store"]
    spec = deepcopy(lineage["spec"])
    ref = spec["generation_record_ref"]
    candidate = next(item for item in spec["inputs"]
                     if item["role"] == spec["candidate"]["input_role"])
    if change == "owner":
        spec["owner"] = "different-owner"
    elif change == "run":
        spec["run_id"] = "different-run"
    elif change == "foreign-store":
        ref["artifact"]["location"] = run_store.record_location(
            "other", ref["attempt_id"], ref["record_version"],
        )
    elif change in ("missing-record", "missing-version"):
        if change == "missing-record":
            ref["attempt_id"] = "absent-generation"
        else:
            ref["record_version"] += 1
        ref["artifact"]["location"] = run_store.record_location(
            store.namespace, ref["attempt_id"], ref["record_version"],
        )
    elif change == "ref-checksum":
        ref["artifact"]["sha256"] = "0" * 64
    elif change == "ref-size":
        ref["artifact"]["size_bytes"] += 1
    elif change == "unregistered-self":
        ref["attempt_id"] = spec["attempt_id"]
        ref["artifact"]["location"] = run_store.record_location(
            store.namespace, ref["attempt_id"], ref["record_version"],
        )
    elif change == "budget-scope":
        spec["budget"]["scope_id"] = "different-scope"
    elif change == "budget-policy":
        spec["budget"]["policy_ref"] = {"name": "different-policy", "revision": "1"}
    elif change == "later-deadline":
        spec["deadline_utc"] = "2099-01-02T00:00:00Z"
    elif change == "later-fraction":
        spec["deadline_utc"] = "2099-01-01T00:00:00.0000001Z"
    elif change == "source-alias":
        alias = lineage["context_ref"]
        assert alias["sha256"] == candidate["source_ref"]["sha256"]
        assert alias != candidate["source_ref"]
        candidate.update(source=alias["location"], source_ref=deepcopy(alias))
    elif change == "source-path":
        candidate.update(source="candidate.txt", source_namespace="controller", source_ref=None)
    elif change == "unverified-input":
        candidate["expected_sha256"] = None
    elif change == "invalid-ref":
        spec["generation_record_ref"] = []
    else:
        ref["record_version"] = True if change == "boolean-version" else 0
    _forbid_claim(monkeypatch, store)
    with pytest.raises(PublicError) as caught:
        lineage["harness"](spec)
    expected_started = None if change == "unverified-input" else False
    assert (caught.value.code, caught.value.stage, caught.value.started) == (
        code, "validate", expected_started,
    )
    with pytest.raises(PublicError, match="NoCommittedRecord"):
        store.committed(spec["attempt_id"])


@pytest.mark.parametrize("deadline", [
    "2098-01-01T00:00:00Z", "2099-01-01T00:00:00.000000000Z",
])
def test_no_later_evaluation_deadline_keeps_original_bounds(lineage, deadline):
    store, spec = lineage["store"], deepcopy(lineage["spec"])
    original = store._read_generation_bounds(lineage["generated"]["attempt_id"])
    spec["deadline_utc"] = deadline
    result = lineage["harness"](spec)
    assert result["exit_code"] == 0
    assert result["generation_record_ref"] == lineage["generated"]["record_ref"]
    assert store._read_generation_bounds(lineage["generated"]["attempt_id"]) == original


def test_expired_original_refuses_before_registration(lineage, monkeypatch):
    _forbid_claim(monkeypatch, lineage["store"])
    monkeypatch.setattr(run_store, "utc_now", lambda: "2100-01-01T00:00:00Z")
    with pytest.raises(PublicError) as caught:
        lineage["harness"](lineage["spec"])
    assert (caught.value.code, caught.value.stage) == ("UnsupportedOperation", "validate")


def test_public_validation_without_store_cannot_authorize_lineage(lineage):
    with pytest.raises(PublicError) as caught:
        execution_service.validate(lineage["spec"], lineage["evaluation_target"],
                                   artifact_reader=lineage["reader"])
    assert (caught.value.code, caught.value.stage) == ("UnsupportedOperation", "validate")


def test_registered_generation_attempt_reuse_keeps_conflict_precedence(lineage, monkeypatch):
    spec = deepcopy(lineage["spec"])
    spec["attempt_id"] = spec["request_id"] = lineage["generated"]["attempt_id"]
    _forbid_claim(monkeypatch, lineage["store"])
    monkeypatch.setattr(generation_lineage, "authorize",
                        lambda *args: pytest.fail("registered conflict read lineage"))
    with pytest.raises(PublicError) as caught:
        lineage["harness"](spec)
    assert (caught.value.code, caught.value.stage) == ("RequestConflict", "claim")


@pytest.mark.parametrize("lineage,code", [
    ("legacy", "UnsupportedOperation"), ("failed", "UnsupportedOperation"),
    ("missing-candidate", "ArtifactUnavailable"), ("missing-role", "IdentityMismatch"),
    ("ambiguous", "IdentityMismatch"),
], indirect=["lineage"])
def test_real_generation_boundaries_refuse_before_claim(lineage, monkeypatch, code):
    store, generated = lineage["store"], lineage["generated"]
    before = store.committed(generated["attempt_id"])
    _forbid_claim(monkeypatch, store)
    with pytest.raises(PublicError) as caught:
        lineage["harness"](lineage["spec"])
    assert (caught.value.code, caught.value.stage, caught.value.started) == (
        code, "validate", False,
    )
    assert store.committed(generated["attempt_id"]).payload_bytes == before.payload_bytes


def _retained_path(lineage, family):
    payload = lineage["generation_before"].payload
    if family == "candidate":
        ref = next(item["artifact"] for item in payload["artifacts"]
                   if item["role"] == "candidate")
    else:
        ref = next(item["retained_ref"] for item in payload["bound_inputs"]
                   if item["role"] == "generation_plan")
    store = lineage["store"]
    relative = ref["location"].removeprefix(f"stores/{store.namespace}/")
    path = (store.root / relative).resolve()
    assert path.is_relative_to((store.root / "objects").resolve())
    return path


@pytest.mark.parametrize("family", ["candidate", "plan-copy"])
@pytest.mark.parametrize("damage,code", [
    ("missing", "ArtifactUnavailable"), ("corrupt", "ArtifactIntegrityError"),
])
def test_retained_sources_are_verified_before_claim(lineage, monkeypatch, family, damage, code):
    path = _retained_path(lineage, family)
    if damage == "missing":
        path.unlink()
    else:
        original = path.read_bytes()
        assert original
        path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    _forbid_claim(monkeypatch, lineage["store"])
    with pytest.raises(PublicError) as caught:
        lineage["harness"](lineage["spec"])
    assert (caught.value.code, caught.value.stage, caught.value.started) == (
        code, "validate", False,
    )


def test_candidate_changed_between_validation_and_capture_starts_no_worker(lineage, monkeypatch):
    store = lineage["store"]
    path = _retained_path(lineage, "candidate")
    claim = store.claim

    def change_before_capture(attempt, digest):
        value = claim(attempt, digest)
        path.write_bytes(b"changed after admission")
        return value

    monkeypatch.setattr(store, "claim", change_before_capture)
    monkeypatch.setattr(execution_service, "_run_steps",
                        lambda *args: pytest.fail("damaged candidate started a worker"))
    result = lineage["harness"](lineage["spec"])
    assert result["started"] is False and result["process_outcome"] == "not_started"
    assert result["generation_record_ref"] == lineage["generated"]["record_ref"]
    assert any(item["role"] == "candidate" and "ArtifactIntegrityError" in item["reasons"]
               for item in result["bound_inputs"])
    assert store.committed(result["attempt_id"]).record_ref == result["record_ref"]
    monkeypatch.setattr(generation_lineage, "authorize",
                        lambda *args: pytest.fail("refusal replay read damaged lineage"))
    assert lineage["harness"](lineage["spec"])["record_ref"] == result["record_ref"]


def test_completed_replay_precedes_missing_sources_retired_target_and_expiry(lineage, monkeypatch):
    store, spec = lineage["store"], lineage["spec"]
    result = lineage["harness"](spec)
    for family in ("candidate", "plan-copy"):
        _retained_path(lineage, family).unlink()
    monkeypatch.setattr(run_store, "utc_now", lambda: "2100-01-01T00:00:00Z")
    monkeypatch.setattr(generation_lineage, "authorize",
                        lambda *args: pytest.fail("completed replay revalidated lineage"))
    _forbid_claim(monkeypatch, store)
    retired = replace(lineage["evaluation_target"], target_id="retired", module_root=None)
    replay = execute_attempt(store, retired, spec)
    assert replay["record_ref"] == result["record_ref"]
    assert store.committed(spec["attempt_id"]).payload_bytes == store.committed(
        spec["attempt_id"], result["record_ref"]["record_version"],
    ).payload_bytes


def test_changed_registered_request_conflicts_before_any_fresh_read(lineage, monkeypatch):
    spec = lineage["spec"]
    result = lineage["harness"](spec)
    changed = deepcopy(spec)
    changed["deadline_utc"] = "2099-01-02T00:00:00Z"
    monkeypatch.setattr(generation_lineage, "authorize",
                        lambda *args: pytest.fail("conflict revalidated lineage"))
    _forbid_claim(monkeypatch, lineage["store"])
    with pytest.raises(PublicError) as caught:
        execute_attempt(lineage["store"], lineage["evaluation_target"], changed)
    assert (caught.value.code, caught.value.stage) == ("RequestConflict", "claim")
    assert lineage["store"].committed(spec["attempt_id"]).record_ref == result["record_ref"]


@pytest.mark.parametrize("lineage", ["history"], indirect=True)
def test_nonterminal_fixed_ref_does_not_fall_forward_to_finished_current(lineage, monkeypatch):
    store, generated = lineage["store"], lineage["generated"]
    current = store.committed(generated["attempt_id"])
    older = store.committed(generated["attempt_id"], 1)
    assert current.payload["phase"] == "finished" and current.record_ref["record_version"] == 2
    assert older.payload["phase"] == "finalizing"
    spec = deepcopy(lineage["spec"])
    spec["generation_record_ref"] = older.record_ref
    _forbid_claim(monkeypatch, store)
    with pytest.raises(PublicError) as caught:
        lineage["harness"](spec)
    assert (caught.value.code, caught.value.stage) == ("UnsupportedOperation", "validate")
    assert store.committed(generated["attempt_id"]).record_ref == current.record_ref
    assert store.committed(generated["attempt_id"], 1).payload_bytes == older.payload_bytes


def test_unsealed_ordinary_run_cannot_borrow_another_attempts_generation_plan(lineage, monkeypatch):
    spec = deepcopy(lineage["generation_spec"])
    attempt = run_store.allocate_attempt(**{key: lineage["inputs"]["attempt"][key] for key in (
        "run_id", "owner", "target_request", "deadline_utc", "resources", "budget",
        "retry_of", "retry_reason",
    )})
    spec.update(attempt)
    spec["output_root"] = "unsealed/" + attempt["attempt_id"]
    generated = execute_attempt(
        lineage["store"], lineage["target"], spec, artifact_reader=lineage["store"],
    )
    assert generated["exit_code"] == 0
    assert lineage["store"]._read_generation_bounds(generated["attempt_id"]) is None
    evaluation = deepcopy(lineage["spec"])
    evaluation["generation_record_ref"] = generated["record_ref"]
    _forbid_claim(monkeypatch, lineage["store"])
    with pytest.raises(PublicError) as caught:
        lineage["harness"](evaluation)
    assert (caught.value.code, caught.value.stage) == ("UnsupportedOperation", "validate")


@pytest.mark.parametrize("fault,code", [
    ("record-bytes", "RecordIntegrityError"), ("bounds-bytes", "ArtifactIntegrityError"),
    ("bounds-budget", "ArtifactIntegrityError"),
])
def test_damaged_store_metadata_is_not_relabelled_as_foreign(lineage, monkeypatch, fault, code):
    store = lineage["store"]
    with store._connection() as connection:
        if fault == "record-bytes":
            # Fault injection in this disposable Store only; production triggers stay unchanged.
            connection.execute("DROP TRIGGER records_no_update")
            connection.execute("UPDATE records SET payload = ?", (b"damaged",))
        else:
            connection.execute("DROP TRIGGER generation_inputs_no_update")
            data = connection.execute(
                "SELECT data FROM generation_inputs WHERE role = 'original-bounds'",
            ).fetchone()[0]
            bounds = decode(data)
            bounds["budget"]["declared_by"] = []
            altered = encode(bounds)
            checksum = sha256(altered if fault == "bounds-budget" else data).hexdigest()
            connection.execute(
                "UPDATE generation_inputs SET data = ?, sha256 = ? WHERE role = 'original-bounds'",
                (altered, checksum),
            )
    _forbid_claim(monkeypatch, store)
    with pytest.raises(PublicError) as caught:
        lineage["harness"](lineage["spec"])
    assert (caught.value.code, caught.value.stage, caught.value.started) == (
        code, "validate", False,
    )


def test_failed_commit_after_real_evaluation_never_replays_the_worker(lineage, monkeypatch):
    store = lineage["store"]
    supervise, processes = execution_service.local_process._supervise, []

    def counted(*args, **kwargs):
        result = supervise(*args, **kwargs)
        processes.append(result["pid"])
        return result

    def broken_append(*args, **kwargs):
        raise sqlite3.OperationalError("local persistence-failure control")

    monkeypatch.setattr(execution_service.local_process, "_supervise", counted)
    monkeypatch.setattr(store, "_append", broken_append)
    with pytest.raises(PublicError) as caught:
        lineage["harness"](lineage["spec"])
    assert caught.value.code == "ExecutionPersistenceError" and caught.value.started is True
    assert caught.value.latest_record_ref is None and caught.value.partial_record.started is True
    assert len(processes) == 1 and processes[0] is not None
    _forbid_claim(monkeypatch, store)
    monkeypatch.setattr(generation_lineage, "authorize",
                        lambda *args: pytest.fail("recovery read fresh lineage"))
    with pytest.raises(PublicError) as recovery:
        lineage["harness"](lineage["spec"])
    assert recovery.value.code == "RecoveryRequired" and recovery.value.started is not False
    assert len(processes) == 1
    assert store.committed(lineage["generated"]["attempt_id"]).record_ref == (
        lineage["generated"]["record_ref"]
    )


@pytest.mark.parametrize("live", [True, False], ids=["live-owner", "owner-gone"])
def test_registered_lineage_without_record_uses_existing_state(lineage, monkeypatch, live):
    store, spec = lineage["store"], lineage["spec"]
    claim = store.claim({key: spec[key] for key in execution_service.ATTEMPT_FIELDS},
                        request_digest(spec))
    try:
        if not live:
            claim.release()
        monkeypatch.setattr(generation_lineage, "authorize",
                            lambda *args: pytest.fail("registered request read lineage"))
        _forbid_claim(monkeypatch, store)
        with pytest.raises(PublicError) as caught:
            execute_attempt(store, lineage["evaluation_target"], spec)
        assert caught.value.code == ("AttemptInProgress" if live else "RecoveryRequired")
        assert caught.value.latest_record_ref is None
    finally:
        claim.release()


def test_cancelled_lineage_retains_not_started_facts_and_the_same_ref(lineage, monkeypatch):
    cancellation = threading.Event()
    cancellation.set()
    monkeypatch.setattr(execution_service, "_run_steps",
                        lambda *args: pytest.fail("cancelled evaluation started a worker"))
    result = lineage["harness"](lineage["spec"], cancellation=cancellation)
    assert result["started"] is False
    assert result["generation_record_ref"] == lineage["generated"]["record_ref"]
    monkeypatch.setattr(generation_lineage, "authorize",
                        lambda *args: pytest.fail("cancelled replay read lineage"))
    _forbid_claim(monkeypatch, lineage["store"])
    assert lineage["harness"](lineage["spec"])["record_ref"] == result["record_ref"]


def test_apps_publication_failure_keeps_committed_lineage_and_new_process_replays(
    lineage, monkeypatch, tmp_path,
):
    store, spec = lineage["store"], lineage["spec"]
    request = {
        "schema_version": 1, "prepared_ref": spec["prepared_ref"],
        "attempt": {key: spec[key] for key in execution_service.ATTEMPT_FIELDS},
        "proposal": lineage["proposal"], "output_root": spec["output_root"],
    }
    # The host saves the whole original attempt before the first submission.
    saved = tmp_path / "saved-execute.json"
    saved.write_bytes(encode(request))
    (tmp_path / "storage.json").write_bytes(encode(lineage["config"]))

    def unavailable(*args, **kwargs):
        raise OSError("local publication-failure control")

    with monkeypatch.context() as fault:
        fault.setattr(archive, "_publish_directory", unavailable)
        failed = api.execute(
            decode(saved.read_bytes()), workspace=tmp_path, storage_config=lineage["config"],
            execute_harness=lineage["harness"], output_id="failed-lineage",
        )
    committed = store.committed(spec["attempt_id"])
    assert failed.directory is None and failed.result["exit_code"] == 6
    assert failed.result["record_ref"] == committed.record_ref
    assert failed.result["error"]["latest_record_ref"] == committed.record_ref
    assert committed.payload["generation_record_ref"] == lineage["generated"]["record_ref"]
    (tmp_path / "expected-ref.json").write_bytes(encode(committed.record_ref))
    _retained_path(lineage, "candidate").write_bytes(b"changed after original submission")
    script = """
import subprocess, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from inferrsi.apps import api
from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness.executor import _generation_lineage as generation_lineage
from functools import partial
from inferrsi.harness.executor import execute_attempt
from inferrsi.harness.executor import LocalCpuTarget
from inferrsi.harness.records import RunStore, allocate_attempt
from inferrsi.harness.records._run_store import Claim
root = Path(sys.argv[2])
load = lambda name: decode((root / name).read_bytes())
store = RunStore(root / 'store', 'generation')
def forbidden(*args, **kwargs):
    raise AssertionError('replay started or committed a new attempt')
subprocess.Popen = forbidden
Claim.commit = forbidden
store.claim = forbidden
generation_lineage.authorize = forbidden
retired = partial(execute_attempt, store, LocalCpuTarget('retired', '2', root / 'retired'))
output = api.execute(load('saved-execute.json'), workspace=root,
                     storage_config=load('storage.json'), execute_harness=retired,
                     output_id='replayed-lineage')
assert output.result['exit_code'] == 0
assert output.result['record_ref'] == load('expected-ref.json')
with store._connection() as connection:
    assert connection.execute('SELECT count(*) FROM attempts').fetchone()[0] == 2
    assert connection.execute('SELECT count(*) FROM records').fetchone()[0] == 2
assert (output.directory / 'manifest.json').is_file()
assert (output.directory / 'result.json').is_file()
for name in ('manifest.json', 'result.json'):
    raw = (output.directory / name).read_bytes()
    assert encode(decode(raw)) == raw
print(encode(output.result['record_ref']).decode('utf-8'))
"""
    child = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script,
         str(Path(__file__).resolve().parents[2] / "src"), str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", check=True,
    )
    assert decode(child.stdout.strip().encode("utf-8")) == committed.record_ref
    assert store.committed(spec["attempt_id"]).payload_bytes == committed.payload_bytes
