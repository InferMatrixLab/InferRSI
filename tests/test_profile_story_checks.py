"""Exercise the profile review page with narrative checks generated from real artifacts."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from test_optimization_story import campaign, log_document, write_log

from inferrsi.apps.views.dashboard import dashboard_snapshot, render_dashboard, write_dashboard


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
    script = Path(__file__).with_name("check_profile_review.cjs")
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
