"""The evidence summary resamples paired groups and retains every observation."""
import json
import sys

import pytest

from tools import evaluate_indexer
from tools.evaluate_indexer import percentile, summarize


def test_constant_paired_groups_have_exact_gain_and_interval():
    groups = []
    for _ in range(20):
        groups.append({arm: {
            name: {"ns": value, "output_sha256": "same"}
            for name in ("hot_relevance/dev01", "hot_relevance/dev02", "search")
        } for arm, value in (("A", 100), ("B", 80))})
    result = summarize(groups)
    assert result["primary_reduction_percent"] == 20
    assert result["primary_95ci"] == [20, 20]
    assert result["paths"]["search"]["A"]["n"] == 20
    assert result["paths"]["search"]["output_parity"]
    groups[0]["B"]["search"]["output_sha256"] = "different"
    assert not summarize(groups)["paths"]["search"]["output_parity"]


def test_tail_is_nearest_rank_not_interpolated_or_trimmed():
    assert percentile(list(range(1, 21)), .95) == 19
    assert percentile([1], .95) == 1


def test_find_and_frozen_collect_measurements_have_no_comparable_primary():
    row = {"ns": 100, "output_sha256": "same"}
    summary = summarize([{"A": {"hot_relevance/q": row, "cli_find_search": row},
                          "B": {"hot_find/q": row, "cli_find_search": row}}])
    assert list(summary["paths"]) == ["cli_find_search"]
    assert summary["unpaired_paths"] == {"A": ["hot_relevance/q"], "B": ["hot_find/q"]}
    assert summary["primary_reduction_percent"] is None and summary["primary_95ci"] is None


@pytest.mark.parametrize("shared_parity,verdict", [(True, "INCONCLUSIVE"), (False, "FAIL")])
def test_different_cli_contracts_only_compare_shared_paths(tmp_path, monkeypatch, shared_parity,
                                                          verdict):
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps({
        "baseline_revision": "baseline", "measurement": {"groups": 1},
        "primary": {"gain_min_percent": 0, "each_query_p50_max_regression_percent": 0},
        "secondary_limits": {},
    }))

    def child(root, action, payload):
        if action == "identity":
            return {"revision": root.name, "corpus": "same-corpus"}
        if action == "contracts":
            return [{"passed": True}]
        assert action == "bench"
        old = root.name == "baseline"
        prefix = "cli_" if old else "cli_find_"
        names = (prefix + "relevance", prefix + "search")
        output = "same" if old or shared_parity else "changed"
        return {name: {"ns": 100 if old else 80, "output_sha256": output}
                for name in ("hot_relevance/scoped", *names)}

    output = tmp_path / "output"
    monkeypatch.setattr(evaluate_indexer, "child", child)
    monkeypatch.setattr(sys, "argv", [
        "evaluate_indexer", "--baseline", str(tmp_path / "baseline"), "--candidate",
        str(tmp_path / "candidate"), "--protocol", str(protocol), "--output", str(output),
    ])
    evaluate_indexer.main()
    result = json.loads((output / "timing.json").read_bytes())
    assert result["verdict"] == verdict
    expected_failures = [] if shared_parity else ["hot_relevance/scoped output mismatch"]
    assert result["failed_gates"] == expected_failures
    summary = result["summary"]
    assert list(summary["paths"]) == ["hot_relevance/scoped"]
    assert summary["paths"]["hot_relevance/scoped"]["output_parity"] == shared_parity
    assert summary["unpaired_paths"] == {
        "A": ["cli_relevance", "cli_search"], "B": ["cli_find_relevance", "cli_find_search"],
    }
