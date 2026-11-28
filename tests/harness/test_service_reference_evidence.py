"""Reference receipts remain mandatory at each service campaign decision."""

import json
import subprocess

import pytest

from inferrsi.harness.manager import _state as optimization
from tests.fixtures.service_reuse import begin, call, rejected, settings, submit
from tests.fixtures.service_reuse import campaign as campaign


def assert_round_blocked(campaign):
    root = campaign["root"]
    assert (
        rejected(
            [
                "session",
                "round",
                "--session",
                str(root),
                "--candidate",
                str(campaign["repo"]),
                "--hypothesis",
                "Try another candidate",
            ]
        )
        == 2
    )
    assert "Cannot establish selected parent" in campaign["capsys"].readouterr().err


@pytest.mark.parametrize(
    "source, stage, candidate_latency",
    [
        ("baseline", "measure-001", 90),
        ("candidate", "warmup-001", 90),
        ("candidate", "measure-001", 90),
        ("candidate", "quality", 90),
        ("candidate", "precheck", 90),
        ("candidate", "ready", 90),
        ("baseline", "quality", 110),
    ],
)
def test_lost_required_receipt_blocks_round_and_final(campaign, source, stage, candidate_latency):
    initial = begin(campaign)["latest_observation"]
    candidate = submit(campaign, a=candidate_latency)["latest_observation"]
    root = campaign["root"]
    record = initial if source == "baseline" else candidate
    (root / record["path"] / "execution" / stage / "result.json").unlink()
    status = call(campaign, "status")
    assert not status["can_finalize"]
    assert status["final_block_reason"] == "unverifiable_evaluation_evidence"
    assert_round_blocked(campaign)
    final = call(campaign, "final", "--reason", "Retest after evidence loss")["final"]
    assert final["assessment"]["verdict"] == "INCONCLUSIVE"
    assert not (root / final["path"] / "service").exists()


@pytest.mark.parametrize("action", ["round", "final"])
def test_parent_evidence_lost_during_execution_blocks_settlement(campaign, monkeypatch, action):
    begin(campaign)
    parent = submit(campaign, a=94)["latest_observation"]
    selected = submit(campaign, a=88)["best"]
    execute = optimization._service_execute

    def lose_parent_warmup(*args):
        execution = execute(*args)
        assert execution["assessment"]["verdict"] == "PASS"
        path = campaign["root"] / parent["path"] / "execution/warmup-001/result.json"
        payload = json.loads(path.read_text())
        payload["binding"]["service_id"] = "unrelated-service"
        path.write_text(json.dumps(payload))
        return execution

    monkeypatch.setattr(optimization, "_service_execute", lose_parent_warmup)
    if action == "round":
        result = submit(campaign, a=82, expected=2)
    else:
        result = call(campaign, "final", "--reason", "Confirm the selected comparison", expected=2)
    attempt = result["latest_observation"]
    assert attempt["assessment_before_settlement"]["verdict"] == "PASS"
    assert attempt["assessment"]["verdict"] == "INCONCLUSIVE"
    assert attempt["assessment"]["reason"] == "unverifiable_evaluation_evidence"
    assert result["best"] == selected


def test_first_candidate_after_refresh_requires_new_parent_measurement(campaign):
    begin(campaign)
    previous = submit(campaign, a=90)["latest_observation"]
    changed = campaign["root"].parent / "conditions.json"
    changed.write_text(json.dumps({**previous["conditions"], "id": "next", "workload": "next"}))
    refresh = call(
        campaign, "refresh-references", "--reason", "New workload", "--conditions", changed
    )
    assert refresh["best"] is None
    parent = refresh["latest_observation"]["execution"]["references"][1]
    path = campaign["root"] / parent["path"]
    (path.parent / "execution/measure-001/result.json").unlink()
    assert_round_blocked(campaign)


def test_changed_external_baseline_quality_reference_blocks_final(campaign):
    config = settings()
    config["quality"].update(reference_path="quality-reference.json")
    campaign["config"].write_text(json.dumps(config))
    revision = subprocess.check_output(
        ["git", "-C", campaign["repo"], "rev-parse", "HEAD"], text=True
    ).strip()
    external = {
        "status": "completed",
        "revision": revision,
        "conditions": config["conditions"],
        "service_id": "external-service",
        "run_id": "external-run",
        "dataset": "synthetic",
        "scorer": "exact-v1",
        "unit": "points",
        "samples": 2,
        "quality": 1,
    }
    root = campaign["root"]
    (root.parent / "protocol/quality-reference.json").write_text(json.dumps(external))
    begin(campaign)
    assert submit(campaign, a=91)["can_finalize"]
    frozen_quality = root / "frozen/protocol/quality-reference.json"
    frozen_quality.chmod(0o644)
    frozen_quality.write_text(json.dumps({**external, "run_id": "different-run"}))
    assert (
        call(campaign, "final", "--reason", "Retest selected")["final"]["assessment"]["reason"]
        == "unverifiable_evaluation_evidence"
    )
