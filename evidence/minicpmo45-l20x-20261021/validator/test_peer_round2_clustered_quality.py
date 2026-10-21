"""Acceptance controls use synthetic IDs only; no holdout audio is generated."""

from copy import deepcopy

import pytest
from peer_round2_clustered_quality import aggregate
from peer_round2_noninferiority import evaluate

IDS = [f"synthetic-{i:03d}" for i in range(256)]
MARGINS = {"wer_percentage_points": 0.2, "sim_x100_drop": 0.5, "utmos_drop": 0.05}


def document():
    return {
        "tasks": ["wer", "sim", "utmos"],
        "rows": {
            key: {
                "wer": {"substitutions": 0, "deletions": 0, "insertions": 0, "hits": 10},
                "sim": 50.0,
                "utmos": 4.0,
            }
            for key in IDS
        },
    }


def test_identical_repeats_pass_without_expanding_prompt_count():
    merged = aggregate([document() for _ in range(3)], IDS)
    assert len(merged["rows"]) == 256
    assert merged["rows"][IDS[0]]["wer"]["hits"] == 30
    result = evaluate(merged, deepcopy(merged), MARGINS, IDS)
    assert result["n"] == 256
    assert result["verdict"] == "PASS"
    assert all(metric["upper_one_sided_95"] == 0 for metric in result["metrics"].values())


def test_within_prompt_average_keeps_between_prompt_bootstrap_uncertainty():
    reference = document()
    repeats = [document() for _ in range(3)]
    expected = document()
    for i, prompt in enumerate(IDS):
        between = -1 if i < 128 else 1
        expected["rows"][prompt]["sim"] += between
        for repeat, within in zip(repeats, (-2, 0, 2), strict=True):
            repeat["rows"][prompt]["sim"] += between + within
    measured = evaluate(aggregate([reference] * 3, IDS), aggregate(repeats, IDS), MARGINS, IDS)
    single_cluster_means = evaluate(reference, expected, MARGINS, IDS)
    assert measured == single_cluster_means
    assert measured["metrics"]["sim_x100_drop"]["upper_one_sided_95"] > 0


def test_real_degradation_is_not_averaged_away():
    reference = aggregate([document() for _ in range(3)], IDS)
    bad = document()
    for row in bad["rows"].values():
        row["sim"] -= 1
    candidate = aggregate([deepcopy(bad) for _ in range(3)], IDS)
    assert evaluate(reference, candidate, MARGINS, IDS)["verdict"] == "FAIL"


@pytest.mark.parametrize(
    "case", ["missing_run", "missing_id", "denominator", "nonfinite", "negative"]
)
def test_incomplete_or_invalid_repetitions_are_rejected(case):
    docs = [document() for _ in range(3)]
    if case == "missing_run":
        docs.pop()
    elif case == "missing_id":
        docs[1]["rows"].pop(IDS[0])
    elif case == "denominator":
        docs[1]["rows"][IDS[0]]["wer"]["hits"] += 1
    elif case == "nonfinite":
        docs[1]["rows"][IDS[0]]["sim"] = float("nan")
    else:
        docs[1]["rows"][IDS[0]]["wer"]["insertions"] = -1
    with pytest.raises(ValueError):
        aggregate(docs, IDS)
