"""Dashboard aggregation uses recorded evidence and keeps missing data explicit."""

import json
from pathlib import Path

import pytest

from inferrsi.harness.dashboard import write_dashboard
from inferrsi.harness.dashboard_data import load_dashboard
from inferrsi.harness.dashboard_timeline import temporal_chart


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def run(root: Path, name: str, gain: float, *, quality: str, verified: bool) -> None:
    directory = root / "runs" / name
    write_json(directory / "run.lock.json", {
        "model": "example-model", "model_revision": "example-revision",
        "workload_id": "example-workload", "scenario": "http", "backend": "cuda",
        "comparison_scope": "http_e2e", "baseline_command": ["python", "bench.py"],
        "device_ids": ["0"],
    })
    write_json(directory / "repositories.lock.json", {"baseline": {"snapshot_hash": "a" * 64}})
    write_json(directory / "status.json", {"state": "completed", "run_dir": "/private/run"})
    write_json(directory / "evaluation.json", {
        "verdict": "PASS", "metric_key": "throughput", "metric_unit": "tokens/s",
        "direction": "maximize", "improvement_pct": gain,
        "baseline": {"median": 100, "range_pct_of_median": 1},
        "candidate": {"median": 100 + gain, "range_pct_of_median": 2},
        "source_integrity": {"verified": verified},
        "statistical_significance": "not established",
    })
    write_json(directory / "validation" / "execution.json", {
        "status": quality, "returncode": 0 if quality == "completed" else 1,
    })


def candidate(root: Path, name: str, run_id: str, **extra: object) -> None:
    write_json(root / "candidates" / name / "candidate.json", {
        "candidate_id": name, "title": name, "run_id": run_id, **extra,
    })


def test_old_run_preserves_missing_files_and_corrupt_event_lines(tmp_path):
    write_json(tmp_path / "run.lock.json", {"repo": "/private/repo"})
    (tmp_path / "events.jsonl").write_text(
        '{"phase":"measurement","side":"baseline","trial":1}\n'
        'not-json\n'
        '{"phase":"quality_validation"}\n', encoding="utf-8"
    )

    view = load_dashboard(tmp_path)

    assert view["rounds"] is None
    assert view["candidates"][0]["candidate_id"] is None
    assert view["candidates"][0]["evaluation_state"] == "missing"
    assert view["candidates"][0]["quality"] == "not_recorded"
    assert view["candidates"][0]["corrupt_event_lines"] == [2]
    assert [event["stage"] for event in view["candidates"][0]["events"]] == [
        "execution", "validation"
    ]
    assert "/private/" not in json.dumps(view)


def test_single_run_exposes_its_recorded_target_without_inventing_a_gain(tmp_path):
    write_json(tmp_path / "run.lock.json", {})
    write_json(tmp_path / "evaluation.json", {"min_improvement_pct": 20})

    overview = load_dashboard(tmp_path)["overview"]

    assert overview["target_improvement_pct"] == 20
    assert overview["best_improvement_pct"] is None
    assert overview["target_gap_pct"] is None


def test_best_gain_requires_quality_and_source_integrity_and_tracks_noise(tmp_path):
    write_json(tmp_path / "campaign.json", {
        "campaign_id": "example", "goal": {"target_improvement_pct": 20},
        "noise": {"band_pct": 2},
    })
    for name, gain, quality, verified in [
        ("a", 5, "completed", True),
        ("b", 30, "failed", True),
        ("c", 40, "completed", False),
        ("d", 1.5, "completed", True),
        ("e", -3, "completed", True),
    ]:
        run(tmp_path, name, gain, quality=quality, verified=verified)
        candidate(tmp_path, name, name)

    view = load_dashboard(tmp_path)
    rows = {row["candidate_id"]: row for row in view["candidates"]}

    assert view["overview"]["best_improvement_pct"] == 5
    assert view["overview"]["target_gap_pct"] == 15
    assert rows["b"]["quality"] == "failed"
    assert rows["d"]["outcome"] == "noise"
    assert rows["e"]["outcome"] == "regressed"
    assert all(item["refs"] for item in view["diagnostics"])


def test_campaign_does_not_compare_different_workloads(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    for name, gain in (("a", 5), ("b", 30)):
        run(tmp_path, name, gain, quality="completed", verified=True)
        candidate(tmp_path, name, name)
    lock = tmp_path / "runs/b/run.lock.json"
    data = json.loads(lock.read_text(encoding="utf-8"))
    data["workload_id"] = "different-workload"
    write_json(lock, data)

    overview = load_dashboard(tmp_path)["overview"]

    assert overview["comparison_state"] == "incompatible"
    assert overview["best_improvement_pct"] is None


def test_best_gain_requires_a_recorded_zero_exit_code_and_completed_run(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    run(tmp_path, "a", 5, quality="completed", verified=True)
    run(tmp_path, "b", 9, quality="completed", verified=True)
    candidate(tmp_path, "a", "a")
    candidate(tmp_path, "b", "b")
    write_json(tmp_path / "runs/a/validation/execution.json", {"status": "completed"})
    write_json(tmp_path / "runs/b/status.json", {"state": "failed"})

    view = load_dashboard(tmp_path)

    assert view["candidates"][0]["quality"] == "not_recorded"
    assert view["overview"]["best_improvement_pct"] is None


def test_campaign_does_not_compare_different_baseline_snapshots(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    for name in ("a", "b"):
        run(tmp_path, name, 5, quality="completed", verified=True)
        candidate(tmp_path, name, name)
    write_json(tmp_path / "runs/b/repositories.lock.json", {
        "baseline": {"snapshot_hash": "b" * 64},
    })

    assert load_dashboard(tmp_path)["overview"]["comparison_state"] == "incompatible"


def test_unmeasured_failed_candidate_does_not_hide_other_recorded_gains(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    run(tmp_path, "a", 5, quality="completed", verified=True)
    candidate(tmp_path, "a", "a")
    write_json(tmp_path / "runs/b/status.json", {"state": "failed"})
    candidate(tmp_path, "b", "b")

    overview = load_dashboard(tmp_path)["overview"]

    assert overview["comparison_state"] == "comparable"
    assert overview["best_improvement_pct"] == 5


def test_rollback_is_visible_and_does_not_count_as_best_gain(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    for name, gain in (("a", 5), ("b", 3)):
        run(tmp_path, name, gain, quality="completed", verified=True)
        candidate(tmp_path, name, name, round=1)
    (tmp_path / "rounds.jsonl").write_text(json.dumps({
        "round": 1, "decision": {"candidate_id": "a", "outcome": "rolled_back"},
    }) + "\n", encoding="utf-8")

    view = load_dashboard(tmp_path)

    assert view["overview"]["best_improvement_pct"] == 3
    assert view["candidates"][0]["decision"] == "rolled_back"
    assert any(item["kind"] == "rolled_back" and item["refs"] for item in view["diagnostics"])


def test_unsafe_and_mismatched_artifact_refs_are_not_followed(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    run(tmp_path, "run-a", 1, quality="completed", verified=True)
    candidate(tmp_path, "a", "run-a", agent_trace_ref={
        "path": "../outside-secret", "sha256": "0" * 64,
    })
    (tmp_path.parent / "outside-secret").write_text("private contents", encoding="utf-8")
    candidate(tmp_path, "b", "run-a", agent_trace_ref={
        "path": "candidates/b/agent_trace.jsonl", "sha256": "0" * 64,
    })
    (tmp_path / "candidates/b/agent_trace.jsonl").write_text('{}\n', encoding="utf-8")

    view = load_dashboard(tmp_path)
    refs = {row["candidate_id"]: row["artifacts"]["agent_trace"] for row in view["candidates"]}

    assert refs["a"]["state"] == "missing"
    assert refs["a"]["missing_reason"] == "unsafe_path"
    assert refs["b"]["missing_reason"] == "hash_mismatch"
    assert "private contents" not in json.dumps(view)


def test_run_symlink_outside_campaign_is_not_read(tmp_path):
    root = tmp_path / "campaign"
    outside = tmp_path / "outside"
    write_json(root / "campaign.json", {"campaign_id": "example"})
    candidate(root, "a", "run-a")
    outside.mkdir()
    (outside / "events.jsonl").write_text('{"phase":"measurement"}\n', encoding="utf-8")
    (root / "runs").mkdir()
    try:
        (root / "runs/run-a").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    row = load_dashboard(root)["candidates"][0]

    assert row["event_state"] == "unsafe"
    assert row["events"] == []
    assert row["artifacts"]["events"]["missing_reason"] == "unsafe_path"


def test_malformed_record_fields_do_not_crash_dashboard(tmp_path):
    write_json(tmp_path / "run.lock.json", {})
    write_json(tmp_path / "status.json", {"state": ["bad"]})
    write_json(tmp_path / "validation/execution.json", {"status": {"bad": True}})
    (tmp_path / "events.jsonl").write_text('{"type":{},"phase":[]}\n', encoding="utf-8")

    row = load_dashboard(tmp_path)["candidates"][0]

    assert row["state"] == "not_recorded"
    assert row["quality"] == "not_recorded"
    assert row["events"][0]["type"] is None


def test_corrupt_evaluation_is_not_reported_as_present(tmp_path):
    write_json(tmp_path / "run.lock.json", {})
    (tmp_path / "evaluation.json").write_text('{"verdict":', encoding="utf-8")

    row = load_dashboard(tmp_path)["candidates"][0]

    assert row["evaluation_state"] == "corrupt"
    assert row["artifacts"]["evaluation"]["state"] == "missing"
    assert row["artifacts"]["evaluation"]["missing_reason"] == "corrupt"


def test_corrupt_rounds_and_missing_tool_calls_remain_visible(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    run(tmp_path, "a", 5, quality="completed", verified=True)
    candidate(tmp_path, "a", "a")
    (tmp_path / "rounds.jsonl").write_text('{"round":1}\nnot-json\n', encoding="utf-8")

    view = load_dashboard(tmp_path)

    assert view["rounds_state"] == "corrupt"
    assert view["corrupt_round_lines"] == [2]
    assert view["candidates"][0]["artifacts"]["tool_calls"]["missing_reason"] == "not_collected"


def test_undeclared_stages_are_distinct_from_missing_stages(tmp_path):
    write_json(tmp_path / "campaign.json", {
        "campaign_id": "example", "stages_declared": ["execution", "validation"],
    })

    stages = {item["name"]: item["state"] for item in load_dashboard(tmp_path)["stages"]}

    assert stages["diagnosis"] == "not_applicable"
    assert stages["execution"] == "stage_not_recorded"


def test_export_escapes_untrusted_candidate_data_and_omits_raw_paths(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    run(tmp_path, "run-a", 5, quality="completed", verified=True)
    candidate(tmp_path, "a", "run-a", title='__DASHBOARD_CHART__</script><img onerror="bad()">')
    (tmp_path / "runs/run-a/status.json").write_text(
        '{"state":"completed","run_dir":"/private/person/run"}', encoding="utf-8"
    )

    output = write_dashboard(tmp_path)
    html = output.read_text(encoding="utf-8")

    assert '/private/person/run' not in html
    assert '</script><img onerror="bad()">' not in html
    assert r'\u003cimg' in html
    assert '__DASHBOARD_CHART__' in html
    assert '<svg ' in html


def test_unbounded_chart_axis_is_rejected(tmp_path):
    write_json(tmp_path / "run.lock.json", {})
    write_json(tmp_path / "summary-chart.json", {
        "layout": "chain", "baseline": {"metrics": {"gain": 1}},
        "metrics": [{"key": "gain"}], "axis": {"step": 1e-100},
        "points": [{"phase": "a", "label": "x", "values": {"gain": 2}}],
    })

    html = write_dashboard(tmp_path).read_text(encoding="utf-8")

    assert 'No measured candidate results recorded.' in html


def test_time_chart_uses_terminal_events_and_marks_quality_failure_and_missing_values(tmp_path):
    write_json(tmp_path / "campaign.json", {
        "campaign_id": "example", "goal": {"target_improvement_pct": 20},
        "noise": {"band_pct": 2},
    })
    for name, gain, quality in (("a", 5, "completed"), ("b", 4, "failed"),
                                ("d", 7, "completed")):
        run(tmp_path, name, gain, quality=quality, verified=True)
        candidate(tmp_path, name, name, title=f"candidate-{name}", round=1)
    candidate(tmp_path, "c", "c", round=1)
    write_json(tmp_path / "runs/c/status.json", {"state": "failed"})
    for index, name in enumerate(("a", "b", "c", "d")):
        directory = tmp_path / "runs" / name
        events = [{"time": f"2026-01-01T00:0{index}:00Z", "phase": "measurement"}]
        if name != "d":
            events.append({"time": f"2026-01-01T00:0{index}:30Z",
                           "phase": "crashed" if name == "c" else "complete"})
        (directory / "events.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
        )
    (tmp_path / "rounds.jsonl").write_text(json.dumps({
        "round": 1, "decision": {"candidate_id": "a", "outcome": "rolled_back"},
    }) + "\n", encoding="utf-8")

    svg, note = temporal_chart(load_dashboard(tmp_path))

    assert 'data-kind="noise-band"' in svg
    assert 'data-kind="target-line"' in svg
    assert 'data-kind="marker-quality_failed"' in svg
    assert 'data-kind="marker-failed"' in svg and 'no numeric result' in svg
    assert 'data-kind="marker-rollback"' in svg
    assert svg.count('data-kind="stage-event"') == 4
    assert 'candidate-d: improved' not in svg
    assert '1 result(s) have no recorded terminal timestamp' in note


def test_time_chart_does_not_invent_timestamps_or_compare_incompatible_runs(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    for name in ("a", "b"):
        run(tmp_path, name, 5, quality="completed", verified=True)
        candidate(tmp_path, name, name)
        (tmp_path / "runs" / name / "events.jsonl").write_text(
            '{"time":"2026-01-01T00:00:00Z","phase":"complete"}\n', encoding="utf-8"
        )
    lock = tmp_path / "runs/b/run.lock.json"
    data = json.loads(lock.read_text(encoding="utf-8"))
    data["workload_id"] = "different-workload"
    write_json(lock, data)

    svg, note = temporal_chart(load_dashboard(tmp_path))

    assert 'data-kind="marker-improved"' not in svg
    assert 'Incompatible candidate measurements are not plotted together' in note
    (tmp_path / "runs/a/events.jsonl").write_text('{"phase":"complete"}\n', encoding="utf-8")
    (tmp_path / "runs/b/events.jsonl").write_text('{"phase":"complete"}\n', encoding="utf-8")
    assert temporal_chart(load_dashboard(tmp_path))[0] == ""


def test_time_chart_escapes_untrusted_candidate_labels(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    run(tmp_path, "a", 5, quality="completed", verified=True)
    candidate(tmp_path, "a", "a", title='<script>alert("example")</script>')
    (tmp_path / "runs/a/events.jsonl").write_text(
        '{"time":"2026-01-01T00:00:00Z","phase":"complete"}\n', encoding="utf-8"
    )

    svg, _ = temporal_chart(load_dashboard(tmp_path))

    assert '<script>' not in svg
    assert '&lt;script&gt;' in svg
