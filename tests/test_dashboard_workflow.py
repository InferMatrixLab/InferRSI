"""A reviewer can replay the same run without changing its counts or verdict."""

import json
import sys

import pytest

from inferrsi.harness.runner import run_experiment
from inferrsi.harness.scenarios.external import execute_trial
from inferrsi.observability.dashboard_data import load_dashboard
from inferrsi.runspec import RunSpec


def test_dashboard_tracks_real_native_abba_and_validation(tmp_path):
    command = (sys.executable, "-c", "from pathlib import Path; import sys; "
               "Path(sys.argv[1]).write_text(sys.argv[2])", "{result}")
    spec = RunSpec(repo=str(tmp_path), output_dir=str(tmp_path / "runs"), repetitions=2,
                   baseline_command=(*command, '{"metrics":{"latency_ms":10}}'),
                   candidate_command=(*command, '{"metrics":{"latency_ms":8}}'),
                   validation_command=(sys.executable, "-c", "pass"))
    opened = []

    def observe_then_execute(command, cwd, trial_dir, deadline, metric_key):
        run_dir = trial_dir.parent.parent if metric_key else trial_dir.parent
        row = load_dashboard(run_dir)["candidates"][0]
        nodes = row["run_workflow"]["nodes"]
        current, = [n for n in nodes if n["state"] == "running"]
        opened.append((current["kind"], current["side"], current["trial"]))
        assert all(n["state"] == "completed" for n in nodes if n is not current)
        return execute_trial(command, cwd, trial_dir, deadline, metric_key)

    path = run_experiment(spec, {"backend": "cpu"}, execute=observe_then_execute,
                          snapshot=lambda repo, exclude: {"available": True, "snapshot_hash": "s"})
    assert opened == [("measurement", "baseline", 1), ("measurement", "candidate", 1),
                      ("measurement", "candidate", 2), ("measurement", "baseline", 2),
                      ("quality_validation", None, None)]
    row = load_dashboard(path)["candidates"][0]
    assert row["quality"] == "passed" and row["verdict"] == "PASS"
    nodes = row["run_workflow"]["nodes"]
    assert len(nodes) == 6 and all(n["end"] is None and n["state"] == "completed" for n in nodes)
    for n in nodes:
        if n["kind"] != "source_snapshot":
            assert n["seconds"] >= 0 and n["duration_source"] == "command"
    assert [(g["state"], g["completed"], g["wall_seconds"]) for g in
            row["run_workflow"]["groups"]] == [("completed", 4, None), ("completed", 1, None)]


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


@pytest.mark.parametrize("validation_edge", [
    {"phase": "quality_validation"},
    {"phase": "quality_validation_end", "state": "failed"},
])
def test_validator_counts_for_native_and_paired_traces(tmp_path, validation_edge):
    (tmp_path / "run.lock.json").write_text('{"repetitions": 2, "validation_command": ["check"]}')
    (tmp_path / "status.json").write_text('{"state":"failed"}')
    (tmp_path / "events.jsonl").write_text(
        '{"phase":"measurement","side":"baseline","trial":1}\n'
        + json.dumps(validation_edge) + "\n"
    )
    (tmp_path / "validation").mkdir()
    (tmp_path / "validation/execution.json").write_text('{"status":"failed","returncode":1}')
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
        assert row["quality"] == "failed"
        assert (quality["completed"], quality["total"], quality["unit"]) == (count, total, "cases")
        assert "never export this" not in json.dumps(row)
    for bad in ('{"completed":3,"total":2,"unit":"cases"}', '[]', '{'):
        (tmp_path / "validation/progress.json").write_text(bad)
        row = load_dashboard(tmp_path)["candidates"][0]
        quality = row["run_workflow"]["groups"][1]
        assert (quality["state"], quality["completed"], quality["total"]) == ("failed", 0, 1)
        assert row["artifacts"]["validation_progress"]["state"] == "missing"


def test_crashed_end_remains_terminal_without_command_record(tmp_path):
    (tmp_path / "events.jsonl").write_text(
        '{"phase":"measurement_end","side":"baseline","trial":1,"state":"crashed"}\n'
    )
    (tmp_path / "run.lock.json").write_text('{"repetitions":2}')
    (tmp_path / "status.json").write_text('{"state":"crashed"}')
    group = load_dashboard(tmp_path)["candidates"][0]["run_workflow"]["groups"][0]
    assert group["state"] == "crashed" and group["completed"] == 0


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
