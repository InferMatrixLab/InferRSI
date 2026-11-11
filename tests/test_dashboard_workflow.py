"""A reviewer can replay the same run without changing its counts or verdict."""

import json

from inferrsi.observability.dashboard_data import load_dashboard


def test_live_workflow_replay(tmp_path):
    def write(name, data):
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")

    write("run.lock.json", {"repetitions": 1, "validation_command": ["check"]})
    write("status.json", {"state": "running"})
    trace = tmp_path / "events.jsonl"
    events = [
        {
            "time": "2026-01-01T00:00:02Z",
            "phase": "measurement_end",
            "side": "candidate",
            "trial": 1,
            "state": "completed",
            "elapsed_seconds": 1,
        },
        {
            "time": "2026-01-01T00:00:01Z",
            "phase": "measurement",
            "side": "candidate",
            "trial": 1,
            "state": "running",
        },
        {
            "time": "2026-01-01T00:00:00Z",
            "phase": "measurement",
            "side": "baseline",
            "trial": 1,
            "state": "running",
        },
    ]

    def read():
        trace.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        return load_dashboard(tmp_path)["candidates"][0]

    events.append(events[0])
    row = read()
    nodes = row["run_workflow"]["nodes"]
    assert [n["state"] for n in nodes] == ["running", "completed"]
    assert nodes[1]["line"] == 1
    performance, accuracy = row["run_workflow"]["groups"]
    assert (performance["completed"], performance["total"], performance["state"]) == (
        1,
        2,
        "running",
    )
    assert (accuracy["completed"], accuracy["total"], accuracy["state"]) == (0, 1, "pending")
    events.append(
        {
            "time": "2026-01-01T00:00:03Z",
            "phase": "measurement_end",
            "side": "baseline",
            "trial": 1,
            "state": "cancelled",
            "elapsed_seconds": 3,
        }
    )
    write("status.json", {"state": "cancelled"})
    row = read()
    performance, accuracy = row["run_workflow"]["groups"]
    assert (performance["completed"], performance["state"], performance["wall_seconds"]) == (
        1,
        "cancelled",
        3,
    )
    assert accuracy["state"] == "skipped"
    assert row["verdict"] == "not_recorded"
    # Two different terminal observations for one node cannot establish its result.
    events.append(dict(events[0], state="failed"))
    assert read()["run_workflow"]["groups"][0]["state"] == "unknown"


def test_validator_counts_and_legacy_trace(tmp_path):
    (tmp_path / "run.lock.json").write_text('{"repetitions": 2, "validation_command": ["check"]}')
    (tmp_path / "status.json").write_text('{"state":"failed"}')
    (tmp_path / "events.jsonl").write_text(
        '{"phase":"measurement","side":"baseline","trial":1}\n'
        '{"phase":"quality_validation_end","state":"failed"}\n'
    )
    (tmp_path / "validation").mkdir()
    for count, total in [(1, None), (2, 2), (0, 0)]:
        (tmp_path / "validation/progress.json").write_text(
            json.dumps(
                {
                    "completed": count,
                    "total": total,
                    "unit": "cases",
                    "private": "never export this",
                }
            )
        )
        row = load_dashboard(tmp_path)["candidates"][0]
        perf, quality = row["run_workflow"]["groups"]
        assert perf["state"] == "unknown" and perf["wall_seconds"] is None
        assert quality["state"] == "failed"
        assert (quality["completed"], quality["total"], quality["unit"]) == (count, total, "cases")
        assert "never export this" not in json.dumps(row)
    (tmp_path / "validation/progress.json").write_text('{"completed":3,"total":2,"unit":"cases"}')
    assert (
        load_dashboard(tmp_path)["candidates"][0]["run_workflow"]["groups"][1]["state"] == "unknown"
    )


def test_provider_events_share_activity_without_exporting_payload(tmp_path):
    from inferrsi.observability.dashboard_data import _events

    path = tmp_path / "events.jsonl"
    path.write_text(
        '{"type":"item.completed","item":{"type":"command_execution","command":"private"}}\n'
        '{"type":"agent.tool","name":"run_visible_checks","output":"private"}\n'
        '{"type":"turn.failed","error":{"message":"private"}}\n'
        '{"type":"agent.failed","reason":"private"}\n'
    )
    events = _events(path, tmp_path)[0]
    assert [event["activity"] for event in events] == ["tool", "tool", "error", "error"]
    assert [event["line"] for event in events] == [1, 2, 3, 4]
    assert "private" not in json.dumps(events)
