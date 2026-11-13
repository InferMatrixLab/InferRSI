"""Exercise the same retrieval projection in both layouts and refresh modes."""

import json
import threading

import pytest
from test_retrieval_projection import FIXTURE

from inferrsi.observability.dashboard import dashboard_snapshot, render_dashboard
from inferrsi.observability.dashboard_live import DashboardServer

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def browser():
    with playwright.sync_playwright() as driver:
        instance = driver.chromium.launch()
        yield instance
        instance.close()


@pytest.mark.parametrize("profile_first", [False, True])
@pytest.mark.parametrize("live", [False, True])
def test_navigation_keyboard_versions_and_refresh(browser, tmp_path, profile_first, live):
    FIXTURE["build"](tmp_path)
    if profile_first:
        path = tmp_path / "campaign.json"
        doc = json.loads(path.read_text())
        path.write_text(json.dumps({**doc, "review_layout": "profile_first"}))
    server = worker = None
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors, requests = [], []
    initial_polls = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: requests.append(r.url))
    try:
        if live:
            page.route("**/api/state", lambda route: initial_polls.append(route), times=1)
            server = DashboardServer(tmp_path, None, 0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            page.goto(f"http://127.0.0.1:{server.server_port}")
        else:
            path = tmp_path / "dashboard.html"
            path.write_text(render_dashboard(dashboard_snapshot(tmp_path)))
            page.goto(path.as_uri())
        if profile_first:
            page.locator("#language").click()
        root = page.locator("#knowledge-navigation")
        summary = root.locator(":scope > details > summary")
        summary.focus()
        if live:
            # Refresh between focus and Enter, so keyboard continuity is checked
            # deterministically rather than depending on the first poll's timing.
            assert len(initial_polls) == 1
            initial_polls[0].continue_()
            status = page.locator("#connection" if profile_first else "#live-status")
            playwright.expect(status).to_contain_text("Connected", timeout=15000)
            playwright.expect(summary).to_be_focused()
        page.keyboard.press("Enter")
        root.get_by_role("button", name="capture", exact=True).click()
        capture = root.locator('details[data-kt-key="navigation:capture"]')
        playwright.expect(capture).to_have_attribute("open", "")
        assert "campaign capture-context → collect" in capture.inner_text()
        assert "5" in capture.get_by_role("table").first.inner_text()
        assert "2" in capture.get_by_role("table").first.inner_text()
        rows = capture.get_by_role("table").nth(1)
        assert rows.get_by_text("Context budget", exact=True).count() == 3
        capture.get_by_role("button", name="R1 · repeat · retry", exact=True).focus()
        page.keyboard.press("Enter")
        target = page.locator("[data-experiment-id]:focus") if profile_first else page.locator(
            "#run-review")
        assert target.count() == 1
        detail = target.locator("..") if profile_first else target
        assert "retry" in detail.inner_text()
        if not profile_first:
            catalog = detail.locator(".retrieval").filter(
                has=page.get_by_role("heading", name="catalog", exact=True))
            assert "context budget Not requested" in catalog.inner_text()
            assert "Assembly not requested" in catalog.inner_text()
            assert "undefined" not in catalog.inner_text()
            assembled = detail.locator(".retrieval").filter(
                has=page.get_by_role("heading", name="capture", exact=True))
            assert "context budget 54 bytes" in assembled.inner_text()
            assert "54 bytes of context" in assembled.inner_text()
        detail.get_by_role("button", name="Open retrieval · capture", exact=True).click()
        assert root.get_by_role("button", name="capture", exact=True).get_attribute(
            "aria-pressed") == "true"
        archive = root.locator('details[data-kt-key="search/archive/round-1.json"]')
        archive.locator(":scope > summary").click()
        assert "declarations and archive-reviewed associations are separate" in archive.inner_text()
        assert "Archive-reviewed association" in archive.inner_text()
        assert "counts are not added" in archive.inner_text()
        if live:
            record = tmp_path / "search/archive/round-1.json"
            doc = json.loads(record.read_text())
            doc["coverage"], doc["counts"] = "partial", None
            declaration = dict(doc["declarations"][0])
            declarations = archive.locator(
                'details[data-kt-key="search/archive/round-1.json:declarations"]')
            declarations.locator(":scope > summary").click()
            artifact_title = "Changes and result artifacts"
            capture_artifacts = capture.get_by_text(artifact_title, exact=True).first
            archive_artifacts = archive.get_by_text(artifact_title, exact=True).first
            capture_artifacts.click()
            archive_artifacts.click()
            for field, value in (("source", None), ("context_id", []), ("context_id", {})):
                focused_artifacts = archive_artifacts if value == [] else capture_artifacts
                focused_artifacts.focus()
                doc["declarations"][0] = {**declaration, field: value}
                record.write_text(json.dumps(doc))
                playwright.expect(declarations.locator("pre")).to_contain_text(
                    f'"{field}": {json.dumps(value)}', timeout=15000)
                playwright.expect(archive.locator(":scope > summary")).to_contain_text("Partial")
                playwright.expect(archive).to_contain_text("source_mismatch")
                playwright.expect(focused_artifacts).to_be_focused()
                assert capture_artifacts.locator("..").evaluate("n=>n.open")
                assert archive_artifacts.locator("..").evaluate("n=>n.open")
                assert archive.evaluate("n=>n.open")
                assert declarations.evaluate("n=>n.open")
                assert root.get_by_role("button", name="capture", exact=True).get_attribute(
                    "aria-pressed") == "true"
                assert "Not recorded" in archive.get_by_role("table").first.inner_text()
            doc["declarations"][0] = declaration
            record.write_text(json.dumps(doc))
            playwright.expect(archive).not_to_contain_text("source_mismatch", timeout=15000)
            playwright.expect(declarations.locator("pre")).to_contain_text('"caller_declaration"')
        root.get_by_label("Knowledge round").select_option("2")
        assert root.get_by_role("button", name="capture", exact=True).count() == 0
        root.get_by_role("button", name="collect", exact=True).click()
        collect = root.locator('details[data-kt-key="navigation:collect"]')
        assert "collect" in collect.inner_text() and "weighted-lexical-v1" in collect.inner_text()
        assert "use not recorded in this field" in collect.inner_text()
        assert not errors
        if not live:
            assert all(url.startswith("file:") for url in requests)
    finally:
        page.close()
        if server:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()


@pytest.mark.parametrize("profile_first", [False, True])
def test_chinese_table_fallback_and_narrow_screen(browser, tmp_path, profile_first):
    FIXTURE["build"](tmp_path)
    snapshot = dashboard_snapshot(tmp_path)
    if profile_first:
        snapshot["data"]["review_layout"] = "profile_first"
    path = tmp_path / "dashboard.html"
    path.write_text(render_dashboard(snapshot))
    page = browser.new_page(viewport={"width": 390, "height": 844})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(path.as_uri())
        if not profile_first:
            page.locator("#language-zh").click()
        root = page.locator("#knowledge-navigation")
        root.locator(":scope > details > summary").click()
        root.get_by_role("button", name="catalog", exact=True).click()
        capture = root.locator('details[data-kt-key="navigation:catalog"]')
        assert "knowledge search" in capture.inner_text()
        assert "未请求" in capture.inner_text()
        assert capture.get_by_role("table").first.is_visible()
        assert root.bounding_box()["width"] <= 390
        assert not errors
    finally:
        page.close()
