"""The live dashboard reads recorded updates without exposing the campaign tree."""

import copy
import gzip
import http.client
import json
import random
import shutil
import socket
import string
import subprocess
import threading
from pathlib import Path

import pytest

from inferrsi.cli import main
from inferrsi.observability import dashboard_live
from inferrsi.observability.dashboard import write_dashboard
from inferrsi.observability.dashboard_live import DashboardServer


@pytest.fixture
def dashboard_server(tmp_path):
    (tmp_path / "campaign.json").write_text(
        json.dumps({"campaign_id": "synthetic-live", "synthetic": True}), encoding="utf-8"
    )
    server = DashboardServer(tmp_path, None, 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield server
    server.shutdown()
    worker.join(timeout=5)
    server.server_close()


def request(server, path, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_poll_reads_new_records_and_uses_conditional_updates(dashboard_server, tmp_path):
    status, headers, body = request(dashboard_server, "/api/state")
    assert status == 200 and json.loads(body)["data"]["candidates"] == []
    first_etag = headers["ETag"]
    assert request(dashboard_server, "/api/state", {"If-None-Match": first_etag})[0] == 304

    candidate = tmp_path / "candidates" / "new" / "candidate.json"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(json.dumps({"candidate_id": "new", "title": "New trial"}),
                         encoding="utf-8")
    status, headers, body = request(dashboard_server, "/api/state", {"If-None-Match": first_etag})
    rows = json.loads(body)["data"]["candidates"]
    assert status == 200 and headers["ETag"] != first_etag
    assert [row["candidate_id"] for row in rows] == ["new"]
    assert rows[0]["improvement_pct"] is None


@pytest.mark.parametrize("gain,target", [
    (1.7976931348623157e308, 20),
    (-1.7976931348623157e308, 1.7976931348623157e308),
    (5, 1.7976931348623157e308),
])
def test_live_poll_withholds_extreme_branch_chart(dashboard_server, tmp_path, monkeypatch,
                                                  gain, target):
    (tmp_path / "campaign.json").write_text(json.dumps({
        "campaign_id": "synthetic-live", "goal": {"target_improvement_pct": target},
    }), encoding="utf-8")
    candidate = tmp_path / "candidates" / "new" / "candidate.json"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(json.dumps({"candidate_id": "new", "run_id": "run-a"}), encoding="utf-8")
    run = tmp_path / "runs" / "run-a"
    run.mkdir(parents=True)
    (run / "run.lock.json").write_text("{}", encoding="utf-8")
    (run / "evaluation.json").write_text(json.dumps({
        "verdict": "PASS", "improvement_pct": gain, "source_integrity": {"verified": True},
    }), encoding="utf-8")
    (run / "status.json").write_text('{"state":"completed"}', encoding="utf-8")
    (run / "validation").mkdir()
    (run / "validation/execution.json").write_text(
        '{"status":"completed","returncode":0}', encoding="utf-8")

    def fail_render(_spec):
        raise AssertionError("unbounded values reached the shared renderer")

    monkeypatch.setattr("inferrsi.observability.dashboard.build_svg", fail_render)
    status, _, body = request(dashboard_server, "/api/state")
    snapshot = json.loads(body)

    assert status == 200 and snapshot["chart"] == ""
    assert snapshot["data"]["chart_note"] == "Recorded values exceed the supported chart scale."


def test_compressed_live_responses_preserve_content_and_representation_etags(dashboard_server):
    status, plain_headers, plain = request(dashboard_server, "/api/state")
    assert status == 200
    status, headers, compressed = request(
        dashboard_server, "/api/state", {"Accept-Encoding": "gzip"}
    )
    assert status == 200 and headers["Content-Encoding"] == "gzip"
    assert headers["Vary"] == "Accept-Encoding, X-InferRSI-Compact"
    assert gzip.decompress(compressed) == plain and len(compressed) < len(plain)
    assert headers["ETag"] != plain_headers["ETag"]
    assert request(dashboard_server, "/api/state", {
        "Accept-Encoding": "gzip", "If-None-Match": headers["ETag"]
    })[0] == 304
    assert request(dashboard_server, "/api/state", {"If-None-Match": headers["ETag"]})[0] == 200
    status, headers, uncompressed = request(dashboard_server, "/api/state", {
        "Accept-Encoding": "gzip;q=0"
    })
    assert status == 200 and "Content-Encoding" not in headers and uncompressed == plain
    status, headers, html = request(dashboard_server, "/", {"Accept-Encoding": "gzip"})
    assert status == 200 and headers["Content-Encoding"] == "gzip"
    assert b'"live": true' in gzip.decompress(html)


def test_compact_live_transport_interns_repeated_context_without_changing_legacy_api(
    dashboard_server, monkeypatch
):
    rng = random.Random(42)
    text = "".join(rng.choices(string.ascii_letters + string.digits, k=60000))
    snapshot = {"data": {"candidates": [
        {"optimization_trace": {"context": {"text": text}}},
        {"optimization_trace": {"context": {"text": text}}},
        {"optimization_trace": None},
    ]}, "chart": "", "temporal": ""}
    monkeypatch.setattr(dashboard_live, "dashboard_snapshot", lambda *_: copy.deepcopy(snapshot))
    _, _, legacy = request(dashboard_server, "/api/state", {"Accept-Encoding": "gzip"})
    status, headers, compact = request(dashboard_server, "/api/state", {
        "Accept-Encoding": "gzip", "X-InferRSI-Compact": "1"
    })
    assert status == 200 and headers["Content-Encoding"] == "gzip"
    legacy_data = json.loads(gzip.decompress(legacy))["data"]
    compact_data = json.loads(gzip.decompress(compact))["data"]
    assert legacy_data == snapshot["data"]
    assert compact_data["_context_pool"] == [text]
    contexts = [row["optimization_trace"]["context"]["text"]
                for row in compact_data["candidates"][:2]]
    assert contexts == [{"$context": 0}, {"$context": 0}]
    assert len(compact) < len(legacy) * 0.75


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for the UI regression")
def test_compact_contexts_are_restored_exactly_in_the_browser():
    template = Path(__file__).parents[1] / "src/inferrsi/observability/template.html"
    script = r"""
const fs = require('node:fs'), assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[1], 'utf8');
const source = html.slice(html.indexOf('  function restoreContexts('),
                          html.indexOf('  let data = restoreContexts('));
const restore = new Function(source + '\nreturn restoreContexts;')();
const view = {_context_pool:['full context'], candidates:[
  {optimization_trace:{context:{text:{$context:0}}}},
  {optimization_trace:{context:{text:{$context:0}}}},
  {optimization_trace:null}]};
const restored = restore(view);
assert.equal(restored.candidates[0].optimization_trace.context.text, 'full context');
assert.equal(restored.candidates[1].optimization_trace.context.text, 'full context');
assert(!('_context_pool' in restored));
assert.throws(() => restore({_context_pool:[], candidates:[
  {optimization_trace:{context:{text:{$context:0}}}}]}));
assert.deepEqual(restore({candidates:[]}), {candidates:[]});
"""
    subprocess.run([shutil.which("node"), "-e", script, str(template)], check=True,
                   capture_output=True, text=True)


def test_live_endpoint_is_loopback_only_and_does_not_serve_source_files(dashboard_server):
    assert dashboard_server.server_address[0] == "127.0.0.1"
    assert request(dashboard_server, "/campaign.json")[0] == 404
    assert request(dashboard_server, "/api/state", {"Host": "attacker.example"})[0] == 403
    # SSH forwarding may use a different local port from the remote listener.
    assert request(dashboard_server, "/api/state", {"Host": "localhost:34567"})[0] == 200
    status, headers, _ = request(dashboard_server, "/api/state")
    assert status == 200 and headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert "Access-Control-Allow-Origin" not in headers


def test_idle_browser_connection_does_not_block_other_requests(dashboard_server):
    accepted = threading.Event()
    original = dashboard_server.get_request

    def observe_connection():
        connection = original()
        accepted.set()
        return connection

    dashboard_server.get_request = observe_connection
    idle = socket.create_connection(("127.0.0.1", dashboard_server.server_port), timeout=2)
    try:
        idle.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n")
        assert accepted.wait(2)
        assert request(dashboard_server, "/api/state")[0] == 200
    finally:
        idle.close()


def test_live_and_offline_html_keep_separate_network_policies(dashboard_server, tmp_path):
    status, _, body = request(dashboard_server, "/")
    assert status == 200 and b'"live": true' in body
    assert b"connect-src 'self'" in body
    offline = write_dashboard(tmp_path, tmp_path / "offline.html").read_bytes()
    assert b'"live": false' in offline
    assert b"connect-src 'self'" not in offline


def test_temporarily_invalid_campaign_returns_503_then_recovers(dashboard_server, tmp_path):
    campaign = tmp_path / "campaign.json"
    campaign.write_text("{", encoding="utf-8")
    assert request(dashboard_server, "/api/state")[0] == 503
    campaign.write_text(json.dumps({"campaign_id": "synthetic-live"}), encoding="utf-8")
    assert request(dashboard_server, "/api/state")[0] == 200


def test_live_cli_rejects_incompatible_flags(tmp_path):
    with pytest.raises(SystemExit):
        main(["dashboard", "--input", str(tmp_path), "--live", "--output", "out.html"])
    with pytest.raises(SystemExit):
        main(["dashboard", "--input", str(tmp_path), "--port", "8765"])


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for the UI regression")
def test_live_selection_matches_identity_after_rows_change():
    template = Path(__file__).parents[1] / "src/inferrsi/observability/template.html"
    script = r"""
const fs = require('node:fs'), assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[1], 'utf8');
const source = html.slice(html.indexOf('  function matchingIndex('),
                          html.indexOf('  function applySnapshot('));
assert(source.includes('function matchingIndex'));
const a = {candidate_id:'a', run_id:null, round:1};
const run = {candidate_id:null, run_id:'run-only', round:null};
let data = {candidates:[{candidate_id:'b', run_id:'other', round:1},
                        {candidate_id:'a', run_id:'new-run', round:1}, run]};
const find = new Function('data', source + '\nreturn matchingIndex;')(data);
assert.equal(find(a), 1);  // Insertion and newly linked run preserve the candidate.
assert.equal(find(run), 2);
data.candidates = [{candidate_id:'different', run_id:'new-run', round:1}];
assert.equal(find({candidate_id:'a', run_id:'new-run', round:1}), -1);
data.candidates = [{candidate_id:'a', run_id:'x', round:1},
                   {candidate_id:'a', run_id:'y', round:2}];
assert.equal(find(a), -1);  // Ambiguous identities never select another row.
"""
    subprocess.run([shutil.which("node"), "-e", script, str(template)], check=True,
                   capture_output=True, text=True)
