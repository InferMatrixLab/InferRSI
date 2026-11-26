import hashlib
import json

import pytest

from inferrsi.apps.views.dashboard import dashboard_snapshot
from inferrsi.apps.views.experiment_timing import experiment_timing


def test_verified_external_calls_preserve_partial_and_parallel_time(tmp_path):
    manifest = {"campaign_id": "demo", "review_layout": "profile_first"}
    raw = json.dumps({"schema_version": 1, "campaign_id": "demo", "steps": [
        {"kind": "experiment", "label": "task", "actor": "controller", "basis": "process",
         "start": "2026-05-10T10:00:00+08:00", "end": "2026-05-10T10:00:10+08:00"},
        {"kind": "model_call", "label": "#1", "actor": "agent", "model": "example-model",
         "basis": "client", "start": "2026-05-10T02:00:01Z", "end": "2026-05-10T02:00:09Z"},
        {"kind": "model_call", "label": "#2", "actor": "agent", "model": "example-model",
         "basis": "receipt only", "end": "2026-05-10T02:00:10Z", "prompt": "private payload"},
    ]}).encode()
    manifest["experiment_timing_sha256"] = hashlib.sha256(raw).hexdigest()
    (tmp_path / "campaign.json").write_text(json.dumps(manifest))
    path = tmp_path / "experiment-timing.json"
    path.write_bytes(raw)
    history = dashboard_snapshot(tmp_path)["data"]["experiment_timing"]
    assert history["ledger"] == "verified" and "private payload" not in json.dumps(history)
    assert [s["seconds"] for s in history["steps"]] == [10, 8, None]
    assert history["first"] == "2026-05-10T02:00:00.000000+00:00"
    assert history["last"] == "2026-05-10T02:00:10.000000+00:00"
    path.write_bytes(raw + b" ")
    history = dashboard_snapshot(tmp_path)["data"]["experiment_timing"]
    assert history["ledger"] == "unavailable" and not history["steps"]


def test_linked_calls_pair_by_run_source_and_request_and_keep_ambiguous_markers(tmp_path):
    def event(line, kind, request, clock, **details):
        return {"source": "agent_trace", "type": "agent." + kind, "line": line, "phase": None,
                "time": f"2026-05-10T02:00:{clock:02}Z", "details": {"request": request, **details}}

    events = [event(1, "request", 1, 1), event(2, "request", 2, 2),
              event(3, "response", 2, 8, provider_model="example-model"),
              event(4, "response", 1, 9), event(5, "request", 3, 10),
              event(6, "request", 3, 12), event(7, "response", 3, 15)]
    view = {"campaign_id": "sample", "candidates": [{"round": 1, "candidate_id": "a",
            "events": events}, {"round": 2, "candidate_id": "b", "events": [
                event(1, "response", 1, 16)]}]}
    steps = experiment_timing(view, tmp_path)["steps"]
    calls = [s for s in steps if s["kind"] == "model_call"]
    assert [(s["actor"], s["label"], s["seconds"]) for s in calls] == [
        ("a", "#1", 8), ("a", "#2", 6), ("b", "#1", None)]
    assert calls[1]["model"] == "example-model"
    assert sum(s["kind"] == "agent_event" for s in steps) == 3


def test_execution_span_excludes_later_saves_but_orders_all_records(tmp_path):
    steps = [
        {"kind": "operation", "label": "work", "actor": "agent", "basis": "client",
         "start": "2026-01-20T10:00:00.5Z", "end": "2026-01-20T10:00:01Z"},
        {"kind": "experiment", "label": "task", "actor": "controller", "basis": "process",
         "start": "2026-01-20T18:00:00+08:00", "end": "2026-01-20T10:00:01.12Z"},
    ]
    raw = json.dumps({"schema_version": 1, "campaign_id": "demo", "steps": steps}).encode()
    (tmp_path / "experiment-timing.json").write_bytes(raw)
    view = {"campaign_id": "demo", "candidates": [],
            "experiment_timing_sha256": hashlib.sha256(raw).hexdigest(),
            "story": {"versions": [{"state": "present", "version": 1,
                                    "recorded_at": "2026-01-25T06:00:00Z"}]}}
    history = experiment_timing(view, tmp_path)
    assert [row["label"] for row in history["steps"]] == ["task", "work", "v1"]
    assert history["execution_span"] == {"first": "2026-01-20T10:00:00.000000+00:00",
                                        "last": "2026-01-20T10:00:01.120000+00:00",
                                        "seconds": 1.12}
    assert history["last"].startswith("2026-01-25")
    assert history["steps"][1]["seconds"] == 0.5


@pytest.mark.parametrize(("campaign", "changes", "count"), [
    ("other", {}, 1), ("demo", {"end": "2026-01-19T09:59:59Z"}, 1),
    ("demo", {"model": None}, 1), ("demo", {"round": True}, 1), ("demo", {}, 5001),
    ("demo", {"start": "2026-01-20T10:00:00.1234567Z"}, 1),
])
def test_invalid_timing_ledger_with_matching_digest(tmp_path, campaign, changes, count):
    step = {"kind": "model_call", "model": "demo", "label": "call", "actor": "agent",
            "basis": "client", "start": "2026-01-20T10:00:00Z", **changes}
    if step["model"] is None:
        del step["model"]
    raw = json.dumps({"schema_version": 1, "campaign_id": campaign,
                      "steps": [step] * count}).encode()
    (tmp_path / "experiment-timing.json").write_bytes(raw)
    history = experiment_timing({"campaign_id": "demo", "candidates": [],
                                 "experiment_timing_sha256": hashlib.sha256(raw).hexdigest()},
                                tmp_path)
    assert history["ledger"] == "unavailable"
    assert history["steps"] == [] and history["execution_span"] is None
