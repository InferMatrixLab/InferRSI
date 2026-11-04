"""Current H3 receipt must not let the frozen preflight snapshot hide a sample."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "evidence/h3-ref2va-4x910b1-320"


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_preflight_status_stays_a_frozen_snapshot_with_a_current_receipt():
    status = load("results/status.json")
    current = load("results/status-v2.json")
    baseline = load("results/baseline-5s-complete.json")
    snapshot = current["historical_preflight_snapshot"]

    assert status["execution"] == "queued"
    assert status["four_device_samples"] == 0
    assert status["verdict"] == "INCONCLUSIVE"
    assert snapshot["path"] == "results/status.json"
    assert snapshot["stage"] == "preflight_preparation"
    assert snapshot["frozen_by"] == "plan/preflight-integrity.json"
    assert snapshot["execution"] == status["execution"]
    assert snapshot["four_device_samples"] == status["four_device_samples"]
    assert current["successor_of"] == "results/status.json"
    assert current["role"] == "current_campaign_receipt"
    assert current["verdict"] == "INCONCLUSIVE"
    assert current["speedup"] is None
    assert current["quality_acceptance"] is False
    assert current["campaign_acceptance"] is False

    sample = current["baseline_preflight"]
    measured = next(
        item for item in baseline["samples_including_warmups"]
        if item["label"] == "measured-5-seed0-0"
    )
    alive = [worker for worker in baseline["lifecycle"]["workers"] if worker["alive"]]
    assert sample["receipt"] == "results/baseline-5s-complete.json"
    assert sample["measured_samples"] == baseline["cells"][0]["completed"] == 1
    assert sample["measured_request"]["label"] == measured["label"]
    assert sample["measured_request"]["e2e_ms"] == measured["e2e_ms"]
    assert sample["measured_request"]["http_status"] == measured["http_status"]
    assert sample["steps"] == measured["steps"] == 50
    assert sample["hardware"] == baseline["hardware"]
    assert sample["lifecycle"]["status"] == baseline["lifecycle"]["status"] == "fail"
    assert sample["lifecycle"]["forced_signals"] == baseline["lifecycle"]["forced_signals"]
    assert sample["lifecycle"]["worker_teardown"] == "failed"
    assert len(alive) == baseline["lifecycle"]["expected_workers"]
    assert all(worker["exit_code"] is None for worker in alive)
    assert sample["verdict"] == baseline["verdict"] == "INCONCLUSIVE"
    assert "PASS" not in (current["verdict"], sample["verdict"], baseline["verdict"])

    later = current["later_records"]["fifteen_second_lifecycle_control"]
    fifteen = load(later["receipt"])
    assert later["run"] == fifteen["run"]
    assert fifteen["run"] != baseline["run"]
