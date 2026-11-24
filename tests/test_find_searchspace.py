"""Find applies a verified SearchSpace pair after lexical ranking."""

import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.knowledge import knowledge_find
from inferrsi.knowledge.knowledge_find import Corpus, find, load_corpus
from inferrsi.knowledge.searchspace_index import (
    CATALOG,
    INDEX,
    LIBRARY,
    MATRIX,
    StaleSearchspaceIndex,
    load_searchspace_coordinate,
)
from tools.build_skill_coverage import render_coordinate_index

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / LIBRARY
GRAPH = "ascend-graph-mode"
QUERY = "graph mode"


@pytest.fixture(scope="module")
def corpus():
    coordinate = load_searchspace_coordinate(ROOT, "SSD", "Diagnose")
    return load_corpus(ROOT, searchspace_index=coordinate.index)


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
    source = json.loads((PROJECT / INDEX).read_bytes())["source"]
    assert filtered["searchspace_filter"] == {
        "resource": "SSD", "stage": "Configure",
        "source": {
            key: source[key]
            for key in ("matrix_path", "matrix_sha256", "catalog_sha256", "metadata_sha256")
        },
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
        foreign = Corpus([document], _searchspace_index=coordinate.index)
        result = find(QUERY, foreign, searchspace_coordinate=coordinate)
        assert result["matched"] == 0 and result["no_match"] is True
        assert result["items"] == []


@pytest.fixture
def checkout(tmp_path):
    matrix = tmp_path / MATRIX
    matrix.parent.mkdir()
    shutil.copyfile(PROJECT / MATRIX, matrix)
    registry = json.loads((PROJECT / CATALOG).read_bytes())
    graph = registry["skills"][GRAPH]
    registry["skills"] = {GRAPH: graph}
    relative = LIBRARY / graph["path"] / "SKILL.md"
    entrypoint = tmp_path / relative
    entrypoint.parent.mkdir(parents=True)
    shutil.copyfile(PROJECT / relative, entrypoint)
    (tmp_path / CATALOG).write_text(json.dumps(registry), encoding="utf-8")
    (tmp_path / INDEX).write_text(render_coordinate_index(tmp_path), encoding="utf-8", newline="\n")
    return tmp_path, entrypoint


@pytest.mark.parametrize("sidecar", [False, True])
def test_cli_reopens_pinned_coordinate_hit(checkout, capsys, sidecar):
    root, entrypoint = checkout
    scope = {"scope": "quartz"}
    metadata = json.dumps({"applicability": scope})
    header = f"---\nname: {GRAPH}\ndescription: Diagnose graph mode.\n"
    if sidecar:
        entrypoint.with_name("metadata.json").write_text(metadata, encoding="utf-8")
    else:
        header += f"metadata:\n  inferrsi: |\n    {metadata}\n"
    entrypoint.write_text(header + "---\nProcedure.\n", encoding="utf-8", newline="\r\n")
    (root / INDEX).write_text(render_coordinate_index(root), encoding="utf-8", newline="\n")

    # Only the declaration matches. The registered Ascend backend downweights this CUDA query.
    args = ["find", "cuda quartz", "--skill-root", str(root / LIBRARY), "--kinds", "skill",
            "--no-external", "--json"]
    assert main(args) == 0
    baseline, = json.loads(capsys.readouterr().out)["items"]
    assert main([*args, "--searchspace-coordinate", "SSD", "Diagnose", "--decision-cards"]) == 0
    filtered = json.loads(capsys.readouterr().out)
    hit, = filtered["items"]
    pin = hit.pop("decision_card")
    assert hit == baseline and hit["id"] == GRAPH
    assert filtered["searchspace_filter"]["stage"] == "Diagnose"
    assert main(pin["read_args"]) == 0
    read = json.loads(capsys.readouterr().out)
    assert read["card"]["declared"]["applicability"] == scope
    assert read["revision"] == pin["revision"] and read["card_bytes"] == pin["card_bytes"]


def test_cli_rejects_an_exclusion_written_after_index_load(checkout, monkeypatch, capsys):
    root, entrypoint = checkout
    original_load = load_corpus

    def load_after_exclusion(*args, **kwargs):
        before = entrypoint.read_bytes()
        exclusion = b'      "searchspace_not_applicable": "New exclusion during Find",\n'
        entrypoint.write_bytes(before.replace(b"    {\n", b"    {\n" + exclusion, 1))
        return original_load(*args, **kwargs)

    monkeypatch.setattr(knowledge_find, "load_corpus", load_after_exclusion)
    with pytest.raises(SystemExit) as exc:
        main(["find", QUERY, "--skill-root", str(root / LIBRARY), "--no-external",
              "--kinds", "skill", "--searchspace-coordinate", "SSD", "Diagnose", "--json"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "SearchSpace sources changed during Find" in captured.err
    assert "python tools/build_skill_coverage.py --searchspace-index" in captured.err


@pytest.mark.parametrize("path", (MATRIX, CATALOG))
def test_find_rechecks_matrix_and_registry_after_ranking(checkout, monkeypatch, path):
    root, _ = checkout
    coordinate = load_searchspace_coordinate(root / LIBRARY, "SSD", "Diagnose")
    corpus = load_corpus(kinds=("skill",), searchspace_index=coordinate.index)
    original_rank = knowledge_find.rank

    def rank_then_edit(*args):
        result = original_rank(*args)
        source = root / path
        source.write_bytes(source.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(knowledge_find, "rank", rank_then_edit)
    with pytest.raises(StaleSearchspaceIndex, match="changed during Find"):
        find(QUERY, corpus, searchspace_coordinate=coordinate)


def test_find_uses_bound_corpus_and_ignores_unrelated_file_change(checkout):
    root, entrypoint = checkout
    coordinate = load_searchspace_coordinate(root / LIBRARY, "SSD", "Diagnose")
    bound = load_corpus(kinds=("skill",), searchspace_index=coordinate.index)
    unrelated = root / "docs" / "reference-matrix.md"
    unrelated.write_text("Unrelated matrix content", encoding="utf-8")
    assert find(QUERY, bound, searchspace_coordinate=coordinate)["items"][0]["id"] == GRAPH
    plain = load_corpus(root / LIBRARY, kinds=("skill",))
    assert find(QUERY, bound) == find(QUERY, plain)

    entrypoint.write_bytes(entrypoint.read_bytes() + b"\nA new ranking body.\n")
    (root / INDEX).write_text(render_coordinate_index(root), encoding="utf-8", newline="\n")
    current_coordinate = load_searchspace_coordinate(root / LIBRARY, "SSD", "Diagnose")
    current = load_corpus(kinds=("skill",), searchspace_index=current_coordinate.index)
    for left, right in ((bound, current_coordinate), (current, coordinate)):
        with pytest.raises(ValueError, match="same verified source"):
            find(QUERY, left, searchspace_coordinate=right)


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
