"""Find can annotate ranked hits with the checked-in SearchSpace pairs."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.knowledge.knowledge_find import Corpus, find, load_corpus
from inferrsi.knowledge.searchspace_index import (
    LIBRARY,
    MATRIX,
    load_searchspace_coordinate,
    load_searchspace_index,
)

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / LIBRARY
DISPLAY = "--show-searchspace-coordinates"
QUERY = "graph mode"
GRAPH = "ascend-graph-mode"
GRAPH_COORDINATES = {
    "state": "covered",
    "coordinates": [["Accelerator", "Configure"], ["Accelerator", "Diagnose"],
                    ["Accelerator", "Verify"], ["SSD", "Diagnose"]],
}


@pytest.fixture(scope="module")
def index():
    return load_searchspace_index(PROJECT)


@pytest.fixture(scope="module")
def verified_corpus(index):
    return load_corpus(searchspace_index=index)


def test_display_keeps_plain_find_order_and_scores(verified_corpus, index):
    baseline = find(QUERY, load_corpus(ROOT), limit=12, explain=True)
    displayed = find(QUERY, verified_corpus, limit=12, explain=True,
                     show_searchspace_coordinates=True)

    assert displayed["items"][0]["id"] == GRAPH
    assert displayed["items"][0]["searchspace_coordinates"] == GRAPH_COORDINATES
    assert displayed.pop("searchspace_source") == index.source
    assert index.source["matrix_path"] == MATRIX.as_posix()
    matrix_sha256 = hashlib.sha256((PROJECT / MATRIX).read_bytes()).hexdigest()
    assert index.source["matrix_sha256"] == matrix_sha256
    for hit in displayed["items"]:
        hit.pop("searchspace_coordinates", None)
    assert displayed == baseline


def test_display_keeps_all_pairs_after_coordinate_filter(verified_corpus):
    filter_coordinate = load_searchspace_coordinate(ROOT, "SSD", "Configure")
    displayed = find(QUERY, verified_corpus, limit=1, searchspace_coordinate=filter_coordinate,
                     show_searchspace_coordinates=True)

    assert displayed["searchspace_filter"]["source"] == displayed["searchspace_source"]
    assert displayed["items"][0]["id"] == "ascend-model-adaptation"
    assert displayed["items"][0]["searchspace_coordinates"] == {
        "state": "covered",
        "coordinates": [["Accelerator", "Configure"], ["SSD", "Configure"], ["SSD", "Diagnose"]],
    }


def test_display_requires_a_verified_ranking_source():
    with pytest.raises(ValueError, match="verified SearchSpace index"):
        find(QUERY, Corpus([]), show_searchspace_coordinates=True)


def test_display_distinguishes_unknown_coverage_and_other_sources(verified_corpus, index, tmp_path):
    display = {"show_searchspace_coordinates": True}
    unknown = find("husky", verified_corpus, limit=1, **display)["items"][0]
    assert unknown["id"] == "husky"
    assert unknown["searchspace_coordinates"] == {"state": "unknown", "coordinates": []}

    graph = next(doc for doc in verified_corpus.documents if doc.identity == GRAPH)
    for document in (
        replace(graph, identity="unregistered", qualified=""),
        replace(graph, root=tmp_path, qualified=""),
        replace(graph, path=f"other/{graph.path}", qualified=""),
    ):
        corpus = Corpus([document], _searchspace_index=index)
        assert "searchspace_coordinates" not in find(QUERY, corpus, **display)["items"][0]

    for kind, query in (
        ("record", "prefill decode graph"), ("case", "NPU OOM after caching per-step masks"),
    ):
        result = find(query, verified_corpus, limit=15, **display)
        hits = [hit for hit in result["items"] if hit["kind"] == kind]
        assert hits
        assert all("searchspace_coordinates" not in hit for hit in hits)


def test_cli_displays_full_pairs_and_provenance(capsys):
    command = ["find", QUERY, "--skill-root", str(ROOT), "--no-external", "--limit", "1"]
    assert main(command) == 0
    assert "SearchSpace" not in capsys.readouterr().out

    assert main(command + [DISPLAY]) == 0
    text = capsys.readouterr().out
    assert MATRIX.as_posix() in text and "sha256" in text
    assert "[covered]" in text and "Accelerator × Verify" in text and "SSD × Diagnose" in text
    assert "SSD × Configure" not in text

    assert main(command + [DISPLAY, "--searchspace-coordinate", "SSD", "Configure", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert ["SSD", "Diagnose"] in result["items"][0]["searchspace_coordinates"]["coordinates"]
    assert result["searchspace_source"] == result["searchspace_filter"]["source"]


def test_cli_display_requires_explicit_checkout_root(capsys):
    with pytest.raises(SystemExit) as error:
        main(["find", QUERY, "--no-external", DISPLAY])
    assert error.value.code == 2
    assert "explicit --skill-root" in capsys.readouterr().err
