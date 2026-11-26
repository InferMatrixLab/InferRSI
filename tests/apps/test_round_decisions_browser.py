"""Round-level decisions preserve evidence boundaries and exact run navigation."""

import json
import threading
from contextlib import contextmanager

import pytest

from inferrsi.apps.views.dashboard import dashboard_snapshot, render_dashboard
from inferrsi.apps.views.dashboard_live import DashboardServer
from inferrsi.harness.records.campaign_records import record_decision
from tests.apps.test_optimization_story import campaign, log_document, write_log
from tests.apps.test_optimization_trace import record, setup_campaign, trace_document, write_trace
from tests.apps.test_retrieval_projection import FIXTURE

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


@contextmanager
def dashboard(browser, root, profile, live=False, snapshot=None):
    manifest = root / "campaign.json"
    doc = json.loads(manifest.read_text())
    if profile:
        doc["review_layout"] = "profile_first"
    manifest.write_text(json.dumps(doc))
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors, requests = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    server = worker = None
    try:
        if live:
            server = DashboardServer(root, None, 0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            page.goto(f"http://127.0.0.1:{server.server_port}")
            expect(page.locator("#connection" if profile else "#live-status")).to_contain_text(
                "Connected", timeout=15000)
        else:
            snapshot = snapshot or dashboard_snapshot(root)
            if profile:
                snapshot["data"]["review_layout"] = "profile_first"
            path = root / "dashboard.html"
            path.write_text(render_dashboard(snapshot), encoding="utf-8")
            page.goto(path.as_uri())
        if profile:
            page.locator("#language").click()
            page.locator("#round-decisions-link").click()
            expect(page.locator("#round-decision-panel")).to_have_attribute("open", "")
        yield page
        assert not errors
        if not live:
            assert not [url for url in requests if url.startswith(("http:", "https:"))]
    finally:
        page.close()
        if server:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()


@pytest.mark.parametrize("profile", [False, True])
@pytest.mark.parametrize("live", [False, True])
def test_round_chain_navigation_and_refresh(cpu_browser, tmp_path, profile, live):
    doc = log_document(campaign(tmp_path))
    record_decision(tmp_path, candidate_id="b", round_number=2, outcome="rejected")
    write_log(tmp_path, doc)
    row = dashboard_snapshot(tmp_path)["data"]["candidates"][0]
    with dashboard(cpu_browser, tmp_path, profile, live) as page:
        root = page.locator("#round-decisions")
        stages = [root.locator(f'[data-rd-stage="{i}"]') for i in range(1, 6)]
        analysis, retrieval, alternatives, choice, result = stages
        expect(root.locator("h3")).to_have_text([
            "01 Bottleneck analysis", "02 Retrieval results", "03 Alternatives",
            "04 Final selection", "05 Execution results"])
        expect(analysis).to_contain_text("No bottleneck analysis recorded for this round")
        expect(root.locator("select")).to_have_value("1")
        expect(retrieval).to_contain_text("Returned items · 2")
        expect(retrieval).to_contain_text("Caller declared rejection · Not the bottleneck")
        expect(alternatives).to_contain_text("launch.graph")
        expect(alternatives).to_contain_text("other alternatives are unknown")
        expect(alternatives.get_by_text("Fusion", exact=True)).to_have_count(0)
        expect(choice).to_contain_text("Selected options · launch.graph")
        expect(choice).to_contain_text("Why this candidate · Direct fix")
        expect(choice).not_to_contain_text("Adopted")
        expect(result).to_contain_text("a · run-a")
        expect(result).to_contain_text("100 tokens/s → 104 tokens/s")
        expect(result).to_contain_text("Post-validation decision (record) · Adopted")
        retrieval.get_by_role("button", name="Open retrieval evidence").click()
        expect(page.locator("#knowledge-navigation")).to_contain_text("package:graphs")
        result.get_by_role("button", name="Open run evidence").click()
        if profile:
            expect(page.locator(f'[data-experiment-id="{row["experiment_id"]}"]')).to_be_focused()
        else:
            expect(page.locator("#run-review")).to_contain_text("run-a")

        root.locator("select").select_option("2")
        expect(retrieval).to_contain_text("No retrieval snapshot linked to this round")
        expect(retrieval).not_to_contain_text("package:graphs")
        expect(choice).to_contain_text("Selected options · precision.fp8")
        expect(choice).not_to_contain_text("launch.graph")
        expect(result).to_contain_text("Quality · Failed")
        expect(result).to_contain_text("Post-validation decision (record) · Rejected")
        summary = alternatives.locator("summary")
        summary.click()
        expect(alternatives).to_contain_text("Out of budget")
        if live:
            root.locator("select").focus()
            doc["iterations"][1]["candidates"][0]["why"] = "Updated reason from live snapshot"
            write_log(tmp_path, doc)
            expect(choice).to_contain_text("Updated reason from live snapshot", timeout=15000)
            expect(root.locator("select")).to_be_focused()
            expect(root.locator("select")).to_have_value("2")
            expect(alternatives.locator("details")).to_have_attribute("open", "")
        page.locator("#language" if profile else "#language-zh").click()
        expect(root).to_have_attribute("aria-label", "逐轮决策")
        expect(root.locator("select")).to_have_value("2")
        expect(alternatives.locator("details")).to_have_attribute("open", "")
        expect(result).to_contain_text("验证后决定（记录） · 拒绝")
        for width in (1600, 768, 375, 320):
            page.set_viewport_size({"width": width, "height": 1000})
            assert root.evaluate("n => n.scrollWidth <= n.clientWidth + 1")
            if width <= 375:
                assert root.locator(".rd-grid").evaluate(
                    "n => getComputedStyle(n).gridTemplateColumns.split(' ').length") == 1


@pytest.mark.parametrize("profile", [False, True])
def test_missing_round_and_snapshot_do_not_invent_first_round(cpu_browser, tmp_path, profile):
    campaign(tmp_path)
    snapshot = dashboard_snapshot(tmp_path)
    for row in snapshot["data"]["candidates"]:
        row["round"] = None
        row["decision"] = "not_recorded"
    with dashboard(cpu_browser, tmp_path, profile, snapshot=snapshot) as page:
        root = page.locator("#round-decisions")
        expect(root.locator("select option")).to_have_text(["Round not recorded"])
        expect(root).to_contain_text("Their order does not establish a first round")
        expect(root).to_contain_text("No round-specific alternatives recorded")
        expect(root).to_contain_text("Choice and selection rationale not recorded")
        expect(root).to_contain_text("a · run-a")
        expect(root).to_contain_text("b · run-b")
        expect(root).not_to_contain_text("Returned items · 0")


@pytest.mark.parametrize("profile", [False, True])
def test_round_trace_preserves_declared_alternatives_and_attempt(cpu_browser, tmp_path, profile):
    setup_campaign(tmp_path)
    doc = trace_document()
    doc["search_space"]["items"][0]["description"] = "<img src=x onerror=alert(1)>"
    write_trace(tmp_path / "optimization.json", doc)
    record(tmp_path)
    with dashboard(cpu_browser, tmp_path, profile) as page:
        root = page.locator("#round-decisions")
        alternatives = root.locator('[data-rd-stage="3"]')
        expect(alternatives).to_contain_text("An option not yet attempted")
        expect(alternatives).to_contain_text("<img src=x onerror=alert(1)>")
        expect(root.locator("img")).to_have_count(0)
        choice = root.locator('[data-rd-stage="4"]')
        expect(choice).to_contain_text("Caller-recorded attempt")
        expect(choice).to_contain_text("Measure option A")
        expect(choice).not_to_contain_text("Adopted")
        root.get_by_text("Caller-recorded context · candidate-a", exact=True).click()
        expect(root).to_contain_text("A declaration, not a retained retrieval result snapshot")
        expect(root).to_contain_text("search query")


@pytest.mark.parametrize("profile", [False, True])
def test_multiple_runs_and_conflicts_remain_visible(cpu_browser, tmp_path, profile):
    FIXTURE["build"](tmp_path)
    snapshot = dashboard_snapshot(tmp_path)
    rows = snapshot["data"]["candidates"]
    round_number = next(row["round"] for row in rows if row["run_id"] == "retry")
    with dashboard(cpu_browser, tmp_path, profile) as page:
        root = page.locator("#round-decisions")
        root.locator("select").select_option(str(round_number))
        result = root.locator('[data-rd-stage="5"]')
        for row in [row for row in rows if row["round"] == round_number]:
            card = result.locator(":scope > article").filter(
                has=page.get_by_role("heading", name=f'{row["candidate_id"]} · {row["run_id"]}',
                                     exact=True))
            expect(card).to_have_count(1)
            card.get_by_role("button", name="Open run evidence").click()
            if profile:
                expect(page.locator(
                    f'[data-experiment-id="{row["experiment_id"]}"]')).to_be_focused()
            else:
                expect(page.locator("#run-review")).to_contain_text(row["run_id"])
        expect(result).to_contain_text("INCONCLUSIVE")
        retrieval = root.locator('[data-rd-stage="2"]')
        expect(retrieval).to_contain_text("Returned items · 5")
        expect(retrieval).to_contain_text("Context omitted")
        expect(retrieval).to_contain_text("Caller declared use (not proof of consumption)")


@pytest.mark.parametrize("profile", [False, True])
def test_tampered_capture_and_decision_conflict_are_not_hidden(cpu_browser, tmp_path, profile):
    doc = log_document(campaign(tmp_path))
    doc["iterations"][0]["decision"]["outcome"] = "rejected"
    write_log(tmp_path, doc)
    path = tmp_path / "knowledge/r1.json"
    assert path.is_file()
    capture = json.loads(path.read_text())
    capture["assembled_text"] += "tampered"
    path.write_text(json.dumps(capture))
    with dashboard(cpu_browser, tmp_path, profile) as page:
        root = page.locator("#round-decisions")
        retrieval = root.locator('[data-rd-stage="2"]')
        expect(retrieval).not_to_contain_text("Context assembled")
        expect(retrieval).not_to_contain_text("Returned items · 0")
        expect(root).to_contain_text("Decision conflicts with the run record")
        expect(root.locator('[data-rd-stage="5"]')).to_contain_text(
            "Post-validation decision (record) · Adopted")


@pytest.mark.parametrize("profile", [False, True])
def test_shared_context_conflict_and_zero_hits_stay_distinct(cpu_browser, tmp_path, profile):
    FIXTURE["build"](tmp_path)
    doc = json.loads((tmp_path / "review-input.json").read_text())
    doc["iterations"][1]["context_ids"].append("capture")
    write_log(tmp_path, doc)
    with dashboard(cpu_browser, tmp_path, profile) as page:
        root = page.locator("#round-decisions")
        root.locator("select").select_option("2")
        retrieval = root.locator('[data-rd-stage="2"]')
        capture = retrieval.locator(":scope > article").filter(
            has=page.get_by_role("heading", name="capture", exact=True))
        empty = retrieval.locator(":scope > article").filter(
            has=page.get_by_role("heading", name="empty", exact=True))
        expect(capture).to_contain_text("round_conflict")
        expect(capture).to_contain_text("Returned items · 5")
        expect(empty).to_contain_text("Returned items · 0")
        expect(empty).not_to_contain_text("No retrieval snapshot")


@pytest.mark.parametrize("profile", [False, True])
def test_run_navigation_without_experiment_ids_uses_exact_round_candidate_run(
        cpu_browser, tmp_path, profile):
    campaign(tmp_path)
    snapshot = dashboard_snapshot(tmp_path)
    for row in snapshot["data"]["candidates"]:
        row.pop("experiment_id")
    with dashboard(cpu_browser, tmp_path, profile, snapshot=snapshot) as page:
        root = page.locator("#round-decisions")
        root.locator("select").select_option("2")
        root.get_by_role("button", name="Open run evidence").click()
        if profile:
            summary = page.locator('#rounds > details > summary').filter(has_text="B")
            expect(summary).to_be_focused()
            expect(summary.locator("..")).to_have_attribute("open", "")
        else:
            expect(page.locator("#run-review")).to_contain_text("run-b")


@pytest.mark.parametrize("profile", [False, True])
@pytest.mark.parametrize("experiment_ids", [False, True])
def test_duplicate_run_identities_disable_navigation(
    cpu_browser, tmp_path, profile, experiment_ids,
):
    campaign(tmp_path)
    snapshot = dashboard_snapshot(tmp_path)
    rows = snapshot["data"]["candidates"]
    if not experiment_ids:
        rows[0].pop("experiment_id")
    rows.append(dict(rows[0]))
    with dashboard(cpu_browser, tmp_path, profile, snapshot=snapshot) as page:
        result = page.locator('#round-decisions [data-rd-stage="5"]')
        expect(result.get_by_text("Ambiguous candidate/run identity", exact=True)).to_have_count(2)
        expect(result.get_by_role("button", name="Open run evidence")).to_have_count(0)


@pytest.mark.parametrize("profile", [False, True])
@pytest.mark.parametrize("live", [False, True])
def test_shared_search_only_round_preserves_queries_and_requests(
    cpu_browser, tmp_path, profile, live,
):
    FIXTURE["build"](tmp_path)
    path = tmp_path / "search/round-3.json"
    search = json.loads(path.read_text())
    assert search["context_ids"] == []
    search["events"] = [
        {"id": "shell:1", "action": "search", "tool": "rg", "query": "dense BF16",
         "scope": ["cases"], "materials": [{"ref": "cases/launch.md"}]},
        {"id": "catalog:1", "action": "search", "tool": "knowledge search",
         "request": {"query": "<img src=x onerror=alert(1)>", "relevance": "decode launch",
                     "limit": 7}, "materials": []},
        {"id": "explicit:1", "action": "search", "tool": "collect",
         "request": {"ids": ["package:graphs", "package:kv"]}, "materials": []},
        {"id": "missing:1", "action": "search", "tool": "rg", "materials": []},
    ]
    path.write_text(json.dumps(search))
    with dashboard(cpu_browser, tmp_path, profile, live) as page:
        root = page.locator("#round-decisions")
        root.locator("select").select_option("3")
        retrieval = root.locator('[data-rd-stage="2"]')
        expect(retrieval).to_contain_text("No retrieval snapshot linked to this round")
        expect(retrieval).to_contain_text("Query · dense BF16")
        expect(retrieval).to_contain_text("Query · <img src=x onerror=alert(1)> · decode launch")
        expect(retrieval).to_contain_text("Query · package:graphs, package:kv")
        expect(retrieval).to_contain_text("Query · Not recorded")
        expect(retrieval).not_to_contain_text("Returned items")
        expect(retrieval.locator("img")).to_have_count(0)
        event = retrieval.locator("article").filter(
            has=page.get_by_role("heading", name="search · rg · shell:1", exact=True)).last
        event.get_by_text("Request and event evidence", exact=True).click()
        evidence = json.loads(event.locator("pre").inner_text())
        assert evidence["scope"] == ["cases"]
        assert evidence["materials"] == [{"ref": "cases/launch.md"}]
        page.locator("#language" if profile else "#language-zh").click()
        expect(retrieval).to_contain_text("查询 · dense BF16")
        expect(retrieval).to_contain_text("查询 · 未记录")
        expect(root.locator("select")).to_have_value("3")


@pytest.mark.parametrize("profile", [False, True])
def test_external_experiment_ids_disambiguate_missing_round_run(cpu_browser, tmp_path, profile):
    campaign(tmp_path)
    snapshot = dashboard_snapshot(tmp_path)
    for row in snapshot["data"]["candidates"]:
        row.update(round=None, candidate_id="external", run_id=None)
    with dashboard(cpu_browser, tmp_path, profile, snapshot=snapshot) as page:
        result = page.locator('#round-decisions [data-rd-stage="5"]')
        expect(result.get_by_role("button", name="Open run evidence")).to_have_count(2)
        expect(result).not_to_contain_text("Ambiguous")
        result.get_by_role("button", name="Open run evidence").last.click()
        if profile:
            experiment_id = snapshot["data"]["candidates"][1]["experiment_id"]
            expect(page.locator(f'[data-experiment-id="{experiment_id}"]')).to_be_focused()
        else:
            expect(page.locator("#run-review strong").first).to_have_text("B")


def test_managed_round_knowledge_and_measured_score(cpu_browser, tmp_path):
    campaign(tmp_path)
    snapshot = dashboard_snapshot(tmp_path)
    data = snapshot["data"]
    card, unused = "ops/example/tiling", "ops/example/unused"
    external = {
        "channel": "cannbot-knowledge", "platform": "a3", "state": "ok",
        "revision": "a" * 40, "score_scale": "knowledge-search.v5", "count": 2,
        "path": "knowledge/search.json",
        "items": [{"locator": ref, "score": 5, "card_sha256": "b" * 64}
                  for ref in (card, unused)],
        "reads": [{"locator": card, "page": 1}, {"locator": unused, "page": 1}],
    }
    data["managed_diagnoses"] = [
        {"rounds": [1], "bottleneck": "Repeated dispatch",
         "measurement_summary": "Dispatch took 4 ms."},
        {"rounds": [], "bottleneck": "Unassigned finding",
         "measurement_summary": "Separate sample."},
    ]
    data["managed_retrievals"] = [
        {"round": 1, "query": "tile sizes", "items": [
            {"ref": "package:tile", "title": "Tiling", "delivered": True},
        ], "external": external},
        {"round": None, "submitted_rounds": [2], "query": "earlier snapshot", "items": []},
        {"round": 2, "query": "empty query", "items": [],
         "external": {**external, "count": 0, "items": [], "reads": []}},
    ]
    row = {
        **data["candidates"][0],
        "round": 1, "candidate_id": "candidate-001", "run_id": "attempt-one",
        "metric_key": "speedup", "measured_score": 2, "verdict": "PASS",
        "managed_submission": {"hypothesis": "Reuse a table", "strategy": "Share across layers",
                               "alternatives": ["Cache across requests"],
                               "selection_reason": "Layers share positions"},
        "knowledge_uses": [{"source": "cannbot-knowledge", "ref": card,
                            "retrieval_round": 1, "page": 1}],
    }
    data["candidates"] = [row]
    data["pending_candidate"] = {
        "round": 2, "candidate_id": "candidate-002", "knowledge_uses": [],
        "managed_submission": {"hypothesis": "Fuse two kernels", "strategy": "",
                               "alternatives": [], "selection_reason": ""},
    }
    with dashboard(cpu_browser, tmp_path, False, snapshot=snapshot) as page:
        root = page.locator("#round-decisions")
        analysis, retrieval, alternatives, choice, result = (
            root.locator(f'[data-rd-stage="{i}"]') for i in range(1, 6))
        expect(alternatives).to_contain_text("Submitted option · Reuse a table")
        expect(alternatives).to_contain_text("Cache across requests")
        expect(alternatives).not_to_contain_text(unused)
        expect(choice).to_contain_text("Submitted strategy · Share across layers")
        expect(choice).to_contain_text("Selection rationale at submission · Layers share positions")
        expect(choice).not_to_contain_text("Cache across requests")
        expect(analysis).to_contain_text("Repeated dispatch")
        expect(analysis).to_contain_text("Dispatch took 4 ms.")
        expect(analysis).not_to_contain_text("Unassigned finding")
        expect(retrieval).not_to_contain_text("earlier snapshot")
        expect(retrieval).to_contain_text("Query · tile sizes")
        expect(retrieval).to_contain_text("Local knowledge")
        expect(retrieval).to_contain_text("CANNBot · a3")
        expect(retrieval).to_contain_text("Read receipts · Pages 1")
        expect(retrieval).to_contain_text(unused)
        expect(result).to_contain_text("candidate-001")
        expect(result).to_contain_text("Measured score · 2 · speedup")
        expect(result).to_contain_text(
            "Agent-declared knowledge use · cannbot-knowledge · " + card,
        )
        expect(result).not_to_contain_text(unused)
        root.locator("select").select_option("2")
        expect(retrieval).to_contain_text("Snapshot available at submission")
        expect(retrieval).to_contain_text("Query · earlier snapshot")
        expect(retrieval).to_contain_text("Retrieval round unknown")
        expect(retrieval).to_contain_text("Channel state · No hits")
        expect(alternatives).to_contain_text("Submitted option · Fuse two kernels")
        expect(alternatives).to_contain_text("Other alternatives were not recorded")
        expect(alternatives).not_to_contain_text("Cache across requests")
        expect(choice).to_contain_text("candidate-002")
        expect(choice).to_contain_text("Submitted hypothesis · Fuse two kernels")
        expect(choice).to_contain_text("Selection rationale at submission · Not recorded")
        expect(choice).not_to_contain_text("Choice and selection rationale not recorded")
        expect(result).to_contain_text("Awaiting assessment")
        expect(result).not_to_contain_text("candidate-001")
        expect(analysis).to_contain_text("No bottleneck analysis recorded for this round")
        root.locator("select").select_option("unassigned")
        expect(analysis).to_contain_text("Unassigned finding")
        expect(analysis).not_to_contain_text("Repeated dispatch")
