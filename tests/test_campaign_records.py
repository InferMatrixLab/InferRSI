"""Local campaign records connect runs without copying private run artifacts."""

import json

import pytest

from inferrsi.cli import main
from inferrsi.harness.campaign_records import create_campaign, record_candidate, record_decision
from inferrsi.observability.dashboard_data import load_dashboard


def test_record_candidates_in_one_round_and_reference_trace(tmp_path):
    create_campaign(tmp_path, "campaign", target=20, synthetic=True)
    for name in ("a", "b"):
        run = tmp_path / "runs" / name
        run.mkdir(parents=True)
        (run / "run.lock.json").write_text("{}", encoding="utf-8")
    trace = tmp_path / "candidates/a/trace.jsonl"
    trace.parent.mkdir(parents=True)
    trace.write_text(json.dumps({"type": "agent.tool", "stage": "search", "schema_version": 1,
                                 "campaign_id": "campaign", "candidate_id": "a", "run_id": "a",
                                 "round": 1, "time": "2026-01-01T00:00:00Z"}) + "\n",
                     encoding="utf-8")
    record_candidate(tmp_path, candidate_id="a", run_id="a", round_number=1, title="First",
                     agent_trace="candidates/a/trace.jsonl")
    record_candidate(tmp_path, candidate_id="b", run_id="b", round_number=1, title="Second")

    rounds = [json.loads(line) for line in (tmp_path / "rounds.jsonl").read_text().splitlines()]
    view = load_dashboard(tmp_path)

    assert rounds == [{"round": 1, "candidates": ["a", "b"]}]
    assert view["synthetic"] is True
    assert view["candidates"][0]["artifacts"]["agent_trace"]["state"] == "present"
    assert any(event["stage"] == "search" for event in view["candidates"][0]["events"])


def test_campaign_records_refuse_overwrite_and_escaping_refs(tmp_path):
    create_campaign(tmp_path, "campaign")
    with pytest.raises(FileExistsError):
        create_campaign(tmp_path, "campaign")
    run = tmp_path / "runs/a"
    run.mkdir(parents=True)
    (run / "run.lock.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="relative path"):
        record_candidate(tmp_path, candidate_id="a", run_id="a", round_number=1, title="First",
                         agent_trace="../outside.jsonl")
    assert not (tmp_path / "rounds.jsonl").exists()
    assert not (tmp_path / "candidates/a/candidate.json").exists()


def test_campaign_and_dashboard_cli_round_trip(tmp_path, capsys):
    root = tmp_path / "campaign"
    assert main(["campaign", "init", "--directory", str(root), "--id", "example"]) == 0
    run = root / "runs/run-a"
    run.mkdir(parents=True)
    (run / "run.lock.json").write_text("{}", encoding="utf-8")
    assert main(["campaign", "record", "--directory", str(root), "--candidate", "a",
                 "--run-id", "run-a", "--round", "1", "--title", "First"]) == 0
    translations = tmp_path / "translations.json"
    translations.write_text('{"schema_version":1,"zh":{"First":"第一项"}}', encoding="utf-8")
    assert main(["dashboard", "--input", str(root), "--translations", str(translations)]) == 0
    assert (root / "dashboard.html").is_file()
    assert "第一项" in (root / "dashboard.html").read_text(encoding="utf-8")
    assert "dashboard" in capsys.readouterr().out


def test_round_decision_is_recorded_once_and_visible(tmp_path):
    create_campaign(tmp_path, "example")
    run = tmp_path / "runs/a"
    run.mkdir(parents=True)
    (run / "run.lock.json").write_text("{}", encoding="utf-8")
    record_candidate(tmp_path, candidate_id="a", run_id="a", round_number=1, title="First")
    record_decision(tmp_path, candidate_id="a", round_number=1, outcome="rolled_back")

    assert load_dashboard(tmp_path)["candidates"][0]["decision"] == "rolled_back"
    with pytest.raises(ValueError, match="already has a decision"):
        record_decision(tmp_path, candidate_id="a", round_number=1, outcome="adopted")


def test_record_cli_accepts_optimization_details_and_rejects_unsafe_location(tmp_path):
    root = tmp_path / "campaign"
    create_campaign(root, "example")
    run = root / "runs/run-a"
    run.mkdir(parents=True)
    (run / "run.lock.json").write_text("{}", encoding="utf-8")
    details = tmp_path / "details.json"
    details.write_text(json.dumps({"change_kind": "code", "summary": "Reduce launch overhead",
                                   "code_locations": [{"path": "src/engine.py", "line_start": 7}],
                                   "commands": [{"label": "Benchmark",
                                                 "argv": ["python", "bench.py", "--candidate",
                                                          "a", "--gpu", "4", "--api-key",
                                                          "FAKE_TEST_SECRET"]}]}),
                       encoding="utf-8")
    assert main(["campaign", "record", "--directory", str(root), "--candidate", "a",
                 "--run-id", "run-a", "--round", "1", "--title", "First",
                 "--details-json", str(details)]) == 0
    row = load_dashboard(root)["candidates"][0]
    assert row["optimization"]["summary"] == "Reduce launch overhead"
    assert row["optimization"]["code_locations"][0]["line_start"] == 7
    assert row["optimization"]["commands"][0]["argv"].startswith("python bench.py")
    assert "--candidate a --gpu 4" in row["optimization"]["commands"][0]["argv"]
    assert "FAKE_TEST_SECRET" not in (root / "candidates/a/candidate.json").read_text()
    assert "FAKE_TEST_SECRET" not in json.dumps(row)
    with pytest.raises(ValueError, match="safe relative path"):
        record_candidate(root, candidate_id="b", run_id="run-a", round_number=1, title="Second",
                         details={"code_locations": [{"path": "../private.py"}]})
    assert not (root / "candidates/b/candidate.json").exists()


def test_record_cli_rejects_excessively_nested_details_without_traceback(tmp_path, capsys):
    details = tmp_path / "details.json"
    # Stay below the input byte limit while exceeding the JSON recursion limit
    # on the supported Windows and Linux Python builds.
    details.write_text("[" * 10000 + "0" + "]" * 10000, encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["campaign", "record", "--directory", str(tmp_path), "--candidate", "a",
              "--run-id", "run-a", "--round", "1", "--title", "First",
              "--details-json", str(details)])
    error = capsys.readouterr().err
    assert "too deeply nested" in error and "Traceback" not in error
