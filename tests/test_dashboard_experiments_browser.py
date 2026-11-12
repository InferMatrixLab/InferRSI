"""Optional real-browser regressions: pip install playwright; playwright install chromium."""

import json
import runpy
import shutil
import threading
from pathlib import Path

import pytest

from inferrsi.observability.dashboard import dashboard_snapshot, render_dashboard
from inferrsi.observability.dashboard_live import DashboardServer

playwright = pytest.importorskip("playwright.sync_api")
FIXTURE = runpy.run_path(str(Path(__file__).parent / "fixtures/dashboard_experiments.py"))


@pytest.fixture
def browser():
    with playwright.sync_playwright() as driver:
        instance = driver.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture
def campaign(tmp_path):
    FIXTURE["build"](tmp_path)
    return tmp_path


def test_offline_axes_keyboard_exact_run_and_shared_selection(browser, campaign):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors, requests = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: requests.append(r.url))
    page.goto((campaign / "dashboard.html").as_uri())
    root = page.locator("#summary-experiments")
    root.locator('[data-xp-control="workload"]').select_option("W1")
    assert page.locator('#chart [data-xp-control="workload"]').input_value() == "W1"
    assert root.locator(".xp-chart").count() == 2
    assert root.locator(".xp-card").nth(1).locator(".xp-event-mark").count() == 1
    assert root.locator(".xp-card").first.locator(".xp-segment").count() == 3
    point = root.locator('.xp-point[aria-label^="quality-rejected"]')
    point.focus()
    page.keyboard.press("Enter")
    selected_id = point.get_attribute("data-xp-id")
    assert page.locator(f'#chart .xp-point[data-xp-id="{selected_id}"]').get_attribute(
        "aria-pressed") == "true"
    detail = root.locator(".xp-detail")
    assert "FAIL" in detail.inner_text() and "7.5 s" in detail.inner_text()
    assert "-0.5 s" in detail.inner_text() and "B / r" in detail.inner_text()
    assert "not locally reproduced" in detail.inner_text()
    event = root.locator('.xp-events button').filter(
        has_text="Graph capture failed before benchmark")
    event.click()
    assert "no E2E result" in detail.inner_text()
    assert "Value" not in detail.locator("dt").all_text_contents()
    root.locator('[data-xp-control="workload"]').select_option("W-throughput")
    point = root.locator('.xp-point[aria-label^="native-run-b"]')
    point.focus()
    page.keyboard.press("Space")
    assert "native-run-b" in detail.inner_text() and "110 tokens/s" in detail.inner_text()
    detail.get_by_role("button", name="Open experiment · native-run-b").click()
    assert "native-run-b" in page.locator("#run-review").inner_text()
    # A legacy candidate-only link offers both runs rather than opening the first.
    page.locator('[data-live-key="summary-records"] summary').click()
    page.locator('button.chip').filter(has_text="native-repeat · Ambiguous").click()
    chooser = page.locator("#run-review")
    assert chooser.get_by_role("button").count() == 2
    chooser.get_by_role("button").filter(has_text="native-run-a").click()
    assert "native-run-a" in page.locator("#run-review").inner_text()
    page.locator('#candidate-filter').select_option(
        label='legacy-metric · legacy-metric.json')
    legacy = page.locator('#candidate-inspection table')
    assert 'Sample 1' in legacy.inner_text() and 'Round 1' not in legacy.inner_text()
    assert legacy.locator('td').last.inner_text() == 'Not recorded'
    assert not errors
    assert all(url.startswith("file:") for url in requests)
    page.close()


def test_time_axis_chinese_narrow_screen_and_accessible_table(browser, campaign):
    page = browser.new_page(viewport={"width": 390, "height": 844})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto((campaign / "dashboard.html").as_uri())
    page.locator("#language-zh").click()
    root = page.locator("#summary-experiments")
    root.get_by_label("工作负载", exact=True).select_option("W1")
    root.get_by_label("横轴", exact=True).select_option("timestamp")
    assert root.locator(".xp-chart").count() == 1
    assert "未定位记录" in root.inner_text()
    root.locator('[data-xp-table] summary').click()
    assert root.get_by_role("table").is_visible()
    assert "graph-capture-failed" in root.inner_text()
    assert root.bounding_box()["width"] <= 390
    point = root.locator('.xp-point[aria-label^="vae-graph"]')
    point.focus()
    assert "2026-01-01T12:02:00.000Z" in root.locator(".xp-detail").inner_text()
    assert "数值" in root.locator(".xp-detail").inner_text()
    assert not errors
    page.close()


@pytest.mark.parametrize("profile_first", [False, True])
def test_real_live_refresh_keeps_filters_and_measurement_then_marks_disappearance(
    browser, campaign, profile_first,
):
    if profile_first:
        path = campaign / "campaign.json"
        data = json.loads(path.read_text())
        data["review_layout"] = "profile_first"
        path.write_text(json.dumps(data))
    server = DashboardServer(campaign, None, 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(f"http://127.0.0.1:{server.server_port}")
        if profile_first:
            page.locator("#language").click()
        root = page.locator("#summary-experiments")
        root.locator('[data-xp-control="workload"]').select_option("W-throughput")
        point = root.locator('.xp-point[aria-label^="native-run-b"]')
        point.focus()
        identity = point.get_attribute("data-xp-id")
        # Reorder directories and update the selected run's value while keeping its identity.
        (campaign / "candidates/native-run-b").rename(campaign / "candidates/aaa-reordered")
        path = campaign / "runs/native-run-b/evaluation.json"
        data = json.loads(path.read_text())
        data["candidate"]["median"] = 107
        path.write_text(json.dumps(data))
        playwright.expect(root.locator(".xp-detail")).to_contain_text(
            "107 tokens/s", timeout=15000)
        assert root.locator('[data-xp-control="workload"]').input_value() == "W-throughput"
        assert root.locator(f'.xp-point[data-xp-id="{identity}"]').get_attribute(
            "aria-pressed") == "true"
        shutil.rmtree(campaign / "candidates/aaa-reordered")
        playwright.expect(root.locator(".xp-detail")).to_contain_text(
            "Selection no longer available", timeout=15000)
        assert root.locator('.xp-point[aria-pressed="true"]').count() == 0
        assert not errors
    finally:
        page.close()
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


def test_profile_layout_preserves_partial_summary_and_keyboard_drilldown(browser, campaign):
    snapshot = dashboard_snapshot(campaign)
    snapshot["data"]["review_layout"] = "profile_first"
    path = campaign / "profile.html"
    path.write_text(render_dashboard(snapshot))
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(path.as_uri())
    page.locator("#language").click()
    root = page.locator("#summary-experiments")
    root.locator('[data-xp-control="workload"]').select_option("W-throughput")
    root.locator('.xp-point[aria-label^="native-run-b"]').focus()
    root.get_by_role("button", name="Open experiment · native-run-b").click()
    assert page.locator("[data-experiment-id]:focus").inner_text().find("native-run-b") >= 0
    page.locator("#original-summary-title").click()
    assert "partial" in page.locator("#original-summary-body").inner_text()
    assert "123 s is narrative, not data" in page.locator("#original-summary-body").inner_text()
    assert not errors
    page.close()
