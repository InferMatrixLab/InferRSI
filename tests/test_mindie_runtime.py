"""Exercise the real reader subprocess and MCP transport with an offline library stub."""

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import venv
from pathlib import Path

import pytest

from inferrsi import mindie_project
from inferrsi.mindie_context import MAX_BYTES


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


def test_worker_query_and_explain_are_read_only(reader):
    grant, _ = reader
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
    source = str(Path(mindie_project.__file__).resolve().parents[1])
    process = subprocess.run(
        [sys.executable, "-I", "-B", "-c", f"import sys; sys.path.insert(0, {source!r}); "
         "from inferrsi.cli import main; raise SystemExit(main(['mindie', 'serve']))"],
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
