"""Optional real-browser regressions: pip install playwright; playwright install chromium."""

import json
import runpy
import shutil
import threading
from pathlib import Path

import pytest
from test_optimization_session import session as session
from test_optimization_session import submit
from test_optimization_session import task as task

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
            page.locator('[data-key="summary"] > summary').click()
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
    page.locator('[data-key="summary"] > summary').click()
    root = page.locator("#summary-experiments")
    root.locator('[data-xp-control="workload"]').select_option("W-throughput")
    root.locator('.xp-point[aria-label^="native-run-b"]').focus()
    assert not page.locator('[data-key="rounds"]').evaluate("node => node.open")
    root.get_by_role("button", name="Open experiment · native-run-b").click()
    assert page.locator('[data-key="rounds"]').evaluate("node => node.open")
    assert page.locator("[data-experiment-id]:focus").is_visible()
    assert page.locator("[data-experiment-id]:focus").inner_text().find("native-run-b") >= 0
    page.locator("#original-summary-title").click()
    assert "partial" in page.locator("#original-summary-body").inner_text()
    assert "123 s is narrative, not data" in page.locator("#original-summary-body").inner_text()
    assert not errors
    page.close()


@pytest.mark.parametrize("field", ["hardware", "protocol", "server_profile"])
@pytest.mark.parametrize("profile_first", [False, True])
def test_blank_configuration_renders_isolated_points_and_reason(
    browser, tmp_path, field, profile_first,
):
    FIXTURE["write"](tmp_path / "campaign.json", {
        "campaign_id": "synthetic-blank-config", "synthetic": True,
        **({"review_layout": "profile_first"} if profile_first else {}),
    })
    for round_number in (1, 2):
        metric = FIXTURE["metric"](value=8 + round_number)
        metric["configuration"][field] = "   "
        FIXTURE["external"](tmp_path, f"blank-{round_number}", round_number, [metric])
        control = FIXTURE["metric"]("W2", value=8 + round_number)
        FIXTURE["external"](tmp_path, f"control-{round_number}", round_number, [control])
    path = tmp_path / "dashboard.html"
    path.write_text(render_dashboard(dashboard_snapshot(tmp_path)))
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(path.as_uri())
        if profile_first:
            page.locator("#language").click()
            page.locator('[data-key="summary"] > summary').click()
        root = page.locator("#summary-experiments")
        root.locator('[data-xp-control="workload"]').select_option("W1")
        for panel in (root, page.locator("#chart")):
            assert panel.locator(".xp-point").count() == 2
            assert panel.locator(".xp-segment").count() == 0
        root.locator('.xp-point[aria-label^="blank-1"]').focus()
        detail = root.locator(".xp-detail")
        assert f"unknown configuration: {field}" in detail.inner_text()
        assert "9 s" in detail.inner_text()
        root.locator('[data-xp-table] summary').click()
        assert f"unknown configuration: {field}" in root.get_by_role("table").inner_text()
        root.locator('[data-xp-control="workload"]').select_option("W2")
        assert root.locator(".xp-point").count() == 2
        assert root.locator(".xp-segment").count() == 1
        assert not errors
    finally:
        page.close()


@pytest.mark.parametrize("live", [False, True])
def test_managed_session_preserves_objective_and_token_chart(browser, session, capsys, live):
    submit(session, 2, capsys, usage={"input_tokens": 100, "output_tokens": 20})
    snapshot = dashboard_snapshot(session)
    assert "optimization_session" in snapshot["data"]
    assert "experiments" not in snapshot["data"]
    server = worker = None
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        if live:
            server = DashboardServer(session, None, 0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            page.goto(f"http://127.0.0.1:{server.server_port}")
        else:
            path = session / "dashboard.html"
            path.write_text(render_dashboard(snapshot), encoding="utf-8")
            page.goto(path.as_uri())
        chart = page.locator("#chart")
        curve = chart.get_by_role("img", name="Optimization objective and cumulative tokens")
        playwright.expect(curve).to_be_visible()
        assert "Independent final" in chart.inner_text()
        assert "These curves do not establish cross-environment comparability" in (
            page.locator("#chart-note").inner_text())
        assert "Candidate: round 1, 2" in curve.locator("title").all_text_contents()
        assert "Input + output tokens: round 1, 120" in curve.locator("title").all_text_contents()
        # UI re-renders must preserve the server chart too.
        page.locator("#language-zh").click()
        playwright.expect(curve).to_be_visible()
        page.locator("#language-en").click()
        if live:
            submit(session, 3, capsys, usage={"input_tokens": 200, "output_tokens": 10})
            playwright.expect(curve).to_contain_text("330", timeout=15000)
            playwright.expect(curve).to_be_visible()
            assert "Candidate: round 2, 3" in curve.locator("title").all_text_contents()
            assert "These curves do not establish cross-environment comparability" in (
                page.locator("#chart-note").inner_text())
        assert "No plottable measurement" not in chart.inner_text()
        assert not errors
    finally:
        page.close()
        if server:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()


@pytest.mark.parametrize("live", [False, True])
def test_profile_only_trend_expanded_and_summary_state_survives_render(browser, campaign, live):
    path = campaign / "campaign.json"
    data = json.loads(path.read_text())
    data["review_layout"] = "profile_first"
    path.write_text(json.dumps(data))
    server = worker = None
    page = browser.new_page()
    try:
        if live:
            server = DashboardServer(campaign, None, 0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            page.goto(f"http://127.0.0.1:{server.server_port}")
        else:
            path = campaign / "profile.html"
            path.write_text(render_dashboard(dashboard_snapshot(campaign)))
            page.goto(path.as_uri())
        assert page.locator("#chart .xp-chart").first.is_visible()
        assert page.locator("main > section:not(.trend)").evaluate_all(
            "nodes => nodes.every(n => n.querySelector(':scope > details.panel'))")
        assert page.locator("details.panel[open]").count() == 0
        panel = page.locator('[data-key="summary"]')
        root = page.locator("#summary-experiments")
        assert not root.is_visible()
        panel.locator(":scope > summary").click()
        playwright.expect(root).to_be_visible()
        page.locator("#language").click()
        assert panel.evaluate("node => node.open")
        root.locator('[data-xp-control="workload"]').select_option("W-throughput")
        root.locator('.xp-point[aria-label^="native-run-b"]').focus()
        if live:
            path = campaign / "runs/native-run-b/evaluation.json"
            data = json.loads(path.read_text())
            data["candidate"]["median"] = 107
            path.write_text(json.dumps(data))
            playwright.expect(root.locator(".xp-detail")).to_contain_text(
                "107 tokens/s", timeout=15000)
            assert panel.evaluate("node => node.open")
        panel.locator(":scope > summary").click()
        page.locator("#language").click()
        assert not panel.evaluate("node => node.open")
        if live:
            data["candidate"]["median"] = 106
            path.write_text(json.dumps(data))
            playwright.expect(page.locator("#chart .xp-detail")).to_contain_text(
                "106 tokens/s", timeout=15000)
            assert not panel.evaluate("node => node.open")
    finally:
        page.close()
        if server:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()
