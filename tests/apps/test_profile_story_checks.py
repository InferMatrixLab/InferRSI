"""Exercise the profile review page with narrative checks generated from real artifacts."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from inferrsi.apps.views.dashboard import dashboard_snapshot, render_dashboard, write_dashboard
from inferrsi.harness.records.profile_timeline import attach_profile
from tests.apps.test_optimization_story import campaign, log_document, write_log
from tests.apps.test_profile_timeline import fixture as profile_fixture


def test_published_profile_example_matches_fixture(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    script = repo / "tests/fixtures/dashboard_profile_review.py"
    subprocess.run([sys.executable, str(script), str(tmp_path)], check=True)
    published = repo / "docs/examples/dashboard-profile-review.html"
    assert (tmp_path / "dashboard.html").read_text(encoding="utf-8") == published.read_text(
        encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js runs the exported dashboard")
@pytest.mark.parametrize("conflicts", [True, False])
def test_profile_review_displays_narrative_evidence_conflicts(tmp_path, conflicts):
    document = log_document(campaign(tmp_path))
    manifest = tmp_path / "campaign.json"
    manifest.write_text(json.dumps({**json.loads(manifest.read_text()),
                                    "review_layout": "profile_first"}))
    if conflicts:
        document["knowledge"][0]["used_refs"].append("package:missing")
        document["iterations"][0]["decision"]["outcome"] = "rejected"
    write_log(tmp_path, document)
    html = write_dashboard(tmp_path)
    _check_page(html, "conflicts" if conflicts else "clean")


def _check_page(html, mode):
    script = Path(__file__).parents[1] / "check_profile_review.cjs"
    subprocess.run([shutil.which("node"), str(script), str(html), mode], check=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js runs the exported dashboard")
def test_profile_review_renders_baseline_link_states_and_partial_timings(tmp_path):
    write_log(tmp_path, log_document(campaign(tmp_path)))
    manifest = tmp_path / "campaign.json"
    manifest.write_text(json.dumps({**json.loads(manifest.read_bytes()),
                                    "review_layout": "profile_first",
                                    "experiment_timing_sha256": "0" * 64}))
    snapshot = dashboard_snapshot(tmp_path)
    data = snapshot["data"]
    data["experiment_timing"]["steps"].append(
        {"kind": "model_call", "label": "#1", "model": "demo", "end": "2026-05-10T02:00:10Z",
         "start": None, "seconds": None, "basis": "incomplete"})
    row = data["candidates"][0]
    row["artifacts"]["profile"] = {"state": "present", "sha256": "a" * 64}
    row["optimization_trace"] = {"diagnosis": {
        "scope": "baseline_request", "metric_unit": "s", "total": 5, "source_sha256": "a" * 64,
        "components": [{"name": "Original worker", "samples": [5]}]}}
    links = {"r1": "verified", "late": "not_before", "unknown": "unknown_time", "bad": "unverified"}
    data["profile_captures"] = [{
        "id": "other", "phase": "baseline", "duration_us": 50, "tracks": [{}],
        "workload_id": "unrelated", "comparison_key": "other-clock", "source": {"sha256": "b" * 64},
        "started_at": "2026-05-10T02:00:00Z",
        "timing": {"basis": "Different clock", "stages_ms": {"Other worker": 42}},
        "pre_profile_searches": [{"context_id": key, "state": value}
                                 for key, value in links.items()]
    }]
    original = data["story"]["retrievals"][0]
    for key in ("late", "unknown", "bad"):
        data["story"]["retrievals"].append({**original, "context_id": key,
                                            "assembled_text": "PRIVATE SENTINEL"})
    html = tmp_path / "test-dashboard.html"
    html.write_text(render_dashboard(snapshot), encoding="utf-8")
    _check_page(html, "timing")


def test_profile_and_trace_shortcuts_open_recorded_evidence(browser, tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    source, review = profile_fixture(tmp_path)
    review.write_text(json.dumps({**json.loads(review.read_bytes()),
                                  "started_at": "2026-11-11T08:41:43Z"}))
    attach_profile(tmp_path, capture_id="baseline", source=f"profiles/{source.name}", review=review)
    url = write_dashboard(tmp_path).as_uri()
    page = browser.new_page()
    page.goto(url + "#profiles")
    profile = page.locator('[data-key="profile:baseline-timeline"]')
    playwright.expect(profile.locator("canvas:visible").first).to_be_visible()
    playwright.expect(profile.locator(":scope > summary")).to_be_focused()
    page.locator('[data-key="profile:baseline"] > summary').click()
    page.locator("#profiles-link").click()
    playwright.expect(profile.locator("canvas:visible").first).to_be_visible()
    page.locator("#trace-link").click()
    trace = page.locator('[data-key="experiment-all"]')
    playwright.expect(trace.locator("tbody")).to_contain_text("Warm worker")
    playwright.expect(trace.locator(":scope > summary")).to_be_focused()
    page.locator("#language").click()
    playwright.expect(trace.locator("tbody")).to_be_visible()
    page.reload()
    playwright.expect(trace.locator("tbody")).to_be_visible()
