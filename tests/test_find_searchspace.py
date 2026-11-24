"""Find applies a verified SearchSpace pair after lexical ranking."""

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.knowledge.knowledge_find import Corpus, find, load_corpus
from inferrsi.knowledge.searchspace_index import INDEX, LIBRARY, MATRIX, load_searchspace_coordinate

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / LIBRARY
GRAPH = "ascend-graph-mode"
QUERY = "graph mode"


@pytest.fixture(scope="module")
def corpus():
    return load_corpus(ROOT)


def test_find_filters_real_pairs_before_limit_without_changing_rank(corpus):
    baseline = find(QUERY, corpus, limit=20, explain=True)
    assert baseline["items"][0]["id"] == GRAPH
    assert "searchspace_filter" not in baseline

    diagnose = load_searchspace_coordinate(ROOT, "SSD", "Diagnose")
    graph = find(QUERY, corpus, searchspace_coordinate=diagnose, limit=1, explain=True)
    assert graph["items"] == [baseline["items"][0]]

    configure = load_searchspace_coordinate(ROOT, "SSD", "Configure")
    filtered = find(QUERY, corpus, searchspace_coordinate=configure, limit=1, explain=True)
    all_matches = find(QUERY, corpus, searchspace_coordinate=configure, limit=20, explain=True)
    expected_ids = [item["id"] for item in all_matches["items"]]
    assert expected_ids[0] == "ascend-model-adaptation"
    assert GRAPH not in expected_ids
    expected = [item for item in baseline["items"] if item["id"] in expected_ids]
    assert filtered["items"] == expected[:1]
    assert all_matches["items"][:len(expected)] == expected
    assert filtered["corpus_size"] == baseline["corpus_size"]
    assert filtered["matched"] == len(expected_ids) > len(filtered["items"])
    assert filtered["no_match"] is False
    assert filtered["searchspace_filter"] == {
        "resource": "SSD", "stage": "Configure",
        "source": {"matrix_path": MATRIX.as_posix(),
                   "matrix_sha256": hashlib.sha256((PROJECT / MATRIX).read_bytes()).hexdigest()},
    }


def test_find_filters_out_other_document_kinds_even_when_they_rank_first(corpus):
    query = "prefill decode graph"
    baseline = find(query, corpus, limit=20)
    assert baseline["items"][0]["kind"] == "record"
    coordinate = load_searchspace_coordinate(ROOT, "Accelerator", "Configure")
    filtered = find(query, corpus, searchspace_coordinate=coordinate, limit=1)
    assert filtered["items"] == [next(item for item in baseline["items"] if item["id"] == GRAPH)]


def test_find_rejects_same_named_skill_with_different_root_or_path(corpus, tmp_path):
    coordinate = load_searchspace_coordinate(ROOT, "Accelerator", "Configure")
    graph = next(doc for doc in corpus.documents if doc.identity == GRAPH)
    cases = (
        replace(graph, root=tmp_path, qualified=""),
        replace(graph, path=f"other/{graph.path}", qualified=""),
    )
    for document in cases:
        result = find(QUERY, Corpus([document]), searchspace_coordinate=coordinate)
        assert result["matched"] == 0 and result["no_match"] is True
        assert result["items"] == []


def test_cli_shows_coordinate_and_source_with_or_without_matches(capsys):
    command = ["find", QUERY, "--skill-root", str(ROOT), "--no-external", "--limit", "1"]
    assert main(command) == 0
    assert "SearchSpace" not in capsys.readouterr().out
    command += ["--searchspace-coordinate", "SSD", "Diagnose"]
    assert main(command) == 0
    text = capsys.readouterr().out
    assert "SSD × Diagnose" in text and MATRIX.as_posix() in text
    assert GRAPH in text

    assert main(command + ["--kinds", "record", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["no_match"] is True and result["matched"] == 0 and result["items"] == []
    assert result["searchspace_filter"]["source"]["matrix_path"] == MATRIX.as_posix()


@pytest.mark.parametrize("case, diagnostic", [
    ("missing", "SearchSpace index unavailable"),
    ("invalid", "Invalid SearchSpace index"),
    ("foreign", "Foreign SearchSpace index"),
    ("stale", "Stale SearchSpace index"),
])
def test_cli_reports_actionable_index_failures(tmp_path, capsys, case, diagnostic):
    index_path = tmp_path / INDEX
    index_path.parent.mkdir()
    if case != "missing":
        artifact = json.loads((PROJECT / INDEX).read_bytes())
        if case == "foreign":
            artifact["source"]["matrix_path"] = "other/searchspace-matrix.md"
        index_path.write_text("{" if case == "invalid" else json.dumps(artifact), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["find", QUERY, "--skill-root", str(tmp_path / LIBRARY),
              "--searchspace-coordinate", "SSD", "Configure", "--no-external"])
    assert exc.value.code == 2
    text = capsys.readouterr().err
    assert diagnostic in text
    assert "python tools/build_skill_coverage.py --searchspace-index" in text


@pytest.mark.parametrize("args, stage, diagnostic", [
    ([], "Configure", "explicit --skill-root"),
    (["--skill-root", "custom-library"], "Configure", "matching InferRSI checkout"),
    (["--skill-root", str(ROOT)], "Review", "STAGE"),
])
def test_cli_reports_an_invalid_request(capsys, args, stage, diagnostic):
    with pytest.raises(SystemExit) as exc:
        main(["find", QUERY, "--no-external", "--searchspace-coordinate", "SSD", stage, *args])
    assert exc.value.code == 2
    assert diagnostic in capsys.readouterr().err


def test_cli_reports_missing_pyyaml_without_requesting_regeneration(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.delenv("INFERRSI_LAUNCHER", raising=False)
    with pytest.raises(SystemExit) as exc:
        main(["find", QUERY, "--skill-root", str(ROOT), "--no-external",
              "--searchspace-coordinate", "SSD", "Configure"])
    assert exc.value.code == 2
    text = capsys.readouterr().err
    assert "pip install '<inferrsi-checkout>[skills]'" in text
    assert "build_skill_coverage.py" not in text
