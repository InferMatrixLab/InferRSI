import hashlib
import json

import pytest

from inferrsi.observability.dashboard import dashboard_snapshot
from inferrsi.observability.dashboard_data import _environment_signature, load_dashboard


def assemble(root, record):
    (root / "campaign.json").write_text(json.dumps({"campaign_id": "example"}))
    source = b'{"synthetic": true}'
    (root / "source.json").write_bytes(source)
    record = {
        **record,
        "candidate_id": "example",
        "source_refs": [{"path": "source.json", "sha256": hashlib.sha256(source).hexdigest()}],
    }
    raw = json.dumps(record).encode()
    (root / "external.json").write_bytes(raw)
    candidate = root / "candidates" / "example"
    candidate.mkdir(parents=True, exist_ok=True)
    (candidate / "candidate.json").write_text(
        json.dumps(
            {
                "candidate_id": "example",
                "title": "Example",
                "round": 1,
                "external_record_ref": {
                    "path": "external.json",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
            }
        )
    )


def record():
    return {
        "schema_version": 1,
        "kind": "external_optimization_record",
        "backend": "ascend",
        "protocol": "two-services-v1",
        "state": "completed",
        "performance_verdict": "FAIL",
        "quality": {"verdict": "NOT_RUN"},
        "metrics": [
            {
                "name": "C4",
                "unit": "ms/token",
                "baseline": 42,
                "samples": [40, 38],
                "aggregate": 39,
                "aggregation": "two_round_median",
                "target": 25,
            }
        ],
        "events": [
            {
                "stage": "validation",
                "time": "2026-01-01T12:00:00Z",
                "summary": "Recorded comparison failed",
            }
        ],
    }


def test_external_records_are_native_rows_without_generic_promotion(tmp_path):
    assemble(tmp_path, record())
    view = dashboard_snapshot(tmp_path)
    row = view["data"]["candidates"][0]
    assert row["verdict"] == "FAIL"
    assert row["quality"] == "not_recorded"
    assert row["improvement_pct"] is None
    assert view["data"]["overview"]["best_improvement_pct"] is None
    assert row["external"]["metrics"][0]["aggregate"] == 39
    assert row["external"]["quality_verdict"] == "NOT_RUN"
    assert "C4" in view["chart"]
    assert view["data"]["stages"][4]["state"] == "recorded"


@pytest.mark.parametrize("change", ["hash", "aggregate", "partial", "type"])
def test_incomplete_or_changed_records_fail_closed(tmp_path, change):
    data = record()
    if change == "aggregate":
        data["metrics"][0]["aggregate"] = 2
    if change == "type":
        data["metrics"] = None
    assemble(tmp_path, data)
    if change in ("hash", "partial"):
        (tmp_path / "external.json").write_text("{")
    row = load_dashboard(tmp_path)["candidates"][0]
    assert not row["external"]
    assert row["artifacts"]["external_record"]["state"] == "missing"


def test_empty_and_missing_stages_are_distinct(tmp_path):
    p = tmp_path / "campaign.json"
    p.write_text("{}")
    a = load_dashboard(tmp_path)
    assert a["overview"]["comparison_state"] == "no_data"
    assert a["integration"]["state"] == "not_connected"
    assert all(s["state"] == "stage_not_recorded" for s in a["stages"])
    p.write_text('{"stages_declared": []}')
    b = load_dashboard(tmp_path)
    assert b["integration"]["stage_declaration"] == "explicit_empty"
    assert all(s["state"] == "not_applicable" for s in b["stages"])


def test_ascend_identity_requires_runtime_and_firmware():
    env = {
        "host": {"platform": "synthetic"},
        "target_python": {
            "environment": {
                "python": "3.11",
                "packages": {
                    "torch": "example",
                    "vllm": "example",
                    "torch_npu": "example",
                    "vllm_ascend": "example",
                },
            }
        },
        "device": {
            "status": "available",
            "selection_verified": True,
            "devices": [
                {
                    "index": "0",
                    "uuid": "example",
                    "name": "example-npu",
                    "driver_version": "example",
                }
            ],
        },
    }
    assert _environment_signature(env, ["0"], "ascend") is None
    env["ascend"] = {"cann_version": "example", "firmware_version": "example"}
    first = _environment_signature(env, ["0"], "ascend")
    assert first is not None
    env["ascend"]["firmware_version"] = "changed"
    assert _environment_signature(env, ["0"], "ascend") != first


@pytest.mark.parametrize("change", ["missing_source", "changed_source", "wrong_candidate",
                                    "bad_quality", "too_many_samples", "negative_metric"])
def test_external_contract_rejects_invalid_provenance_or_values(tmp_path, change):
    data = record()
    if change == "bad_quality":
        data["quality"] = {"verdict": "PASS", "correct": 4, "total": 3}
    if change == "too_many_samples":
        data["metrics"][0]["samples"] = [40, 38, 36]
    if change == "negative_metric":
        data["metrics"][0]["baseline"] = -1
    assemble(tmp_path, data)
    if change == "missing_source":
        (tmp_path / "source.json").unlink()
    if change == "changed_source":
        (tmp_path / "source.json").write_text("{}")
    if change == "wrong_candidate":
        p = tmp_path / "candidates/example/candidate.json"
        candidate = json.loads(p.read_text())
        candidate["candidate_id"] = "different"
        p.write_text(json.dumps(candidate))
    row = load_dashboard(tmp_path)["candidates"][0]
    assert not row["external"]


def test_running_external_view_refreshes_without_fake_native_missing_files(tmp_path):
    data = record()
    data.update(state="running", performance_verdict="INCONCLUSIVE", metrics=[])
    assemble(tmp_path, data)
    first = dashboard_snapshot(tmp_path)["data"]["candidates"][0]
    assert first["state"] == "running"
    assert all(ref["state"] == "present" for ref in first["artifacts"].values())
    assert "run_lock" not in first["artifacts"]
    data = record()
    data["quality"] = {"verdict": "FAIL", "correct": 2, "total": 3}
    assemble(tmp_path, data)
    second = dashboard_snapshot(tmp_path)["data"]["candidates"][0]
    assert second["state"] == "completed"
    assert second["quality"] == "failed"
    assert second["external"]["quality_correct"] == 2
    assert second["outcome"] == "unverified"


def test_external_chart_escapes_markup(tmp_path):
    data = record()
    data["metrics"][0]["name"] = '<script>alert("example")</script>'
    assemble(tmp_path, data)
    chart = dashboard_snapshot(tmp_path)["chart"]
    assert "<script>" not in chart
    assert "&lt;script&gt;" in chart



def test_external_record_cannot_override_a_native_run(tmp_path):
    assemble(tmp_path, record())
    path = tmp_path / "candidates/example/candidate.json"
    candidate = json.loads(path.read_text())
    candidate["run_id"] = "native-run"
    path.write_text(json.dumps(candidate))
    row = load_dashboard(tmp_path)["candidates"][0]
    assert not row["external"]
    assert row["artifacts"]["external_record"]["missing_reason"] == "conflicting_run"


def test_collector_freshness_is_independent_of_dashboard_connection(tmp_path):
    assemble(tmp_path, record())
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps({"collection": {"state": "stale",
                                               "observed_at": "2026-01-01T12:00:00Z"}}))
    view = load_dashboard(tmp_path)
    assert view["integration"]["state"] == "connected"
    assert view["integration"]["collection"]["state"] == "stale"


@pytest.mark.parametrize('aggregate,accepted', [(0.15, True), (0.15000000001, True),
                                               (0.150001, False)])
def test_two_round_aggregate_allows_serialization_roundoff(tmp_path, aggregate, accepted):
    data = record()
    data['metrics'][0].update(samples=[0.1, 0.2], aggregate=aggregate)
    assemble(tmp_path, data)
    external = load_dashboard(tmp_path)['candidates'][0]['external']
    assert bool(external) is accepted
    if accepted:
        assert external['metrics'][0]['aggregate'] == aggregate


@pytest.mark.parametrize('count', [0, 1, 2])
def test_chart_colours_follow_roles_with_missing_rounds(tmp_path, count):
    import xml.etree.ElementTree as ET

    data = record()
    data['metrics'][0].update(samples=[40, 38][:count], aggregation='caller_recorded')
    assemble(tmp_path, data)
    svg = ET.fromstring(dashboard_snapshot(tmp_path)['chart'])
    labels = {e.text.split(':')[0]: e.attrib['fill'] for e in svg
              if e.tag.endswith('text') and ':' in (e.text or '')}
    assert labels['Parent'] == '#a0aab7'
    assert labels['Aggregate'] == '#73bf69'
    assert ('R1' in labels) == (count >= 1)
    assert ('R2' in labels) == (count == 2)
    if count:
        assert labels['R1'] == '#5794f2'
    if count == 2:
        assert labels['R2'] == '#ff9830'


def test_empty_external_metrics_remain_visible_and_are_explained(tmp_path):
    from inferrsi.observability.dashboard import _chart

    data = record()
    data['metrics'] = []
    assemble(tmp_path, data)
    snapshot = dashboard_snapshot(tmp_path)
    assert len(snapshot['data']['candidates']) == 1
    assert snapshot['data']['candidates'][0]['events']
    assert snapshot['chart'] == ''
    assert '1 external record(s) have no recorded metrics' in snapshot['data']['chart_note']
    empty = snapshot['data']['candidates'][0]
    assemble(tmp_path, record())
    measured = dashboard_snapshot(tmp_path)
    measured['data']['candidates'].append(empty)
    chart, note = _chart(tmp_path, measured['data'])
    assert 'C4' in chart
    assert '1 external record(s) have no recorded metrics' in note


def test_empty_campaign_snapshot_has_no_gain_or_plot(tmp_path):
    (tmp_path / 'campaign.json').write_text('{}')
    snapshot = dashboard_snapshot(tmp_path)
    assert snapshot['data']['overview']['comparison_state'] == 'no_data'
    assert snapshot['data']['overview']['best_improvement_pct'] is None
    assert snapshot['data']['overview']['target_gap_pct'] is None
    assert snapshot['chart'] == ''
    assert snapshot['data']['chart_note'] == 'No measured candidate results recorded.'
    assert snapshot['temporal'] == ''
