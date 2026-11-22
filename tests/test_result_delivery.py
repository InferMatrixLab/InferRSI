"""Delivery acceptance fixtures use synthetic measurements, never a performance claim."""

import json
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from inferrsi.apps import delivery
from inferrsi.apps.artifacts import atomic_write_json, sha256
from inferrsi.apps.cli import main
from inferrsi.apps.delivery.projection import metric
from inferrsi.apps.delivery.schema import decode, validate_result
from inferrsi.apps.delivery.snapshot import MAX_DOCUMENT_BYTES, Snapshot
from inferrsi.apps.storage import archive
from inferrsi.apps.storage.result import preparation_result
from inferrsi.harness import optimization
from tests.diagnosis_support import diagnosis_evidence


def make_campaign(tmp_path, *, scores=(5,), final=True, final_verdict="PASS", usage=False,
                  benchmark=False, execution_state="completed", returncode=0, metrics_policy=None):
    root = tmp_path / "campaign"
    frozen = root / "frozen"
    frozen.mkdir(parents=True)
    (frozen / "baseline.py").write_text("10", encoding="utf-8")
    (frozen / "TASK.md").write_text("Synthetic test; no accelerator claim", encoding="utf-8")
    plan = {
        "schema_version": 2,
        "task": "synthetic",
        "task_source": "project",
        "condition": "test",
        "candidate_kind": "file",
        "candidate_name": "candidate.py",
        "baseline_path": "frozen/baseline.py",
        "working_candidate": "candidate.py",
        "round_mode": "exact",
        "round_limit": len(scores),
        "max_seconds": 600,
        "final_reserve_seconds": 60,
        "selection": {"direction": "minimize", "metric": "latency", "initial_score": 10},
        "evaluation_settings": {
            "metric_key": "latency",
            "metric_unit": "ms",
            "scope": "synthetic",
            "direction": "minimize",
            "repetitions": 2,
        },
        "frozen_files": {p.name: sha256(p) for p in frozen.iterdir()},
    }
    if benchmark:
        from inferrsi.benchmark.summary import POLICY

        plan.update(task_source="benchmark", report_metadata={
            "benchmark_metrics": POLICY if metrics_policy is None else metrics_policy})
    optimization.initialize(root, plan)
    optimization.record_diagnosis(root, "Reference operation", diagnosis_evidence(root))

    def execute(root, directory, plan, deadline):
        (directory / "execution").mkdir()
        execution = {"status": execution_state, "returncode": returncode, "elapsed_seconds": 1}
        atomic_write_json(directory / "execution/execution.json", execution)
        value = float((directory / "candidate.py").read_text())
        atomic_write_json(directory / "measurement.json", {"synthetic_value": value})
        return execution

    def assess(root, directory, plan, execution):
        value = json.loads((directory / "measurement.json").read_text())["synthetic_value"]
        verdict = final_verdict if "final" in directory.parts else "PASS"
        if value >= 10:
            verdict = "FAIL"
        return {
            "status": "completed",
            "score": value,
            "baseline_score": 10,
            "verdict": verdict,
            "eligible": verdict == "PASS",
            "quality_passed": True,
            "speedup": 10 / value,
            "scope": "synthetic",
            "claim_id": "synthetic-primary",
            "reason": "Synthetic fixture assessment",
            "metrics": {
                "name": "latency",
                "unit": "ms",
                "direction": "minimize",
                "baseline": 10,
                "candidate": value,
                "samples": {"baseline": [10, 10], "candidate": [value, value]},
            },
            "evidence_files": {"measurement.json": sha256(directory / "measurement.json")},
        }

    for index, score in enumerate(scores):
        candidate = root / "candidate.py"
        candidate.write_text(str(score), encoding="utf-8")
        usage_path = None
        if usage and index == 0:
            usage_path = root / "tokens.json"
            atomic_write_json(
                usage_path, {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 50}
            )
        optimization.evaluate_round(
            root,
            candidate=candidate,
            hypothesis=f"Synthetic score {score}",
            usage=usage_path,
            execute=execute,
            assess=assess,
        )
    if final:
        usage_path = root / "session-tokens.json" if usage else None
        if usage_path:
            atomic_write_json(usage_path, {"input_tokens": 1000, "output_tokens": 200})
        optimization.evaluate_round(
            root,
            candidate=None,
            hypothesis="Independent final",
            usage=usage_path,
            execute=execute,
            assess=assess,
            final=True,
        )
    return root


def export(root, tmp_path, name="delivery"):
    output = tmp_path / name
    receipt = delivery.export_bundle(root, output, export_id=name)
    assert receipt["status"] == "published", receipt
    return delivery.read_bundle(output), output


def state(root):
    return json.loads((root / "state.json").read_text())


def rewrite_final(root, value):
    final = value["final"]
    path = root / final["path"] / "observation.json"
    atomic_write_json(
        path, {key: item for key, item in final.items() if key != "observation_sha256"}
    )
    final["observation_sha256"] = sha256(path)
    atomic_write_json(root / "state.json", value)


def test_complete_bundle_agrees_across_views_and_preserves_sources(tmp_path):
    root = make_campaign(tmp_path)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result, output = export(root, tmp_path)
    assert result["completion"]["status"] == "completed"
    assert result["outcome"]["kind"] == "improved"
    assert result["acceptance"]["verdict"] == "PASS"
    assert result["acceptance"]["delivery_accepted"] is True
    assert result["final"]["binding"] == {"verified": True, "kind": "fingerprint"}
    assert len(result["rounds"]) == 1
    final_metric = next(m for m in result["metrics"] if m["phase"] == "final")
    assert (
        final_metric["baseline"],
        final_metric["candidate"],
        final_metric["speedup"],
        final_metric["improvement_pct"],
    ) == (10, 5, 2, 50)
    fingerprint = sha256(output / "campaign-result.json")
    for filename in ("report.md", "report.html"):
        text = (output / filename).read_text()
        assert fingerprint in text and "improved" in text and "PASS" in text
        assert "latency" in text and "ms" in text
    assert {p.name for p in output.iterdir()} == {
        "report.md",
        "report.html",
        "campaign-result.json",
        "artifacts.json",
    }
    assert all((root / name).read_bytes() == raw for name, raw in before.items())
    second, _ = export(root, tmp_path, "second")
    assert second["metrics"] == result["metrics"]
    assert second["outcome"] == result["outcome"]


@pytest.mark.parametrize("final,verdict", [(False, "PASS"), (True, "FAIL"), (True, "INCONCLUSIVE")])
def test_search_pass_is_never_substituted_for_missing_or_failed_final(tmp_path, final, verdict):
    root = make_campaign(tmp_path, final=final, final_verdict=verdict)
    result, _ = export(root, tmp_path)
    assert result["rounds"][0]["verdict"] == "PASS"
    assert result["outcome"]["kind"] == "undetermined"
    assert result["acceptance"]["delivery_accepted"] is False
    assert result["acceptance"]["verdict"] == (verdict if final else None)
    assert result["final"] is not None if final else result["final"] is None
    assert result["completion"]["status"] == ("completed" if final else "incomplete")


@pytest.mark.parametrize("final", [False, True])
def test_baseline_gain_only_after_completed_final(tmp_path, final):
    root = make_campaign(tmp_path, scores=(10,), final=final)
    result, _ = export(root, tmp_path)
    assert result["outcome"]["kind"] == "baseline_retained"
    assert result["outcome"]["optimization_speedup"] == (1 if final else None)
    assert result["acceptance"]["verdict"] == ("FAIL" if final else None)


@pytest.mark.parametrize(
    "damage",
    [
        "missing_measurement",
        "changed_measurement",
        "missing_assessment",
        "invalid_assessment",
        "changed_candidate",
        "changed_final",
    ],
)
def test_damaged_evidence_does_not_rewrite_history_or_accept_different_code(tmp_path, damage):
    root = make_campaign(tmp_path)
    value = state(root)
    directory = root / value["final"]["path"]
    if damage == "missing_measurement":
        (directory / "measurement.json").unlink()
    elif damage == "changed_measurement":
        (directory / "measurement.json").write_text('{"synthetic_value": 1}')
    elif damage == "missing_assessment":
        (directory / "observation.json").unlink()
    elif damage == "invalid_assessment":
        (directory / "observation.json").write_text('{"assessment": "PASS"')
    elif damage == "changed_candidate":
        (root / value["best"]["path"]).write_text("1000")
    else:
        (directory / "candidate.py").write_text("1000")
    result, output = export(root, tmp_path)
    assert result["acceptance"]["delivery_accepted"] is False
    assert result["outcome"]["kind"] == "undetermined"
    assert result["acceptance"]["verdict"] == "PASS"
    assert result["completion"]["status"] == "completed"
    assert "Current gaps" in (output / "report.md").read_text()
    with pytest.raises((ValueError, FileNotFoundError)):
        optimization.read_records(root)  # Normal execution reader remains strict.


@pytest.mark.parametrize("verdict", ["PASS", "FAIL", "INCONCLUSIVE"])
@pytest.mark.parametrize("damage", ["missing", "invalid", "changed"])
def test_cached_final_preserves_history_without_verifying_delivery(tmp_path, verdict, damage):
    root = make_campaign(tmp_path, final_verdict=verdict)
    committed = (root / "state.json").read_bytes()
    record = state(root)["final"]
    observation = root / record["path"] / "observation.json"
    if damage == "missing":
        observation.unlink()
    elif damage == "invalid":
        observation.write_text('{"assessment":')
    else:
        changed = json.loads(observation.read_text())
        changed["assessment"]["verdict"] = "FAIL" if verdict == "PASS" else "PASS"
        atomic_write_json(observation, changed)
    result, output = export(root, tmp_path)
    assert (root / "state.json").read_bytes() == committed
    assert result["completion"]["status"] == "completed"
    assert result["acceptance"]["status"] == "assessed"
    assert result["acceptance"]["verdict"] == verdict
    assert result["acceptance"]["delivery_accepted"] is False
    assert result["outcome"]["kind"] == "undetermined"
    assert result["outcome"]["optimization_speedup"] is None
    provenance = {
        "kind": "cached_state",
        "artifact_ref": "source:state.json",
        "json_pointer": "/final/assessment",
        "verification": "unverified",
    }
    assert result["acceptance"]["assessment_ref"] == "source:state.json"
    assert result["acceptance"]["assessment_provenance"] == provenance
    assert result["final"]["assessment_provenance"] == provenance
    check = next(c for c in result["checks"] if c["phase"] == "final")
    assert check["observation"] == record["assessment"]
    assert check["assessment_provenance"] == provenance
    assert "source:state.json" in check["evidence_refs"]
    assert "source:" + record["path"] + "/observation.json" in check["evidence_refs"]
    assert not [m for m in result["metrics"] if m["phase"] == "final"]
    for filename in ("report.md", "report.html"):
        text = (output / filename).read_text()
        assert "cached state; unverified" in text
        assert "Current gaps" in text


def test_conflicting_retained_observation_cannot_verify_cached_pass(tmp_path):
    root = make_campaign(tmp_path)
    value = state(root)
    record = value["final"]
    observation = root / record["path"] / "observation.json"
    changed = json.loads(observation.read_text())
    changed["assessment"]["verdict"] = "FAIL"
    atomic_write_json(observation, changed)
    record["observation_sha256"] = sha256(observation)
    atomic_write_json(root / "state.json", value)
    result, _ = export(root, tmp_path)
    assert result["acceptance"]["verdict"] == "PASS"
    assert result["acceptance"]["assessment_provenance"]["kind"] == "cached_state"
    assert result["acceptance"]["delivery_accepted"] is False
    assert any(g["code"] == "ASSESSMENT_CONFLICT" for g in result["gaps"])
    result["acceptance"]["delivery_accepted"] = True
    with pytest.raises(ValueError, match="Delivery acceptance requires"):
        validate_result(result)


def test_missing_search_observation_retains_labelled_history(tmp_path):
    root = make_campaign(tmp_path)
    record = state(root)["rounds"][0]
    (root / record["path"] / "observation.json").unlink()
    result, _ = export(root, tmp_path)
    search = result["rounds"][0]
    assert search["verdict"] == "PASS"
    assert search["score"] == record["assessment"]["score"]
    assert search["assessment_ref"] == "source:state.json"
    assert search["assessment_provenance"]["json_pointer"] == "/rounds/0/assessment"
    assert search["assessment_provenance"]["verification"] == "unverified"
    # The independently retained final still supplies its own verified assessment.
    assert result["acceptance"]["assessment_provenance"]["kind"] == "retained_observation"
    assert result["acceptance"]["delivery_accepted"] is True


@pytest.mark.parametrize("phase", ["search", "final"])
def test_oversized_optional_observation_keeps_cached_history_without_reading_it(
    tmp_path, monkeypatch, phase
):
    root = make_campaign(tmp_path)
    value = state(root)
    record = value["final"] if phase == "final" else value["rounds"][0]
    path = root / record["path"] / "observation.json"
    path.write_bytes(b" " * (MAX_DOCUMENT_BYTES + 1))
    original_open = type(path).open

    def bounded_open(self, *args, **kwargs):
        assert self != path, "An oversized observation must not be read, including during recheck"
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "open", bounded_open)
    result, output = export(root, tmp_path)
    assert result["completion"]["status"] == "completed"
    historical = result["acceptance"] if phase == "final" else result["rounds"][0]
    assert historical["verdict"] == "PASS"
    assert historical["assessment_provenance"]["kind"] == "cached_state"
    assert result["acceptance"]["delivery_accepted"] is (phase == "search")
    index = json.loads((output / "artifacts.json").read_text())
    entry = next(
        e for e in index["artifacts"] if e["id"] == "source:" + record["path"] + "/observation.json"
    )
    assert entry["availability"] == "unreadable"
    assert entry["integrity"] == "not_checked"
    assert entry["observed_sha256"] is None
    assert entry["sha256"] == record["observation_sha256"]
    assert "read limit" in entry["access"]


@pytest.mark.parametrize("name", ["plan.json", "state.json", "campaign.json"])
def test_oversized_required_control_document_prevents_publication(tmp_path, name):
    root = make_campaign(tmp_path)
    (root / name).write_bytes(b" " * (MAX_DOCUMENT_BYTES + 1))
    with pytest.raises(ValueError, match="Required delivery control document"):
        delivery.project(root, export_id="oversized-control")
    output = tmp_path / "delivery"
    receipt = delivery.export_bundle(root, output)
    assert receipt["status"] == "error"
    assert not output.exists()


@pytest.mark.parametrize("binding_state", ["verified", "missing", "mismatch", "bad_revision"])
def test_no_fingerprint_requires_verified_exact_revision_run_and_config(tmp_path, binding_state):
    root = make_campaign(tmp_path)
    value = state(root)
    revision = "a" * 40
    config = root / "fixed-config.json"
    atomic_write_json(config, {"candidate_revision": revision, "parameters": {"batch": 1}})
    config_ref = {"path": config.name, "sha256": sha256(config)}
    run = root / "fixed-run.json"
    atomic_write_json(
        run,
        {
            "candidate_revision": revision,
            "configuration_ref": config_ref,
            "attempt_id": value["final"]["path"].rsplit("/", 1)[-1],
            "protocol_digest": value["plan_digest"],
        },
    )
    binding = {
        "revision": revision,
        "run_ref": {"path": run.name, "sha256": sha256(run)},
        "configuration_ref": config_ref,
    }
    value["best"]["sha256"] = None
    value["best"]["binding"] = binding
    value["final"]["candidate_sha256"] = None
    value["final"]["candidate_binding"] = binding
    if binding_state == "missing":
        run.unlink()
    elif binding_state == "mismatch":
        run.write_text("{}")
    elif binding_state == "bad_revision":
        binding["revision"] = "main"
    rewrite_final(root, value)
    result, _ = export(root, tmp_path)
    assert result["acceptance"]["verdict"] == "PASS"
    assert result["acceptance"]["delivery_accepted"] is (binding_state == "verified")
    assert result["final"]["binding"]["kind"] == (
        "exact_revision" if binding_state == "verified" else None
    )


def test_usage_subtotal_and_session_observation_are_not_added(tmp_path):
    root = make_campaign(tmp_path, scores=(5, 4), usage=True)
    result, _ = export(root, tmp_path)
    rounds, session = result["usage"]["tokens"], result["usage"]["session_tokens"]
    assert rounds["coverage"] == "partial" and rounds["value"]["total_tokens"] == 120
    assert rounds["value"]["cached_input_tokens"] == 50
    assert session["value"]["total_tokens"] == 1200 and session["coverage"] == "unknown"
    assert result["usage"]["device_seconds"]["value"] is None
    assert result["usage"]["cost"]["value"] is None


@pytest.mark.parametrize(
    "direction,before,after,comparable,expected",
    [
        ("minimize", 10, 5, True, (2, 50)),
        ("maximize", 10, 20, True, (2, 100)),
        ("minimize", 0, 5, True, (None, None)),
        ("minimize", 10, 0, True, (None, None)),
        ("maximize", 10, 20, False, (None, None)),
        (None, 10, 20, True, (None, None)),
        ("minimize", 1e308, 1e-308, True, (None, None)),
    ],
)
def test_ratio_semantics(direction, before, after, comparable, expected):
    row = metric(
        {
            "baseline": before,
            "candidate": after,
            "direction": direction,
            "unit": "test",
            "statistic": "median",
        },
        phase="test",
        ref="source:test",
        protocol_ref=None,
        comparable=comparable,
    )
    assert (row["speedup"], row["improvement_pct"]) == expected
    assert row["baseline"] == before and row["candidate"] == after


def test_opaque_archive_authority_does_not_fork_metadata_or_fetch(tmp_path, monkeypatch):
    root = make_campaign(tmp_path)
    manifest = {
        "schema_version": 2,
        "archive": {"url": "https://example.org/archive.tar.gz", "sha256": "b" * 64, "bytes": 123},
    }
    (root / "results").mkdir()
    atomic_write_json(root / "results/artifacts.json", manifest)
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: pytest.fail("network access"))
    _, output = export(root, tmp_path)
    index = json.loads((output / "artifacts.json").read_text())
    assert index["archive_authority_ref"] == "source:results/artifacts.json"
    assert "https://example.org" not in (output / "artifacts.json").read_text()
    assert json.loads((root / "results/artifacts.json").read_text()) == manifest


def test_progress_uses_committed_control_and_a_fixed_clock(tmp_path):
    root = make_campaign(tmp_path, final=False)
    (root / "summary.json").write_text(
        '{"state":"completed","final_assessment":{"verdict":"PASS"}}'
    )
    observed = state(root)["started_at"] + 10
    _, result, _ = delivery.project(root, export_id="progress", observed_at=observed)
    assert result["export"]["kind"] == "progress"
    assert result["completion"]["status"] == "incomplete"
    assert result["usage"]["wall_seconds"]["value"] == pytest.approx(10, abs=1e-6)
    with optimization._locked(root), pytest.raises(ValueError, match="writer is active"):
        delivery.project(root, export_id="busy")


def test_snapshot_retries_whole_projection_on_interleaved_write(tmp_path, monkeypatch):
    root = make_campaign(tmp_path)
    complete = (root / "state.json").read_bytes()
    progress = state(root)
    progress.update(final=None, state="active")
    progress.pop("settled_at")
    atomic_write_json(root / "state.json", progress)
    original = Snapshot.stable
    calls = []

    def interleaved(snapshot):
        calls.append(True)
        if len(calls) == 1:
            (root / "state.json").write_bytes(complete)
        return original(snapshot)

    monkeypatch.setattr(Snapshot, "stable", interleaved)
    result, _ = export(root, tmp_path)
    assert len(calls) == 2
    assert result["completion"]["status"] == "completed"
    assert result["acceptance"]["verdict"] == "PASS"
    monkeypatch.setattr(Snapshot, "stable", lambda self: False)
    with pytest.raises(ValueError, match="consistent snapshot"):
        delivery.project(root, export_id="changing")


def test_publication_conflict_and_write_failure_preserve_committed_records(tmp_path, monkeypatch):
    root = make_campaign(tmp_path)
    _, output = export(root, tmp_path)
    before = (root / "state.json").read_bytes()
    original = (output / "campaign-result.json").read_bytes()
    assert delivery.export_bundle(root, output)["status"] == "error"
    assert (output / "campaign-result.json").read_bytes() == original

    def broken(*args):
        raise OSError("synthetic full disk")

    monkeypatch.setattr(archive, "_write_file", broken)
    failed = tmp_path / "failed"
    assert delivery.export_bundle(root, failed)["status"] == "error"
    assert not failed.exists() and not list(tmp_path.glob(".delivery-*"))
    assert (root / "state.json").read_bytes() == before


def test_post_rename_failure_keeps_identity_for_reconciliation(tmp_path, monkeypatch):
    root = make_campaign(tmp_path)
    output = tmp_path / "uncertain"
    original = archive._sync_directory

    def fail_after_publish(path):
        if output.exists() and path == output.parent:
            raise OSError("synthetic fsync failure")
        original(path)

    monkeypatch.setattr(archive, "_sync_directory", fail_after_publish)
    receipt = delivery.export_bundle(root, output, export_id="same-export")
    assert receipt["status"] == "uncertain" and receipt["export_id"] == "same-export"
    assert delivery.read_bundle(output)["export"]["id"] == "same-export"


@pytest.mark.parametrize(
    "bad_path", ["../outside.py", "/outside.py", "x/../../outside.py", "C:\\outside.py", "link.py"]
)
def test_source_traversal_and_symlinks_are_rejected(tmp_path, bad_path):
    root = make_campaign(tmp_path)
    value = state(root)
    outside = tmp_path / "outside.py"
    outside.write_text("private content")
    if bad_path == "link.py":
        (root / bad_path).symlink_to(outside)
    value["best"]["path"] = bad_path
    atomic_write_json(root / "state.json", value)
    output = tmp_path / "rejected"
    assert delivery.export_bundle(root, output)["status"] == "error"
    assert not output.exists() and outside.read_text() == "private content"


def test_untrusted_text_cannot_inject_html_or_markdown_links(tmp_path):
    root = make_campaign(tmp_path)
    value = state(root)
    payload = "</script><script>alert(1)</script> [click](javascript:alert(2))\n# heading |"
    record = value["rounds"][0]
    record["hypothesis"] = payload
    path = root / record["path"] / "observation.json"
    atomic_write_json(path, {k: v for k, v in record.items() if k != "observation_sha256"})
    record["observation_sha256"] = sha256(path)
    atomic_write_json(root / "state.json", value)
    result, output = export(root, tmp_path)
    assert result["rounds"][0]["hypothesis"] == payload
    html = (output / "report.html").read_text()
    markdown = (output / "report.md").read_text()
    assert "<script" not in html and "</script>" not in html
    assert "[click](javascript:" not in markdown and "<script" not in markdown
    assert 'href="javascript:' not in html


def test_historical_summary_preserves_verdict_without_inventing_rounds_or_binding(tmp_path):
    root = tmp_path / "historical"
    root.mkdir()
    atomic_write_json(
        root / "summary.json",
        {"schema_version": 1, "state": "completed", "final_assessment": {"verdict": "PASS"}},
    )
    result, _ = export(root, tmp_path)
    assert result["acceptance"]["verdict"] == "PASS"
    assert result["acceptance"]["delivery_accepted"] is False
    assert result["rounds"] is None and result["final"] is None
    assert result["completion"]["status"] == "completed"


@pytest.mark.parametrize("external_name", ["external.json", "result.json"])
def test_legacy_and_external_scope_are_not_iterative_acceptance(tmp_path, external_name):
    root = tmp_path / "single"
    root.mkdir()
    atomic_write_json(
        root / "run.lock.json",
        {
            "metric_key": "latency",
            "metric_unit": "ms",
            "direction": "minimize",
            "comparison_scope": "L2",
        },
    )
    atomic_write_json(root / "status.json", {"state": "completed"})
    atomic_write_json(
        root / "evaluation.json",
        {"verdict": "PASS", "baseline": {"median": 10}, "candidate": {"median": 5}},
    )
    result, _ = export(root, tmp_path, "single-export")
    assert result["campaign"]["task_kind"] == "single_experiment"
    assert result["rounds"] is None and result["final"] is None
    assert result["acceptance"]["scope"] == "L2"
    external = root / external_name
    atomic_write_json(
        external,
        {
            "schema_version": 1,
            "kind": "external_optimization_record",
            "candidate_id": "imported",
            "state": "completed",
            "backend": "test",
            "protocol": "test",
            "source_refs": [
                {"path": "evaluation.json", "sha256": sha256(root / "evaluation.json")}
            ],
            "performance_verdict": "PASS",
            "metrics": [{"baseline": 10, "aggregate": 5}],
        },
    )
    result, _ = export(external, tmp_path, "external-export")
    assert result["acceptance"]["verdict"] == "PASS"
    assert result["acceptance"]["locally_revalidated"] is False
    assert result["metrics"][0]["speedup"] is None
    assert result["final"] is None


def test_apps_operation_success_does_not_mean_optimization_completed(tmp_path):
    path = tmp_path / "result.json"
    prepared = {
        "prepared_id": "prepared",
        "schema_version": 1,
        "artifact": {
            "location": "archive/prepared.json",
            "sha256": "a" * 64,
            "size_bytes": 2,
            "media_type": "application/json",
        },
    }
    atomic_write_json(path, preparation_result(prepared_ref=prepared))
    result, _ = export(path, tmp_path)
    assert result["execution"]["outcome"] == "success"
    assert result["completion"]["status"] == "incomplete"
    assert result["acceptance"]["status"] == "not_assessed"


def test_reader_rejects_versions_nonfinite_and_modified_reports(tmp_path):
    root = make_campaign(tmp_path)
    result, output = export(root, tmp_path)
    result["schema_version"] = 2
    with pytest.raises(ValueError, match="Unsupported"):
        validate_result(result)
    for raw in (b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e400}', b'{"x":0,"x":1}'):
        with pytest.raises(ValueError):
            decode(raw)
    (output / "report.md").write_text("modified")
    with pytest.raises(ValueError, match="integrity"):
        delivery.read_bundle(output)


@pytest.mark.parametrize("name", ["report.md", "report.html", "campaign-result.json"])
@pytest.mark.parametrize("position", [0, -1])
def test_reader_rejects_unique_id_entries_with_duplicate_bundle_locations(tmp_path, name, position):
    root = make_campaign(tmp_path)
    _, output = export(root, tmp_path)
    index_path = output / "artifacts.json"
    index = json.loads(index_path.read_text())
    entry = next(e for e in index["artifacts"] if e["id"] == "bundle:" + name)
    duplicate = {**entry, "id": "duplicate:" + name, "sha256": "0" * 64}
    if position == 0:
        index["artifacts"].insert(0, duplicate)
    else:
        index["artifacts"].append(duplicate)
    atomic_write_json(index_path, index)
    with pytest.raises(ValueError, match="Duplicate delivery bundle location"):
        delivery.read_bundle(output)


def test_export_cli_success_describes_export_not_experiment_verdict(tmp_path, capsys):
    root = make_campaign(tmp_path, final_verdict="FAIL")
    assert main(["export", "--input", str(root), "--output", str(tmp_path / "cli")]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["conclusion"]["acceptance"]["verdict"] == "FAIL"
    assert receipt["report_html"]["label"] == "Open in a browser"


@pytest.mark.parametrize("missing_observation", [False, True])
def test_interrupted_final_is_incomplete_and_keeps_original_inconclusive(
    tmp_path, missing_observation
):
    root = make_campaign(tmp_path)
    value = state(root)
    record = value["final"]
    record["execution"].update(status="timeout", returncode=None)
    record["assessment"].update(status="infrastructure_failure", verdict="INCONCLUSIVE", score=None)
    value["state"] = "blocked"
    execution = root / record["path"] / "execution/execution.json"
    atomic_write_json(execution, record["execution"])
    record["execution_sha256"] = sha256(execution)
    rewrite_final(root, value)
    if missing_observation:
        (root / record["path"] / "observation.json").unlink()
    result, _ = export(root, tmp_path)
    assert result["execution"]["state"] == "blocked"
    assert result["completion"]["status"] == "incomplete"
    assert result["acceptance"]["verdict"] == "INCONCLUSIVE"
    assert result["outcome"]["optimization_speedup"] is None


@pytest.mark.parametrize("missing_observation", [False, True])
@pytest.mark.parametrize("assessment", [None, "PASS", {}])
def test_malformed_assessment_cannot_become_historical_pass(
    tmp_path, missing_observation, assessment
):
    root = make_campaign(tmp_path)
    value = state(root)
    value["final"]["assessment"] = assessment
    rewrite_final(root, value)
    if missing_observation:
        (root / value["final"]["path"] / "observation.json").unlink()
    result, _ = export(root, tmp_path)
    assert result["acceptance"]["status"] == "not_assessed"
    assert result["completion"]["status"] == "incomplete"


def test_frozen_member_change_during_read_cannot_publish_accepted_snapshot(tmp_path, monkeypatch):
    root = make_campaign(tmp_path)
    original = Snapshot.stable
    count = 0

    def changed(snapshot):
        nonlocal count
        count += 1
        (root / "frozen" / f"new-{count}.py").write_text("new file")
        return original(snapshot)

    monkeypatch.setattr(Snapshot, "stable", changed)
    receipt = delivery.export_bundle(root, tmp_path / "changing")
    assert receipt["status"] == "error" and count == 3
    assert "consistent snapshot" in receipt["error"]
    assert not (tmp_path / "changing").exists()


@pytest.mark.parametrize("missing_observation", [False, True])
def test_offline_html_remains_readable_without_scripts_or_network(tmp_path, missing_observation):
    playwright = pytest.importorskip("playwright.sync_api")
    root = make_campaign(tmp_path)
    if missing_observation:
        (root / state(root)["final"]["path"] / "observation.json").unlink()
    _, output = export(root, tmp_path)
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page(java_script_enabled=False, offline=True)
        requests = []
        page.on("request", lambda request: requests.append(request.url))
        page.goto((output / "report.html").as_uri())
        assert page.locator("h1").inner_text() == "RSI result report"
        conclusion = page.locator("body > p").first.inner_text()
        expected = "completed: undetermined" if missing_observation else "completed: improved"
        assert expected in conclusion
        if missing_observation:
            assert "Original assessment: PASS (cached state; unverified)" in conclusion
            assert "Cached historical assessment" in page.locator(".gaps").inner_text()
        assert page.get_by_role("img").count() == 1
        page.locator("details summary").click()
        assert (
            '"schema_id": "inferrsi.campaign-delivery"' in page.locator("details pre").inner_text()
        )
        assert not [url for url in requests if url.startswith(("http:", "https:"))]
        browser.close()


@pytest.fixture
def standalone_native_usage(tmp_path, request):
    from inferrsi.harness import agent_sessions

    job = tmp_path / "agent-job"
    frozen_input = tmp_path / "native-task.txt"
    frozen_input.write_text("Frozen synthetic task", encoding="utf-8")
    agent_sessions.prepare(job, prompt="Synthetic Benchmark task", workspace=tmp_path,
                           title="Synthetic", max_seconds=600, frozen_inputs=(frozen_input,))
    agent_sessions.dispatch(job)
    creation = tmp_path / "creation.json"
    atomic_write_json(creation, {"synthetic_creation": True})
    agent_sessions.bind(job, host="synthetic", session_id="native-session", receipt=creation)
    root = make_campaign(tmp_path, benchmark=True, usage=True,
                         metrics_policy=getattr(request, "param", None))
    control = state(root)
    observation = {
        "host": "synthetic", "host_id": None, "session_id": "native-session",
        "state": "completed", "native_receipt": {"synthetic_terminal": True},
        "usage_scope": "session_total",
        "usage": {"input_tokens": 1000, "output_tokens": 200, "cached_input_tokens": 500},
        "benchmark_token_coverage": {
            "trial_id": "test", "session_id": "native-session", "scope": "trial_agent_session",
            "campaign_plan_digest": control["plan_digest"],
            "started_at": control["started_at"], "ended_at": control["settled_at"],
            "includes": dict.fromkeys(
                ("pre_start", "retrieval", "failures_retries", "final"), True),
        },
    }
    return root, job, observation


def record_native_usage(job, observation):
    from inferrsi.harness import agent_sessions

    path = job.parent / "terminal.json"
    atomic_write_json(path, observation)
    agent_sessions.record(job, observation=path)


def test_single_benchmark_complete_native_usage_through_export_cli(
    standalone_native_usage, tmp_path, capsys,
):
    root, job, observation = standalone_native_usage
    record_native_usage(job, observation)
    output = tmp_path / "complete-native-report"
    assert main(["export", "--input", str(root), "--output", str(output),
                 "--agent-job", str(job)]) == 0
    capsys.readouterr()
    result = delivery.read_bundle(output)
    tokens = result["benchmark_metrics"]["token_usage"]
    assert tokens["coverage"] == "complete" and tokens["total_tokens"] == 1200
    assert tokens["cached_input_tokens"] == 500
    assert result["usage"]["tokens"]["value"]["total_tokens"] == 120  # Never add round subtotal.
    assert result["usage"]["session_tokens"]["coverage"] == "complete"
    assert "token_usage" not in result["benchmark_metrics"]["missing_reasons"]
    assert not any(g["affects"] == "usage.session_tokens" for g in result["gaps"])
    index = decode((output / "artifacts.json").read_bytes())
    source = next(a for a in index["artifacts"] if a["id"] == tokens["source"])
    assert source["integrity"] == "verified" and source["role"] == "native_usage"
    for entry in index["artifacts"]:
        assert not PurePosixPath(entry["location"]).is_absolute()
        assert not PureWindowsPath(entry["location"]).drive
        assert ".." not in PurePosixPath(entry["location"]).parts
    assert source["source_root"] == "agent-job"
    native_state = next(a for a in index["artifacts"] if a["role"] == "native_state")
    assert (native_state["source_root"], native_state["location"]) == ("agent-job", "state.json")
    campaign_state = next(a for a in index["artifacts"] if a["id"] == "source:state.json")
    assert campaign_state.get("source_root") is None and campaign_state["location"] == "state.json"
    inputs = [a for a in index["artifacts"] if a["role"] == "native_frozen_input"]
    assert len(inputs) == 1 and inputs[0]["integrity"] == "verified"
    assert (inputs[0]["source_root"], inputs[0]["location"]) == (
        "agent-input-0", "native-task.txt")
    for name in ("report.md", "report.html"):
        text = (output / name).read_text(encoding="utf-8")
        assert text.index("Benchmark metrics") < text.index("Token consumption")
        assert "1,200" in text


@pytest.mark.parametrize(
    "location", ["/external/state.json", "C:/external/state.json", "../escape"])
def test_reader_rejects_nonrelative_source_locations(tmp_path, location):
    root = make_campaign(tmp_path)
    _, output = export(root, tmp_path)
    index_path = output / "artifacts.json"
    index = decode(index_path.read_bytes())
    source = next(a for a in index["artifacts"] if a["location_kind"] == "source")
    source["location"] = location
    atomic_write_json(index_path, index)
    with pytest.raises(ValueError, match="Unsafe delivery source path"):
        delivery.read_bundle(output)


@pytest.mark.parametrize("fault", [
    "trial", "session", "start", "end", "scope", "includes", "plan", "running", "workspace",
])
def test_single_benchmark_incomplete_or_mismatched_receipt_stays_unknown(
    standalone_native_usage, tmp_path, fault,
):
    root, job, observation = standalone_native_usage
    coverage = observation["benchmark_token_coverage"]
    if fault == "trial":
        coverage["trial_id"] = "another-trial"
    elif fault == "session":
        coverage["session_id"] = "another-session"
    elif fault == "start":
        coverage["started_at"] += 1
    elif fault == "end":
        coverage["ended_at"] -= 1
    elif fault == "scope":
        coverage["scope"] = "round_only"
    elif fault == "includes":
        coverage["includes"]["failures_retries"] = False
    elif fault == "plan":
        coverage["campaign_plan_digest"] = "0" * 64
    elif fault == "running":
        observation["state"] = "running"
    elif fault == "workspace":
        # A different valid job cannot lend its counters to this campaign.
        from inferrsi.harness import agent_sessions

        other = tmp_path / "other"
        other.mkdir()
        job = tmp_path / "other-job"
        agent_sessions.prepare(job, prompt="Other", workspace=other, title="Other", max_seconds=600)
        agent_sessions.dispatch(job)
        agent_sessions.bind(job, host="synthetic", session_id="native-session",
                            receipt=tmp_path / "creation.json")
    record_native_usage(job, observation)
    _, result, _ = delivery.project(root, export_id="incomplete-usage", agent_job=job)
    tokens = result["benchmark_metrics"]["token_usage"]
    assert tokens["total_tokens"] is None
    assert tokens["coverage"] != "complete"
    assert result["benchmark_metrics"]["missing_reasons"]["token_usage"]


def test_single_benchmark_missing_terminal_receipt_preserves_observed_subtotal(
    standalone_native_usage,
):
    root, job, _ = standalone_native_usage
    _, result, _ = delivery.project(root, export_id="missing-native", agent_job=job)
    tokens = result["benchmark_metrics"]["token_usage"]
    assert tokens["total_tokens"] is None and tokens["observed_tokens"] == 1200


def test_single_benchmark_terminal_receipt_without_counters_preserves_campaign_usage(
    standalone_native_usage,
):
    root, job, observation = standalone_native_usage
    del observation["usage"]
    record_native_usage(job, observation)
    _, original, _ = delivery.project(root, export_id="campaign-usage")
    _, result, _ = delivery.project(root, export_id="native-without-counters", agent_job=job)
    tokens = result["benchmark_metrics"]["token_usage"]
    assert tokens == original["benchmark_metrics"]["token_usage"]
    assert tokens["observed_tokens"] == 1200 and tokens["total_tokens"] is None
    assert result["usage"]["session_tokens"] == original["usage"]["session_tokens"]
    assert any(source["type"] == "native_agent_usage" for source in result["sources"])


@pytest.mark.parametrize(
    "standalone_native_usage", [{}, {"metrics_schema_version": 2}], indirect=True)
def test_native_job_preserves_unsupported_policy_reason(standalone_native_usage):
    root, job, observation = standalone_native_usage
    record_native_usage(job, observation)
    _, original, _ = delivery.project(root, export_id="unsupported-original")
    _, result, _ = delivery.project(root, export_id="unsupported-native", agent_job=job)
    assert result["benchmark_metrics"] == original["benchmark_metrics"]
    assert result["benchmark_metrics"]["missing_reasons"]["token_usage"] == [
        "unsupported_or_legacy_metrics_policy"]


def test_native_frozen_input_change_after_status_prevents_complete_export(
    standalone_native_usage, tmp_path, monkeypatch,
):
    from inferrsi.harness import agent_sessions

    root, job, observation = standalone_native_usage
    record_native_usage(job, observation)
    original = agent_sessions.status

    def changed_after_read(path):
        host = original(path)
        (tmp_path / "native-task.txt").write_text("Changed after status", encoding="utf-8")
        return host

    monkeypatch.setattr(agent_sessions, "status", changed_after_read)
    output = tmp_path / "changed-native-input"
    result = delivery.export_bundle(root, output, agent_job=job)
    assert result["status"] == "error" and not output.exists()


def test_progress_without_native_observation_preserves_campaign_usage_source(tmp_path):
    from inferrsi.harness import agent_sessions

    job = tmp_path / "job"
    agent_sessions.prepare(job, prompt="Synthetic", workspace=tmp_path,
                           title="Synthetic", max_seconds=600)
    agent_sessions.dispatch(job)
    receipt = tmp_path / "creation.json"
    atomic_write_json(receipt, {"synthetic_creation": True})
    agent_sessions.bind(job, host="synthetic", session_id="native-session", receipt=receipt)
    root = make_campaign(tmp_path, benchmark=True, usage=True, final=False)
    _, original, _ = delivery.project(root, export_id="progress-original")
    _, result, _ = delivery.project(root, export_id="progress-native", agent_job=job)
    usage = result["benchmark_metrics"]["token_usage"]
    assert usage == original["benchmark_metrics"]["token_usage"]
    assert usage["source"] == "source:state.json" and usage["observed_tokens"] == 120
    assert "session_tokens" not in result["usage"]


def test_retained_native_receipt_change_invalidates_the_delivery_snapshot(standalone_native_usage):
    root, job, observation = standalone_native_usage
    record_native_usage(job, observation)
    snapshot, result, _ = delivery.project(root, export_id="native-snapshot", agent_job=job)
    assert result["benchmark_metrics"]["token_usage"]["total_tokens"] == 1200
    native_state = decode((job / "state.json").read_bytes())
    receipt = job / native_state["last_observation"]["path"]
    receipt.write_bytes(receipt.read_bytes() + b"\n")
    assert not snapshot.stable()


@pytest.mark.parametrize("execution_state,returncode", [
    ("timeout", None), ("unknown", None), ("failed", -9), ("completed", None),
])
def test_benchmark_abnormal_execution_is_unresolved_through_retained_projection(
    tmp_path, execution_state, returncode,
):
    root = make_campaign(tmp_path, benchmark=True, final=False,
                         execution_state=execution_state, returncode=returncode)
    _, result, _ = delivery.project(root, export_id="abnormal-execution")
    # Preserve the Harness's historical classification and verdict.
    assert result["rounds"][0]["assessment_status"] == "infrastructure_failure"
    assert result["rounds"][0]["execution_state"] == execution_state
    metrics = result["benchmark_metrics"]
    assert metrics["infrastructure_failures"] == 0
    assert metrics["unresolved_steps"] == 1 and metrics["step_coverage"] == "partial"
    assert metrics["assessed_steps"] == metrics["accepted_steps"] == 0


def test_benchmark_confirmed_infrastructure_failure_keeps_separate_count(tmp_path):
    root = make_campaign(tmp_path, benchmark=True, final=False,
                         execution_state="failed", returncode=1)
    _, result, _ = delivery.project(root, export_id="confirmed-infra")
    metrics = result["benchmark_metrics"]
    assert metrics["infrastructure_failures"] == 1 and metrics["unresolved_steps"] == 0
    assert metrics["assessed_steps"] == 0 and metrics["step_coverage"] == "complete"
