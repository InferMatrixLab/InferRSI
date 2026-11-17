"""Before/after: does the external channel actually widen what `find` reaches.

This file is the acceptance measurement for the cannbot channel. It runs the
real CLI twice per query -- once gated off, once gated on -- and reports the
counts. The upstream half needs an approved checkout and a built index, so it
is skipped rather than faked when either is absent: a fabricated number here
would be worse than no number.
"""

import json
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
QUERIES = (
    "AscendC tiling 参数怎么计算",
    "CeilDivision 向上取整",
    "matmul 分块 性能",
    "算子 精度 调试 溢出",
    "ACLGraph 图模式 捕获",
    "KV cache 显存 布局",
)


def _run(*args):
    argv = [sys.executable, "-m", "inferrsi", *args]
    if args[0] != "cannbot":          # `cannbot` subcommands print JSON already
        argv.append("--json")
    result = subprocess.run(argv, capture_output=True, text=True, cwd=PROJECT)
    if result.returncode:
        return None
    return json.loads(result.stdout)


def _approved():
    info = _run("cannbot", "describe")
    return bool(info) and info.get("state") == "ok"


def test_gate_off_matches_the_pre_channel_behaviour():
    """`--no-external` must reproduce the output callers already relied on.

    An unflagged run is *supposed* to differ: it adds the gate explanation.
    The invariant is only about `--no-external`, and it must be exact.
    """
    from inferrsi.knowledge.knowledge_find import find, load_corpus
    from inferrsi.apps.cli import _channels

    corpus = load_corpus()
    pre_channel = find("AscendC tiling", corpus, limit=5)
    gated = _run("find", "AscendC tiling", "--no-external")
    assert gated is not None
    assert "external" not in gated
    # Same keys, same counts, same order as the function before channels existed.
    assert sorted(gated) == sorted(pre_channel)
    assert [i["id"] for i in gated["items"]] == [i["id"] for i in pre_channel["items"]]
    assert _channels() is not None  # the registry exists; the flag is what skips it


def test_undeclared_backend_reports_the_gate():
    """Only an undeclared backend may skip a channel without a grant.

    Once a grant records `backend: ascend`, the default path is a declaration
    and must search. The gate explanation is for the case where neither an
    explicit flag nor an approved grant says what platform this is.
    """
    result = _run("find", "AscendC tiling")
    assert result is not None
    from inferrsi.apps.cli import _channels

    registry = _channels()
    entries = result.get("external", [])
    if registry.declared_backend is None:
        assert all(entry["state"] != "ok" for entry in entries)
        assert any("fix" in entry for entry in entries)
    else:
        assert any(entry["state"] == "ok" for entry in entries), (
            "an approved grant declares the backend, so the default path must search"
        )


@pytest.mark.skipif(not _approved(), reason="no approved cannbot checkout with a built index")
def test_local_corpus_is_unchanged_by_the_channel():
    """The channel adds a column; it never re-ranks or trims the local list."""
    for query in QUERIES:
        before = _run("find", query, "--no-external")
        after = _run("find", query, "--backend", "ascend")
        assert before["matched"] == after["matched"], query
        assert [item["id"] for item in before["items"]] == [
            item["id"] for item in after["items"]
        ], query


@pytest.mark.skipif(not _approved(), reason="no approved cannbot checkout with a built index")
def test_channel_returns_locators_with_a_pin():
    result = _run("find", QUERIES[1], "--backend", "ascend")
    entry = next(item for item in result["external"] if item["channel"] == "cannbot-knowledge")
    assert entry["state"] == "ok"
    assert len(entry["revision"]) == 40
    assert entry["score_scale"].startswith("knowledge-search")
    assert entry["items"], "the upstream source has cards for this query"
    for hit in entry["items"]:
        assert hit["locator"] and "/" in hit["locator"]
        assert hit["card_sha256"]
        assert hit["open"].startswith("inferrsi cannbot read ")


@pytest.mark.skipif(not _approved(), reason="no approved cannbot checkout with a built index")
def test_external_hits_never_enter_items():
    for query in QUERIES:
        result = _run("find", query, "--backend", "ascend")
        local_ids = {item["id"] for item in result["items"]}
        for entry in result["external"]:
            for hit in entry.get("items", []):
                assert hit["locator"] not in local_ids


@pytest.mark.skipif(not _approved(), reason="no approved cannbot checkout with a built index")
def test_every_query_reaches_more_than_the_local_corpus():
    """The point of the channel: each query gains upstream coverage."""
    rows = []
    for query in QUERIES:
        before = _run("find", query, "--no-external")
        after = _run("find", query, "--backend", "ascend")
        external = sum(
            entry.get("count", 0) for entry in after["external"] if entry["state"] == "ok"
        )
        rows.append((query, before["matched"], external))
    report = "\n".join(
        f"{query:28} local={local:>4} external={external:>3}" for query, local, external in rows
    )
    print("\nfind coverage before/after:\n" + report)
    assert all(external > 0 for _, _, external in rows), report
    assert any(before == 0 for _, before, _ in rows), (
        "at least one Ascend query should be empty locally and answered upstream"
    )


@pytest.mark.skipif(not _approved(), reason="no approved cannbot checkout with a built index")
def test_read_returns_one_pinned_card():
    result = _run("find", "CeilDivision", "--backend", "ascend")
    entry = next(item for item in result["external"] if item["channel"] == "cannbot-knowledge")
    locator = entry["items"][0]["locator"]
    card = _run("cannbot", "read", locator)
    assert card["state"] == "ok"
    assert card["locator"] == locator
    assert card["text"].strip()
