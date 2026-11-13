"""Projection contracts: numbers, stable identities, conservative joins and references."""

import copy
import json
import runpy
from pathlib import Path

import pytest

from inferrsi.observability.dashboard import dashboard_snapshot, render_dashboard
from inferrsi.observability.dashboard_data import load_dashboard
from inferrsi.observability.dashboard_experiments import (
    DIMENSIONS,
    external_dimensions,
    references_for,
    timestamp,
)

FIXTURE = runpy.run_path(str(Path(__file__).parent / "fixtures/dashboard_experiments.py"))


@pytest.fixture
def campaign(tmp_path):
    FIXTURE["build"](tmp_path)
    return tmp_path


def points(root):
    return load_dashboard(root)["experiments"]["points"]


def test_multi_workload_axes_and_configurations_are_explicit(campaign):
    data = load_dashboard(campaign)
    plot = data["experiments"]
    baseline = [p for p in plot["points"] if p["candidate_id"] == "native-control"]
    assert {p["workload"] for p in baseline} == {"W1", "W2", "W3"}
    assert len({p["axis_key"] for p in baseline}) == 3
    w1 = [p for p in plot["points"] if p["workload"] == "W1"]
    ordinary = [p for p in w1 if p["candidate_id"] in
                ("native-control", "vae-graph", "parallel-stream")]
    assert len({p["series_id"] for p in ordinary}) == 1
    assert ordinary[0]["series_id"] is not None
    tile = next(p for p in w1 if p["scope"] == "vae_tile")
    assert tile["axis_key"] != ordinary[0]["axis_key"]
    changed = next(p for p in w1 if p["candidate_id"] == "different-precision")
    assert changed["series_id"] != ordinary[0]["series_id"]
    assert data["story"]["summary"]["state"] == "partial"
    assert all(not k.startswith("_plot") and k != "_comparison_signature"
               for row in data["candidates"] for k in row)
    assert "synthetic-device" not in json.dumps(data)


def test_unknown_does_not_equal_unknown_and_numbers_never_come_from_text(campaign):
    data = load_dashboard(campaign)["experiments"]
    unknown = [p for p in data["points"] if p["candidate_id"] in ("unknown-a", "unknown-b")]
    assert len(unknown) == 2
    assert all(p["series_id"] is None for p in unknown)
    assert all("missing configuration: hardware" in p["comparison_reasons"] for p in unknown)
    assert all(p["value"] == 9.2 for p in unknown)
    assert not any(p["value"] == 123 for p in data["points"])
    legacy = next(p for p in data["points"] if p["candidate_id"] == "legacy-metric")
    assert legacy["value"] == 11 and legacy["workload"] is None
    assert legacy["plot_reasons"] and legacy["series_id"] is None
    assert timestamp("2026-01-01T12:00:00") is None
    assert timestamp("not-a-time") is None
    assert timestamp("2026-01-01T12:00:00Z") is not None


def test_failure_keeps_measurement_and_missing_artifacts_never_become_zero(campaign):
    data = load_dashboard(campaign)["experiments"]
    failed = next(p for p in data["points"] if p["candidate_id"] == "quality-rejected")
    assert failed["value"] == 7.5 and failed["quality"] == failed["verdict"] == "FAIL"
    assert failed["target_gaps"][0]["gap"] == -0.5
    assert not any(p["value"] == 0 for p in data["points"])
    assert not any(p["candidate_id"] == "graph-capture-failed" for p in data["points"])
    assert any(e["category"] == "failure" and e["workloads"] == ["W1"]
               for e in data["events"])
    missing = next(p for p in data["points"] if p["candidate_id"] == "missing-artifact")
    assert missing["value"] is None
    assert any(r["state"] == "missing" for r in missing["refs"])
    summary_events = [e for e in data["events"] if e["narrative_category"]]
    assert len(summary_events) == 4
    legacy = next(e for e in summary_events if "123 s" in e["description"])
    assert legacy["round"] is None and not legacy["experiment_ids"]


def test_same_candidate_same_round_runs_and_measurements_have_stable_ids(campaign):
    before = points(campaign)
    native = [p for p in before if p["candidate_id"] == "native-repeat"]
    external = [p for p in before if p["candidate_id"] == "repeated-candidate"]
    assert len(native) == len(external) == 2
    assert len({p["id"] for p in before}) == len(before)
    assert {p["run_id"] for p in native} == {"native-run-a", "native-run-b"}
    assert all(p["run_id"] is None and p["source_record"] for p in external)
    assert {p["round"] for p in native} == {3}
    # Candidate directory sorting and metric values do not define identity.
    (campaign / "candidates/native-run-a").rename(campaign / "candidates/zzz-native-a")
    path = campaign / "runs/native-run-a/evaluation.json"
    data = json.loads(path.read_text())
    data["candidate"]["median"] = 108
    path.write_text(json.dumps(data))
    after = points(campaign)
    assert {p["id"] for p in after if p["candidate_id"] == "native-repeat"} == {
        p["id"] for p in native}
    event = next(e for e in load_dashboard(campaign)["experiments"]["events"]
                 if e["narrative_category"] and "native runs" in e["description"])
    assert set(event["experiment_ids"]) == {p["experiment_id"] for p in native}


@pytest.mark.parametrize("artifact,mutate", [
    ("run.lock.json", lambda d: d.update(baseline_command=["python", "other.py"])),
    ("run.lock.json", lambda d: d.update(validation_command=["python", "other.py"])),
    ("run.lock.json", lambda d: d.update(candidate_command=["python", "different-shape.py"])),
    ("repositories.lock.json", lambda d: d["baseline"].update(snapshot_hash="b" * 64)),
    ("environment.json", lambda d: d["target_python"]["environment"].update(python="changed")),
])
def test_native_join_preserves_all_existing_comparison_boundaries(campaign, artifact, mutate):
    native = [p for p in points(campaign) if p["candidate_id"] == "native-repeat"]
    assert native[0]["series_id"] == native[1]["series_id"] is not None
    path = campaign / "runs/native-run-a" / artifact
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data))
    native = [p for p in points(campaign) if p["candidate_id"] == "native-repeat"]
    assert native[0]["series_id"] != native[1]["series_id"]


@pytest.mark.parametrize("direction,definition,value,expected", [
    ("minimize", "improvement_pct", 20, 80),
    ("maximize", "improvement_pct", 20, 120),
    ("minimize", "inverse_latency_ratio", 0.5, 200),
    ("minimize", "inverse_latency_ratio", 0, None),
    ("maximize", "inverse_latency_ratio", 2, None),
    ("minimize", "improvement_pct", 101, None),
    ("minimize", "improvement_pct", -1, None),
    (None, "improvement_pct", 20, None),
])
def test_reference_roles_and_target_conversions(direction, definition, value, expected):
    m = FIXTURE["metric"]()
    m["references"][0]["value"] = 100
    m["references"][2].update(relative_to="local", definition=definition, value=value)
    specs = external_dimensions(m)["references"]
    point = {**dict.fromkeys(DIMENSIONS), "direction": direction, "unit": "s", "refs": []}
    refs = references_for(point, specs)
    assert [r["role"] for r in refs] == ["local_baseline", "external_reference", "frozen_target"]
    assert refs[2]["value"] == expected
    if expected is None:
        assert refs[2]["reason"]


def test_invalid_and_unfrozen_targets_are_retained_with_reasons():
    specs = external_dimensions(FIXTURE["metric"]())["references"]
    point = {**dict.fromkeys(DIMENSIONS), "direction": "minimize", "unit": "s", "refs": []}
    for change in [{"frozen": False}, {"unit": "ms"}, {"relative_to": "absent"},
                   {"provenance": ""}, {"value": float("inf")}]:
        changed = copy.deepcopy(specs)
        changed[2].update(change)
        # Public ingestion rejects non-finite values before conversion.
        if change.get("value") == float("inf"):
            changed[2]["value"] = None
        result = references_for(point, changed)[2]
        assert result["value"] is None and result["reason"]


def test_static_and_live_embed_the_same_self_contained_renderer(campaign):
    snapshot = dashboard_snapshot(campaign)
    offline = render_dashboard(snapshot)
    live = render_dashboard(snapshot, live=True)
    assert "__DASHBOARD_EXPERIMENTS__" not in offline
    assert "window.InferRSIExperiments" in offline and "window.InferRSIExperiments" in live
    assert 'src="http' not in offline
    assert "connect-src 'self'" not in offline and "connect-src 'self'" in live
    snapshot["data"]["review_layout"] = "profile_first"
    renderer = "experimentView.render([byId('chart'),byId('summary-experiments')])"
    assert renderer in render_dashboard(snapshot)


def test_metric_identity_survives_reordering_and_order_is_not_round(campaign):
    before = [p for p in points(campaign) if p["candidate_id"] == "native-control"]
    path = campaign / "native-control.json"
    data = json.loads(path.read_text())
    data["metrics"].reverse()
    for metric in data["metrics"]:
        metric["order"] = 50
    ref = FIXTURE["write"](path, data)
    candidate = campaign / "candidates/native-control/candidate.json"
    data = json.loads(candidate.read_text())
    data["external_record_ref"] = ref
    candidate.write_text(json.dumps(data))
    after = [p for p in points(campaign) if p["candidate_id"] == "native-control"]
    assert {p["id"] for p in before} == {p["id"] for p in after}
    assert all(p["round"] == 1 and p["order"] == 50 for p in after)


def test_redacted_dimensions_and_legacy_reference_roles_are_not_inferred(campaign):
    raw = FIXTURE["metric"](workload="/private/workload")
    mapped = external_dimensions(raw)
    assert mapped["workload"] is None
    for value in [None, [], {}, True, 0, -1]:
        raw["configuration"]["batch"] = value
        assert external_dimensions(raw)["comparison_reasons"]
    raw = FIXTURE["metric"](baseline=10, target=8, references=[])
    FIXTURE["external"](campaign, "legacy-references", 11, [raw])
    p = next(p for p in points(campaign) if p["candidate_id"] == "legacy-references")
    assert len(p["references"]) == 2
    assert all(r["value"] is None and r["reason"] == "unknown reference role"
               for r in p["references"])
    assert [r["original_value"] for r in p["references"]] == [10, 8]


def test_external_event_ids_survive_reorder_only_when_explicit(campaign):
    event_a = {"id": "stable-event", "stage": "execution", "summary": "First"}
    event_b = {"stage": "validation", "summary": "Second"}
    FIXTURE["external"](campaign, "events", 12, [], events=[event_a, event_b])
    def ids():
        return {e["description"]: e["id"] for e in load_dashboard(campaign)["experiments"]["events"]
                if e.get("candidate_id") == "events"}
    before = ids()
    FIXTURE["external"](campaign, "events", 12, [], events=[event_b, event_a])
    after = ids()
    assert before["First"] == after["First"]
    assert before["Second"] != after["Second"]


@pytest.mark.parametrize("field", [
    "model", "model_revision", "shape", "precision", "hardware", "protocol",
    "server_profile", "runtime", "measurement_protocol",
])
@pytest.mark.parametrize("blank", ["", "   ", "\t\r\n", "\u00a0\u2003"])
def test_blank_external_configuration_keeps_points_without_joining(tmp_path, field, blank):
    FIXTURE["write"](tmp_path / "campaign.json", {"campaign_id": "synthetic-blank-config"})
    for round_number in (1, 2):
        metric = FIXTURE["metric"](value=8 + round_number)
        metric["configuration"][field] = blank
        FIXTURE["external"](tmp_path, f"blank-{round_number}", round_number, [metric])
    projected = points(tmp_path)
    assert len(projected) == 2
    assert [p["value"] for p in projected] == [9, 10]
    for p in projected:
        assert p["plot_reasons"] == []  # Values and axes still support independent points.
        assert p["series_id"] is None
        assert f"unknown configuration: {field}" in p["comparison_reasons"]
        assert field not in p["configuration"]
