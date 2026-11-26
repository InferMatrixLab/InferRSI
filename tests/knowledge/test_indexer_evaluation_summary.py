"""The evidence summary resamples paired groups and retains every observation."""
import hashlib

import pytest

from tools.evaluate_indexer import encode, identity, percentile, summarize


@pytest.mark.parametrize("relative", [
    "src/inferrsi/harness/data/repo_packs/vllm/pack.json",
    "src/inferrsi/resources/repo_packs/vllm.json",
])
def test_corpus_fingerprint_covers_repository_pack(tmp_path, monkeypatch, relative):
    monkeypatch.setattr(
        "tools.evaluate_indexer.subprocess.check_output", lambda *args, **kwargs: "fixture\n",
    )
    descriptor = tmp_path / relative
    descriptor.parent.mkdir(parents=True)
    for data in (b"first", b"other"):
        descriptor.write_bytes(data)
        members = {relative: hashlib.sha256(data).hexdigest()}
        assert identity(tmp_path)["corpus"] == {
            "sha256": hashlib.sha256(encode(members)).hexdigest(), "files": 1,
        }


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
