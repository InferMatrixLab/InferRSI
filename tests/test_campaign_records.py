"""Local campaign records connect runs without copying private run artifacts."""

import json

import pytest

from inferrsi.cli import main
from inferrsi.harness.campaign_records import create_campaign, record_candidate, record_decision
from inferrsi.harness.dashboard_data import load_dashboard


def test_record_candidates_in_one_round_and_reference_trace(tmp_path):
    create_campaign(tmp_path, "campaign", target=20, synthetic=True)
    for name in ("a", "b"):
        run = tmp_path / "runs" / name
        run.mkdir(parents=True)
        (run / "run.lock.json").write_text("{}", encoding="utf-8")
    trace = tmp_path / "candidates/a/trace.jsonl"
    trace.parent.mkdir(parents=True)
    trace.write_text('{"type":"agent.tool","stage":"search"}\n', encoding="utf-8")
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
    assert main(["dashboard", "--input", str(root)]) == 0
    assert (root / "dashboard.html").is_file()
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
