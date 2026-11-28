"""Both session sources use the same verified external Read and citation projection."""

import json
from functools import partial

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.cli.arguments import parser
from inferrsi.apps.integrations.cannbot import project as channel
from inferrsi.apps.views.dashboard import dashboard_snapshot
from inferrsi.apps.views.round_citations import read_round_receipt
from tests.apps.test_optimization_session import diagnose, round_arguments
from tests.apps.test_optimization_session import task as task
from tests.apps.test_project_optimization import project as project
from tests.apps.test_project_optimization import start

LOCATOR = "ops/ascendc/apis/synthetic"
REVISION = "a" * 40
CARD_SHA256 = "b" * 64


def _forbid_provider(*args, **kwargs):
    pytest.fail("Offline or rejected operation accessed the provider")


def _snapshot(root):
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _start(source, project, task, tmp_path, capsys, monkeypatch):
    repo, _, _, root = project
    marker = repo / ".git"
    marker.mkdir()
    monkeypatch.chdir(repo)
    calls = []

    def read(locator, *, expected_revision, expected_sha256, page, root, **options):
        assert (locator, expected_revision, expected_sha256, root) == (
            LOCATOR, REVISION, CARD_SHA256, repo.resolve(),
        )
        calls.append(page)
        return {"state": "ok", "locator": locator, "revision": REVISION,
                "card_sha256": CARD_SHA256, "page": page, "pages": 2, "text": f"Page {page}"}

    monkeypatch.setattr(channel, "describe", lambda *a, **kw: {"state": "ok", "revision": REVISION})
    monkeypatch.setattr(channel, "search", lambda *a, **kw: {"revision": REVISION, "items": [
        {"locator": LOCATOR, "card_sha256": CARD_SHA256, "score": 7, "summary": "Synthetic"},
    ]})
    monkeypatch.setattr(channel, "read", read)
    if source == "project":
        start(project, capsys, extra=("--cannbot-platform", "a3"))
        (repo / "config.json").write_text('{"metric": 12}', encoding="utf-8")
        submit = ["campaign", "round", "--session", str(root), "--candidate", str(repo),
                  "--hypothesis", "Test external knowledge citation"]
    else:
        root = tmp_path / "benchmark"
        assert main(["benchmarks", "session", "start", task.name, "--session", str(root),
                     "--rounds", "3", "--max-minutes", "5", "--condition", "synthetic",
                     "--evaluation-timeout-seconds", "15", "--evaluation-args", "",
                     "--cannbot-platform", "a3"]) == 0
        capsys.readouterr()
        diagnose(root, capsys)
        submit = round_arguments(root, 2)
    return root, marker, submit, calls


@pytest.mark.parametrize("source", ["project", "benchmark"])
def test_external_read_and_round_receipt(source, project, task, tmp_path, capsys, monkeypatch):
    from inferrsi.apps.workflows import session_knowledge

    root, marker, submit, calls = _start(source, project, task, tmp_path, capsys, monkeypatch)
    monkeypatch.setattr(session_knowledge, "find_in_session", partial(
        session_knowledge.find_in_session, use_public_read=True,
    ))
    assert main(["find", "device memory", "--session", str(root)]) == 0
    found = json.loads(capsys.readouterr().out)
    hit, = found["external"]["items"]
    read_args = hit["read_args"]
    assert read_args == ["read", "--session", str(root), "--search-ref",
                         found["external"]["reference"]["path"], "--locator", LOCATOR]

    # Compose the selectors against the existing Read defaults. PR 5 attaches
    # these flags to the live parser at the same time as it changes Find argv.
    args = parser().parse_args([*read_args[:-2], "temporary-id"])
    args.id, args.locator, args.page = None, LOCATOR, None
    first = session_knowledge.read_in_session(args, None)
    args.page = 2
    second = session_knowledge.read_in_session(args, None)
    assert [first["receipt"]["page"], second["receipt"]["page"]] == [1, 2]

    before = _snapshot(root)
    for override, message in [
        ({"search_ref": found["reference"]["path"]}, "from the current round"),
        ({"search_ref": str(tmp_path / args.search_ref)}, "from the current round"),
        ({"locator": "missing"}, "from the recorded search"),
        ({"page": 0}, "positive integer"),
        ({"id": "local"}, "Use only"),
    ]:
        with pytest.raises(ValueError, match=message):
            session_knowledge.read_in_session(type(args)(**(vars(args) | override)), None)
    saved = marker.with_name("saved-git")
    marker.rename(saved)
    marker.mkdir()
    with pytest.raises(ValueError, match="not_enabled"):
        session_knowledge.read_in_session(args, None)
    marker.rmdir()
    saved.rename(marker)
    assert _snapshot(root) == before
    assert calls == [1, 2]

    assert main([*submit, "--knowledge-ref", second["reference"]["path"]]) == 0
    capsys.readouterr()
    for operation in ("describe", "search", "read"):
        monkeypatch.setattr(channel, operation, _forbid_provider)
    before = _snapshot(root)
    round_receipt = read_round_receipt(root, 1)
    dashboard = dashboard_snapshot(root)["data"]
    expected = [{"source": "cannbot-knowledge", "retrieval_round": 1, "ref": LOCATOR,
                 "revision": REVISION, "card_sha256": CARD_SHA256, "page": 2}]
    assert round_receipt["knowledge_uses"] == expected
    assert dashboard["candidates"][0]["knowledge_uses"] == expected
    assert _snapshot(root) == before
