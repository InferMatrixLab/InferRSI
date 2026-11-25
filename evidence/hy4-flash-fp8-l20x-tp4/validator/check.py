"""Recompute the retained request medians and correct counts without a GPU."""

import json
from collections import defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]


def records(name):
    return [json.loads(line) for line in (ROOT / "results" / name).read_text().splitlines()]


inputs = json.loads((ROOT / "validator/inputs.json").read_text())
expected_ids = [row["id"] for row in inputs["performance"]["requests"]]
times = defaultdict(list)
ids = defaultdict(list)
judgments = defaultdict(dict)
for row in records("requests.jsonl"):
    assert row["input_tokens"] == 130048 and row["output_tokens"] == 1024
    assert row["first_event_tokens"] >= 1 and row["last_event_tokens"] >= 1
    tpot = (row["last_event_ns"] - row["first_event_ns"]) / 1e6 / (row["output_tokens"] - 1)
    assert tpot == row["tpot_ms"]
    times[row["attempt"]].append(tpot)
    ids[row["attempt"]].append(row["id"])

for row in records("aime.jsonl"):
    answers = judgments[row["attempt"]]
    assert row["id"] not in answers and row["correct"] in (0, 1)
    assert row["finish_reason"] in ("stop", "length")
    answers[row["id"]] = row["correct"]

trials = {trial["attempt"]: trial for trial in records("trials.jsonl")}
for trial in trials.values():
    attempt = trial["attempt"]
    assert len(times[attempt]) == trial["completed_requests"]
    assert ids[attempt] == expected_ids[: trial["completed_requests"]]
    if trial["completed_requests"] == len(expected_ids):
        assert median(times[attempt]) == trial["tpot_p50_ms"]
    if "aime_correct" in trial:
        assert len(judgments[attempt]) == trial["aime_samples"] == 30
        assert list(judgments[attempt]) == inputs["quality"]["item_ids"]
        assert sum(judgments[attempt].values()) == trial["aime_correct"]
summary = json.loads((ROOT / "results/summary.json").read_text())
protocol = json.loads((ROOT / "validator/protocol.json").read_text())
runs = [summary[key] for key in ("baseline", "selected", "independent_final")]
assert len({run["service_id"] for run in runs}) == 3
assert len({run["run_id"] for run in runs}) == 3
assert runs[1]["revision"] == runs[2]["revision"]
for run in runs:
    trial = trials[run["attempt_id"]]
    assert trial["cleanup_verified"] and trial["verdict"] == "PASS"
    for field in ("service_id", "run_id", "revision", "tpot_p50_ms", "aime_correct"):
        assert trial[field] == run[field]
threshold = protocol["objectives"][0]["gain_threshold"]
ceiling = runs[0]["tpot_p50_ms"] * (1 - threshold / 100)
for run in runs[1:]:
    assert run["tpot_p50_ms"] <= ceiling
    assert run["aime_correct"] >= runs[0]["aime_correct"] - protocol["quality"]["tolerance"]
assert summary["acceptance_ceiling_ms_per_token"] == ceiling
assert summary["verdict"] == "PASS"
print("Verified request timings, scores and independent final acceptance.")
