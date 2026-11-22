"""Carry a genuinely generated, retained candidate into the production CPU task."""

from dataclasses import replace
from pathlib import Path

from inferrsi.apps import api
from inferrsi.apps.storage import archive
from inferrsi.apps.storage.artifact_reader import ArtifactReader
from inferrsi.benchmark import assessment, cpu_smoke, preparation, proofs
from inferrsi.benchmark.workers import fixture_worker as worker
from inferrsi.harness import execution_service
from inferrsi.harness.api import Harness
from inferrsi.harness.generation import prepare_generation
from tests.test_apps_generation_plan import generation as generation
from tests.test_harness_generation_seal import cpu_generation as cpu_generation


def test_generated_candidate_uses_a_separate_production_evaluation_attempt(cpu_generation, tmp_path):
    store, target, generation_harness, draft, inputs = cpu_generation
    generation_spec = prepare_generation(store, target, **inputs)
    generated = generation_harness.execute(generation_spec)
    assert generated["exit_code"] == 0
    generation_ref = generated["record_ref"]
    generation_before = store.committed(generated["attempt_id"])
    context_ref = store.read_delivered_context(generated["attempt_id"])["artifact"]
    with store.open(context_ref) as stream:
        context_bytes = stream.read()
    assert context_bytes == draft.content
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
    harness = Harness(
        store, replace(target, module_root=Path(worker.__file__).parent), artifact_reader=reader,
        evidence_capture=api.EvidenceCapture(
            projector.project, candidate_role="candidate", report_role="grader",
        ),
    )
    attempt = harness.allocate(**{key: inputs["attempt"][key] for key in (
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
    evaluated = harness.execute(spec)
    assert evaluated["exit_code"] == 0
    assert evaluated["generation_record_ref"] == generation_ref
    assert evaluated["attempt_id"] == attempt["attempt_id"]
    summary = port.assess(evaluated)
    assert summary["attempt_id"] == attempt["attempt_id"]
    # The generator emits UTF-8 context, deliberately not this task's correct sum.
    assert [(claim["claim_id"], claim["verdict"]) for claim in summary["claims"]] == [
        ("F", "PASS"), ("C", "FAIL"), ("M", "PASS"),
    ]
    decision = archive.read_assessment(config, summary["assessment_ref"])
    assert decision["record_ref"] == evaluated["record_ref"]
    assert decision["record_ref"] != generation_ref
    assert decision["candidate"] == proposal["candidate"]
    view = api.read_attempt_view(
        evaluated["record_ref"], storage_config=config,
        assessment_ref=summary["assessment_ref"], include_trace=True,
    )
    assert view["execution"]["exit_code"] == 0
    assert view["assessment"]["claims"][1]["verdict"] == "FAIL"
    generation_after = store.committed(generated["attempt_id"])
    assert generation_after.record_ref == generation_before.record_ref
    assert generation_after.payload_bytes == generation_before.payload_bytes
    with store.open(context_ref) as stream:
        assert stream.read() == context_bytes
