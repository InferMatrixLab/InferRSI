"""Dashboard aggregation uses recorded evidence and keeps missing data explicit."""

import hashlib
import json
import re
from pathlib import Path

import pytest

from inferrsi.harness import dashboard_data
from inferrsi.harness.dashboard import _bounded_chain, _chart, _round_trend, write_dashboard
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
        "validation_command": ["python", "validate.py"], "device_ids": ["0"],
    })
    write_json(directory / "repositories.lock.json", {"baseline": {"snapshot_hash": "a" * 64}})
    write_json(directory / "environment.json", {
        "host": {"platform": "synthetic-os"},
        "target_python": {"environment": {"python": "synthetic-python", "packages": {
            "vllm": "synthetic-version", "torch": "synthetic-version",
        }}},
        "device": {"status": "available", "selection_verified": True, "devices": [{
            "index": "0", "uuid": "synthetic-device", "name": "synthetic-gpu",
            "driver_version": "synthetic-driver",
        }]},
    })
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


def test_incompatible_campaign_withholds_explicit_chain_chart(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    for name in ("a", "b"):
        run(tmp_path, name, 5, quality="completed", verified=True)
        candidate(tmp_path, name, name)
    lock = tmp_path / "runs/b/run.lock.json"
    data = json.loads(lock.read_text(encoding="utf-8"))
    data["workload_id"] = "different-workload"
    write_json(lock, data)
    write_json(tmp_path / "summary-chart.json", {
        "layout": "chain", "baseline": {"metrics": {"gain": 1}},
        "metrics": [{"key": "gain"}], "axis": {"step": 0.5},
        "points": [{"phase": "a", "label": "x", "values": {"gain": 2}}],
    })

    svg, note = _chart(tmp_path, load_dashboard(tmp_path))

    assert not svg
    assert "incompatible" in note


def test_recorded_chart_title_alone_accepts_narrative_translations(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    run(tmp_path, "a", 5, quality="completed", verified=True)
    candidate(tmp_path, "a", "a")
    write_json(tmp_path / "summary-chart.json", {
        "title": "Experiment trend", "layout": "chain",
        "baseline": {"metrics": {"gain": 1}},
        "metrics": [{"key": "gain"}], "axis": {"step": 0.5},
        "points": [{"phase": "FAIL", "label": "FAIL", "values": {"gain": 2}}],
    })

    svg, _ = _chart(tmp_path, load_dashboard(tmp_path))

    assert '<title data-narrative="">Experiment trend</title>' in svg
    assert re.search(r'<text data-narrative="" [^>]*>Experiment trend</text>', svg)
    assert svg.count('data-narrative=""') == 2
    assert '>FAIL</text>' in svg


def test_round_trend_uses_ordered_independent_measurements_and_omits_missing(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example", "goal": {
        "target_improvement_pct": 20,
    }})
    for name, gain, round_number, quality in (
        ("z", 4.0, 1, "completed"), ("a", 8.0, 2, "failed"),
        ("m", -2.0, 3, "completed"), ("pending", 0.0, 4, "completed"),
    ):
        run(tmp_path, name, gain, quality=quality, verified=True)
        candidate(tmp_path, name, name, round=round_number)
    (tmp_path / "runs/pending/evaluation.json").unlink()

    view = load_dashboard(tmp_path)
    svg, note = _chart(tmp_path, view)

    assert "<polyline " in svg
    assert "Performance by recorded round" in svg
    assert svg.index(">R1</text>") < svg.index(">R2</text>") < svg.index(">R3</text>")
    assert ">R4</text>" not in svg
    assert "quality failed" in svg
    assert "not cumulative" in note and "missing" in note
    assert _round_trend(view)["axis"]["step"] == 0.05


def test_round_trend_does_not_invent_order_with_multiple_candidates_in_a_round(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    for name in ("a", "b"):
        run(tmp_path, name, 5.0, quality="completed", verified=True)
        candidate(tmp_path, name, name, round=1)

    svg, note = _chart(tmp_path, load_dashboard(tmp_path))

    assert "Candidate gain versus paired baseline" in svg
    assert "Independent candidate results" in note


def test_missing_and_corrupt_candidate_metadata_are_not_silently_dropped(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    run(tmp_path, "run-a", 5, quality="completed", verified=True)
    candidate(tmp_path, "a", "run-a", round=1)
    corrupt = tmp_path / "candidates/b/candidate.json"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text('{"candidate_id":', encoding="utf-8")
    (tmp_path / "rounds.jsonl").write_text(json.dumps({
        "round": 1, "candidates": ["a", "b", "c"],
        "decision": {"candidate_id": "b", "outcome": "rolled_back"},
    }) + "\n", encoding="utf-8")

    rows = {row["candidate_id"]: row for row in load_dashboard(tmp_path)["candidates"]}

    assert set(rows) == {"a", "b", "c"}
    assert rows["b"]["candidate_metadata_state"] == "corrupt"
    assert rows["c"]["candidate_metadata_state"] == "file_absent"
    assert rows["b"]["run_id"] is None and rows["c"]["run_id"] is None
    assert rows["b"]["round"] == 1 and rows["b"]["decision"] == "rolled_back"
    with (tmp_path / "rounds.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"round": 2, "candidates": ["b"]}) + "\n")
    ambiguous = {row["candidate_id"]: row for row in load_dashboard(tmp_path)["candidates"]}["b"]
    assert ambiguous["round"] is None and ambiguous["round_state"] == "ambiguous"
    assert ambiguous["decision"] == "not_recorded"


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


@pytest.mark.parametrize("field", ["device", "model", "driver", "runtime", "validator",
                                    "missing_environment", "unsupported_backend"])
def test_campaign_does_not_compare_different_or_unverified_environments(tmp_path, field):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    for name in ("a", "b"):
        run(tmp_path, name, 5, quality="completed", verified=True)
        candidate(tmp_path, name, name)
    environment_path = tmp_path / "runs/b/environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    if field == "device":
        environment["device"]["devices"][0]["uuid"] = "different-synthetic-device"
    elif field == "model":
        environment["device"]["devices"][0]["name"] = "different-synthetic-gpu"
    elif field == "driver":
        environment["device"]["devices"][0]["driver_version"] = "different-driver"
    elif field == "runtime":
        environment["target_python"]["environment"]["packages"]["vllm"] = "different-version"
    elif field in ("validator", "unsupported_backend"):
        lock = tmp_path / "runs/b/run.lock.json"
        data = json.loads(lock.read_text(encoding="utf-8"))
        if field == "validator":
            data["validation_command"] = ["python", "other-validator.py"]
        else:
            data["backend"] = "cpu"
        write_json(lock, data)
    if field == "missing_environment":
        environment_path.unlink()
    else:
        write_json(environment_path, environment)

    view = load_dashboard(tmp_path)

    assert view["overview"]["comparison_state"] == (
        "unverified" if field in ("missing_environment", "unsupported_backend") else "incompatible"
    )
    assert view["overview"]["best_improvement_pct"] is None
    assert "synthetic-device" not in json.dumps(view)


@pytest.mark.parametrize("state,verdict", [("running", "PASS"), ("completed", "INCONCLUSIVE")])
def test_unfinished_or_inconclusive_run_is_not_marked_improved(tmp_path, state, verdict):
    run(tmp_path, "a", 10, quality="completed", verified=True)
    write_json(tmp_path / "runs/a/status.json", {"state": state})
    evaluation = tmp_path / "runs/a/evaluation.json"
    data = json.loads(evaluation.read_text(encoding="utf-8"))
    data["verdict"] = verdict
    write_json(evaluation, data)

    row = load_dashboard(tmp_path / "runs/a")["candidates"][0]

    assert row["outcome"] == "unverified"
    assert row["state"] == state
    assert row["verdict"] == verdict


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


def test_trace_requires_matching_correlation_and_unknown_events_do_not_cover_a_stage(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "campaign"})
    run(tmp_path, "run-a", 1, quality="completed", verified=True)
    trace = tmp_path / "candidates/a/agent_trace.jsonl"
    trace.parent.mkdir(parents=True)
    common = {"schema_version": 1, "campaign_id": "campaign", "candidate_id": "a",
              "run_id": "run-a", "round": 1, "stage": "search",
              "time": "2026-01-01T00:00:00Z"}
    records = [
        {**common, "type": "agent.request"},
        {**common, "type": "agent.tool", "candidate_id": "other"},
        {"type": "agent.tool", "stage": "validation"},
        {**common, "type": "unknown", "stage": "validation"},
    ]
    trace.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
    candidate(tmp_path, "a", "run-a", round=1, agent_trace_ref={
        "path": "candidates/a/agent_trace.jsonl",
        "sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
    })

    view = load_dashboard(tmp_path)
    row = view["candidates"][0]

    assert row["agent_trace_links"] == {"unlinked": [3], "mismatched": [2]}
    assert [event["line"] for event in row["unlinked_agent_events"]] == [3]
    assert row["artifacts"]["tool_calls"]["state"] == "missing"
    assert [event["line"] for event in row["events"]] == [1, 4]
    assert next(stage for stage in view["stages"] if stage["name"] == "validation")["state"] == (
        "stage_not_recorded"
    )


def test_pre_run_trace_links_only_to_unique_matching_candidate(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "campaign"})
    run(tmp_path, "run-a", 1, quality="completed", verified=True)
    trace = tmp_path / "candidates/a/agent_trace.jsonl"
    trace.parent.mkdir(parents=True)
    event = {"type": "agent.context", "schema_version": 1, "campaign_id": "campaign",
             "candidate_id": "a", "run_id": None, "round": 1, "stage": "diagnosis",
             "time": "2026-01-01T00:00:00Z"}
    trace.write_text(json.dumps(event) + "\n", encoding="utf-8")
    candidate(tmp_path, "a", "run-a", round=1, agent_trace_ref={
        "path": "candidates/a/agent_trace.jsonl",
        "sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
    })

    view = load_dashboard(tmp_path)

    assert next(stage for stage in view["stages"] if stage["name"] == "diagnosis")["state"] == (
        "recorded"
    )
    assert view["candidates"][0]["events"][0]["stage"] == "diagnosis"
    write_json(tmp_path / "candidates/b/candidate.json", {
        "candidate_id": "a", "title": "duplicate", "run_id": "run-a", "round": 1,
    })
    row = load_dashboard(tmp_path)["candidates"][0]
    assert row["agent_trace_links"]["unlinked"] == [1]
    assert not row["events"]


def test_trace_explicit_refs_are_checked_and_displayed(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "campaign"})
    run(tmp_path, "run-a", 1, quality="completed", verified=True)
    profile = tmp_path / "profile.json"
    profile.write_text('{"synthetic":true}', encoding="utf-8")
    profile_hash = hashlib.sha256(profile.read_bytes()).hexdigest()
    trace = tmp_path / "candidates/a/agent_trace.jsonl"
    trace.parent.mkdir(parents=True)
    event = {"type": "agent.tool", "schema_version": 1, "campaign_id": "campaign",
             "candidate_id": "a", "run_id": "run-a", "round": 1, "stage": "search",
             "time": "2026-01-01T00:00:00Z", "refs": [
                 {"kind": "profile", "path": "profile.json", "sha256": profile_hash},
                 {"kind": "log", "path": "../private", "sha256": "0" * 64},
             ]}
    trace.write_text(json.dumps(event) + "\n", encoding="utf-8")
    candidate(tmp_path, "a", "run-a", round=1, agent_trace_ref={
        "path": "candidates/a/agent_trace.jsonl",
        "sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
    })

    refs = load_dashboard(tmp_path)["candidates"][0]["events"][0]["refs"]

    assert any(ref.get("kind") == "profile" and ref.get("sha256") == profile_hash for ref in refs)
    assert any(ref.get("kind") == "log" and ref.get("missing_reason") == "unsafe_path"
               for ref in refs)


def test_record_hash_matches_bytes_used_for_rendering_even_if_file_changes(tmp_path, monkeypatch):
    write_json(tmp_path / "run.lock.json", {})
    status = tmp_path / "status.json"
    old = b'{"state":"completed"}'
    status.write_bytes(old)
    original = dashboard_data._snapshot

    def changing_snapshot(root, path, kind):
        data, ref = original(root, path, kind)
        if path == status:
            status.write_text('{"state":"failed"}', encoding="utf-8")
        return data, ref

    monkeypatch.setattr(dashboard_data, "_snapshot", changing_snapshot)
    row = load_dashboard(tmp_path)["candidates"][0]

    assert row["state"] == "completed"
    assert row["artifacts"]["status"]["sha256"] == hashlib.sha256(old).hexdigest()


def test_trace_changed_after_reference_check_is_not_linked(tmp_path, monkeypatch):
    write_json(tmp_path / "campaign.json", {"campaign_id": "campaign"})
    run(tmp_path, "run-a", 1, quality="completed", verified=True)
    trace = tmp_path / "candidates/a/agent_trace.jsonl"
    trace.parent.mkdir(parents=True)
    event = {"type": "agent.tool", "schema_version": 1, "campaign_id": "campaign",
             "candidate_id": "a", "run_id": "run-a", "round": 1, "stage": "search",
             "time": "2026-01-01T00:00:00Z"}
    trace.write_text(json.dumps(event) + "\n", encoding="utf-8")
    candidate(tmp_path, "a", "run-a", round=1, agent_trace_ref={
        "path": "candidates/a/agent_trace.jsonl",
        "sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
    })
    original = dashboard_data._snapshot

    def changing_snapshot(root, path, kind):
        if path == trace:
            trace.write_text(json.dumps({**event, "candidate_id": "other"}) + "\n",
                             encoding="utf-8")
        return original(root, path, kind)

    monkeypatch.setattr(dashboard_data, "_snapshot", changing_snapshot)
    row = load_dashboard(tmp_path)["candidates"][0]

    assert row["artifacts"]["agent_trace"]["missing_reason"] == "hash_mismatch"
    assert not any(event["source"] == "agent_trace" for event in row["events"])


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


def test_branch_chart_preserves_large_latency_regression(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    run(tmp_path, "a", -200, quality="completed", verified=True)
    candidate(tmp_path, "a", "a", title="large-regression")
    evaluation = tmp_path / "runs/a/evaluation.json"
    data = json.loads(evaluation.read_text(encoding="utf-8"))
    data["direction"] = "minimize"
    write_json(evaluation, data)

    svg, _ = _chart(tmp_path, load_dashboard(tmp_path))

    assert "large-regression" in svg
    assert "-200" in svg


@pytest.mark.parametrize("point,step", [(1.0000000000000002, 1e-17), (1.0, 1e-100)])
def test_chain_axis_cannot_stall_or_expand_from_float_rounding(point, step):
    assert not _bounded_chain({
        "layout": "chain", "baseline": {"metrics": {"gain": 1}},
        "metrics": [{"key": "gain"}], "axis": {"step": step},
        "points": [{"phase": "a", "label": "x", "values": {"gain": point}}],
    })


def test_export_does_not_overwrite_evidence_or_follow_output_symlinks(tmp_path):
    write_json(tmp_path / "run.lock.json", {})
    evidence = tmp_path / "evaluation.json"
    evidence.write_text('{"verdict":"PASS"}', encoding="utf-8")
    with pytest.raises(ValueError, match="non-dashboard"):
        write_dashboard(tmp_path, evidence)
    assert evidence.read_text(encoding="utf-8") == '{"verdict":"PASS"}'
    output = tmp_path / "dashboard.html"
    try:
        output.symlink_to(evidence)
    except OSError:
        pytest.skip("file symlinks are unavailable")
    with pytest.raises(ValueError, match="symbolic link"):
        write_dashboard(tmp_path)
    assert evidence.read_text(encoding="utf-8") == '{"verdict":"PASS"}'


def test_dashboard_can_be_regenerated(tmp_path):
    write_json(tmp_path / "run.lock.json", {})
    output = write_dashboard(tmp_path)
    assert write_dashboard(tmp_path) == output


def test_performance_charts_precede_story_and_candidate_details(tmp_path):
    write_json(tmp_path / "run.lock.json", {})
    html = write_dashboard(tmp_path).read_text(encoding="utf-8")
    main = html.split("<main>", 1)[1].split("</main>", 1)[0]
    sections = ["Performance trend · all candidates",
                "Results and stages over time · all candidates", "Optimization story",
                "Candidate details"]
    assert [main.index(section) for section in sections] == sorted(map(main.index, sections))


def test_reviewed_translations_are_embedded_without_changing_evidence(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    candidate(tmp_path, "a", "run-a", details={"summary": "Reduce launch overhead"})
    translations = tmp_path / "translations.json"
    write_json(translations, {"schema_version": 1, "zh": {
        "Reduce launch overhead": "减少启动开销",
        "literal": "</script><img src=x onerror=alert(1)>",
    }})

    html = write_dashboard(tmp_path, translations=translations).read_text(encoding="utf-8")
    payload = re.search(r'<script id="dashboard-data" type="application/json">(.*?)</script>',
                        html, re.DOTALL)
    assert payload is not None
    view = json.loads(payload.group(1))
    assert view["candidates"][0]["optimization"]["summary"] == "Reduce launch overhead"
    assert view["translations"]["zh"]["Reduce launch overhead"] == "减少启动开销"
    assert view["translations"]["zh"]["literal"] == "</script><img src=x onerror=alert(1)>"
    assert "</script><img src=x onerror=alert(1)>" not in html


@pytest.mark.parametrize("raw", [
    '{"schema_version":1,"zh":{"a":"b","a":"c"}}',
    '{"schema_version":true,"zh":{}}',
    '{"schema_version":1,"zh":{"a":""}}',
    '{"schema_version":1,"zh":[],"extra":{}}',
    '{"schema_version":1,"zh":{"a":"\\ud800"}}',
])
def test_invalid_translation_overlay_is_rejected(tmp_path, raw):
    write_json(tmp_path / "run.lock.json", {})
    translations = tmp_path / "translations.json"
    translations.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError, match="translation"):
        write_dashboard(tmp_path, translations=translations)
    assert not (tmp_path / "dashboard.html").exists()


def test_oversized_translation_overlay_is_rejected(tmp_path):
    write_json(tmp_path / "run.lock.json", {})
    translations = tmp_path / "translations.json"
    translations.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="2 MiB"):
        write_dashboard(tmp_path, translations=translations)


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
    assert 'incompatible candidate measurements are not plotted together' in note
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


def test_time_chart_marks_quality_failure_and_rollback_without_measurement(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    run(tmp_path, "a", 1, quality="failed", verified=True)
    (tmp_path / "runs/a/evaluation.json").unlink()
    candidate(tmp_path, "a", "a", round=1)
    (tmp_path / "runs/a/events.jsonl").write_text(
        '{"time":"2026-01-01T00:00:00Z","phase":"complete"}\n', encoding="utf-8"
    )
    (tmp_path / "rounds.jsonl").write_text(json.dumps({
        "round": 1, "decision": {"candidate_id": "a", "outcome": "rolled_back"},
    }) + "\n", encoding="utf-8")

    svg, _ = temporal_chart(load_dashboard(tmp_path))

    assert 'data-kind="marker-quality_failed"' in svg
    assert 'data-kind="marker-rollback"' in svg
    assert 'no numeric result' in svg
    (tmp_path / "runs/a/events.jsonl").write_text(
        '{"time":"2026-01-01T00:00:00Z","phase":"measurement"}\n', encoding="utf-8"
    )
    _, note = temporal_chart(load_dashboard(tmp_path))
    assert '1 result(s) have no recorded terminal timestamp' in note


def test_optimization_details_commands_and_privacy(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    run(tmp_path, "run-a", 5, quality="completed", verified=True)
    lock = tmp_path / "runs/run-a/run.lock.json"
    data = json.loads(lock.read_text(encoding="utf-8"))
    data["candidate_command"] = [
        "/private/bin/python", "/private/trial.py", "--mode", "mtp", "--token", "s3cr3t",
        "--api-key=rawkey", "-H", "Authorization: Bearer hidden", "--max-tokens", "128",
        "unknown-private-value", "-c", "print('hidden source')",
    ]
    write_json(lock, data)
    candidate(tmp_path, "a", "run-a", details={
        "change_kind": "code", "summary": "Improve decode token=private-value",
        "hypothesis": "Reduce launch overhead", "benchmark": "Paired trials",
        "accuracy": "Evaluate a fixed test set", "code_locations": [
            {"path": "vllm/tokenizer.py", "line_start": 5, "line_end": 8,
             "revision": "a" * 40, "scope": "vllm", "note": "Decode path"},
            {"path": "../private.py"},
        ],
        "commands": [{"label": "Candidate server", "argv": [
            "python", "-m", "vllm.entrypoints.openai.api_server", "--speculative-config",
            '{"method":"mtp","num_speculative_tokens":1}',
        ]}],
    })

    row = load_dashboard(tmp_path)["candidates"][0]
    command = row["commands"]["candidate"]
    assert "trial.py" in command and "--mode mtp" in command and "--max-tokens 128" in command
    for secret in ("/private", "s3cr3t", "rawkey", "Bearer hidden", "unknown-private-value",
                   "hidden source", "private-value"):
        assert secret not in json.dumps(row)
    assert row["optimization"]["summary"] == "Improve decode token=[redacted]"
    assert row["optimization"]["code_locations"][0]["path"] == "vllm/tokenizer.py"
    assert row["optimization"]["code_locations"][0]["revision"] == "a" * 40
    assert row["optimization"]["code_locations"][1]["path"] is None
    assert '"method":"mtp"' in row["optimization"]["commands"][0]["argv"]
    assert row["artifacts"]["run_lock"]["sha256"] == hashlib.sha256(lock.read_bytes()).hexdigest()
    for args in (["python", "x.py", "--value", "--sk-abc123XYZ"],
                 ["python", "x.py", "--size", "-1122334455667788"]):
        display = dashboard_data._display_command(args)
        assert "--sk-abc123XYZ" not in display
        assert "-1122334455667788" not in display


def test_trace_preserves_safe_event_fields_and_corrupt_source(tmp_path):
    write_json(tmp_path / "campaign.json", {"campaign_id": "example"})
    run(tmp_path, "run-a", 5, quality="completed", verified=True)
    events = tmp_path / "runs/run-a/events.jsonl"
    events.write_text('bad-runner\n', encoding="utf-8")
    trace = tmp_path / "candidates/a/trace.jsonl"
    trace.parent.mkdir(parents=True)
    event = {
        "schema_version": 1, "campaign_id": "example", "candidate_id": "a",
        "run_id": "run-a", "round": 1, "stage": "search", "type": "agent.tool",
        "time": "2026-01-01T00:00:00Z", "name": "write_candidate", "request": 2,
        "bytes": 100, "result_sha256": "b" * 64,
        "usage": {"input_tokens": 10, "output_tokens": 2, "secret": "DO_NOT_EXPORT"},
        "prompt": "DO_NOT_EXPORT", "reason": {"secret": "DO_NOT_EXPORT"},
    }
    trace.write_text(json.dumps(event) + '\n' + json.dumps({
        **event, "type": "edit.artifact", "name": "ignored", "revision": 3,
        "artifact": "candidate.py",
    }) + '\n' + json.dumps({**event, "type": "agent.tool", "name": "submit_candidate"})
                     + '\n' + json.dumps({
                         **event, "name": "run_visible_benchmark",
                         "reason": "provider_transport_error",
                         "receipt": {"kind": "benchmark", "receipt_sha256": "c" * 64,
                                     "feedback": {"verdict": "PASS", "quality_verdict": "PASS",
                                                  "improvement_pct": 20.5,
                                                  "baseline_values": [2.0],
                                                  "candidate_values": [1.5],
                                                  "secret": "DO_NOT_EXPORT"}},
                     })
                     + '\nbad-agent\n', encoding="utf-8")
    candidate(tmp_path, "a", "run-a", round=1, agent_trace_ref={
        "path": "candidates/a/trace.jsonl",
        "sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
    })

    row = load_dashboard(tmp_path)["candidates"][0]
    event = row["events"][0]
    assert event["tool"] == "write_candidate"
    assert event["details"]["request"] == 2 and event["details"]["bytes"] == 100
    assert event["details"]["usage"] == {"input_tokens": 10, "output_tokens": 2}
    assert event["details"]["result_sha256"] == "b" * 64
    assert "DO_NOT_EXPORT" not in json.dumps(row)
    assert row["events"][1]["type"] == "edit.artifact" and row["events"][1]["stage"] == "search"
    assert row["events"][1]["details"]["artifact"] == "candidate.py"
    assert row["events"][2]["tool"] == "submit_candidate"
    receipt = row["events"][3]["details"]["recorded_receipt"]
    assert receipt["quality_verdict"] == "PASS" and receipt["improvement_pct"] == 20.5
    assert receipt["receipt_sha256"] == "c" * 64
    assert row["events"][3]["details"]["reason"] == "provider_transport_error"
    assert row["corrupt_event_sources"] == {"events": [1], "agent_trace": [5]}
