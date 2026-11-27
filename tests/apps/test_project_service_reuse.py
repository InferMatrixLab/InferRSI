"""Fingerprint-free CPU orchestration controls; no real-model qualification."""

import copy
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.cli.arguments import parser
from inferrsi.apps.delivery import project, read_bundle
from inferrsi.harness import executor, optimization
from inferrsi.harness.executor.serving import _attempt
from inferrsi.harness.records import service_io
from tests.fixtures.service_reuse import begin, call, commit, diagnose, rejected, settings, submit
from tests.fixtures.service_reuse import campaign as campaign
from tests.fixtures.service_reuse import no_fingerprints as no_fingerprints


def read_first_hit(campaign, question):
    args = ["find", question, "--session", str(campaign["root"]), "--limit", "1", "--json"]
    assert main(args) == 0
    result = json.loads(campaign["capsys"].readouterr().out)
    service_io.no_fingerprints(result)
    search = json.loads((campaign["root"] / result["reference"]["path"]).read_bytes())
    assert search["selection"]["method"] == "find-lexical-v1" and search["contexts"] == []
    hit, = result["items"]
    assert "content" not in hit
    assert main(hit["read_args"]) == 0
    delivery = json.loads(campaign["capsys"].readouterr().out)
    assert delivery["content"]
    service_io.no_fingerprints(delivery)
    retained = service_io.read(campaign["root"] / delivery["reference"]["path"])
    assert retained["contexts"][0]["resources"][0]["content"] == delivery["content"]
    return retained


def test_diagnosis_gate_applies_to_service_knowledge(campaign, tmp_path):
    assert call(campaign, "start")["next_action"] == "campaign_baseline"
    with pytest.raises(SystemExit) as error:
        read_first_hit(campaign, "前缀缓存")
    assert error.value.code == 2
    assert "Record measured bottleneck evidence" in campaign["capsys"].readouterr().err
    evidence = tmp_path / "measurement.txt"
    evidence.write_text("Synthetic measurement: the service spends 4 ms in one operation.")
    result = call(campaign, "diagnose", "--bottleneck", "Service operation", "--evidence", evidence)
    assert result["diagnosis"]["reference_epoch"] == 0
    assert call(campaign, "status")["diagnosis"] == result["diagnosis"]
    delivery = read_first_hit(campaign, "前缀缓存")
    assert delivery["contexts"]
    binding = delivery["diagnosis_binding"]
    assert binding["diagnosis_id"] == result["diagnosis"]["id"]
    assert binding["reference_epoch"] == 0
    assert binding["started_at"] >= result["diagnosis"]["recorded_at"]
    call(campaign, "baseline")
    conditions = tmp_path / "conditions.json"
    changed = {**settings()["conditions"], "id": "c1", "runtime": "changed"}
    conditions.write_text(json.dumps(changed))
    refreshed = call(campaign, "refresh-references", "--conditions", conditions,
                     "--reason", "Changed test runtime")
    assert refreshed["next_action"] == "record_bottleneck_diagnosis"
    with pytest.raises(SystemExit) as error:
        read_first_hit(campaign, "前缀缓存")
    assert error.value.code == 2
    assert "Record measured bottleneck evidence" in campaign["capsys"].readouterr().err
    new = call(campaign, "diagnose", "--bottleneck", "Different operation", "--evidence", evidence)
    assert new["diagnosis"]["reference_epoch"] == 1
    recent = read_first_hit(campaign, "前缀缓存")["diagnosis_binding"]
    assert recent["diagnosis_id"] == new["diagnosis"]["id"]
    assert recent["reference_epoch"] == 1

    state_path = campaign["root"] / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["contexts"][0]["diagnosis_id"] = new["diagnosis"]["id"]
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ValueError, match="Knowledge diagnosis differs from the retained capture"):
        optimization.read_records(campaign["root"])


def events(campaign, attempt):
    path = campaign["root"] / attempt["path"] / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_one_service_order_and_independent_final_ignores_workspace(campaign):
    begin(campaign)
    result = submit(campaign, version="accepted", a=95, b=102)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == "PASS"
    log = events(campaign, attempt)
    assert [row["stage"] for row in log] == [
        "ready",
        "warmup",
        "measure",
        "measure",
        "quality",
        "profile",
        "stop",
    ]
    assert len({row["service_id"] for row in log}) == 1
    assert attempt["execution"]["cleanup_verified"] is True
    profile = attempt["execution"]["profile"]
    for relative in [profile["result"], *profile["artifacts"]]:
        assert service_io.safe_path(campaign["root"], relative).is_file()
    (campaign["repo"] / "engine.py").write_text("raise RuntimeError('unsubmitted workspace')")
    final = call(campaign, "final", "--reason", "Synthetic search complete")
    assert final["state"] == "completed"
    assert final["final"]["assessment"]["verdict"] == "PASS"
    assert {row["version"] for row in events(campaign, final["final"])} == {"accepted"}
    assert "profile" not in [row["stage"] for row in events(campaign, final["final"])]
    service_io.no_fingerprints(optimization.read_records(campaign["root"])[2])
    assert call(campaign, "status")["state"] == "completed"
    # Call the projection directly so schema errors are visible before CLI redaction.
    project(campaign["root"], export_id="service-projection")
    assert final["delivery"]["status"] == "published", final["delivery"]
    output = campaign["root"] / "delivery" / "check"
    assert main(["export", "--input", str(campaign["root"]), "--output", str(output)]) == 0
    assert json.loads(campaign["capsys"].readouterr().out)["status"] == "published"
    report = read_bundle(output)
    assert report["completion"]["status"] == "completed"
    assert report["final"]["revision"] == final["final"]["revision"]
    assert report["acceptance"]["verdict"] == "PASS"
    assert report["acceptance"]["delivery_accepted"] is False
    provenance = report["acceptance"]["assessment_provenance"]
    assert provenance["verification"] == "verified"
    assert provenance["artifact_ref"] == f"source:{final['final']['path']}/observation.json"
    observation = campaign["root"] / final["final"]["path"] / "observation.json"
    original = observation.read_bytes()
    try:
        observation.write_text('{"assessment":{"verdict":"FAIL"}}', encoding="utf-8")
        _, report, _ = project(campaign["root"], export_id="service-cached-projection")
    finally:
        observation.write_bytes(original)
    assert report["acceptance"]["verdict"] == "PASS"
    assert report["acceptance"]["assessment_provenance"]["verification"] == "unverified"
    assert report["acceptance"]["delivery_accepted"] is False


def _failed_final(campaign, *, opt_in=True, functional_failure=False):
    if opt_in:
        campaign["start"].append("--allow-final-continuation")
    begin(campaign)
    round_result = submit(campaign, version="first-selection", a=90, final_a=100,
                          final_functional_failure=functional_failure)
    assert round_result["latest_observation"]["assessment"]["verdict"] == "PASS"
    result = call(campaign, "final", "--reason", "Confirm the selected revision")
    assert result["state"] == "completed"
    assert result["final"]["assessment"]["verdict"] == "FAIL"
    assert result["delivery"]["status"] == "published"
    return result


def _continue_args(campaign, failed):
    return [
        "campaign", "round", "--session", str(campaign["root"]),
        "--candidate", str(campaign["repo"]), "--hypothesis", "Improve objective A",
        "--continue-after-final", failed["attempt_id"],
        "--continuation-reason", "Use the remaining search budget",
    ]


@pytest.mark.parametrize("second_verdict", ["PASS", "INCONCLUSIVE"])
def test_continue_after_failed_final_retains_each_final(campaign, second_verdict):
    from inferrsi.apps.views.dashboard import dashboard_snapshot, render_dashboard

    first_result = _failed_final(campaign)
    first = first_result["final"]
    root = campaign["root"]
    first_receipt = root / first["path"] / "observation.json"
    original_bytes = first_receipt.read_bytes()
    original_export = Path(first_result["delivery"]["output"])
    plan = (root / "plan.json").read_bytes()
    deadline = service_io.read(root / "state.json")["deadline"]
    assert first_result["can_continue"] is True
    assert first_result["next_action"] == "continue_search_after_failed_final"

    commit(campaign["repo"], version="second-selection", a=80,
           final_quality_missing=second_verdict == "INCONCLUSIVE")
    args = _continue_args(campaign, first)
    proc = subprocess.run(
        [sys.executable, "-m", "inferrsi", *args],
        cwd=Path(optimization.__file__).resolve().parents[2],
        check=True, capture_output=True, text=True, timeout=30,
    )
    resumed = json.loads(proc.stdout)
    assert resumed["state"] == "active"
    assert resumed["allocated_rounds"] == first_result["allocated_rounds"] + 1
    assert resumed["final"]["attempt_id"] == first["attempt_id"]
    assert resumed["latest_observation"]["continuation"] == {
        "after_final": first["attempt_id"], "reason": "Use the remaining search budget",
    }

    result = call(campaign, "final", "--reason", "Confirm the new selection",
                  expected=0 if second_verdict == "PASS" else 2)
    second = result["latest_observation"]
    assert second["kind"] == "final"
    assert second["assessment"]["verdict"] == second_verdict
    selected = second if second_verdict == "PASS" else first
    assert second["revision"] != first["revision"]
    assert result["final"]["attempt_id"] == selected["attempt_id"]
    assert result["can_continue"] is False
    assert (root / "plan.json").read_bytes() == plan
    assert service_io.read(root / "state.json")["deadline"] == deadline
    assert first_receipt.read_bytes() == original_bytes

    status = call(campaign, "status", expected=0 if second_verdict == "PASS" else 2)
    summary = service_io.read(root / "summary.json")
    dashboard = dashboard_snapshot(root)
    history = status["final_attempts"]
    for document in (summary, dashboard["data"]["service_optimization"]):
        assert document["final_attempts"] == history
        assert document["current_final_attempt_id"] == selected["attempt_id"]
    rendered = render_dashboard(dashboard)
    assert [row["verdict"] for row in history] == ["FAIL", second_verdict]
    for row in history:
        assert row["observation"] in rendered and (root / row["observation"]).is_file()

    assert read_bundle(original_export)["acceptance"]["verdict"] == "FAIL"
    assert result["delivery"]["status"] == "published"
    output = Path(result["delivery"]["output"])
    delivery = read_bundle(output)
    assert delivery["acceptance"]["verdict"] == selected["assessment"]["verdict"]
    assert delivery["acceptance"]["delivery_accepted"] is False
    assert delivery["final"]["attempt_id"] == selected["attempt_id"]
    assert [row["verdict"] for row in delivery["final_attempts"]] == ["FAIL", second_verdict]
    assert sum(row["current"] for row in delivery["final_attempts"]) == 1
    index = json.loads((output / "artifacts.json").read_text(encoding="utf-8"))
    indexed = {entry["id"] for entry in index["artifacts"]}
    for row in delivery["final_attempts"]:
        assert row["assessment_ref"] in indexed
        assert row["assessment_provenance"]["verification"] == "verified"
        for report in ("report.md", "report.html"):
            assert row["attempt_id"] in (output / report).read_text(encoding="utf-8")

    if second_verdict == "PASS":
        try:
            first_receipt.write_text("{}", encoding="utf-8")
            _, projected, _ = project(root, export_id="service-history-mismatch")
        finally:
            first_receipt.write_bytes(original_bytes)
        first_row, second_row = projected["final_attempts"]
        assert first_row["verdict"] == "FAIL"
        assert first_row["assessment_provenance"]["kind"] == "cached_state"
        assert first_row["assessment_provenance"]["verification"] == "unverified"
        assert second_row["assessment_provenance"]["verification"] == "verified"
        assert projected["acceptance"]["verdict"] == "PASS"


@pytest.mark.parametrize("barrier", ["disabled", "rounds", "time", "identity", "reason"])
def test_continuation_admission_preserves_state_on_refusal(campaign, monkeypatch, barrier):
    if barrier == "rounds":
        campaign["start"][campaign["start"].index("--rounds") + 1] = "1"
    failed = _failed_final(campaign, opt_in=barrier != "disabled")["final"]
    root = campaign["root"]
    state = service_io.read(root / "state.json")
    if barrier == "time":
        reserve = service_io.read(root / "plan.json")["final_reserve_seconds"]
        now = optimization._service_deadline(state) - reserve
        monkeypatch.setattr(optimization, "time", SimpleNamespace(time=lambda: now))
    args = _continue_args(campaign, failed)
    if barrier == "identity":
        args[args.index("--continue-after-final") + 1] = "different-attempt"
    if barrier == "reason":
        args[-1] = "  "
    directories = list(root.glob("rounds/*/attempt-*"))
    assert rejected(args) == 2
    assert service_io.read(root / "state.json") == state
    assert list(root.glob("rounds/*/attempt-*")) == directories
    status = call(campaign, "status")
    assert status["can_continue"] is (barrier in ("identity", "reason"))


@pytest.mark.parametrize("evidence", ["selected", "final", "functional_final"])
def test_continuation_status_and_admission_share_evidence_preflight(campaign, evidence):
    functional_failure = evidence == "functional_final"
    first_result = _failed_final(campaign, functional_failure=functional_failure)
    first = first_result["final"]
    assert first_result["can_continue"] is True
    if functional_failure:
        assert first["assessment"]["reason"] == "functional_check_rejected"
    root = campaign["root"]
    state_path = root / "state.json"
    before = state_path.read_bytes()
    attempt = (
        (root / first_result["best"]["path"]).parent if evidence == "selected"
        else root / first["path"]
    )
    stage = "precheck" if functional_failure else "measure-001"
    receipt = attempt / "execution" / stage / "result.json"
    original = receipt.read_bytes()
    commit(campaign["repo"], version="continue-with-valid-reference", a=80)
    args = _continue_args(campaign, first)
    round_directories = sorted(root.glob("rounds/*/attempt-*"))

    receipt.unlink()
    try:
        status = call(campaign, "status")
        assert status["can_continue"] is False
        assert status["next_action"] == "completed"
        reason = status["continuation_block_reason"]
        assert reason == "unverifiable_evaluation_evidence"
        assert rejected(args) == 2
        assert reason in campaign["capsys"].readouterr().err
        assert state_path.read_bytes() == before
        assert sorted(root.glob("rounds/*/attempt-*")) == round_directories
    finally:
        receipt.write_bytes(original)

    status = call(campaign, "status")
    assert status["can_continue"] is True
    assert status["continuation_block_reason"] is None
    assert main(args) == 0
    resumed = json.loads(campaign["capsys"].readouterr().out)
    assert resumed["state"] == "active"
    assert resumed["allocated_rounds"] == first_result["allocated_rounds"] + 1


def test_interrupted_continuation_admission_does_not_charge_twice(campaign, monkeypatch):
    class Interrupted(BaseException):
        pass

    def interrupted(*args):
        raise Interrupted

    first_result = _failed_final(campaign)
    first = first_result["final"]
    root = campaign["root"]
    commit(campaign["repo"], version="continue-once", a=80)
    args = _continue_args(campaign, first)
    with monkeypatch.context() as patch:
        patch.setattr(optimization, "_service_execute", interrupted)
        with pytest.raises(Interrupted):
            main(args)
    state = service_io.read(root / "state.json")
    pending = state["pending"]
    assert pending["round_number"] == 2
    assert pending["continuation"]["after_final"] == first["attempt_id"]
    assert not (root / pending["path"] / "request.json").exists()
    assert rejected(args) == 2
    assert service_io.read(root / "state.json") == state
    assert read_bundle(Path(first_result["delivery"]["output"]))["acceptance"]["verdict"] == "FAIL"

    cleanup = root.parent / "cleanup.json"
    cleanup.write_text(json.dumps({
        "attempt_id": pending["attempt_id"], "observed_at": time.time(),
        "reason": "Controller stopped before service launch", "cleanup_complete": True,
        "services": [],
    }))
    recovered = call(campaign, "recover", "--cleanup-receipt", cleanup, expected=2)
    assert recovered["pending"] is None
    assert recovered["allocated_rounds"] == 2
    assert recovered["latest_observation"]["attempt_id"] == pending["attempt_id"]
    assert recovered["latest_observation"]["assessment"]["verdict"] == "INCONCLUSIVE"
    assert recovered["final"]["attempt_id"] == first["attempt_id"]
    settled = service_io.read(root / "state.json")
    assert settled["deadline"] == state["deadline"]
    assert rejected(args) == 2
    assert service_io.read(root / "state.json") == settled


@pytest.mark.parametrize("failure", ["failed", "missing", "empty"])
def test_profile_failure_preserves_acceptance_and_final_selection(campaign, failure):
    begin(campaign)
    result = submit(campaign, version="profile-unavailable", a=80, profile_mode=failure)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == "PASS"
    assert attempt["assessment"]["quality_passed"] is True
    assert attempt["profiling"] == {"available": False}
    assert attempt["execution"]["profiling_error"]["stage"] == "profile"
    diagnostic = result["profiling_error"]
    assert call(campaign, "recover")["profiling_error"] == diagnostic
    assert diagnostic["message"] and (campaign["root"] / diagnostic["log"]).is_file()
    if failure == "failed":
        assert "synthetic collector failed" in diagnostic["message"]
    selected = result["best"]
    assert selected["attempt_id"] == attempt["attempt_id"]
    assert selected["profile"] is None
    rejected = submit(campaign, version="regression", a=70, b=120)
    assert rejected["latest_observation"]["assessment"]["verdict"] == "FAIL"
    assert rejected["best"] == selected
    final = call(campaign, "final", "--reason", "Regression rejected")
    assert final["final"]["revision"] == selected["revision"]
    assert {row["version"] for row in events(campaign, final["final"])} == {"profile-unavailable"}


def test_conditions_refresh_cannot_finalize_without_new_acceptance(campaign):
    begin(campaign)
    selected = submit(campaign, version="old-selected", a=90)["best"]
    previous_profile = call(campaign, "profile", "--round", "1")["profiling"]
    assert previous_profile["available"]
    assert previous_profile["result"] != selected["profile"]["result"]
    new = copy.deepcopy(settings()["conditions"])
    new.update(id="c1", runtime="changed-stdlib")
    path = campaign["root"].parent / "conditions.json"
    path.write_text(json.dumps(new))
    refreshed = call(
        campaign, "refresh-references", "--conditions", path, "--reason", "New test conditions"
    )
    assert refreshed["diagnosis"] is None
    diagnose(campaign)
    assert refreshed["can_finalize"] is False
    assert refreshed["accepted_attempt_ids"] == []
    assert refreshed["best"] is None
    refresh = refreshed["latest_observation"]["execution"]
    assert refresh["parent_profile_applicability"] == "not_applicable"
    assert refresh["retained_parent_profile"] == selected["profile"]
    assert refresh["retained_parent_profile"]["conditions"] == selected["conditions"]
    rejected = call(campaign, "final", "--reason", "References alone are insufficient")
    assert rejected["final"]["assessment"]["verdict"] == "INCONCLUSIVE"
    assert rejected["final"]["assessment"]["reason"] == "missing_current_conditions_acceptance"
    assert not (campaign["root"] / rejected["final"]["path"] / "service").exists()
    accepted = submit(campaign, version="new-selected", a=80, profile_mode="failed")
    assert accepted["latest_observation"]["profiling"] == {"available": False}
    assert accepted["best"]["conditions"] == new
    assert accepted["best"]["revision"] != selected["revision"]
    final = call(campaign, "final", "--reason", "New conditions accepted")
    assert final["final"]["assessment"]["verdict"] == "PASS"


def test_stagnation_is_advisory_and_recover_does_not_retrigger(campaign):
    begin(campaign)
    best = submit(campaign, version="accepted", a=95)["best"]
    submit(campaign, version="reject1", a=110)
    result = submit(campaign, version="reject2", a=111)
    assert result["state"] == "active"
    event, = result["stagnation"]["events"]
    assert event["best"]["profile"] == best["profile"]
    stored, = service_io.read(campaign["root"] / "state.json")["stagnation"]["events"]
    assert stored["best"]["attempt_id"] == best["attempt_id"] and "profile" not in stored["best"]
    recovered = call(campaign, "recover")
    assert recovered["stagnation"] == result["stagnation"]
    improved = submit(campaign, version="gain", a=90)
    assert improved["stagnation"]["consecutive"] == 0


def test_baseline_selected_final_has_no_self_gain_requirement(campaign):
    begin(campaign)
    submit(campaign, version="no-improvement", a=100)
    final = call(campaign, "final", "--reason", "No candidate selected")
    assert final["final"]["assessment"]["verdict"] == "PASS"
    assert final["best"]["kind"] == "baseline"


def test_missing_performance_evidence_blocks_without_quality_or_profile(campaign):
    begin(campaign)
    result = submit(campaign, version="missing", a=90, missing_metric=True, expected=2)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == "INCONCLUSIVE"
    assert "quality" not in [row["stage"] for row in events(campaign, attempt)]
    assert "profile" not in [row["stage"] for row in events(campaign, attempt)]


def test_service_mode_cli_does_not_require_legacy_metric_arguments(campaign):
    args = parser().parse_args(campaign["start"])
    assert args.evaluation_mode == "service_reuse" and args.metric_key is None
    with pytest.raises(SystemExit):
        parser().parse_args(["benchmarks", "session", "baseline", "--session", "unused"])


def test_service_knowledge_uses_find_without_file_fingerprints(campaign):
    call(campaign, "start")
    diagnose(campaign)
    retained = read_first_hit(campaign, "前缀缓存")
    context, = retained["contexts"]
    assert context["ref"].startswith("package:")
    assert context["resources"][0]["content"]
    assert context["revision"] == context["sources"][0]["commit"]
    service_io.no_fingerprints(retained)
    from inferrsi.apps.views.dashboard import dashboard_snapshot

    snapshot = dashboard_snapshot(campaign["root"])
    service_io.no_fingerprints(snapshot)
    assert snapshot["data"]["evaluation_mode"] == "service_reuse"


def test_service_read_follows_a_link_at_the_search_revision(campaign):
    from tests.apps.test_campaign_task_selection import BASELINE_CUE

    call(campaign, "start")
    diagnose(campaign)
    root = campaign["root"]
    assert main(["find", BASELINE_CUE, "--backend", "cuda", "--session", str(root),
                 "--limit", "2"]) == 0
    found = json.loads(campaign["capsys"].readouterr().out)
    hit = found["items"][0]
    assert hit["material_ref"] == "package:inferrsi.common.skills.inference_benchmark_design"
    assert main(hit["read_args"]) == 0
    primary = json.loads(campaign["capsys"].readouterr().out)
    link = "references/benchmark-commands.md"
    assert f"]({link})" in primary["content"]
    assert main([*hit["read_args"], "--resource", link]) == 0
    opened = json.loads(campaign["capsys"].readouterr().out)
    assert opened["revision"] == primary["revision"] == hit["revision"]
    retained = json.loads((root / opened["reference"]["path"]).read_bytes())
    context, = retained["contexts"]
    selected, = context["resources"]
    assert selected["role"] == "reference"
    assert selected["path"] == opened["content_resource"] and selected["path"].endswith(link)
    assert selected["content"] == opened["content"]
    assert context["content_bytes"] == len(opened["content"].encode()) > 0
    assert retained["request"]["search_ref"] == found["reference"]["path"]
    service_io.no_fingerprints(retained)


def test_knowledge_and_dashboard_never_enter_legacy_fingerprint_readers(campaign):
    begin(campaign)
    context = read_first_hit(campaign, "optimization")
    assert context["contexts"]
    service_io.no_fingerprints(context)
    submit(campaign, version="selected", a=90)
    from inferrsi.apps.views.dashboard import (
        dashboard_snapshot,
        render_dashboard,
        write_dashboard,
    )

    snapshot = dashboard_snapshot(campaign["root"])
    service_io.no_fingerprints(snapshot)
    page = render_dashboard(snapshot)
    assert "Service-reuse optimization" in page and "Objective values" in page
    assert "sha256" not in page.lower()
    # A refresh replaces the page this writer produced earlier.
    output = write_dashboard(campaign["root"])
    assert write_dashboard(campaign["root"]) == output


def test_service_reuse_page_can_be_rewritten_by_the_dashboard_writer(tmp_path):
    from inferrsi.apps.views.dashboard import _write_view_document, render_dashboard

    # write_dashboard renders this page and replaces only pages it recognizes as its own.
    snapshot = {"data": {"evaluation_mode": "service_reuse"}, "chart": "<svg></svg>"}
    page = render_dashboard(snapshot)
    output = tmp_path / "dashboard.html"
    assert _write_view_document(output, page, generator="InferRSI dashboard") == output
    assert _write_view_document(output, page, generator="InferRSI dashboard") == output
    assert output.read_text(encoding="utf-8") == page


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"quality": 0}, 0),
        ({"quality_rejected": True}, 0),
        ({"quality_missing": True}, 2),
        ({"functional_failure": True}, 0),
        ({"foreign_stage": "quality"}, 2),
    ],
)
def test_rejections_and_missing_stage_evidence_are_distinct(campaign, changes, expected):
    begin(campaign)
    result = submit(campaign, version="rejected", a=90, expected=expected, **changes)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == ("FAIL" if expected == 0 else "INCONCLUSIVE")
    assert result["best"]["kind"] == "baseline"
    assert attempt["profiling"] == {"available": False}
    assert not any(
        row["id"] == "profile" and row["status"] == "completed"
        for row in attempt["execution"]["steps"]
    )


def test_profile_timeout_retains_quality_and_stops_without_silent_retry(campaign):
    config = settings()
    config["sampling"]["profile_timeout_seconds"] = 1
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    result = submit(campaign, version="timeout", a=90, profile_mode="timeout")
    attempt = result["latest_observation"]
    stage = next(row for row in attempt["execution"]["steps"] if row["id"] == "profile")
    assert stage["status"] == "timeout"
    assert attempt["assessment"]["quality_passed"] is True
    assert attempt["execution"]["cleanup_verified"] is True
    assert attempt["assessment"]["verdict"] == "PASS"
    assert attempt["execution"]["profiling_error"]["status"] == "timed_out"
    recovered = call(campaign, "recover")
    assert recovered["latest_observation"] == attempt


def test_profile_interruption_retains_verdict_with_verified_cleanup(campaign, monkeypatch):
    from inferrsi.harness.executor.trials import external

    begin(campaign)
    original = external.execute_trial

    def interrupted(command, *args, **kwargs):
        if "profile" in command:
            raise KeyboardInterrupt()
        return original(command, *args, **kwargs)

    monkeypatch.setattr(external, "execute_trial", interrupted)
    result = submit(campaign, version="interrupted", a=90)
    assert result["latest_observation"]["execution"]["profiling_error"]["status"] == "interrupted"
    assert result["latest_observation"]["assessment"]["verdict"] == "PASS"
    assert result["latest_observation"]["assessment"]["quality_passed"] is True
    assert result["latest_observation"]["execution"]["cleanup_verified"] is True


def test_incomplete_baseline_prevents_candidate_search(campaign):
    commit(campaign["repo"], missing_metric=True)
    call(campaign, "start")
    result = call(campaign, "baseline", expected=2)
    assert result["best"] is None and result["state"] == "blocked"
    assert (
        rejected(
            [
                "campaign",
                "round",
                "--session",
                str(campaign["root"]),
                "--candidate",
                str(campaign["repo"]),
                "--hypothesis",
                "must not start",
            ]
        )
        == 2
    )


def test_baseline_comparison_quality_and_pause_resume(campaign):
    config = settings()
    config["quality"].pop("threshold")
    config["quality"].update(mode="baseline_comparison", tolerance=0)
    config["stagnation"] = {"rounds": 1, "action": "pause"}
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    result = submit(campaign, version="worse-quality", a=90, quality=0)
    assert result["state"] == "paused"
    assert result["latest_observation"]["assessment"]["quality_passed"] is False
    resumed = call(campaign, "resume", "--reason", "Reviewed system-wide bottlenecks")
    repeated = call(campaign, "resume", "--reason", "Reviewed system-wide bottlenecks")
    assert resumed["stagnation"] == repeated["stagnation"]
    assert resumed["state"] == "active"


def test_accepted_but_unselected_candidate_keeps_its_verdict(campaign):
    config = settings()
    config["stagnation"] = {"rounds": 1, "action": "pause"}
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    rejected_round = submit(campaign, version="rejected", a=110)
    assert rejected_round["state"] == "paused"
    call(campaign, "resume", "--reason", "Try a second-objective gain")
    result = submit(campaign, version="second-objective-gain", a=102, b=90)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["eligible"] is True
    assert attempt["selected"] is False
    assert result["best"]["kind"] == "baseline"
    assert result["state"] == "active"
    assert result["stagnation"]["consecutive"] == 0
    assert result["stagnation"]["notified"] is False
    assert result["stagnation"]["events"] == rejected_round["stagnation"]["events"]


def test_screening_below_estimate_runs_formal_quality_and_profile_on_same_service(campaign):
    config = settings()
    config["screening"] = {
        "command": [arg.replace("measure", "screening") for arg in config["commands"]["measure"]],
        "estimated_gain": 50,
    }
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    result = submit(campaign, version="actual-gain", a=95)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == "PASS"
    log = events(campaign, attempt)
    assert [r["stage"] for r in log].count("screening") == 2
    assert len({r["service_id"] for r in log}) == 1


@pytest.mark.parametrize("screen", ["screen_reject", "screen_error"])
@pytest.mark.parametrize("latency,verdict", [(90, "PASS"), (110, "FAIL")])
def test_unsuccessful_screening_collects_all_formal_results(campaign, screen, latency, verdict):
    config = settings()
    config["screening"] = {
        "command": [arg.replace("measure", "screening") for arg in config["commands"]["measure"]],
        "estimated_gain": 50,
    }
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    result = submit(campaign, version="screened", a=latency, **{screen: True})
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == verdict
    execution = attempt["execution"]
    if screen == "screen_reject":
        assert execution["screening"]["passed"] is False
    else:
        assert execution["screening"]["error"]
    formal = [s["result"] for s in execution["steps"] if s["id"].startswith("measure-")]
    assert [set(sample["scenarios"]) for sample in formal] == [{"a", "b"}, {"a", "b"}]
    assert all(sample["scenarios"]["a"]["latency"] == latency for sample in formal)
    log = events(campaign, attempt)
    stages = [row["stage"] for row in log]
    assert stages[-2:] == ["profile", "stop"]
    assert stages.count("quality") == (verdict == "PASS")
    assert len({row["service_id"] for row in log}) == 1


def test_optional_profile_command_and_timeout_configuration(campaign):
    config = settings()
    del config["commands"]["profile"]
    config["sampling"]["profile_timeout_seconds"] = 0
    campaign["config"].write_text(json.dumps(config))
    assert rejected(campaign["start"]) == 2
    assert not campaign["root"].exists()
    config["sampling"]["profile_timeout_seconds"] = 2
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    attempt = submit(campaign, version="no-profiler", a=90)["latest_observation"]
    assert attempt["assessment"]["verdict"] == "PASS"
    assert attempt["profiling"] == {"available": False}
    assert "profile" not in [e["stage"] for e in events(campaign, attempt)]
    failure = call(campaign, "profile", "--round", "1", expected=2)
    assert failure["profiling_error"]["message"]


@pytest.mark.parametrize("damage", [None, "missing", "empty", "receipt", "binding", "artifacts"])
def test_recover_commits_existing_observation_once_without_remeasurement(
    campaign, monkeypatch, damage
):
    begin(campaign)
    selected = submit(campaign, version="previous-selection", a=95)["best"]
    previous = service_io.read(
        campaign["root"] / selected["path"].removesuffix("/candidate") / "observation.json"
    )
    original = optimization.atomic_write_json

    def fail_state_commit(path, data):
        if path.name == "state.json" and data.get("pending") is None and data.get("attempts"):
            if data["attempts"][-1]["kind"] == "round":
                raise OSError("synthetic coordinator state-write failure")
        return original(path, data)

    monkeypatch.setattr(optimization, "atomic_write_json", fail_state_commit)
    commit(campaign["repo"], version="recovery", a=90)
    assert (
        rejected(
            [
                "campaign",
                "round",
                "--session",
                str(campaign["root"]),
                "--candidate",
                str(campaign["repo"]),
                "--hypothesis",
                "Injected settlement interruption",
            ]
        )
        == 2
    )
    campaign["capsys"].readouterr()
    monkeypatch.setattr(optimization, "atomic_write_json", original)
    pending = service_io.read(campaign["root"] / "state.json")["pending"]
    observation_path = campaign["root"] / pending["path"] / "observation.json"
    observation = service_io.read(observation_path)
    profile = observation["execution"]["profile"]
    artifact = campaign["root"] / profile["artifacts"][0]
    if damage == "missing":
        artifact.unlink()
    elif damage == "empty":
        artifact.write_text("")
    elif damage == "receipt":
        (campaign["root"] / profile["result"]).write_text('{"status":"incomplete"}')
    elif damage == "binding":
        profile["binding"]["service_id"] = "another-service"
        receipt_path = campaign["root"] / profile["result"]
        receipt = service_io.read(receipt_path)
        receipt["binding"] = profile["binding"]
        receipt_path.write_text(json.dumps(receipt))
        observation_path.write_text(json.dumps(observation))
    elif damage == "artifacts":
        profile["artifacts"] = []
        observation_path.write_text(json.dumps(observation))
    result = call(campaign, "recover")
    attempt = result["latest_observation"]
    log = events(campaign, attempt)
    assert result["completed_rounds"] == 2
    assert len(log) == 7
    assert attempt["assessment"]["verdict"] == "PASS"
    assert result["best"]["attempt_id"] == attempt["attempt_id"]
    assert result["accepted_attempt_ids"] == [selected["attempt_id"], attempt["attempt_id"]]
    assert attempt["profiling"]["available"] is (damage is None)
    if damage:
        assert attempt["profiling"] == {"available": False}
    assert service_io.read(
        campaign["root"] / previous["path"] / "observation.json"
    ) == previous
    again = call(campaign, "recover")
    assert again["latest_observation"] == attempt
    assert len(events(campaign, attempt)) == len(log)


@pytest.mark.parametrize("interrupted", [False, True])
@pytest.mark.parametrize("damage", ["profile", "configuration"])
def test_final_rechecks_selected_evidence_before_settlement(
    campaign, monkeypatch, interrupted, damage
):
    begin(campaign)
    selected = submit(campaign, version="selected", a=90)["best"]
    selected_attempt = service_io.read(
        campaign["root"] / selected["path"].removesuffix("/candidate") / "observation.json"
    )
    expected = 2 if damage == "configuration" else 0
    execute, write = optimization._service_execute, optimization.atomic_write_json

    def execute_then_damage(*args):
        result = execute(*args)
        assert result["assessment"]["verdict"] == "PASS"
        if not interrupted:
            damage_evidence()
        return result

    def damage_evidence():
        if damage == "profile":
            (campaign["root"] / selected["profile"]["artifacts"][0]).unlink()
        else:
            (campaign["root"] / selected["effective_config_path"]).write_text('{"mode":"altered"}')

    def fail_state_commit(path, data):
        if path.name == "state.json" and data.get("final") is not None:
            raise OSError("synthetic final state-write failure")
        return write(path, data)

    monkeypatch.setattr(optimization, "_service_execute", execute_then_damage)
    if interrupted:
        monkeypatch.setattr(optimization, "atomic_write_json", fail_state_commit)
        assert rejected(
            ["campaign", "final", "--session", str(campaign["root"]), "--reason", "Stop search"]
        ) == 2
        campaign["capsys"].readouterr()
        monkeypatch.setattr(optimization, "atomic_write_json", write)
        pending = service_io.read(campaign["root"] / "state.json")["pending"]
        assert service_io.read(
            campaign["root"] / pending["path"] / "observation.json"
        )["assessment"]["verdict"] == "PASS"
        damage_evidence()
        result = call(campaign, "recover", expected=expected)
    else:
        result = call(campaign, "final", "--reason", "Stop search", expected=expected)
    final = result["final"]
    assert result["best"] == selected
    if damage == "configuration":
        assert result["state"] == "blocked"
        assert final["assessment"]["verdict"] == "INCONCLUSIVE"
        assert final["assessment"]["reason"] == "unverifiable_selected_configuration"
        assert final["assessment_before_settlement"]["verdict"] == "PASS"
    else:
        assert result["state"] == "completed"
        assert final["assessment"]["verdict"] == "PASS"
    assert final["execution"]["assessment"]["verdict"] == "PASS"
    assert service_io.read(
        campaign["root"] / selected_attempt["path"] / "observation.json"
    ) == selected_attempt
    log = events(campaign, final)
    assert [row["stage"] for row in log] == [
        "ready", "warmup", "measure", "measure", "quality", "stop"
    ]
    again = call(campaign, "recover", expected=expected)
    assert again["final"] == final
    assert events(campaign, final) == log


def test_final_requires_retained_configuration_even_when_profile_is_unavailable(campaign):
    begin(campaign)
    selected = submit(campaign, version="selected", a=90)["best"]
    config_path = campaign["root"] / selected["effective_config_path"]
    config_path.write_text('{"mode":"altered"}')
    result = call(campaign, "final", "--reason", "Cannot establish selected configuration")
    assert result["final"]["assessment"]["reason"] == "unverifiable_selected_configuration"
    config_path.write_text(json.dumps(settings()["conditions"]["effective_config"]))
    (campaign["root"] / selected["profile"]["artifacts"][0]).unlink()
    result = call(campaign, "final", "--reason", "Retest selected candidate")
    assert result["final"]["assessment"]["verdict"] == "PASS"


@pytest.mark.parametrize("block", ["commands", "sampling", "conditions", "quality", "stagnation"])
def test_invalid_protocol_containers_rejected_before_campaign_writes(campaign, block):
    config = settings()
    config[block] = []
    campaign["config"].write_text(json.dumps(config))
    assert rejected(campaign["start"]) == 2
    assert not campaign["root"].exists()


def test_live_dashboard_state_has_no_content_fingerprint(campaign):
    import threading
    from urllib.request import urlopen

    from inferrsi.apps.views.dashboard_live import DashboardServer

    call(campaign, "start")
    server = DashboardServer(campaign["root"], None, 0)
    worker = threading.Thread(target=server.serve_forever)
    worker.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/api/state") as response:
            assert response.status == 200 and response.headers.get("ETag") is None
            service_io.no_fingerprints(json.load(response))
        with urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
            assert b"Service-reuse optimization" in response.read()
    finally:
        server.shutdown()
        worker.join()
        server.server_close()


@pytest.mark.parametrize("compatible", [True, False])
def test_existing_quality_reference_is_reused_only_when_compatible(campaign, compatible):
    config = settings()
    config["quality"].pop("threshold")
    config["quality"].update(
        mode="baseline_comparison", tolerance=0, reference_path="reference.json"
    )
    revision = subprocess.check_output(
        ["git", "-C", str(campaign["repo"]), "rev-parse", "HEAD"], text=True
    ).strip()
    reference = {
        "status": "completed",
        "revision": revision,
        "conditions": config["conditions"],
        "service_id": "previous-service",
        "run_id": "previous-run",
        "dataset": "synthetic",
        "scorer": "exact-v1" if compatible else "incompatible-scorer",
        "samples": 2,
        "quality": 1,
    }
    protocol = Path(campaign["start"][campaign["start"].index("--protocol") + 1])
    (protocol / "reference.json").write_text(json.dumps(reference))
    campaign["config"].write_text(json.dumps(config))
    call(campaign, "start")
    result = call(campaign, "baseline", expected=0 if compatible else 2)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == ("PASS" if compatible else "INCONCLUSIVE")
    assert "quality" not in [row["stage"] for row in events(campaign, attempt)]


@pytest.mark.parametrize("same_version", [False, True])
def test_reference_refresh_uses_baseline_cache_without_testing_parent_quality(
    campaign, same_version
):
    config = settings()
    config["quality"].pop("threshold")
    config["quality"].update(
        mode="baseline_comparison", tolerance=0, reference_path="reference.json"
    )
    revision = subprocess.check_output(
        ["git", "-C", str(campaign["repo"]), "rev-parse", "HEAD"], text=True
    ).strip()
    reference = {
        "status": "completed", "revision": revision, "conditions": config["conditions"],
        "service_id": "previous-service", "run_id": "previous-run",
        "dataset": "synthetic", "scorer": "exact-v1", "samples": 2, "quality": 1,
    }
    protocol = Path(campaign["start"][campaign["start"].index("--protocol") + 1])
    (protocol / "reference.json").write_text(json.dumps(reference))
    campaign["config"].write_text(json.dumps(config))
    selected = begin(campaign)["best"]
    if not same_version:
        selected = submit(campaign, version="selected-parent", a=90)["best"]
        assert selected["revision"] != revision
    conditions = {**config["conditions"], "id": "c1", "runtime": "changed-stdlib"}
    conditions_path = campaign["root"].parent / "conditions.json"
    conditions_path.write_text(json.dumps(conditions))
    failed = call(
        campaign, "refresh-references", "--conditions", conditions_path,
        "--reason", "Changed conditions", expected=2,
    )["latest_observation"]
    assert failed["assessment"]["verdict"] == "INCONCLUSIVE"
    assert "incompatible baseline reference" in (
        failed["execution"]["runs"][0]["assessment"]["reason"]
    )
    failed_path = campaign["root"] / failed["path"] / "observation.json"
    before_retry = failed_path.read_bytes()
    repaired = campaign["root"].parent / "repaired-protocol"
    shutil.copytree(protocol, repaired)
    reference.update(conditions=conditions, service_id="new-service", run_id="new-run")
    (repaired / "reference.json").write_text(json.dumps(reference))
    result = call(
        campaign, "refresh-references", "--conditions", conditions_path,
        "--reason", "Refresh compatible references", "--retry-of", failed["attempt_id"],
        "--repair-reason", "Supplied compatible baseline quality evidence",
        "--repair-protocol", repaired,
    )
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == "PASS"
    references = attempt["execution"]["references"]
    assert [item["revision"] for item in references] == [revision, selected["revision"]]
    assert all(item["conditions"] == conditions for item in references)
    assert references[0]["quality_score"] == 1
    assert len(attempt["execution"]["runs"]) == (1 if same_version else 2)
    if same_version:
        assert references[0] == references[1]
    else:
        assert references[1]["quality_score"] is None
        assert references[1]["profile"] is None
        parent_run = attempt["execution"]["runs"][1]
        for name in ("quality", "profile"):
            assert next(step for step in parent_run["steps"] if step["id"] == name) == {
                "id": name, "status": "skipped", "reason": "performance_reference_only"
            }
    for reference in references:
        log_path = campaign["root"] / reference["path"].removesuffix("/candidate") / "events.jsonl"
        stages = [json.loads(line)["stage"] for line in log_path.read_text().splitlines()]
        assert stages == ["ready", "warmup", "measure", "measure", "stop"]
    assert result["best"] is None and result["can_finalize"] is False
    assert failed_path.read_bytes() == before_retry
    diagnose(campaign)
    accepted = submit(campaign, version="current-conditions", a=80)
    assert accepted["latest_observation"]["assessment"]["verdict"] == "PASS"
    assert accepted["best"]["conditions"] == conditions


def test_execution_script_repair_is_retained_and_final_uses_selected_scripts(campaign):
    begin(campaign)
    selected = submit(campaign, version="selected", a=90)["best"]
    broken = submit(campaign, version="missing-measurement", a=80, missing_metric=True, expected=2)
    old = broken["latest_observation"]
    protocol = Path(campaign["start"][campaign["start"].index("--protocol") + 1])
    repaired = campaign["root"].parent / "repaired-protocol"
    shutil.copytree(protocol, repaired)
    path = repaired / "protocol.py"
    path.write_text(
        path.read_text().replace(
            'if phase == "service":',
            'raise RuntimeError("repaired script rejected")\nif phase == "service":',
        )
    )
    attempt = call(
        campaign,
        "round",
        "--candidate",
        campaign["repo"],
        "--hypothesis",
        "Execution repair",
        "--retry-of",
        old["attempt_id"],
        "--repair-reason",
        "Investigated fixture",
        "--repair-protocol",
        repaired,
        expected=2,
    )
    assert attempt["best"] == selected
    assert attempt["latest_observation"]["protocol_path"] != selected["protocol_path"]
    inspection = campaign["root"].parent / "cleanup.json"
    inspection.write_text(
        json.dumps(
            {
                "attempt_id": attempt["latest_observation"]["attempt_id"],
                "observed_at": 1,
                "reason": "Inspected failed precheck; no service started",
                "cleanup_complete": True,
                "services": [],
            }
        )
    )
    call(
        campaign,
        "resume",
        "--reason",
        "Abandon failed execution repair",
        "--cleanup-receipt",
        inspection,
    )
    result = call(campaign, "final", "--reason", "Retest retained selected script set")
    assert result["final"]["assessment"]["verdict"] == "PASS"
    assert result["final"]["protocol_path"] == selected["protocol_path"]


def test_round_usage_export_is_retained_without_fingerprint(campaign):
    begin(campaign)
    export = campaign["root"].parent / "usage.json"
    export.write_text('{"input_tokens":10,"output_tokens":2}')
    commit(campaign["repo"], version="usage", a=90)
    result = call(
        campaign,
        "round",
        "--candidate",
        campaign["repo"],
        "--hypothesis",
        "Usage evidence",
        "--usage-export",
        export,
    )
    summary = optimization.read_records(campaign["root"])[2]
    assert summary["usage"]["total_tokens"] == 12
    assert result["latest_observation"]["observations"]["usage_source"] == {"kind": "caller_export"}
    call(campaign, "recover")
    assert optimization.read_records(campaign["root"])[2]["usage"]["total_tokens"] == 12


def test_exact_round_policy_and_legacy_argument_validation(campaign):
    campaign["start"] += ["--round-mode", "exact"]
    begin(campaign)
    submit(campaign, version="one-of-eight", a=90)
    result = call(campaign, "final", "--reason", "Incomplete exact budget")
    assert result["final"]["assessment"]["reason"] == "incomplete_round_policy"
    assert result["state"] == "active"
    from inferrsi.harness.evaluator import project_steps

    assert [
        step["side"]
        for step in project_steps(
            {
                "quality_command": ["quality"],
                "measure_command": ["measure"],
                "warmups": 0,
                "repetitions": 2,
            }
        )
        if step["phase"] == "measurement"
    ] == ["baseline", "candidate", "candidate", "baseline"]


def test_current_epoch_candidate_can_seed_selection_below_old_parent_rank(campaign):
    begin(campaign)
    old = submit(campaign, version="old-parent", a=90)["best"]
    conditions = copy.deepcopy(settings()["conditions"])
    conditions.update(id="c1", runtime="new-runtime")
    path = campaign["root"].parent / "conditions.json"
    path.write_text(json.dumps(conditions))
    call(campaign, "refresh-references", "--conditions", path, "--reason", "New runtime")
    diagnose(campaign)
    result = submit(campaign, version="c1-accepted", a=92, b=90)
    assert result["best"]["revision"] != old["revision"]
    assert result["best"]["measurements"]["values"]["a"] > old["measurements"]["values"]["a"]
    assert result["best"]["attempt_id"] in result["accepted_attempt_ids"]


def test_missing_mode_marker_rejects_without_falling_back_to_file_fingerprints(campaign):
    call(campaign, "start")
    path = campaign["root"] / "plan.json"
    plan = json.loads(path.read_text())
    del plan["evaluation_mode"]
    path.write_text(json.dumps(plan))
    assert rejected(["campaign", "status", "--session", str(campaign["root"])]) == 2
    from inferrsi.apps.views.dashboard import dashboard_snapshot

    with pytest.raises(ValueError, match="Incompatible service campaign"):
        dashboard_snapshot(campaign["root"])


def test_final_checks_selected_revision_against_original_attempt(campaign):
    begin(campaign)
    submit(campaign, version="selected", a=90)
    path = campaign["root"] / "state.json"
    state = json.loads(path.read_text())
    state["best"]["revision"] = state["initial_reference"]["revision"]
    path.write_text(json.dumps(state))
    result = call(campaign, "final", "--reason", "Selected revision cannot be established")
    assert result["final"]["assessment"]["reason"] == "unverifiable_selected_attempt_binding"
    assert result["final"]["assessment"]["verdict"] == "INCONCLUSIVE"
    assert not (campaign["root"] / result["final"]["path"] / "service").exists()


@pytest.mark.parametrize("role", ["baseline", "candidate"])
def test_final_rebuilds_changed_retained_code_from_recorded_commit(campaign, role):
    begin(campaign)
    if role == "candidate":
        alternate = campaign["repo"].with_name("alternate-repo")
        shutil.copytree(campaign["repo"], alternate)
        campaign["repo"] = alternate
    result = submit(campaign, version="accepted", a=90 if role == "candidate" else 100)
    selected = result["best"]
    saved = campaign["root"] / selected["path"] / "engine.py"
    saved.unlink()
    saved.write_text("raise RuntimeError('changed retained source must never run')\n")
    # The current checkout and file set are not the authority for an older commit.
    (campaign["repo"] / "engine.py").unlink()
    result = call(campaign, "final", "--reason", "Verify original committed version")
    final = result["final"]
    assert final["assessment"]["verdict"] == "PASS"
    assert final["revision"] == selected["revision"]
    expected_version = "accepted" if role == "candidate" else "baseline"
    assert {row["version"] for row in events(campaign, final)} == {expected_version}
    assert "changed retained" not in (
        campaign["root"] / final["path"] / "candidate/engine.py"
    ).read_text()


def test_missing_authoritative_repository_cannot_run_retained_selection(campaign):
    begin(campaign)
    selected = submit(campaign, version="selected", a=90)["best"]
    shutil.rmtree(campaign["repo"] / ".git")
    result = call(campaign, "final", "--reason", "Source commit unavailable", expected=2)
    final = result["final"]
    assert final["assessment"]["verdict"] == "INCONCLUSIVE"
    assert result["best"] == selected
    assert not (campaign["root"] / final["path"] / "service").exists()


def test_independent_profile_deadline_still_runs_bounded_stop(campaign):
    config = settings()
    config["sampling"]["stage_timeout_seconds"] = 8
    campaign["config"].write_text(json.dumps(config))
    index = campaign["start"].index("--evaluation-timeout-seconds")
    campaign["start"][index + 1] = "6"
    begin(campaign)
    result = submit(campaign, version="deadline", a=90, profile_mode="timeout")
    attempt = result["latest_observation"]
    execution = attempt["execution"]
    steps = {row["id"]: row for row in execution["steps"]}
    assert steps["profile"]["status"] == "timeout"
    assert steps["stop"]["status"] == "completed"
    assert execution["cleanup_timeout_seconds"] == 8
    assert execution["cleanup_budget_scope"] == "separate_from_evaluation"
    assert execution["cleanup_verified"] is True
    assert attempt["assessment"]["verdict"] == "PASS"
    assert attempt["assessment"]["quality_passed"] is True
    assert [row["stage"] for row in events(campaign, attempt)][-1] == "stop"


def test_required_measurement_timeout_still_uses_bounded_cleanup(campaign):
    campaign["start"][campaign["start"].index("--evaluation-timeout-seconds") + 1] = "6"
    begin(campaign)
    result = submit(campaign, version="deadline", a=90, measure_timeout=True, expected=2)
    attempt = result["latest_observation"]
    execution = attempt["execution"]
    steps = {item["id"]: item for item in execution["steps"]}
    assert steps["measure-001"]["status"] == "timeout"
    assert steps["stop"]["status"] == "completed"
    assert execution["cleanup_verified"] is True
    assert attempt["assessment"]["verdict"] == "INCONCLUSIVE"
    assert attempt["profiling"] == {"available": False}
    assert "capture" not in execution


@pytest.mark.parametrize("attribute", ["export-ignore", "export-subst"])
def test_execution_preserves_tree_inputs_despite_export_attributes(campaign, attribute):
    repo = campaign["repo"]
    payload = repo / "inputs/payload.txt"
    payload.parent.mkdir()
    content = b"literal $Format:%s$\r\n\x00payload\n"
    payload.write_bytes(content)
    payload.chmod(0o755)
    (repo / ".gitattributes").write_text(f"inputs/payload.txt {attribute}\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitattributes", "inputs"], check=True)
    commit(repo)
    campaign["start"] += ["--include", "inputs"]
    baseline = begin(campaign)["latest_observation"]
    candidate = submit(campaign, version="accepted", a=90)["latest_observation"]
    final = call(campaign, "final", "--reason", "Verify exact committed inputs")["final"]
    assert final["assessment"]["verdict"] == "PASS"
    for attempt in (baseline, candidate, final):
        for directory in ("candidate", "workspace"):
            retained = campaign["root"] / attempt["path"] / directory / "inputs/payload.txt"
            assert retained.read_bytes() == content
            assert retained.stat().st_mode & 0o777 == 0o555


@pytest.mark.parametrize("invalid", ["missing", "symlink"])
def test_tree_snapshot_rejects_missing_or_special_declared_input(campaign, invalid):
    repo = campaign["repo"]
    if invalid == "symlink":
        (repo / invalid).symlink_to("engine.py")
        subprocess.run(["git", "-C", str(repo), "add", invalid], check=True)
        commit(repo)
    revision = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    destination = repo.parent / "snapshot"
    with pytest.raises(ValueError, match="missing|symbolic"):
        executor.retain_service_revision(repo, destination, ["engine.py", invalid], revision)
    assert not destination.exists()


@pytest.mark.parametrize("staged", [False, True])
@pytest.mark.parametrize("includes", [["inputs"], None])
def test_revision_rejects_deleted_files_inside_declared_directory(campaign, staged, includes):
    repo = campaign["repo"]
    inputs = repo / "inputs"
    inputs.mkdir()
    (inputs / "keep.txt").write_text("keep")
    deleted = inputs / "delete.txt"
    deleted.write_text("delete")
    subprocess.run(["git", "-C", str(repo), "add", "inputs"], check=True)
    commit(repo)
    executor.service_revision(repo, includes)

    deleted.unlink()
    if staged:
        subprocess.run(["git", "-C", str(repo), "add", "-u"], check=True)
    with pytest.raises(ValueError, match="Commit declared candidate inputs"):
        executor.service_revision(repo, includes)

    subprocess.run(["git", "-C", str(repo), "add", "-u"], check=True)
    commit(repo)
    revision = executor.service_revision(repo, includes)
    destination = repo.parent / "snapshot"
    executor.retain_service_revision(repo, destination, includes, revision)
    assert (destination / "inputs/keep.txt").read_text() == "keep"
    assert not (destination / "inputs/delete.txt").exists()


def test_revision_ignores_untracked_cache_but_rejects_untracked_input(campaign):
    repo = campaign["repo"]
    inputs = repo / "inputs"
    inputs.mkdir()
    (inputs / "keep.txt").write_text("keep")
    subprocess.run(["git", "-C", str(repo), "add", "inputs"], check=True)
    commit(repo)
    revision = executor.service_revision(repo, ["inputs"])

    cache = inputs / "__pycache__"
    cache.mkdir()
    (cache / "entry").touch()
    assert executor.service_revision(repo, ["inputs"]) == revision

    (inputs / "new.txt").touch()
    with pytest.raises(ValueError, match="Commit declared candidate inputs"):
        executor.service_revision(repo, ["inputs"])


def test_revision_ignores_deletions_outside_declared_inputs(campaign):
    repo = campaign["repo"]
    inputs = repo / "inputs"
    inputs.mkdir()
    (inputs / "keep.txt").write_text("keep")
    subprocess.run(["git", "-C", str(repo), "add", "inputs"], check=True)
    commit(repo)
    revision = executor.service_revision(repo, ["inputs"])
    (repo / "engine.py").unlink()
    assert executor.service_revision(repo, ["inputs"]) == revision


@pytest.mark.parametrize("rejections", [1, 2])
def test_refresh_resets_stagnation_without_erasing_history(campaign, rejections):
    begin(campaign)
    for index in range(rejections):
        before = submit(campaign, version=f"rejected-{index}", a=110)
    conditions = {**settings()["conditions"], "id": "new-conditions"}
    path = campaign["root"].parent / "conditions.json"
    path.write_text(json.dumps(conditions))
    refreshed = call(
        campaign, "refresh-references", "--conditions", path, "--reason", "Changed workload"
    )
    diagnose(campaign)
    assert refreshed["stagnation"]["consecutive"] == 0
    assert refreshed["stagnation"]["notified"] is False
    assert refreshed["stagnation"]["events"] == before["stagnation"]["events"]
    after = submit(campaign, version="new-conditions-rejected", a=110)
    assert after["stagnation"]["consecutive"] == 1
    assert after["stagnation"]["events"] == before["stagnation"]["events"]


@pytest.mark.parametrize("round_mode", ["exact", "up_to"])
def test_refresh_without_round_capacity_preserves_finalizable_state(campaign, round_mode):
    campaign["start"][campaign["start"].index("--rounds") + 1] = "1"
    campaign["start"] += ["--round-mode", round_mode]
    begin(campaign)
    submit(campaign, version="selected", a=90)
    before = service_io.read(campaign["root"] / "state.json")
    conditions = {**settings()["conditions"], "id": "new-conditions"}
    path = campaign["root"].parent / "conditions.json"
    path.write_text(json.dumps(conditions))
    assert rejected([
        "campaign", "refresh-references", "--session", str(campaign["root"]),
        "--conditions", str(path), "--reason", "No acceptance capacity",
    ]) == 2
    assert "No round budget for current-conditions acceptance" in (
        campaign["capsys"].readouterr().err
    )
    assert service_io.read(campaign["root"] / "state.json") == before
    assert not (campaign["root"] / "references").exists()
    result = call(campaign, "final", "--reason", "Complete original conditions")
    assert result["final"]["assessment"]["verdict"] == "PASS"


def test_backfill_after_final_preserves_original_evidence_and_selection(campaign, monkeypatch):
    from inferrsi.apps.views.dashboard import dashboard_snapshot, render_dashboard
    from inferrsi.harness.executor.trials import external

    baseline = begin(campaign)["best"]
    attempt = submit(campaign, version="selected", a=90)["latest_observation"]
    inline = attempt["execution"]["profile"]
    root = campaign["root"]
    state = service_io.read(root / "state.json")
    observation = service_io.read(root / attempt["path"] / "observation.json")
    for choice in (state["best"], state["comparison_parent"], observation["best_after"]):
        assert choice["attempt_id"] == attempt["attempt_id"]
        assert "profile" not in choice
    for choice in (
        state["initial_reference"], observation["initial"], observation["parent"],
        observation["best_after"]["parent_reference_at_acceptance"],
    ):
        assert choice["attempt_id"] == baseline["attempt_id"]
        assert "profile" not in choice
    original_files = [
        root / attempt["path"] / "observation.json",
        root / inline["result"], root / inline["artifacts"][0],
    ]
    final = call(campaign, "final", "--reason", "Search complete")
    original_files.append(root / final["final"]["path"] / "observation.json")
    originals = {p: p.read_bytes() for p in original_files}
    usage = optimization.read_records(root)[2]["usage"]

    published = call(campaign, "profile", "--round", "1")
    assert published["target_attempt_id"] == attempt["attempt_id"]
    profile = published["profiling"]
    assert profile["available"] and profile["result"] != inline["result"]
    assert all((root / path).is_file() for path in [profile["result"], *profile["artifacts"]])
    binding = service_io.read(root / profile["result"])["binding"]
    for key in ("revision", "conditions", "effective_config"):
        assert binding[key] == inline["binding"][key]
    for key in ("service_id", "run_id"):
        assert binding[key] != inline["binding"][key]
    evidence_root = (root / profile["result"]).parents[2]
    backfill_events = [
        json.loads(line) for line in (evidence_root / "events.jsonl").read_text().splitlines()
    ]
    assert [row["stage"] for row in backfill_events] == ["ready", "warmup", "profile", "stop"]
    assert {row["service_id"] for row in backfill_events} == {binding["service_id"]}
    snapshot = dashboard_snapshot(root)
    reported = snapshot["data"]["service_optimization"]
    assert reported["selected_candidate"]["profile"] == inline
    reported_round = next(
        r for r in reported["attempts"] if r["attempt_id"] == attempt["attempt_id"]
    )
    assert reported_round["profiling"] == profile
    assert reported_round["best_after"]["profile"] == inline
    report = render_dashboard(snapshot)
    assert "Profiling available: yes" in report and profile["result"] in report
    execute = external.execute_trial

    def fail_capture(command, *args, **kwargs):
        if "profile" in command:
            return {"status": "failed", "error": "backfill collector failed", "returncode": 9}
        return execute(command, *args, **kwargs)

    monkeypatch.setattr(external, "execute_trial", fail_capture)
    failed = call(campaign, "profile", "--round", "1", expected=2)
    assert "backfill collector failed" in failed["profiling_error"]["message"]
    assert call(campaign, "recover")["profiling_error"] == failed["profiling_error"]

    def interrupt_capture(command, *args, **kwargs):
        if "profile" in command:
            raise KeyboardInterrupt()
        return execute(command, *args, **kwargs)

    monkeypatch.setattr(external, "execute_trial", interrupt_capture)
    interrupted = call(campaign, "profile", "--round", "1", expected=130)
    assert interrupted["profiling_error"]["status"] == "interrupted"
    status = call(campaign, "status")
    assert status["rounds"] == [
        {
            "round_number": 1,
            "attempt_id": attempt["attempt_id"],
            "verdict": "PASS",
            "profiling": profile,
        }
    ]
    assert status["best"] == final["best"] and status["final"] == final["final"]
    assert status["best"]["profile"] == inline
    assert status["allocated_rounds"] == final["allocated_rounds"]
    _, state_view, summary = optimization.read_records(root)
    assert state_view["best"] == status["best"]
    assert summary["usage"] == usage
    current = next(r for r in summary["attempts"] if r["attempt_id"] == attempt["attempt_id"])
    assert current["profiling"] == profile
    assert all(path.read_bytes() == content for path, content in originals.items())


def test_backfill_targets_last_terminal_retry_after_deadline(campaign, monkeypatch):
    begin(campaign)
    old = submit(campaign, version="missing", missing_metric=True, expected=2)["latest_observation"]
    root = campaign["root"]
    old_path = root / old["path"] / "observation.json"
    old_bytes = old_path.read_bytes()
    ineligible = call(campaign, "profile", "--round", "1", expected=2)
    assert ineligible["profiling_error"]["message"]
    result = submit(campaign, version="rejected", a=110, retry=old["attempt_id"])
    settled = result["latest_observation"]
    assert settled["assessment"]["verdict"] == "FAIL"
    state = service_io.read(root / "state.json")
    monkeypatch.setattr(optimization, "time", SimpleNamespace(time=lambda: state["deadline"] + 300))
    assert call(campaign, "status")["remaining_seconds"] == 0
    with optimization._locked(root):
        locked = call(campaign, "profile", "--round", "1", expected=2)
        assert locked["profiling_error"]["message"]
    published = call(campaign, "profile", "--round", "1")
    assert published["target_attempt_id"] == settled["attempt_id"]
    assert published["profiling"]["available"] is True
    assert (root / published["profiling"]["result"]).is_file()
    assert old_path.read_bytes() == old_bytes
    assert call(campaign, "status")["latest_observation"]["profiling"] == published["profiling"]


@pytest.mark.parametrize("damage", [None, "partial", "unreadable"])
def test_legacy_round_availability_is_derived_without_changing_history(campaign, damage):
    from inferrsi.apps.views.dashboard import dashboard_snapshot, render_dashboard

    begin(campaign)
    attempt = submit(campaign, version="old", a=90)["latest_observation"]
    root = campaign["root"]
    state_path = root / "state.json"
    state = service_io.read(state_path)
    historical = next(a for a in state["attempts"] if a["attempt_id"] == attempt["attempt_id"])
    historical.pop("profiling", None)
    profile = historical["execution"]["profile"]
    trace = service_io.read(root / profile["result"])
    profile.pop("capture_started_at")
    profile.pop("capture_ended_at")
    profile["receipt"] = trace
    step = next(s for s in historical["execution"]["steps"] if s["id"] == "profile")
    step["result"] = trace
    if damage == "partial":
        profile.pop("binding")
    if damage == "unreadable":
        receipt = root / profile["result"]
        receipt.unlink()
        receipt.mkdir()
    state_path.write_text(json.dumps(state))
    obs = root / attempt["path"] / "observation.json"
    obs.write_text(json.dumps(historical))
    old_bytes = obs.read_bytes()
    plan = service_io.read(root / "plan.json")
    plan["runtime_version"] = "older-release"
    (root / "plan.json").write_text(json.dumps(plan))
    status = call(campaign, "status")
    assert not status["can_finalize"]
    assert status["final_block_reason"] == "runtime_version_mismatch"
    assert status["next_action"] == "use_recorded_runtime_version"
    assert status["recorded_runtime_version"] == "older-release"
    actual = status["latest_observation"]
    assert actual["assessment"] == attempt["assessment"]
    expected = {"available": False} if damage else {
        "available": True, "result": profile["result"], "artifacts": profile["artifacts"]
    }
    assert actual["profiling"] == expected
    snapshot = dashboard_snapshot(root)
    report = snapshot["data"]["service_optimization"]
    assert report["final_block_reason"] == "runtime_version_mismatch"
    assert report["attempts"][-1]["profiling"] == expected
    assert ("Profiling available: no" if damage else "Profiling available: yes") in (
        render_dashboard(snapshot)
    )
    assert obs.read_bytes() == old_bytes
    if damage is None:
        final = SimpleNamespace(session_action="final", reason="done")
        with pytest.raises(ValueError, match="Runtime package version changed"):
            optimization.service_command(root, final)


def test_damaged_optional_evidence_falls_back_and_allows_final(campaign):
    from inferrsi.apps.views.dashboard import dashboard_snapshot

    begin(campaign)
    attempt = submit(campaign, version="selected", a=90)["latest_observation"]
    root = campaign["root"]
    inline = attempt["profiling"]
    backfill = call(campaign, "profile", "--round", 1)["profiling"]
    assert backfill["available"] and backfill != inline
    index = root / attempt["path"] / "backfills/index.json"
    index.write_text('{"captures":' + "[" * 1500 + "]" * 1500 + "}")
    status = call(campaign, "status")
    assert status["rounds"][0]["profiling"] == inline
    assert status["can_finalize"]

    artifact = root / inline["artifacts"][0]
    artifact.unlink()
    artifact.symlink_to(artifact.name)
    status = call(campaign, "status")
    assert status["rounds"][0]["profiling"] == {"available": False}
    assert status["can_finalize"]
    report = dashboard_snapshot(root)["data"]["service_optimization"]
    assert report["attempts"][-1]["profiling"] == {"available": False}
    final = call(campaign, "final", "--reason", "Retest selected candidate")["final"]
    assert final["assessment"]["verdict"] == "PASS"


@pytest.mark.parametrize("boundary", ["checkpoint", "start", "progress"])
@pytest.mark.parametrize("latency,verdict", [(90, "PASS"), (110, "FAIL")])
def test_delayed_double_recovery_settles_checkpoint_and_only_proven_time(
    campaign, monkeypatch, boundary, latency, verdict
):
    class CoordinatorCrash(BaseException):
        pass

    begin(campaign)
    root = campaign["root"]
    initial = service_io.read(root / "state.json")
    plan = service_io.read(root / "plan.json")
    original_write = _attempt.atomic_write_json
    frozen = {}

    def stop_after_durable_boundary(path, document):
        if frozen and path == frozen["path"]:
            return  # Model termination: no subsequent execution receipt survives.
        original_write(path, document)
        if path.name != "execution.json" or not document.get("checkpoint"):
            return
        capture = document.get("capture")
        reached = (
            boundary == "checkpoint" and capture is None
            or boundary == "start" and capture is not None and not capture["elapsed_seconds"]
            or boundary == "progress" and capture is not None
            and capture["elapsed_seconds"] > 0 and "ended_at" not in capture
        )
        if reached:
            frozen["path"] = path
            raise CoordinatorCrash()

    with monkeypatch.context() as m:
        m.setattr(_attempt, "atomic_write_json", stop_after_durable_boundary)
        with pytest.raises(CoordinatorCrash):
            submit(campaign, version="interrupted", a=latency)

    state = service_io.read(root / "state.json")
    pending = state["pending"]
    retained = service_io.read(frozen["path"])
    checkpoint = retained["checkpoint"]
    assert checkpoint["assessment"]["verdict"] == verdict
    assert checkpoint["binding"] == service_io.read(root / pending["path"] / "request.json")
    assert checkpoint["measurements"]["values"]["a"] == latency
    assert checkpoint["quality_score"] == (1 if verdict == "PASS" else None)
    before_events = events(campaign, pending)
    assert [e["stage"] for e in before_events].count("measure") == 2
    assert [e["stage"] for e in before_events].count("quality") == (verdict == "PASS")
    assert not (root / pending["path"] / "observation.json").exists()

    # The test leaves the managed service context so a real process never leaks.
    # Recovery must still require the operator's proof for the interrupted receipt.
    check_proofs = boundary == "checkpoint" and verdict == "FAIL"
    if check_proofs:
        original = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert rejected(["campaign", "recover", "--session", str(root)]) == 2
    campaign["capsys"].readouterr()
    if check_proofs:
        assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == original
    if boundary == "start":
        denied = call(campaign, "profile", "--round", "1", expected=2)
        assert "cleanup" in denied["profiling_error"]["message"].lower()
        assert rejected([
            "campaign", "round", "--session", str(root), "--candidate", str(campaign["repo"]),
            "--hypothesis", "Unresolved prior cleanup",
        ]) == 2
        campaign["capsys"].readouterr()
        assert service_io.read(root / "state.json")["pending"] == pending
    owner = service_io.read(root / pending["path"] / "service/owner.json")
    now = time.time() + 120
    monkeypatch.setattr(optimization, "time", SimpleNamespace(time=lambda: now))
    inspection = root.parent / "cleanup.json"
    proof = {
        "attempt_id": pending["attempt_id"], "observed_at": now, "reason": "Inspected owner",
        "cleanup_complete": True, "services": [{
            "service_id": owner["service_id"], "pid": owner["pid"], "domain_empty": True,
        }],
    }
    if check_proofs:
        baseline = next(row for row in state["attempts"] if row["kind"] == "baseline")
        other = service_io.read(root / baseline["path"] / "service/owner.json")
        assert baseline["attempt_id"] != pending["attempt_id"]
        assert other["service_id"] != owner["service_id"]
        other_service = [
            {"service_id": other["service_id"], "pid": other["pid"], "domain_empty": True}
        ]
        for invalid in (
            {**proof, "attempt_id": baseline["attempt_id"], "services": other_service},
            {**proof, "services": other_service},
            {**proof, "attempt_id": baseline["attempt_id"]},
        ):
            inspection.write_text(json.dumps(invalid))
            assert rejected([
                "campaign", "recover", "--session", str(root), "--cleanup-receipt", str(inspection)
            ]) == 2
            assert "cleanup" in campaign["capsys"].readouterr().err.lower()
            assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == original
    inspection.write_text(json.dumps(proof))
    first = call(campaign, "recover", "--cleanup-receipt", inspection)
    assert first["profiling_error"]["status"] == "interrupted"
    attempt = first["latest_observation"]
    assert attempt["assessment"] == checkpoint["assessment"]
    assert attempt["profiling"] == {"available": False}
    assert first["completed_rounds"] == 1
    assert (first["best"]["attempt_id"] == attempt["attempt_id"]) is (verdict == "PASS")
    credited = retained.get("capture", {}).get("elapsed_seconds", 0)
    for result in (first, call(campaign, "recover")):
        assert result["remaining_seconds"] == pytest.approx(initial["deadline"] + credited - now)
        assert result["remaining_search_seconds"] == pytest.approx(
            result["remaining_seconds"] - plan["final_reserve_seconds"]
        )
        assert result["latest_observation"]["assessment"] == checkpoint["assessment"]
    ledger = service_io.read(root / "state.json").get("profiling_accounting", {})
    if boundary == "checkpoint":
        assert ledger == {}
    else:
        assert set(ledger) == {retained["capture"]["id"]}
        assert ledger[retained["capture"]["id"]]["elapsed_seconds"] == credited
        assert (credited > 0) is (boundary == "progress")
    assert service_io.read(root / "plan.json")["final_reserve_seconds"] == 30
    assert events(campaign, pending) == before_events


def advance_clock_during_profile(monkeypatch, seconds):
    from inferrsi.harness.executor.trials import external

    wall_offset = 0
    clock = SimpleNamespace(
        time=lambda: time.time() + wall_offset, monotonic=lambda: time.monotonic() + wall_offset,
    )
    monkeypatch.setattr(_attempt, "time", clock)
    monkeypatch.setattr(optimization, "time", clock)
    original = external.execute_trial
    evaluation_limits = []

    def simulate_capture(command, work, destination, deadline, *args, **kwargs):
        nonlocal wall_offset
        if wall_offset and "measure" in command:
            evaluation_limits.append(deadline - clock.monotonic())
        executed = original(command, work, destination, deadline - wall_offset, *args, **kwargs)
        if "profile" in command and not wall_offset:
            wall_offset = seconds
        return executed

    monkeypatch.setattr(external, "execute_trial", simulate_capture)
    return clock, evaluation_limits


def test_effective_deadline_after_profiling_crosses_original_wall_deadline(campaign, monkeypatch):
    config = settings()
    config["sampling"]["profile_timeout_seconds"] = 700
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    root = campaign["root"]
    clock, evaluation_limits = advance_clock_during_profile(monkeypatch, 620)
    first = submit(campaign, version="slow-profile", a=90)
    assert first["latest_observation"]["assessment"]["verdict"] == "PASS"
    assert first["latest_observation"]["profiling"]["available"]
    assert first["latest_observation"]["elapsed_seconds"] >= 620
    state = service_io.read(root / "state.json")
    assert clock.time() > state["deadline"]
    assert optimization.read_records(root)[2]["wall_elapsed_seconds"] >= 620
    status = call(campaign, "status")
    assert 0 < status["remaining_search_seconds"] < status["remaining_seconds"]
    assert status["remaining_seconds"] - status["remaining_search_seconds"] == pytest.approx(30)
    assert status["can_finalize"] is True
    second = submit(campaign, version="quality-rejected", a=80, quality=0)
    assert second["latest_observation"]["assessment"]["verdict"] == "FAIL"
    final = call(campaign, "final", "--reason", "Independent final")
    assert final["final"]["assessment"]["verdict"] == "PASS"
    # Both repetitions of the new candidate and both repetitions of final have a live stage budget.
    assert len(evaluation_limits) == 4 and all(0 < limit <= 8 for limit in evaluation_limits)
    reserve = service_io.read(root / "plan.json")["final_reserve_seconds"]
    assert reserve == 30


def test_lost_profile_allows_next_round(campaign):
    begin(campaign)
    selected = submit(campaign, version="selected", a=90)["latest_observation"]
    (campaign["root"] / selected["profiling"]["artifacts"][0]).unlink()
    status = call(campaign, "status")
    assert status["can_finalize"]
    assert status["latest_observation"]["profiling"] == {"available": False}
    result = submit(campaign, version="rejected", a=110)
    assert result["latest_observation"]["assessment"]["verdict"] == "FAIL"
    assert result["best"]["attempt_id"] == selected["attempt_id"]


def test_standalone_capture_leaves_search_budget_and_reserve_intact(campaign, monkeypatch):
    config = settings()
    config["sampling"]["profile_timeout_seconds"] = 120
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    attempt = submit(campaign, version="quality-rejected", a=90, quality=0)["latest_observation"]
    assert attempt["profiling"] == {"available": False}
    root = campaign["root"]
    before = call(campaign, "status")
    original = service_io.read(root / "state.json")
    clock, measurements = advance_clock_during_profile(monkeypatch, 60)
    result = call(campaign, "profile", "--round", "1")
    assert result["profiling"]["available"] and measurements == []
    state = service_io.read(root / "state.json")
    capture = state["profiling_accounting"][result["capture_id"]]
    assert capture["elapsed_seconds"] >= 60
    assert state["deadline"] == original["deadline"]
    after = call(campaign, "status")
    assert after["remaining_seconds"] == pytest.approx(
        state["deadline"] + capture["elapsed_seconds"] - clock.time(), abs=0.5
    )
    assert before["remaining_seconds"] - after["remaining_seconds"] < 5
    assert after["remaining_seconds"] - after["remaining_search_seconds"] == pytest.approx(30)
    assert after["allocated_rounds"] == before["allocated_rounds"]
    assert after["best"] == before["best"] and after["can_finalize"]
    assert service_io.read(root / "plan.json")["final_reserve_seconds"] == 30


@pytest.mark.parametrize("switch", [["--decision", "paired"], ["--require-explanation"]])
def test_paired_and_explanation_switches_are_refused_in_service_mode(campaign, switch):
    # Both switches read AB/BA pairs and profiles; service reuse must not silently drop them.
    with pytest.raises(SystemExit):
        main([*campaign["start"], *switch])
    campaign["capsys"].readouterr()
    assert not (campaign["root"] / "plan.json").exists()


def test_mechanism_declaration_is_refused_in_service_mode(campaign, tmp_path):
    begin(campaign)
    commit(campaign["repo"], version="declared", a=90)
    declaration = tmp_path / "mechanism.json"
    declaration.write_text(json.dumps({"mechanism": "Synthetic", "expect": [
        {"region": "norm", "direction": "decrease"}]}))
    with pytest.raises(SystemExit):
        main(["campaign", "round", "--session", str(campaign["root"]),
              "--candidate", str(campaign["repo"]), "--hypothesis", "Declared candidate",
              "--mechanism-file", str(declaration)])
    campaign["capsys"].readouterr()
    state = json.loads((campaign["root"] / "state.json").read_text())
    assert state["pending"] is None and not state.get("attempts", [])[1:]
