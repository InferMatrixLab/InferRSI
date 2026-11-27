"""Exercise the real reader subprocess and MCP transport with an offline library stub."""

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import time
import venv
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.integrations import external_channels
from inferrsi.apps.integrations.cannbot import project as cannbot_project
from inferrsi.apps.integrations.mindie import navigation
from inferrsi.apps.integrations.mindie import project as mindie_project
from inferrsi.apps.integrations.mindie.context import MAX_BYTES
from inferrsi.knowledge import knowledge_find
from inferrsi.knowledge.knowledge_find import load_corpus
from inferrsi.knowledge.searchspace_index import LIBRARY


@pytest.fixture
def reader(tmp_path):
    # Install only a small library double into a disposable interpreter. The
    # production worker still runs with -I -B, including its metadata checks,
    # SQLite connection, read-only overrides and exception masking.
    runtime = tmp_path / "runtime"
    venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(runtime)
    python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    result = subprocess.run(
        [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        capture_output=True, text=True, check=True, timeout=20,
    )
    site = Path(result.stdout.strip())
    metadata = site / "mindie_knowledge-0.13.13.dist-info" / "METADATA"
    metadata.parent.mkdir()
    metadata.write_text("Name: mindie-knowledge\nVersion: 0.13.13\n", encoding="utf-8")
    files = {
        "__init__.py": "",
        "state_layout.py": "from pathlib import Path\ndef state_root(root, domain):\n"
                           "    return Path(root) / domain\n",
        "graded/__init__.py": "",
        "graded/index.py": '''
            class RoutingIndex:
                def __init__(self, units):
                    self.units = list(units)
                    self.generation = "fixture-generation"
        ''',
        "graded/repository.py": '''
            import os
            import sqlite3
            import subprocess
            import sys
            import time
            from pathlib import Path

            class GradedRepository:
                def __init__(self, store):
                    self.store = store

                def available(self):
                    return True

                def _read(self, item):
                    return item

                def _load(self):
                    return self._rebuild_index({
                        "units": ["fixture body"], "generation": "fixture-generation",
                    }, 0)

                def _rebuild_index(self, catalog, started):
                    raise AssertionError("A read must not persist a rebuilt index")

                def observe_delivered(self, index, payload, **kwargs):
                    raise AssertionError("A read must not update delivery counters")

                def query(self, query, *, navigation_only=False, **kwargs):
                    if query == "workspace-probe":
                        cwd = Path.cwd()
                        bench = os.environ.get("MINDIE_BENCH_WORKSPACE")
                        roots = ([Path(bench)] if bench else
                                 [cwd, cwd.parent / "workspace", cwd.parent / "work"])
                        ledger = next((root / "logs/experiment-ledger.jsonl" for root in roots
                                       if (root / "logs/experiment-ledger.jsonl").is_file()), None)
                        root = ledger.parent.parent if ledger else roots[0]
                        if (root / "logs").is_dir():
                            (root / "logs/knowledge_query_audit.jsonl").write_text(query)
                        if "include_archived" in kwargs:
                            assert bench is None and ledger is None and cwd.name == "reader"
                            return {"cards": [], "results": []}
                        return {"cwd": str(cwd), "bench_workspace": bench,
                                "ledger": ledger.read_text() if ledger else None}
                    if query == "value-error":
                        raise ValueError("FIXTURE_PRIVATE_PATH/catalog")
                    if query == "runtime-error":
                        raise RuntimeError("FIXTURE_PRIVATE_PATH/catalog")
                    # This checks the actual SQLite connection, not just its URI.
                    try:
                        self.store.db.execute("UPDATE sentinel SET value = 'changed'")
                    except sqlite3.OperationalError as exc:
                        if "readonly" not in str(exc):
                            raise
                    else:
                        raise AssertionError("The catalog connection permits writes")
                    index = self._load()
                    payload = {"results": [{"ref": "mindie://operators/units/fixture@1"}],
                               "navigation_only": navigation_only,
                               "value": self.store.db.execute(
                                   "SELECT value FROM sentinel").fetchone()["value"]}
                    self.observe_delivered(index, payload, delivery="query")
                    if query.startswith("navigation-") or query == "graph mode":
                        assert navigation_only
                        assert kwargs == {
                            "conditions": {}, "token_budget": 8000,
                            "include_unknown": False, "include_archived": False,
                            "limit": 20 if query == "navigation-limit" else 5,
                        }
                        if query == "navigation-timeout":
                            time.sleep(30)
                        if query in ("navigation-detached-output", "navigation-parent-exit"):
                            marker = Path(__file__).with_name("reader-child.pid")
                            program = (
                                "import os, sys, time; from pathlib import Path; "
                                "Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(15)"
                            )
                            holds_stdout = query == "navigation-parent-exit"
                            child = subprocess.Popen(
                                [sys._base_executable, "-I", "-c", program, str(marker)],
                                stdout=sys.stdout if holds_stdout else subprocess.DEVNULL,
                            )
                            while not marker.is_file() and child.poll() is None:
                                time.sleep(0.01)
                            assert marker.is_file()
                            if holds_stdout:
                                os._exit(0)
                        if query == "navigation-oversized":
                            sys.stdout.write("X" * (2 * 1024 * 1024 + 1))
                            sys.stdout.flush()
                            time.sleep(30)
                        if query == "navigation-malformed":
                            return {"cards": {"private": "FIXTURE_PRIVATE_PATH"}, "results": []}
                        if query in ("navigation-missing-status", "navigation-empty-status"):
                            item = {"ref": "mindie://operators/units/unit-1@1"}
                            if query == "navigation-empty-status":
                                item["match_status"] = ""
                            return {"cards": [item], "results": [item]}
                        if query == "navigation-native-cards":
                            item = {"ref": "mindie://operators/units/unit-z@3",
                                    "id": "unit-z", "revision": 3, "match_status": "matched"}
                            return {"cards": [item], "results": []}
                        if query == "navigation-foreign":
                            return {"cards": [{"ref": "mindie://foreign/units/unit-1@1",
                                               "match_status": "matched"}], "results": []}
                        if query == "navigation-denied":
                            return {
                                "status": "denied",
                                "cards": [{"ref": "mindie://operators/units/unit-1@1",
                                           "match_status": "matched"}],
                                "results": [],
                            }
                        if query == "navigation-limit":
                            return {"cards": [
                                {"ref": f"mindie://operators/units/unit-{i}@1",
                                 "match_status": "matched"} for i in range(23)
                            ], "results": []}
                        prefix = "mindie://operators/units/"
                        if query == "navigation-no-match":
                            return {"cards": [], "excluded_conditions": {}}
                        if query == "navigation-withheld-native":
                            return {
                                "cards": [],
                                "excluded_conditions": {
                                    "unknown": 3, "mismatch": 2, "archived_or_superseded": 1,
                                },
                                "unverified_cards": [{
                                    "ref": prefix + "unit-unknown@1",
                                    "match_status": "condition_unknown",
                                }],
                            }
                        if query == "navigation-invalid-counts":
                            return {"cards": [], "excluded_conditions": {"unknown": True}}
                        if query == "navigation-unmatched":
                            return {"cards": [
                                {"ref": prefix + "unit-unknown@1",
                                 "match_status": "condition_unknown"},
                                {"ref": prefix + "unit-mismatched@1", "match_status": "mismatched"},
                            ], "results": []}
                        return {
                            "results": [
                                {"ref": prefix + "unit-legacy@1", "match_status": "matched"},
                            ],
                            "foundation_cards": [
                                {"ref": prefix + "unit-foundation@1", "match_status": "matched"},
                            ],
                            "unverified_cards": [
                                {"ref": prefix + "unit-unverified@1",
                                 "match_status": "condition_unknown"},
                            ],
                            "cards": [
                                {"ref": prefix + "unit-z@3"},
                                {"ref": prefix + "unit-z@3", "match_status": "matched",
                                 "excerpt": "FIXTURE_PRIVATE_PATH", "body": "fixture body",
                                 "score": 42, "card_sha256": "fake", "revision": 3},
                                {"ref": prefix + "unit-z@3", "match_status": "matched"},
                                {"ref": prefix + "unit-empty@1", "match_status": ""},
                                {"ref": prefix + "unit-invalid@1", "match_status": ["matched"]},
                                {"ref": prefix + "unit-unknown@1",
                                 "match_status": "condition_unknown"},
                                {"ref": prefix + "unit-mismatched@1", "match_status": "mismatched"},
                                {"ref": "mindie://foreign/units/unit-1@1",
                                 "match_status": "matched"},
                                {"ref": prefix + "unit-unpinned", "match_status": "matched"},
                                {"ref": prefix + "unit-revision-conflict@3",
                                 "revision": 4, "match_status": "matched"},
                                {"ref": prefix + "unit-id-conflict@1",
                                 "id": "unit-other", "match_status": "matched"},
                                {"ref": prefix + "unit-a@2", "match_status": "matched"},
                            ],
                            "revision": "fixture-generation", "raw_response": "fixture body",
                        }
                    return payload

                def explain(self, refs, **kwargs):
                    index = self._load()
                    payload = {"units": [{"id": "fixture", "revision": 1,
                                          "content": index.units[0]}],
                               "requires": [], "unresolved": []}
                    self.observe_delivered(index, payload, delivery="explain")
                    return payload
        ''',
    }
    for name, source in files.items():
        path = site / "mindie_knowledge" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source), encoding="utf-8")
    root = tmp_path / "knowledge"
    (root / "operators").mkdir(parents=True)
    database = root / "operators" / "state-v4.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE sentinel(value TEXT)")
        db.execute("INSERT INTO sentinel VALUES ('original')")
    engine = tmp_path / "engine.json"
    engine.write_text(json.dumps({"root": str(root), "domain": "operators"}), encoding="utf-8")
    return {"python": str(python), "engine": str(engine), "domain": "operators"}, metadata


@pytest.mark.parametrize("extended_path", [
    False,
    pytest.param(True, marks=pytest.mark.skipif(os.name != "nt", reason="Windows extended path")),
])
def test_worker_query_and_explain_are_read_only(reader, extended_path):
    grant, _ = reader
    if extended_path:
        engine_path = Path(grant["engine"])
        engine = json.loads(engine_path.read_text(encoding="utf-8"))
        engine["root"] = "\\\\?\\" + engine["root"]
        engine_path.write_text(json.dumps(engine), encoding="utf-8")
    query = json.loads(mindie_project._worker(grant, "query", b'{"query":"fixture"}'))
    assert query == {"results": [{"ref": "mindie://operators/units/fixture@1"}],
                     "navigation_only": True, "value": "original"}
    explained = json.loads(mindie_project._worker(
        grant, "explain", json.dumps({"refs": [query["results"][0]["ref"]]}).encode(),
    ))
    assert explained["units"][0]["content"] == "fixture body"
    assert explained["requires"] == explained["unresolved"] == []


@pytest.mark.parametrize("ambient, sibling", [(False, "workspace"), (True, "work")])
def test_worker_ignores_ambient_workspaces(reader, tmp_path, monkeypatch, ambient, sibling):
    grant, _ = reader
    checkout, unrelated = tmp_path / "checkout", tmp_path / "unrelated"
    temp_root = tmp_path / "temporary"
    # A one-level temporary cwd would still discover this sibling ledger.
    protected = [checkout, unrelated, temp_root / sibling]
    for root in protected:
        (root / "logs").mkdir(parents=True)
        (root / "logs/experiment-ledger.jsonl").write_text('{"run_id":"fixture-private"}\n')
    monkeypatch.chdir(checkout)
    monkeypatch.setattr(mindie_project.tempfile, "tempdir", str(temp_root))
    if ambient:
        monkeypatch.setenv("MINDIE_BENCH_WORKSPACE", str(unrelated))
    else:
        monkeypatch.delenv("MINDIE_BENCH_WORKSPACE", raising=False)
    before = {path: path.read_bytes() for root in protected
              for path in root.rglob("*") if path.is_file()}
    result = json.loads(mindie_project._worker(grant, "query", b'{"query":"workspace-probe"}'))
    after = {path: path.read_bytes() for root in protected
             for path in root.rglob("*") if path.is_file()}
    assert after == before
    assert result["ledger"] is None and result["bench_workspace"] is None
    assert not Path(result["cwd"]).exists()  # The private working directory was cleaned up.
    assert {path.name for path in temp_root.iterdir()} == {sibling}


@pytest.mark.parametrize("mismatch, message", [
    ("version", "The project reader supports mindie-knowledge 0.13.13"),
    ("domain", "The installed MindIE domain differs from the project grant"),
])
def test_worker_rejects_version_or_domain_mismatch(reader, mismatch, message):
    grant, metadata = reader
    if mismatch == "version":
        metadata.write_text("Name: mindie-knowledge\nVersion: 0.13.12\n", encoding="utf-8")
    else:
        grant["domain"] = "other-domain"
    with pytest.raises(mindie_project.ReadFailure, match=message) as error:
        mindie_project._worker(grant, "query", b'{"query":"fixture"}')
    assert error.value.exit_code == 1


@pytest.mark.parametrize("query, message", [
    ("value-error", "MindIE rejected the read"),
    ("runtime-error", "The local MindIE catalog is unavailable"),
])
def test_worker_masks_private_library_errors(reader, query, message):
    grant, _ = reader
    with pytest.raises(mindie_project.ReadFailure) as error:
        mindie_project._worker(grant, "query", json.dumps({"query": query}).encode())
    assert str(error.value) == message
    assert error.value.exit_code == 1
    assert json.loads(error.value.response) == {"isError": True, "error": message}
    assert b"FIXTURE_PRIVATE_PATH" not in error.value.response


@pytest.fixture
def enabled_navigation(reader, tmp_path, monkeypatch):
    grant, metadata = reader
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    monkeypatch.chdir(checkout)
    adapter = tmp_path / "adapter.json"
    adapter.write_text(json.dumps({"python": grant["python"], "engine_config": grant["engine"]}),
                       encoding="utf-8")
    assert mindie_project.enable(adapter, "operators")["available"]
    corpus = knowledge_find.Corpus([knowledge_find.Document(
        "fixture-nav", "skill", "active", None, "Local navigation", "navigation",
        {"title": "Local navigation"},
    )])
    monkeypatch.setattr(knowledge_find, "load_corpus", lambda *args, **kwargs: corpus)
    return checkout, metadata, Path(grant["engine"])


_NAVIGATION = ["--backend", "ascend", "--external-source", "mindie-agent"]
_DEFAULT_FIND = ["--default-find", "--backend", "ascend"]


def _find_navigation(capsys, query, *options):
    assert main(["find", query, *_NAVIGATION, *options, "--json"]) == 0
    raw = capsys.readouterr().out
    assert "FIXTURE_PRIVATE_PATH" not in raw and "fixture body" not in raw
    return json.loads(raw)["external"][0]


def test_explicit_navigation_preserves_native_order_and_local_results(
    enabled_navigation, tmp_path, monkeypatch, capsys,
):
    checkout, _, _ = enabled_navigation
    real_exchange = navigation._exchange
    started = []
    processes = []
    request_path = mindie_project._grant_path(checkout).parent
    protected = [request_path, tmp_path / "knowledge"]
    before = {path: path.read_bytes() for root in protected
              for path in root.rglob("*") if path.is_file()}

    def observe(start, stop, arguments, request):
        def observed_start():
            process = start()
            processes.append(process)
            started.append(request)
            return process

        return real_exchange(observed_start, stop, arguments, request)

    monkeypatch.setattr(navigation, "_exchange", observe)
    monkeypatch.setattr(cannbot_project, "load_grant", lambda root: {"backend": "ascend"})
    monkeypatch.setattr(cannbot_project, "describe", lambda *args, **kwargs: {"state": "ok"})
    monkeypatch.setattr(cannbot_project, "search", lambda *args, **kwargs: {"items": [
        {"locator": "fixture", "score": 42, "title": "CANNBot fixture"},
    ]})
    command = ["find", "navigation-order", "--json"]
    assert main([*command, "--no-external"]) == 0
    local = json.loads(capsys.readouterr().out)
    assert main(command) == 0
    default = json.loads(capsys.readouterr().out)
    cannbot, = default["external"]
    assert cannbot["channel"] == "cannbot-knowledge" and cannbot["state"] == "ok"
    assert default["backend"] == "ascend" and cannbot["items"][0]["score"] == 42
    assert default["items"] == local["items"]
    assert local["items"]
    assert not started

    assert main([*command, *_NAVIGATION]) == 0
    raw = capsys.readouterr().out
    assert "fixture body" not in raw and "FIXTURE_PRIVATE_PATH" not in raw
    found = json.loads(raw)
    assert found["items"] == local["items"]
    entry, = found["external"]
    assert entry["state"] == "ok"
    assert not {"revision", "score_scale"} & entry.keys()
    assert entry["items"] == [
        {"locator": "mindie://operators/units/unit-z@3", "title": "unit-z", "status": "matched"},
        {"locator": "mindie://operators/units/unit-a@2", "title": "unit-a", "status": "matched"},
    ]
    assert len(started) == 2 and started[0] is started[1]
    assert all(process.wait(timeout=1) == 0 for process in processes)
    assert {path: path.read_bytes() for root in protected
            for path in root.rglob("*") if path.is_file()} == before

    assert main(["find", "navigation-order", *_NAVIGATION]) == 0
    rendered = capsys.readouterr().out
    assert "mindie://operators/units/unit-z@3" in rendered
    assert "open:" not in rendered and "fixture-generation" not in rendered
    assert _find_navigation(capsys, "navigation-limit", "--external-limit", "30")["count"] == 20


@pytest.mark.parametrize("query", ["navigation-missing-status", "navigation-empty-status"])
def test_navigation_rejects_unclassified_refs(enabled_navigation, capsys, query):
    entry = _find_navigation(capsys, query)
    assert entry["state"] == "rejected" and entry["count"] == 0
    assert entry["detail"] == "MindIE returned invalid navigation data."


def test_navigation_reads_pinned_native_cards(enabled_navigation, capsys):
    entry = _find_navigation(capsys, "navigation-native-cards")
    assert entry["state"] == "ok" and entry["count"] == 1
    assert entry["items"] == [
        {"locator": "mindie://operators/units/unit-z@3", "title": "unit-z", "status": "matched"},
    ]


def test_navigation_leaves_native_results_independent_of_local_coordinate(
    enabled_navigation, monkeypatch, capsys,
):
    monkeypatch.setattr(knowledge_find, "load_corpus", load_corpus)
    root = Path(__file__).resolve().parents[2] / LIBRARY
    command = [
        "find", "graph mode", *_NAVIGATION, "--skill-root", str(root),
        "--kinds", "skill", "--limit", "1", "--json",
    ]
    assert main(command) == 0
    baseline = json.loads(capsys.readouterr().out)
    assert baseline["items"][0]["id"] == "ascend-graph-mode"
    assert baseline["external"][0]["count"] == 2

    assert main([*command, "--searchspace-coordinate", "SSD", "Configure",
                 "--show-searchspace-coordinates", "--decision-cards"]) == 0
    filtered = json.loads(capsys.readouterr().out)
    hit, = filtered["items"]
    assert hit["id"] == "ascend-model-adaptation"
    assert ["SSD", "Configure"] in hit["searchspace_coordinates"]["coordinates"]
    assert filtered["searchspace_filter"]["stage"] == "Configure"
    assert filtered["searchspace_source"] == filtered["searchspace_filter"]["source"]
    before, = baseline["external"]
    after, = filtered["external"]
    assert after["channel"] == before["channel"] == "mindie-agent"
    assert after["state"] == before["state"] == "ok"
    assert after["items"] == before["items"]

    pin = hit["decision_card"]
    assert main(pin["read_args"]) == 0
    read = json.loads(capsys.readouterr().out)
    assert read["card"]["revision"] == read["revision"] == pin["revision"]
    assert read["card_bytes"] == pin["card_bytes"]


def test_navigation_excludes_explicit_native_nonmatches(enabled_navigation, capsys):
    entry = _find_navigation(capsys, "navigation-unmatched")
    assert entry["state"] == "ok" and entry["count"] == 0
    assert "items" not in entry
    assert entry["withheld"] == {"condition_unknown": 1, "mismatched": 1}


@pytest.fixture
def project_sources(enabled_navigation, tmp_path, monkeypatch, capsys):
    checkout, _, _ = enabled_navigation
    upstream = tmp_path / "cannbot"
    (upstream / ".git").mkdir(parents=True)
    (upstream / "knowledge").mkdir()
    script = upstream / ".agents/skills/knowledge-query/scripts/knowledge_query.py"
    script.parent.mkdir(parents=True)
    script.touch()
    cannbot_calls, mindie_calls = [], []
    real_start = navigation._start
    real_search = navigation.MindieNavigationChannel.search

    def cannbot_worker(grant, action, arguments, *, timeout, request=None):
        cannbot_calls.append((action, arguments, request))
        if action == "discover":
            return {"revision": "a" * 40, "cards": 1}
        if arguments["query"] == "navigation-cannbot-error":
            raise cannbot_project.ChannelFailure("fixture search failed")
        return {"revision": "a" * 40, "items": [{
            "locator": "ops/fixture", "title": "CANNBot fixture", "score": 1,
            "card_sha256": "a" * 64,
        }]}

    def start_mindie(argv, **kwargs):
        mindie_calls.append(argv[-1])
        return real_start(argv, **kwargs)

    def search_mindie(self, query, *, platform, limit, request):
        assert platform is None
        return real_search(self, query, platform=platform, limit=limit, request=request)

    def enable(*, mindie=False, cannbot=None):
        if mindie:
            assert main(["mindie", "enable", "--adapter-config", str(tmp_path / "adapter.json"),
                         *_DEFAULT_FIND]) == 0
            assert json.loads(capsys.readouterr().out)["default_find_backend"] == "ascend"
        if cannbot is not None:
            assert main(["cannbot", "enable", "--checkout", str(upstream), "--python",
                         sys.executable, "--backend", cannbot, "--platform", "a2"]) == 0
            capsys.readouterr()
            cannbot_calls.clear()

    monkeypatch.setattr(cannbot_project, "_run", cannbot_worker)
    monkeypatch.setattr(navigation, "_start", start_mindie)
    monkeypatch.setattr(navigation.MindieNavigationChannel, "search", search_mindie)
    return checkout, enable, cannbot_calls, mindie_calls


def _find_sources(capsys, query, *args):
    assert main(["find", query, "--json", *args]) == 0
    found = json.loads(capsys.readouterr().out)
    return found, {entry["channel"]: entry for entry in found.get("external", [])}


@pytest.mark.parametrize("mindie,cannbot", [(True, True), (True, False), (False, True)])
def test_ordinary_find_uses_independently_approved_sources(
    project_sources, capsys, mindie, cannbot,
):
    _, enable, cannbot_calls, mindie_calls = project_sources
    enable(mindie=mindie, cannbot="ascend" if cannbot else None)
    query = "navigation-order"
    local, entries = _find_sources(capsys, query, "--no-external")
    assert not entries and not mindie_calls and not cannbot_calls

    found, entries = _find_sources(capsys, query)
    assert found["items"] == local["items"] and local["items"]
    assert found["backend"] == "ascend"
    if cannbot:
        assert entries["cannbot-knowledge"]["items"][0]["locator"] == "ops/fixture"
        assert [(action, arguments) for action, arguments, _ in cannbot_calls] == [
            ("discover", {}), ("search", {"query": query, "platform": "a2", "limit": 100}),
        ]
        assert cannbot_calls[0][2] is cannbot_calls[1][2]
    else:
        assert entries["cannbot-knowledge"]["state"] == "not_enabled"
        assert not cannbot_calls
    if mindie:
        entry = entries["mindie-agent"]
        assert entry["state"] == "ok"
        assert [hit["locator"] for hit in entry["items"]] == [
            "mindie://operators/units/unit-z@3", "mindie://operators/units/unit-a@2",
        ]
        assert mindie_calls == ["describe", "query"]
    else:
        assert "mindie-agent" not in entries and not mindie_calls


def test_ordinary_find_requires_backend_when_grants_conflict(project_sources, capsys):
    _, enable, cannbot_calls, mindie_calls = project_sources
    enable(mindie=True, cannbot="cuda")
    _, entries = _find_sources(capsys, "navigation-order")
    assert set(entries) == {"cannbot-knowledge", "mindie-agent"}
    assert all(entry["state"] == "backend_unknown" for entry in entries.values())
    assert all("conflicting task backends" in entry["detail"] for entry in entries.values())
    _, entries = _find_sources(capsys, "navigation-order", "--backend", "cuda")
    assert not entries and not mindie_calls and not cannbot_calls

    _, entries = _find_sources(
        capsys, "navigation-order", "--backend", "ascend", "--platform", "a3",
    )
    assert all(entry["state"] == "ok" for entry in entries.values())
    assert mindie_calls == ["describe", "query"]
    assert cannbot_calls[-1][1]["platform"] == "a3"


def test_default_find_grant_revocation_and_managed_scope(project_sources, capsys):
    checkout, enable, cannbot_calls, mindie_calls = project_sources
    enable(mindie=True, cannbot="ascend")
    assert main(["mindie", "describe"]) == 0
    assert json.loads(capsys.readouterr().out)["default_find_backend"] == "ascend"
    settings = {"channel": "cannbot-knowledge", "backend": "ascend", "platform": "a2"}
    provider = external_channels.round_provider({
        "external_knowledge": settings,
        "external_knowledge_project": external_channels.freeze_project(checkout),
    })
    assert provider.search("fixture", settings=settings, limit=1, timeout=5)["state"] == "ok"
    assert [action for action, _, _ in cannbot_calls] == ["discover", "search"]
    assert not mindie_calls

    assert main(["mindie", "disable"]) == 0
    capsys.readouterr()
    _, entries = _find_sources(capsys, "navigation-order")
    assert entries["cannbot-knowledge"]["state"] == "ok"
    assert "mindie-agent" not in entries and not mindie_calls


def test_default_find_requires_explicit_opt_in_and_backend(project_sources, tmp_path, capsys):
    _, enable, cannbot_calls, mindie_calls = project_sources
    command = ["mindie", "enable", "--adapter-config", str(tmp_path / "adapter.json")]
    for args, message in (
        (["--default-find"], "--default-find requires --backend ascend"),
        (["--backend", "ascend"], "--backend requires --default-find"),
    ):
        with pytest.raises(SystemExit) as error:
            main([*command, *args])
        assert error.value.code == 2
        assert message in capsys.readouterr().err

    enable(mindie=True, cannbot="ascend")
    _, entries = _find_sources(capsys, "navigation-order", *_NAVIGATION)
    assert set(entries) == {"mindie-agent"} and not cannbot_calls

    assert main(command) == 0
    assert "default_find_backend" not in json.loads(capsys.readouterr().out)
    mindie_calls.clear()
    _, entries = _find_sources(capsys, "navigation-order")
    assert set(entries) == {"cannbot-knowledge"} and not mindie_calls


@pytest.mark.parametrize("query,failed,state", [
    ("navigation-malformed", "mindie-agent", "rejected"),
    ("navigation-timeout", "mindie-agent", "timeout"),
    ("navigation-cannbot-error", "cannbot-knowledge", "rejected"),
])
def test_ordinary_find_preserves_completed_sources(project_sources, capsys, query, failed, state):
    _, enable, _, _ = project_sources
    enable(mindie=True, cannbot="ascend")
    local, _ = _find_sources(capsys, query, "--no-external")
    found, entries = _find_sources(capsys, query, "--external-timeout", "2")
    assert found["items"] == local["items"] and local["items"]
    assert entries.pop(failed)["state"] == state
    completed, = entries.values()
    assert completed["state"] == "ok" and completed["items"]


def test_ordinary_find_exposes_native_condition_counts(project_sources, capsys):
    _, enable, _, _ = project_sources
    enable(mindie=True)
    for query, expected in (
        ("navigation-no-match", {"condition_unknown": 0, "mismatched": 0}),
        ("navigation-withheld-native", {"condition_unknown": 3, "mismatched": 2}),
    ):
        _, entries = _find_sources(capsys, query)
        entry = entries["mindie-agent"]
        assert entry["state"] == "ok" and entry["count"] == 0
        assert entry["withheld"] == expected
        assert "unit-unknown" not in json.dumps(entry)
    _, entries = _find_sources(capsys, "navigation-invalid-counts")
    assert entries["mindie-agent"]["state"] == "rejected"
    assert main(["find", "navigation-withheld-native"]) == 0
    assert "withheld by conditions: 3 condition_unknown, 2 mismatched" in capsys.readouterr().out


def test_navigation_requires_explicit_ascend_backend(enabled_navigation, monkeypatch, capsys):
    def never(*args):
        pytest.fail("MindIE must be gated before starting its worker")

    monkeypatch.setattr(navigation, "_exchange", never)
    selected = ["find", "navigation-order", "--external-source", "mindie-agent"]
    for arguments, message in (
        ([], "requires --backend ascend"),
        (["--backend", "cuda"], "requires --backend ascend"),
        (["--backend", "ascend", "--platform", "a3"], "--platform applies to CANNBot"),
    ):
        with pytest.raises(SystemExit) as error:
            main([*selected, *arguments])
        assert error.value.code == 2
        assert message in capsys.readouterr().err
    assert main([*selected, "--no-external", "--json"]) == 0
    assert "external" not in json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(
    "change", ["revoke", "revoke-at-launch", "replace-checkout", "change-grant"],
)
def test_navigation_rejects_grant_changes_before_query_launch(
    enabled_navigation, monkeypatch, capsys, change,
):
    checkout, _, _ = enabled_navigation
    real_discover = navigation.MindieNavigationChannel.describe
    real_exchange = navigation._exchange
    real_start = navigation._start
    actions = []

    def observe_start(argv, **kwargs):
        actions.append(argv[-1])
        return real_start(argv, **kwargs)

    def discover_and_change(channel, *, request):
        status = real_discover(channel, request=request)
        assert status.state == "ok"
        if change == "revoke":
            mindie_project.disable()
        elif change == "replace-checkout":
            (checkout / ".git").rename(checkout / "replaced-git")
            (checkout / ".git").mkdir()
        elif change == "change-grant":
            payload = mindie_project._load_grant(checkout)
            mindie_project._grant_path(checkout).write_bytes(
                mindie_project._json({**payload, "domain": "different"})
            )
        return status

    def exchange_and_change(start, stop, arguments, request):
        if change == "revoke-at-launch" and json.loads(arguments).get("query"):
            mindie_project.disable()
        return real_exchange(start, stop, arguments, request)

    monkeypatch.setattr(navigation, "_start", observe_start)
    monkeypatch.setattr(navigation.MindieNavigationChannel, "describe", discover_and_change)
    monkeypatch.setattr(navigation, "_exchange", exchange_and_change)
    assert _find_navigation(capsys, "navigation-order")["state"] == "not_enabled"
    assert actions == ["describe"]


def test_navigation_uses_captured_checkout_after_cwd_changes(
    enabled_navigation, tmp_path, monkeypatch, capsys,
):
    unrelated = tmp_path / "unapproved-checkout"
    (unrelated / ".git").mkdir(parents=True)
    real_discover = navigation.MindieNavigationChannel.describe

    def discover_and_change_cwd(channel, *, request):
        status = real_discover(channel, request=request)
        monkeypatch.chdir(unrelated)
        return status

    monkeypatch.setattr(navigation.MindieNavigationChannel, "describe", discover_and_change_cwd)
    result = _find_navigation(capsys, "navigation-order")
    assert result["state"] == "ok" and result["count"] == 2


@pytest.mark.parametrize("failure, state, action", [
    ("no-grant", "not_enabled", None),
    ("no-dependency", "unreachable", "describe"),
    ("wrong-version", "version_mismatch", "describe"),
    ("wrong-domain", "rejected", "describe"),
])
def test_navigation_unavailable_without_approved_catalog(
    enabled_navigation, monkeypatch, capsys, failure, state, action,
):
    _, metadata, engine = enabled_navigation
    if failure == "no-grant":
        mindie_project.disable()
    elif failure == "no-dependency":
        metadata.unlink()
        metadata.parent.rmdir()
    elif failure == "wrong-version":
        metadata.write_text("Name: mindie-knowledge\nVersion: 0.13.12\n", encoding="utf-8")
    else:
        source = json.loads(engine.read_text(encoding="utf-8"))
        engine.write_text(json.dumps({**source, "domain": "foreign"}), encoding="utf-8")
    real_start = navigation._start
    actions = []

    def observe_start(argv, **kwargs):
        actions.append(argv[-1])
        return real_start(argv, **kwargs)

    monkeypatch.setattr(navigation, "_start", observe_start)
    assert _find_navigation(capsys, "navigation-order")["state"] == state
    assert actions == ([action] if action else [])


@pytest.mark.parametrize("query, state", [
    ("navigation-malformed", "rejected"),
    ("navigation-foreign", "rejected"),
    ("navigation-denied", "unreachable"),
    ("navigation-oversized", "rejected"),
    ("navigation-timeout", "timeout"),
])
def test_navigation_bounds_output_and_reaps_worker(
    enabled_navigation, monkeypatch, capsys, query, state,
):
    real_start = navigation._start
    children = []
    workdirs = []

    def observe_start(argv, **kwargs):
        process = real_start(argv, **kwargs)
        children.append((argv[-1], process))
        workdirs.append(kwargs["cwd"])
        return process

    monkeypatch.setattr(navigation, "_start", observe_start)
    started = time.monotonic()
    timeout = "2" if state == "timeout" else "8"
    entry = _find_navigation(capsys, query, "--external-timeout", timeout)
    assert entry["state"] == state and entry["count"] == 0
    if query == "navigation-oversized":
        assert "output exceeded 2 MiB" in entry["detail"]
    assert time.monotonic() - started < 10
    assert [action for action, _ in children] == ["describe", "query"]
    assert all(process.wait(timeout=1) is not None for _, process in children)
    assert all(not directory.exists() for directory in workdirs)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object integration")
@pytest.mark.parametrize("query, state", [
    ("navigation-detached-output", "ok"),
    ("navigation-parent-exit", "timeout"),
])
def test_windows_navigation_reaps_descendant_even_after_launcher_exits(
    enabled_navigation, monkeypatch, capsys, query, state,
):
    import ctypes
    from ctypes import wintypes as win

    _, metadata, _ = enabled_navigation
    marker = metadata.parent.parent / "mindie_knowledge/graded/reader-child.pid"
    real_stop = navigation._stop
    exited_before_cleanup = []

    def observe_stop(process):
        if marker.exists():
            try:
                process.wait(timeout=0)
            except subprocess.TimeoutExpired:
                exited_before_cleanup.append(False)
            else:
                exited_before_cleanup.append(True)
        return real_stop(process)

    monkeypatch.setattr(navigation, "_stop", observe_stop)
    started = time.monotonic()
    entry = _find_navigation(capsys, query, "--external-timeout", "3")
    assert entry["state"] == state
    assert time.monotonic() - started < 5
    assert exited_before_cleanup == [True]
    pid = int(marker.read_text())
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (win.DWORD, win.BOOL, win.DWORD)
    kernel.OpenProcess.restype = win.HANDLE
    kernel.WaitForSingleObject.argtypes = (win.HANDLE, win.DWORD)
    kernel.WaitForSingleObject.restype = win.DWORD
    kernel.CloseHandle.argtypes = (win.HANDLE,)
    handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
    if handle:
        try:
            assert kernel.WaitForSingleObject(handle, 0) == 0
        finally:
            kernel.CloseHandle(handle)
    else:
        assert ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: PID already gone


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object integration")
@pytest.mark.parametrize("failing_api, query", [
    ("_query_job", "navigation-order"),
    ("_terminate_job", "navigation-detached-output"),
])
def test_windows_navigation_rejects_unconfirmed_job_cleanup(
    enabled_navigation, monkeypatch, capsys, failing_api, query,
):
    from inferrsi.apps.integrations.mindie import _windows_worker

    monkeypatch.setattr(_windows_worker, failing_api, lambda *args: False)
    entry = _find_navigation(capsys, query, "--external-timeout", "3")
    assert entry["state"] == "rejected" and entry["count"] == 0
    assert entry["detail"] == "channel resource cleanup failed"


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object integration")
def test_windows_navigation_refuses_uncontained_worker(enabled_navigation, monkeypatch, capsys):
    from inferrsi.apps.integrations.mindie import _windows_worker

    update = _windows_worker._update_attributes

    def reject_job_attribute(attributes, flags, attribute, *args):
        if attribute == _windows_worker._JOB_LIST:
            return False
        return update(attributes, flags, attribute, *args)

    def unexpected_launch(*args):
        pytest.fail("MindIE must not start without its Job Object")

    monkeypatch.setattr(_windows_worker, "_update_attributes", reject_job_attribute)
    monkeypatch.setattr(_windows_worker, "_create_process", unexpected_launch)
    assert _find_navigation(capsys, "navigation-order")["state"] == "unreachable"


def test_navigation_uses_isolated_working_directory(
    enabled_navigation, tmp_path, monkeypatch, capsys,
):
    checkout, _, _ = enabled_navigation
    unrelated, temporary = tmp_path / "unrelated", tmp_path / "temporary"
    roots = [checkout, unrelated, temporary / "workspace", temporary / "work"]
    for root in roots:
        (root / "logs").mkdir(parents=True)
        (root / "logs/experiment-ledger.jsonl").write_text("fixture ledger\n")
    monkeypatch.setenv("MINDIE_BENCH_WORKSPACE", str(unrelated))
    monkeypatch.setattr(mindie_project.tempfile, "tempdir", str(temporary))
    result = _find_navigation(capsys, "workspace-probe")
    assert result["state"] == "ok" and result["count"] == 0
    assert all(list((root / "logs").iterdir()) == [root / "logs/experiment-ledger.jsonl"]
               for root in roots)
    assert {path.name for path in temporary.iterdir()} == {"workspace", "work"}


@pytest.mark.parametrize("oversized_line", ["newline", "eof", "boundary-newline"])
def test_mcp_stdio_round_trip(reader, tmp_path, monkeypatch, oversized_line):
    grant, _ = reader
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(Path, "home", lambda: home)
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    monkeypatch.chdir(checkout)
    adapter = tmp_path / "adapter.json"
    adapter.write_text(json.dumps({"python": grant["python"], "engine_config": grant["engine"]}),
                       encoding="utf-8")
    assert mindie_project.enable(adapter, "operators")["available"]
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-11-25"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "knowledge_query", "arguments": {"query": "fixture"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "knowledge_explain", "arguments": {
                "refs": ["mindie://operators/units/fixture@1"]}}},
    ]
    wire = "".join(json.dumps(message) + "\n" for message in requests)
    wire += '{bad json\n{"jsonrpc":"2.0","id":5,"method":42}\n[]\n'
    wire += '{"jsonrpc":"2.0","id":6,"method":"ping"}\n'
    discarded = json.dumps({"jsonrpc": "2.0", "id": "discarded", "method": "tools/call",
                            "params": {"name": "knowledge_query",
                                       "arguments": {"query": "fixture"}}})
    if oversized_line == "boundary-newline":
        # The rejected first chunk already includes its terminating newline.
        wire += discarded.ljust(MAX_BYTES) + "\n"
    else:
        # The valid JSON tail belongs to one oversized physical line, even
        # when it takes multiple bounded reads to reach the tail or EOF.
        wire += " " * (2 * (MAX_BYTES + 1)) + discarded
        if oversized_line == "newline":
            wire += "\n"
    if oversized_line != "eof":
        wire += '{"jsonrpc":"2.0","id":7,"method":"ping"}\n'
    source = str(Path(__file__).resolve().parents[2] / "src")
    process = subprocess.run(
        [sys.executable, "-I", "-B", "-c", f"import sys; sys.path.insert(0, {source!r}); "
         "from inferrsi.apps.cli import main; raise SystemExit(main(['mindie', 'serve']))"],
        input=wire, text=True, capture_output=True, timeout=30, check=True,
    )
    assert process.stderr == ""
    replies = [json.loads(line) for line in process.stdout.splitlines()]
    # The initialized notification produces no response, and the server can
    # still answer a ping after both JSON syntax and request-shape errors.
    expected_ids = [1, 2, 3, 4, None, 5, None, 6, None]
    if oversized_line != "eof":
        expected_ids.append(7)
    assert [reply["id"] for reply in replies] == expected_ids
    assert all(reply["jsonrpc"] == "2.0" for reply in replies)
    assert replies[0]["result"]["protocolVersion"] == "2025-11-25"
    assert {tool["name"] for tool in replies[1]["result"]["tools"]} == {
        "knowledge_query", "knowledge_explain",
    }
    for reply in replies[2:4]:
        result = reply["result"]
        assert result["isError"] is False
        response = result["structuredContent"]
        receipt = Path(response["receipt_directory"])
        assert json.loads((receipt / "receipt.json").read_text())["exit_code"] == 0
        assert json.loads((receipt / "result.json").read_text()) == response["result"]
    assert replies[3]["result"]["structuredContent"]["result"]["units"][0]["content"] == (
        "fixture body"
    )
    assert [reply["error"]["code"] for reply in replies[4:7]] == [-32700, -32600, -32600]
    assert replies[7]["result"] == {}
    assert replies[8]["error"]["code"] == -32600
    if oversized_line != "eof":
        assert replies[9]["result"] == {}
    # Only the two intended reads may create receipts: the discarded tail
    # must not dispatch another knowledge call.
    assert len(list(receipt.parent.iterdir())) == 2
