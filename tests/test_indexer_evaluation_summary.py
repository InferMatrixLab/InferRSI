"""The evidence summary resamples paired groups and retains every observation."""
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
