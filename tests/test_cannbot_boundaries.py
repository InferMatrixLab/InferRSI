"""Synthetic upstream processes exercise the actual CLI and raw-byte boundary."""

import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

from inferrsi.apps.cannbot import project
from inferrsi.apps.cannbot.read_worker import _MAX_UPSTREAM

REPO = Path(__file__).resolve().parents[1]
REVISION = "ab" * 20


def cli(*args, cwd=None, timeout=12):
    return subprocess.run(
        [sys.executable, "-m", "inferrsi", *args],
        cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False,
    )


def discovery():
    return {"schema_version": "knowledge-discovery.v1", "cards": 1,
            "index": {"built_repository_state": {"commit": REVISION}}}


def commit_revision(source):
    subprocess.run(
        ["git", "-C", str(source), "-c", "user.name=Synthetic Fixture",
         "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
         "commit", "--allow-empty", "-qm", "synthetic revision"], check=True,
    )
    return subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True,
    ).strip()


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("PYTHONPATH", str(REPO / "src"))
    root = tmp_path / "project"
    root.mkdir()
    (root / ".git").mkdir()
    monkeypatch.chdir(root)
    source = tmp_path / "upstream"
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    monkeypatch.setattr(sys.modules[__name__], "REVISION", commit_revision(source))
    (source / "knowledge/ops").mkdir(parents=True)
    card = source / "knowledge/ops/card.md"
    card.write_text("\n".join(f"synthetic line {i}" for i in range(401)))
    script = source / ".agents/skills/knowledge-query/scripts/knowledge_query.py"
    script.parent.mkdir(parents=True)
    native = script.parent / "retrieval"
    native.mkdir()
    (native / "__init__.py").touch()
    (native / "index.py").write_text(
        "import hashlib\n"
        "def load_contract(root):\n"
        "    return None, lambda text: ({}, text)\n"
        "def card_fingerprint(metadata, body):\n"
        "    return hashlib.sha256(body.encode()).hexdigest()\n"
    )
    script.write_text(f"import json\nprint(json.dumps({discovery()!r}))\n")
    project.enable(upstream=source, python=Path(sys.executable), platforms=["a2"])
    return source, script, card


def search_payload(card):
    return {"schema_version": "knowledge-search.v5", "index": discovery()["index"],
            "results": [{"path": "ops/card", "title": "synthetic", "score": 1.0,
                         "platforms": ["a2"],
                         "card_sha256": hashlib.sha256(card.read_bytes()).hexdigest()}]}


def set_source(script, raw):
    script.write_text(f"import sys\nsys.stdout.buffer.write({raw!r})\n")


@pytest.mark.parametrize("raw", [
    b'{"cards": 1, "cards": 2}', b'{"x": NaN}', b'{"x": Infinity}',
    b'{"x": -Infinity}', b'{"x": 1e999}', b'[]', b'{"x": {"y": 1, "y": 2}}',
    b'\xff', b'{"schema_version": "knowledge-discovery.v1", "cards": 1, "index": []}',
])
def test_rejects_original_source_bytes(upstream, raw):
    _, script, _ = upstream
    set_source(script, raw)
    assert project.describe()["state"] == "rejected"


@pytest.mark.parametrize("mutation", [
    {"results": {}}, {"results": [42]},
    {"results": [{"path": "ops/card", "score": "bad"}]},
    {"index": []},
])
def test_search_shape_is_rejected(upstream, mutation):
    _, script, card = upstream
    set_source(script, json.dumps({**search_payload(card), **mutation}).encode())
    with pytest.raises(project.ChannelFailure) as error:
        project.search("query")
    assert error.value.state == "rejected"


@pytest.mark.parametrize("args", [
    ("cannbot", "search", "tiling", "--limit", "1"),
    ("find", "tiling", "--external-limit", "1", "--json"),
])
def test_source_cap_precedes_card_reads(upstream, args):
    _, script, card = upstream
    payload = search_payload(card)
    first = payload["results"][0]
    # These extra rows are well-shaped, but their files do not exist. Reading
    # either of them would reject the query instead of returning the first hit.
    payload["results"].extend([
        {**first, "path": "ops/not-requested-a"},
        {**first, "path": "ops/not-requested-b"},
    ])
    script.write_text(
        "import json, sys\n"
        f"print(json.dumps({discovery()!r} if sys.argv[1] == 'discover' "
        f"else {payload!r}))\n"
    )
    result = cli(*args)
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    if args[0] == "find":
        response = response["external"][0]
    assert response["state"] == "ok"
    assert [hit["locator"] for hit in response["items"]] == ["ops/card"]


def test_unknown_schema_is_version_mismatch(upstream):
    _, script, _ = upstream
    set_source(script, json.dumps({**discovery(), "schema_version": "future"}).encode())
    assert project.describe()["state"] == "version_mismatch"


@pytest.mark.parametrize("pipe", ["stdout", "stderr"])
def test_output_cap_stops_a_producer_before_it_finishes(upstream, pipe):
    source, script, _ = upstream
    marker = source / "finished"
    script.write_text(
        "import sys, time\nfrom pathlib import Path\n"
        f"sys.{pipe}.buffer.write(b'x' * {_MAX_UPSTREAM + 1})\n"
        f"sys.{pipe}.flush()\ntime.sleep(3)\n"
        "Path('finished').touch()\n"
    )
    started = time.monotonic()
    assert project.describe(timeout=6)["state"] == "rejected"
    assert time.monotonic() - started < 2
    assert not marker.exists()


def test_read_binds_all_pages_to_search_digest(upstream):
    _, script, card = upstream
    script.write_text(
        "import json, sys\n"
        f"print(json.dumps({discovery()!r} if sys.argv[1] == 'discover' "
        f"else {search_payload(card)!r}))\n"
    )
    result = cli("find", "synthetic", "--backend", "ascend", "--json")
    assert result.returncode == 0, result.stderr
    hit = json.loads(result.stdout)["external"][0]["items"][0]
    opened = cli(*shlex.split(hit["open"])[1:])
    body = json.loads(opened.stdout)
    assert body["revision"] == REVISION
    assert body["card_sha256"] == hit["card_sha256"]
    assert body["has_more"]
    page = cli(*shlex.split(hit["open"])[1:], "--page", "2")
    assert json.loads(page.stdout)["card_sha256"] == hit["card_sha256"]
    assert json.loads(page.stdout)["revision"] == REVISION
    card.write_text("changed")
    changed = cli(*shlex.split(hit["open"])[1:], "--page", "2")
    assert changed.returncode != 0
    assert "changed since the search" in changed.stderr
    assert not changed.stdout
    current = json.loads(cli("cannbot", "read", "ops/card").stdout)
    assert current["card_sha256"] == hashlib.sha256(card.read_bytes()).hexdigest()


def test_read_refuses_path_escape(upstream):
    source, _, _ = upstream
    (source / "private.md").write_text("not knowledge")
    result = cli("cannbot", "read", "../private")
    assert result.returncode != 0
    assert "not knowledge" not in result.stdout + result.stderr


@pytest.mark.parametrize("page", [1, 2])
def test_read_rejects_revision_drift_with_unchanged_card(upstream, page):
    source, script, card = upstream
    script.write_text(
        "import json, sys\n"
        f"print(json.dumps({discovery()!r} if sys.argv[1] == 'discover' "
        f"else {search_payload(card)!r}))\n"
    )
    found = json.loads(cli("find", "synthetic", "--json").stdout)["external"][0]
    hit = found["items"][0]
    assert f"--revision {found['revision']}" in hit["open"]
    changed_revision = commit_revision(source)
    assert changed_revision != found["revision"]
    result = cli(*shlex.split(hit["open"])[1:], "--page", str(page))
    assert result.returncode != 0
    assert "revision changed since the search" in result.stderr
    assert "synthetic line" not in result.stdout + result.stderr
    current = project.read(hit["locator"], page=page)
    assert current["revision"] == changed_revision
    assert current["card_sha256"] == hit["card_sha256"]


def test_read_rejects_revision_change_during_read(upstream, monkeypatch, capsys):
    from inferrsi.apps.cannbot import read_worker

    source, _, _ = upstream
    original = read_worker._card_bytes

    def changing_card(root, locator):
        raw = original(root, locator)
        commit_revision(source)
        return raw

    monkeypatch.setattr(read_worker, "_card_bytes", changing_card)
    with pytest.raises(SystemExit):
        read_worker.read(source, {"locator": "ops/card", "expected_revision": REVISION})
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "version_mismatch"
    assert "text" not in result


def test_read_uses_approved_checkout_not_inherited_git_directory(upstream, monkeypatch):
    source, _, _ = upstream
    monkeypatch.setenv("GIT_DIR", str(source / "nonexistent-git-directory"))
    assert project.read("ops/card", expected_revision=REVISION)["revision"] == REVISION


@pytest.mark.parametrize("revision", ["", "HEAD", "abc", "A" * 40, "a" * 39, 42])
def test_read_rejects_invalid_expected_revision_before_worker(monkeypatch, revision):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid revision started a worker")

    monkeypatch.setattr(project, "_run", unexpected)
    with pytest.raises(project.ChannelFailure, match="expected_revision"):
        project.read("ops/card", expected_revision=revision)


def test_native_fingerprint_and_raw_byte_digest_are_distinct(upstream):
    _, script, card = upstream
    native = script.parent / "retrieval/index.py"
    native.write_text(native.read_text().replace(
        "hashlib.sha256(body.encode())", "hashlib.sha256(b'parsed:' + body.encode())"
    ))
    raw_digest = hashlib.sha256(card.read_bytes()).hexdigest()
    native_digest = hashlib.sha256(b"parsed:" + card.read_bytes()).hexdigest()
    payload = search_payload(card)
    payload["results"][0]["card_sha256"] = native_digest
    set_source(script, json.dumps(payload).encode())
    hit = project.search("query")["items"][0]
    assert hit["source_card_sha256"] == native_digest
    assert hit["card_sha256"] == raw_digest != native_digest
    assert project.read(hit["locator"], expected_sha256=raw_digest)["card_sha256"] == raw_digest
    card.write_text("different indexed content")
    with pytest.raises(project.ChannelFailure) as error:
        project.search("query")
    assert error.value.state == "index_stale"


@pytest.mark.parametrize("backend", [[], ["--backend", "ascend"]])
def test_outside_git_project_reports_not_enabled(tmp_path, monkeypatch, backend):
    root = tmp_path.resolve()
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        pytest.skip("temporary directory is inside a Git project")
    monkeypatch.setenv("PYTHONPATH", str(REPO / "src"))
    result = cli("find", "tiling", *backend, "--json", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["items"]
    assert payload["external"][0]["state"] == "not_enabled"
    assert "Git project" in payload["external"][0]["fix"]


def test_platform_override_and_cuda_gate(upstream):
    _, script, card = upstream
    script.write_text(
        "import json, sys\n"
        "if sys.argv[1] == 'search':\n"
        "    assert sys.argv[sys.argv.index('--platform') + 1] == 'a3'\n"
        f"print(json.dumps({discovery()!r} if sys.argv[1] == 'discover' "
        f"else {search_payload(card)!r}))\n"
    )
    result = cli("find", "synthetic", "--platform", "a3", "--json")
    assert json.loads(result.stdout)["external"][0]["state"] == "ok"
    script.write_text("raise RuntimeError('must not be called')\n")
    for args in (("--backend", "cuda"), ("--no-external",)):
        result = cli("find", "tiling", *args, "--json")
        assert "external" not in json.loads(result.stdout)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group cleanup")
@pytest.mark.parametrize("phase", ["discover", "search"])
def test_cli_deadline_kills_upstream_descendants(upstream, phase):
    source, script, _ = upstream
    script.write_text(
        "import json, os, subprocess, sys, time\nfrom pathlib import Path\n"
        f"if sys.argv[1] == {phase!r}:\n"
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "    Path('pids.json').write_text(json.dumps([os.getpid(), child.pid]))\n"
        "    time.sleep(30)\n"
        f"print(json.dumps({discovery()!r}))\n"
    )
    started = time.monotonic()
    result = cli("find", "tiling", "--external-timeout", "0.8", "--json", timeout=5)
    assert result.returncode == 0, result.stderr
    assert time.monotonic() - started < 4
    entry = json.loads(result.stdout)["external"][0]
    assert entry["state"] == "timeout"
    assert entry["elapsed_ms"] >= 700
    assert "items" not in entry
    pids = json.loads((source / "pids.json").read_text())
    for pid in pids:
        # Linux may briefly retain a reparented zombie; it cannot execute work.
        state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                               capture_output=True, text=True, check=False).stdout.strip()
        assert not state or state.startswith("Z"), (pid, state)


def test_cli_larger_budget_reaches_subprocess(upstream):
    _, script, card = upstream
    script.write_text(
        "import json, sys, time\ntime.sleep(0.4)\n"
        f"print(json.dumps({discovery()!r} if sys.argv[1] == 'discover' "
        f"else {search_payload(card)!r}))\n"
    )
    short = cli("find", "tiling", "--external-timeout", "0.6", "--json")
    assert json.loads(short.stdout)["external"][0]["state"] == "timeout"
    long = cli("find", "tiling", "--external-timeout", "2", "--json")
    assert json.loads(long.stdout)["external"][0]["state"] == "ok"


@pytest.mark.parametrize("count", [1, 3])
def test_nonreturning_adapter_cannot_hold_cli_exit(count):
    code = f'''
import json, threading, time
from inferrsi.knowledge.channels import ChannelRegistry, search_channels
class Hung:
    name = "hung"
    backend = "ascend"
    def describe(self, *, request):
        threading.Event().wait()
started = time.monotonic()
results = search_channels(ChannelRegistry([Hung() for _ in range({count})]),
                          "q", backend="ascend", timeout=0.1)
print(json.dumps({{"elapsed": time.monotonic() - started,
                  "states": [r.status.state for r in results],
                  "times": [r.elapsed_ms for r in results]}}))
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            timeout=3, check=True)
    data = json.loads(result.stdout)
    assert data["states"] == ["timeout"] * count
    assert data["elapsed"] < 0.25
    assert all(t >= 80 for t in data["times"])
