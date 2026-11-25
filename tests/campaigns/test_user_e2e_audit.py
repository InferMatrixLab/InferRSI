"""CPU negative controls for #479; synthetic times/images, never A2 qualification."""

import copy
import hashlib
import io
import json
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from e2e.qwen_image.audit import (
    Report,
    audit,
    audit_selection,
    check_choices,
    check_final_reply,
    check_independent,
    check_outputs,
    check_timing_aa,
    image_requests,
    read,
    recompute,
    select_patch_round,
)
from e2e.qwen_image.driver import discover, launch
from e2e.qwen_image.retest import execute, git, seal, write
from inferrsi.apps.cli import main
from inferrsi.harness.artifact_primitives import digest, sha256
from inferrsi.harness.optimization import read_records

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPOSITORY_ROOT / "tests/fixtures/user_e2e"


def invoke(argv):
    with redirect_stdout(io.StringIO()) as output:
        assert main(argv) == 0, output.getvalue()
    return json.loads(output.getvalue())


def ref(root, path):
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256(path)}


@pytest.fixture(scope="module")
def campaign(tmp_path_factory):
    Image = pytest.importorskip("PIL.Image")
    root = tmp_path_factory.mktemp("synthetic-user-e2e")
    repo, protocol, campaign = (root / name for name in ("repo", "protocol", "campaign"))
    repo.mkdir()
    protocol.mkdir()
    (repo / "engine.py").write_bytes(b"LATENCY = 100\n")
    git(repo, "init")
    git(repo, "add", "engine.py")
    git(repo, "-c", "user.name=Synthetic Control", "-c", "user.email=control@example.invalid",
        "commit", "-m", "Synthetic baseline")
    baseline = git(repo, "rev-parse", "HEAD").decode().strip()
    cases = [{"seed": seed, "prompt": f"Synthetic seed {seed}"} for seed in range(42, 48)]
    write(protocol / "cases.json", cases)
    write(protocol / "workload.json", {
        "width": 1280, "height": 704, "dtype": "bfloat16", "batch_size": 1,
        "concurrency": 1, "tensor_parallel_size": 1, "guidance_scale": 1,
        "num_inference_steps": 8, "timing_scope": "Omni.generate_to_decoded_image",
        "requests": cases,
    })
    scheduler = {"num_steps": 8, "timesteps": list(range(8)), "sigmas": [1, 0]}
    for case in cases:
        Image.new("RGBA", (1280, 704), (case["seed"], 0, 0, 255)).save(
            protocol / f"seed-{case['seed']}.png")
    # A real child process is started for every quality/measurement step. It
    # copies fixed synthetic images; no model, Codex or accelerator is involved.
    (protocol / "measure.py").write_bytes(
        (FIXTURES / "measure.py").read_bytes())
    instructions = root / "request.md"
    instructions.write_text("Synthetic software control; no performance claim.", encoding="utf-8")
    command = '"{python}" "{protocol}/measure.py" "{candidate}" "{result}"'
    timing_rows = []
    for group, arms in enumerate((("baseline", "candidate"), ("candidate", "baseline")), start=1):
        for arm in arms:
            step = f"measurement-{group:03d}-{arm}"
            directory = root / f"aa-{step}"
            directory.mkdir()
            result = directory / "result.json"
            subprocess.run([sys.executable, str(protocol / "measure.py"), str(repo), str(result)],
                           check=True)
            timing_rows.append({"step": step, "result": ref(root, result)})
    trace = root / "timing-aa.json"
    write(trace, timing_rows)
    write(protocol / "timing-policy.json", {
        "estimator": "maximum_absolute_paired_change_pct", "observed_noise_pct": 0,
        "adoption_threshold_pct": 1, "adoption_comparator": "current_best",
        "aa_sha256": sha256(trace),
    })
    invoke(["campaign", "start", "--directory", str(campaign), "--repo", str(repo),
            "--include", "engine.py", "--protocol", str(protocol),
            "--instructions", str(instructions), "--measure-command", command,
            "--quality-command", command, "--metric-key", "median_ms", "--metric-unit", "ms",
            "--direction", "minimize", "--quality-key", "correct", "--scope", "synthetic-only",
            "--repetitions", "2", "--warmups", "0", "--min-improvement-pct", "1",
            "--rounds", "3", "--round-mode", "exact", "--max-minutes", "5",
            "--evaluation-timeout-seconds", "30"])
    repeat_paths = []
    for index in range(2):
        directory = root / f"baseline-repeat-{index}"
        directory.mkdir()
        result = directory / "result.json"
        subprocess.run([sys.executable, str(campaign / "frozen/protocol/measure.py"),
                        str(campaign / "frozen/baseline"), str(result)], check=True)
        repeat_paths.append(result)
    invoke(["campaign", "diagnose", "--directory", str(campaign),
            "--bottleneck", "Synthetic measured request latency",
            "--evidence", str(repeat_paths[0])])
    for value in (90, 110, 80):
        (repo / "engine.py").write_bytes(f"LATENCY = {value}\n".encode())
        invoke(["campaign", "round", "--directory", str(campaign), "--candidate", str(repo),
                "--hypothesis", "Synthetic declared source change"])
    invoke(["campaign", "final", "--directory", str(campaign)])
    patch = root / "delivered.patch"
    patch.write_bytes(git(repo, "diff", "--binary", "HEAD"))
    _, state, _ = read_records(campaign)
    selected = select_patch_round(state["rounds"])
    submission = root / "submission.json"
    write(submission, {"candidate_id": selected["candidate_id"], "attempt": selected["path"],
                       "candidate_sha256": selected["candidate_sha256"],
                       "patch_sha256": sha256(patch)})
    plan, _ = seal(repo, baseline, campaign, patch, root / "independent", submission=submission)
    execute(root / "independent", plan, 60)
    plan, state, _ = read_records(campaign)
    choices = {}
    current_best = plan["baseline_sha256"]
    for index, record in enumerate(state["rounds"]):
        event_root = root / record["candidate_id"]
        event_root.mkdir()
        choice = {}
        for offset, key in enumerate(("plan_event", "first_edit_event", "measurement_event")):
            event = {"sequence": index * 3 + offset, "raw": "synthetic host event",
                     "host_session_id": "synthetic-session"}
            if offset == 0:
                event["choice"] = {
                    "starting_best_sha256": current_best,
                    "alternatives": ["synthetic A", "synthetic B"],
                    "chosen_measure": "synthetic A", "reason": "Synthetic control rationale",
                    "expected_effect": "reduce synthetic metric", "risk": "synthetic risk",
                    "sources": ["synthetic source"],
                    "feedback_or_initial_analysis": "Synthetic previous observation",
                }
            path = event_root / (key + ".json")
            write(path, event)
            choice[key] = ref(root, path)
        review = event_root / "review.json"
        diff = event_root / "candidate-source.txt"
        diff.write_bytes((campaign / record["path"] / "candidate/engine.py").read_bytes())
        write(review, {"independent": True, "reviewer": "synthetic-control-reviewer",
                       "basis": "Synthetic applicability evidence",
                       "diff_refs": [ref(root, diff)], "verdict": "PASS",
                       "candidate_sha256": record["candidate_sha256"],
                       "expectation": "supported"})
        choice["review"] = ref(root, review)
        choices[record["candidate_id"]] = choice
        current_best = record["best_after"]["sha256"]
    preparation = root / "preparation.json"
    write(preparation, {
        "input_version": "synthetic-v1", "baseline_revision": baseline,
        "plan_digest": digest(plan), "protocol_frozen_at": state["started_at"],
        "runspec": {"repository": "vllm-project/vllm-omni", "revision": baseline,
                    "backend": "ascend", "device_class": "A2", "device_count": 1,
                    "model": "Qwen-Image-2.1-Turbo"},
        "codex": {"client": "synthetic", "version": "synthetic", "model": "synthetic",
                  "configuration_sha256": "synthetic"},
        "inferrsi": {"version": "synthetic", "runtime_digest": digest(plan["runtime_identity"])},
        "a2_skill": {"name": "synthetic", "sha256": "synthetic"},
        "checks": dict.fromkeys(("noninteractive_login", "healthy_exclusive_device",
                                 "model_bytes_verified", "baseline_repeat_before_search",
                                 "owned_resources_cleaned"), True),
        "quality_cases": ref(root, campaign / "frozen/protocol/cases.json"),
        "timing_policy": ref(root, campaign / "frozen/protocol/timing-policy.json"),
        "workload": ref(root, campaign / "frozen/protocol/workload.json"),
        "expected_scheduler": scheduler,
    })
    reply = root / "reply.txt"
    reply.write_text(
        f"Selected {selected['candidate_id']}. Baseline 100 ms, final 80 ms, "
        "a 20 ms (20%) reduction. Quality 6/6. See independent/receipt.json "
        "and independent/candidate.patch. These are synthetic measurements.",
        encoding="utf-8")
    observer = {
        "round_choices": choices, "preparation": ref(root, preparation),
        "timing_aa": ref(root, trace),
        "submission": ref(root, submission),
        "final_reply": ref(root, reply), "interventions": [],
        "independent_directory": "independent", "baseline_repeat": {
            "results": [ref(root, path) for path in repeat_paths],
            "fresh_process_ids": [read(path)["process"]["id"] for path in repeat_paths],
            "search_started_at": state["rounds"][0]["started_at"],
            "source_sha256": [plan["baseline_sha256"]] * 2,
            "effective_scheduler": scheduler,
            "environment_identity": "synthetic-not-a-device",
            "workload_sha256": sha256(protocol / "workload.json"),
        },
    }
    write(root / "observer.json", observer)
    return root, repo, campaign, plan, state, observer, baseline, patch


def codes(report):
    return {item["code"] for item in report.findings}


@pytest.mark.parametrize("change,expected", [
    ("missing", "INCONCLUSIVE"), ("different_trace", "FAIL"), ("lower_gate", "FAIL"),
])
def test_timing_aa_must_match_the_frozen_raw_measurements(campaign, change, expected):
    root, _, _, plan, _, observer, *_ = campaign
    observer = copy.deepcopy(observer)
    plan = copy.deepcopy(plan)
    preparation = read(root / observer["preparation"]["path"])
    if change == "missing":
        del observer["timing_aa"]
    elif change == "different_trace":
        observer["timing_aa"] = observer["preparation"]
    else:
        plan["evaluation_settings"]["min_improvement_pct"] = 0
    report = Report()
    check_timing_aa(root, observer, preparation, plan, report)
    assert report.document()["workflow_verdict"] == expected


def test_complete_synthetic_journey_recomputes_choices_and_two_receipts(campaign):
    root, _, path, *_ = campaign
    report = audit(path, root / "observer.json")
    assert report["workflow_verdict"] == "PASS", report
    assert [row["decision"] for row in report["rounds"]] == [
        "adopt", "keep_previous_best", "adopt"]
    assert report["rounds"][1]["incremental_improvement_pct"] < 0
    assert report["rounds"][2]["starting_best_sha256"] == report["rounds"][0]["source_sha256"]
    for receipt in ("session_final", "independent_patch_retest"):
        assert report[receipt]["baseline_ms"] == 100
        assert report[receipt]["candidate_ms"] == 80
        assert report[receipt]["delta_ms"] == 20


def test_cross_arm_swap_is_rejected_even_with_identical_arm_multisets(campaign):
    _, _, root, plan, state, *_ = campaign
    directory = root / state["rounds"][0]["path"]
    execution = read(directory / "execution/execution.json")
    execution["steps"][2:4] = reversed(execution["steps"][2:4])
    with pytest.raises(ValueError, match="Cross-arm"):
        recompute(directory, plan["evaluation_settings"], execution)


def test_slower_candidate_must_not_replace_best(campaign):
    _, _, root, plan, state, *_ = campaign
    altered = copy.deepcopy(state)
    altered["rounds"][1]["best_after"] = {
        "sha256": altered["rounds"][1]["candidate_sha256"], "score": 110, "kind": "candidate"}
    report = Report()
    audit_selection(plan, altered, root, report)
    assert "wrong_adopt_reject_decision" in codes(report)


def test_change_inside_noise_must_not_replace_the_previous_best(campaign, monkeypatch):
    _, _, root, plan, state, *_ = campaign
    altered = copy.deepcopy(state)
    record = altered["rounds"][-1]
    record["assessment"]["score"] = 89.5  # Below baseline 100, within 1% of best 90.
    record["best_after"]["score"] = 89.5
    original = recompute

    def replay(directory, *args):
        if directory == root / record["path"]:
            return record["assessment"]
        return original(directory, *args)

    monkeypatch.setattr("e2e.qwen_image.audit.recompute", replay)
    report = Report()
    audit_selection(plan, altered, root, report)
    assert report.rounds[-1]["decision"] == "keep_previous_best"
    assert "wrong_adopt_reject_decision" in codes(report)


def test_baseline_winner_still_selects_real_patch_and_earliest_tie():
    rounds = [{"candidate_id": name, "assessment": {
        "status": "completed", "quality_passed": True, "score": score, "eligible": False}}
        for name, score in (("first", 110), ("second", 110), ("third", 120))]
    assert select_patch_round(rounds)["candidate_id"] == "first"


def test_wrong_legal_patch_rejected_before_any_measurement(campaign):
    root, repo, path, _, _, _, baseline, _ = campaign
    wrong = root / "different.patch"
    original = (repo / "engine.py").read_bytes()
    try:
        (repo / "engine.py").write_bytes(b"LATENCY = 85\n")
        wrong.write_bytes(git(repo, "diff", "HEAD"))
    finally:
        (repo / "engine.py").write_bytes(original)
    output = root / "wrong-independent"
    with pytest.raises(ValueError, match="original submission"):
        seal(repo, baseline, path, wrong, output, submission=root / "submission.json")
    assert not (output / "seal.json").exists()
    assert not (output / "attempt/execution").exists()


def test_different_patch_with_identical_source_is_rejected(campaign, tmp_path):
    root, repo, path, _, _, _, baseline, original = campaign
    clone = tmp_path / "baseline"
    git(repo, "clone", "--quiet", "--config", "core.autocrlf=false", str(repo), str(clone))
    equivalent = tmp_path / "equivalent.patch"
    equivalent.write_bytes(b"Equivalent change with a distinct header\n\n" + original.read_bytes())
    git(clone, "apply", str(equivalent))
    assert (clone / "engine.py").read_bytes() == (repo / "engine.py").read_bytes()
    output = tmp_path / "independent"
    with pytest.raises(ValueError, match="original submission"):
        seal(repo, baseline, path, equivalent, output, submission=root / "submission.json")
    assert not output.exists()


def test_sealed_source_drift_is_rejected_before_timing(campaign):
    root, repo, path, _, _, _, baseline, patch = campaign
    output = root / "changed-after-seal"
    plan, _ = seal(repo, baseline, path, patch, output, submission=root / "submission.json")
    (output / "attempt/candidate/engine.py").write_bytes(b"LATENCY = 1\n")
    with pytest.raises(ValueError, match="changed before timing"):
        execute(output, plan, 30)
    assert not (output / "attempt/execution").exists()


def test_posthoc_choice_is_rejected(campaign):
    root, _, _, _, state, observer, *_ = campaign
    observer = copy.deepcopy(observer)
    choice = observer["round_choices"][state["rounds"][0]["candidate_id"]]
    choice["plan_event"], choice["first_edit_event"] = (
        choice["first_edit_event"], choice["plan_event"])
    report = Report()
    report.rounds = [{"starting_best_sha256": "synthetic"}] * len(state["rounds"])
    check_choices(root, observer, state["rounds"], report)
    assert "choice_recorded_after_edit_or_measurement" in codes(report)


def test_missing_choice_review_never_becomes_automatic_pass(campaign):
    root, _, _, _, state, observer, *_ = campaign
    observer = copy.deepcopy(observer)
    del observer["round_choices"][state["rounds"][0]["candidate_id"]]["review"]
    report = Report()
    report.rounds = [{"starting_best_sha256": "synthetic"}] * len(state["rounds"])
    check_choices(root, observer, state["rounds"], report)
    assert "choice_evidence_unavailable" in codes(report)


@pytest.mark.parametrize("change,expected", [
    ("fresh_process_ids", "baseline_repeat_not_across_fresh_processes"),
    ("source_sha256", "baseline_repeat_wrong_source"),
    ("effective_scheduler", "baseline_repeat_protocol_mismatch"),
])
def test_unqualified_baseline_stays_inconclusive(campaign, change, expected):
    root, _, path, plan, state, observer, *_ = campaign
    observer = copy.deepcopy(observer)
    observer["baseline_repeat"][change] = {
        "fresh_process_ids": ["same", "same"], "source_sha256": ["wrong", "wrong"],
        "effective_scheduler": {"synthetic_grid": [99]},
    }[change]
    report = Report()
    check_outputs(path, plan, state, root, observer, report)
    assert expected in codes(report)
    assert report.document()["workflow_verdict"] == ("FAIL" if change == "source_sha256"
                                                     else "INCONCLUSIVE")


def test_independent_receipt_cannot_be_bound_to_a_different_attempt(campaign):
    root, _, _, plan, state, observer, *_ = campaign
    selected = {**select_patch_round(state["rounds"]), "path": "wrong-attempt"}
    report = Report()
    check_independent(root, observer, selected, plan, report)
    assert "independent_selection_binding_mismatch" in codes(report)


def test_assistance_is_separate_from_correct_results(campaign):
    root, _, path, _, _, observer, *_ = campaign
    observer = copy.deepcopy(observer)
    observer["interventions"] = [{"kind": "assistance", "stage": "baseline",
                                  "at_seconds": 12, "reason": "synthetic connection repair",
                                  "action": "synthetic repair"}]
    receipt = root / "assisted-observer.json"
    write(receipt, observer)
    report = audit(path, receipt)
    assert report["workflow_verdict"] == "FAIL"
    assert report["completion_mode"] == "assisted"
    assert report["independent_patch_retest"]["quality_passed"] is True
    assert report["first_blocked_step"] == "baseline"


def test_live_driver_refuses_dirty_project_before_launch(campaign):
    root, repo, _, _, _, _, baseline, _ = campaign
    with pytest.raises(ValueError, match="clean"):
        launch(repo, baseline, root / "never-launched", executable="not-a-command",
               model="synthetic", timeout=10)
    assert not (root / "never-launched").exists()


def test_driver_sends_only_the_natural_request_to_one_new_session(campaign, tmp_path):
    _, repo, _, _, _, _, baseline, _ = campaign
    clean = tmp_path / "clean-project"
    git(repo, "clone", "--no-checkout", str(repo), str(clean))
    git(clean, "checkout", "--detach", baseline)
    output = tmp_path / "host-output"
    fake_host = FIXTURES / "codex_host.py"
    receipt = launch(clean, baseline, output, executable=[sys.executable, str(fake_host)],
                     model="synthetic-model", timeout=15)
    expected = REPOSITORY_ROOT / "e2e/qwen_image/request.txt"
    assert (output / "final-reply.txt").read_text(encoding="utf-8") == (
        expected.read_text(encoding="utf-8").strip())
    assert receipt["native_session_ids"] == ["synthetic-session"]
    assert receipt["native_turn_completed"] is True
    assert receipt["elapsed_seconds"] > 0
    assert (output / "events.jsonl").is_file()


def test_discovery_excludes_old_or_other_project_campaigns(campaign):
    root, repo, path, _, state, *_ = campaign
    assert discover(root, repo, state["started_at"] - 1) == path
    with pytest.raises(ValueError, match="one new campaign"):
        discover(root, repo, state["started_at"] + 1)


@pytest.mark.parametrize("archive,host,expected", [
    (b"candidate A\n", b"candidate A\n", None),
    (b"candidate A\n", b"candidate A\r\n", "observer_reply_differs_from_host_output"),
    (b"candidate A", b"candidate B", "observer_reply_differs_from_host_output"),
    (b"\xef\xbb\xbf \r\n", None, "empty_final_reply"),
])
def test_final_reply_preserves_the_host_bytes(tmp_path, archive, host, expected):
    reply = tmp_path / "observer-reply.txt"
    reply.write_bytes(archive)
    host_reply = None
    if host is not None:
        host_reply = tmp_path / "final-reply.txt"
        host_reply.write_bytes(host)
    report = Report()
    check_final_reply(tmp_path, {"final_reply": ref(tmp_path, reply)}, report, host_reply)
    if expected:
        assert report.findings == [{"code": expected, "verdict": "FAIL"}]
    else:
        assert not report.findings
        assert report.results["final_reply_sha256"] == sha256(host_reply)


def test_missing_host_reply_is_inconclusive_even_with_observer_copy(tmp_path):
    reply = tmp_path / "observer-reply.txt"
    reply.write_bytes(b"Retained copy")
    report = Report()
    check_final_reply(tmp_path, {"final_reply": ref(tmp_path, reply)}, report,
                      tmp_path / "missing-host-output.txt")
    assert report.findings == [
        {"code": "final_reply_evidence_unavailable", "verdict": "INCONCLUSIVE"}]


def test_missing_evidence_is_not_a_passing_skip(tmp_path):
    report = audit(tmp_path, tmp_path / "missing-observer.json")
    assert report["workflow_verdict"] == "INCONCLUSIVE"


@pytest.mark.parametrize("field,expected,verdict", [
    ("effective_scheduler", "effective_scheduler_changed", "FAIL"),
    ("environment_identity", "environment_or_workload_not_comparable", "INCONCLUSIVE"),
    ("median_ms", "raw_quality_or_timing_evidence_contradicted", "FAIL"),
])
def test_raw_candidate_changes_are_not_hidden_by_summary(
        campaign, tmp_path, field, expected, verdict):
    root, _, path, plan, state, observer, *_ = campaign
    record = state["rounds"][0]
    step = "measurement-001-candidate"
    directory = tmp_path / "attempt/execution" / step
    shutil.copytree(path / record["path"] / "execution" / step, directory)
    result = read(directory / "result.json")
    result[field] = {"effective_scheduler": {"num_steps": 1},
                     "environment_identity": "different-synthetic-environment",
                     "median_ms": 1}[field]
    write(directory / "result.json", result)
    write(directory.parent / "execution.json", {"steps": [{"id": step}]})
    fake_state = {"rounds": [], "final": {**record, "path": "attempt"}}
    report = Report()
    check_outputs(tmp_path, plan, fake_state, root, observer, report)
    assert expected in codes(report)
    assert report.document()["workflow_verdict"] == verdict


@pytest.mark.parametrize("attempt,step,missing", [
    ("round", "quality-baseline", False),
    ("final", "measurement-001-candidate", True),
    ("independent", "measurement-001-candidate", False),
])
def test_worker_must_load_the_source_of_its_arm(campaign, monkeypatch, attempt, step, missing):
    root, _, path, _, state, *_ = campaign
    directory = {"round": path / state["rounds"][0]["path"],
                 "final": path / state["final"]["path"],
                 "independent": root / "independent/attempt"}[attempt]
    target = directory / "execution" / step / "result.json"

    def worker_result(filename):
        result = read(filename)
        if filename == target:
            if missing:
                del result["loaded_source_sha256"]
            else:
                result["loaded_source_sha256"] = "0" * 64
        return result

    monkeypatch.setattr("e2e.qwen_image.audit.read", worker_result)
    report = audit(path, root / "observer.json")
    assert report["workflow_verdict"] == ("INCONCLUSIVE" if missing else "FAIL")
    code = "loaded_source_identity_missing" if missing else "wrong_source_loaded"
    assert any(row["code"] == code and row["step"] == step for row in report["findings"])


def test_verified_flag_cannot_hide_a_different_loaded_source(campaign):
    _, _, root, plan, state, *_ = campaign
    record = state["rounds"][0]
    directory = root / record["path"]
    execution = read(directory / "execution/execution.json")
    expected = {"baseline": plan["baseline_sha256"], "candidate": record["candidate_sha256"]}
    execution["source_checks"][0]["expected"]["candidate"] = "different-source"
    execution["source_checks"][0]["actual"]["candidate"] = "different-source"
    execution["source_checks"][0]["verified"] = True
    with pytest.raises(ValueError, match="Loaded source"):
        recompute(directory, plan["evaluation_settings"], execution, expected)


def test_repeated_source_is_not_another_optimization_round(campaign):
    _, _, root, plan, state, *_ = campaign
    altered = copy.deepcopy(state)
    first = altered["rounds"][0]
    altered["rounds"] = [first, copy.deepcopy(first)]
    altered["best"] = first["best_after"]
    altered["final"] = None
    report = Report()
    audit_selection(plan, altered, root, report)
    assert "unchanged_or_repeated_candidate" in codes(report)


def test_rejected_quality_cannot_be_adopted_as_best(campaign, tmp_path):
    _, _, root, plan, state, *_ = campaign
    record = copy.deepcopy(state["rounds"][0])
    directory = tmp_path / "attempt"
    shutil.copytree(root / record["path"], directory)
    result_path = directory / "execution/quality-candidate/result.json"
    result = read(result_path)
    result["correct"] = False
    write(result_path, result)
    execution = read(directory / "execution/execution.json")
    execution["steps"] = execution["steps"][:2]
    execution["source_checks"] = execution["source_checks"][:2]
    write(directory / "execution/execution.json", execution)
    record["path"] = "attempt"
    record["assessment"] = recompute(directory, plan["evaluation_settings"], execution)
    assert record["assessment"]["status"] == "candidate_failure"
    altered = {**state, "rounds": [record], "best": record["best_after"], "final": None}
    report = Report()
    audit_selection(plan, altered, tmp_path, report)
    assert "wrong_adopt_reject_decision" in codes(report)


def test_unstable_baseline_pixels_are_inconclusive_not_candidate_failure(campaign):
    from PIL import Image

    root, _, path, plan, state, observer, *_ = campaign
    observer = copy.deepcopy(observer)
    old_path = root / observer["baseline_repeat"]["results"][1]["path"]
    directory = root / "unstable-baseline-repeat"
    shutil.copytree(old_path.parent, directory)
    result = read(directory / "result.json")
    Image.new("RGBA", (1280, 704), (0, 0, 0, 255)).save(directory / "seed-42.png")
    with Image.open(directory / "seed-42.png") as image:
        result["requests"][0]["pixel_sha256"] = hashlib.sha256(image.tobytes()).hexdigest()
    write(directory / "result.json", result)
    image_requests(directory, result)  # Internally consistent, but a different baseline image.
    observer["baseline_repeat"]["results"][1] = ref(root, directory / "result.json")
    report = Report()
    check_outputs(path, plan, state, root, observer, report)
    assert "baseline_pixel_reference_unqualified" in codes(report)
    assert report.document()["workflow_verdict"] == "INCONCLUSIVE"


@pytest.mark.parametrize("complete", [True, False])
def test_pytest_replay_entry_writes_verdict_and_never_hides_gaps(campaign, tmp_path, complete):
    root, _, path, *_ = campaign
    observer = root / "observer.json" if complete else tmp_path / "unavailable.json"
    output = tmp_path / "report"
    result = subprocess.run([
        sys.executable, "-m", "pytest", "e2e/qwen_image", "--e2e-campaign", str(path),
        "--e2e-observer", str(observer), "--e2e-artifacts", str(output),
    ], cwd=REPOSITORY_ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == (0 if complete else 1), result.stdout + result.stderr
    assert read(output / "pytest-report.json")["workflow_verdict"] == (
        "PASS" if complete else "INCONCLUSIVE")
