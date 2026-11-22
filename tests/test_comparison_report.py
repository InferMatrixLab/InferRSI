"""Comparison reports retain evidence, unknown values and escaped Agent narrative."""

import hashlib
import json

import pytest

from inferrsi.apps.views.comparison_report import write_comparison_report
from inferrsi.benchmark.comparison import DEFAULT_POLICY, attempt_accounting, summarize


def report():
    trials = []
    for condition, speedup in (("on", 2), ("off", 1.5)):
        trials.append({
            "id": "task-1-" + condition, "task": "task", "repeat": 1,
            "condition": condition, "status": "completed", "eligible": True, "gaps": [],
            "metrics": {"speedup": speedup, "wall_seconds": 10, "tokens": None},
            "usage": {"tokens": {"value": None, "coverage": "unknown"}},
            "trace": [{"round": 1, "strategy": "request-invariant reuse",
                       "hypothesis": "Retain conditioning", "knowledge_refs": ["context-1"],
                       "speedup": speedup, "best_speedup": speedup, "quality": "PASS",
                       "adopted": True},
                      {"round": 2, "strategy": "rejected fusion", "speedup": None,
                       "best_speedup": speedup, "quality": "FAIL", "adopted": False}],
            "final": {"speedup": speedup, "verdict": "PASS", "independent": True},
            "knowledge_deliveries": ["context-1"] if condition == "on" else [],
            "evidence": "trials/task-1-" + condition + "/delivery",
        })
    return {"schema_version": 1, "focus": "knowledge", "tasks": ["task"], "repeats": 1,
            "policy": DEFAULT_POLICY, "trials": trials,
            "assessment": summarize(trials, ["task"], 1, DEFAULT_POLICY)}


def test_json_markdown_and_offline_html_describe_one_snapshot(tmp_path):
    value = report()
    value["trials"][0]["final"] = {
        "speedup": 2, "binding": {"verified": True}, "delivery_accepted": True,
        "selected_candidate": {"candidate_id": "candidate-001", "path": "rounds/candidate.py"},
        "assessment": {"status": "completed", "verdict": "PASS",
                       "case_metrics": [{"id": "compact", "baseline_median_ms": 10.5,
                                         "candidate_median_ms": 5.25, "speedup": 2,
                                         "samples_ms": {"baseline": [10, 11],
                                                        "candidate": [5, 5.5]}}],
                       "evidence_files": {"measurement/result.json": "raw-evidence-digest"}},
    }
    paths = write_comparison_report(value, tmp_path / "report")
    assert set(paths) == {"json", "markdown", "html"}
    from pathlib import Path

    raw = Path(paths["json"]).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert json.loads(raw) == value
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
    html = Path(paths["html"]).read_text(encoding="utf-8")
    for document in (markdown, html):
        assert digest in document
        assert "Efficiency improved" in document
        assert "rejected fusion" in document
        assert "Independent final" in document
        assert "unknown" in document
        assert "context-1" in document
        assert "Baseline median" in document
        assert "compact" in document
        assert "candidate-001" in document
        assert "Cached input" in document
        assert "raw-evidence-digest" not in document
        assert "samples_ms" not in document
        assert "descriptive" not in document or "statistical significance" in document
    assert "<svg" in html
    assert "diamond = independent final" in html
    assert "<script" not in html
    assert "http://" not in html.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "https://" not in html
    assert "Actual model consumption is unverified" in html
    assert "<details><summary>Usage and evidence</summary>" in html
    assert "<td>compact</td><td>10.5</td><td>5.25</td><td>2.000×</td><td>2</td>" in html
    assert "<pre>" not in html


def test_imported_narrative_is_text_in_html_and_markdown(tmp_path):
    value = report()
    malicious = '<script>alert(1)</script> | [click](javascript:alert(2))\n# Heading'
    value["trials"][0]["trace"][0]["strategy"] = malicious
    value["trials"][0]["id"] = '"><img src=x onerror=alert(1)>'
    paths = write_comparison_report(value, tmp_path)
    from pathlib import Path

    html = Path(paths["html"]).read_text(encoding="utf-8")
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html
    assert "<script>" not in markdown
    assert r"\[click\]\(javascript:alert\(2\)\)" in markdown
    assert r"\|" in markdown
    assert r"\# Heading" in markdown
    assert "<br>" in markdown


def test_incomplete_report_retains_failure_and_planned_count(tmp_path):
    value = report()
    value["trials"][1].update(status="blocked", eligible=False, final=None,
                               gaps=["final timed out"])
    value["assessment"] = summarize(value["trials"], ["task"], 1, DEFAULT_POLICY)
    paths = write_comparison_report(value, tmp_path)
    from pathlib import Path

    html = Path(paths["html"]).read_text(encoding="utf-8")
    assert "Insufficient evidence" in html
    assert "final timed out" in html
    assert "Blocked · excluded from comparison" in html
    assert "Completed trials" in html
    assert "Eligible pairs" in html
    assert "No independent final recorded." in html


def test_regeneration_only_replaces_derived_files(tmp_path):
    sentinel = tmp_path / "original-evidence.json"
    sentinel.write_bytes(b"immutable source")
    value = report()
    write_comparison_report(value, tmp_path)
    value["trials"][0]["gaps"].append("late observation")
    write_comparison_report(value, tmp_path)
    assert sentinel.read_bytes() == b"immutable source"
    assert not list(tmp_path.glob(".comparison-*"))
    assert "late observation" in (tmp_path / "report.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("update", [{"schema_version": True}, {"schema_version": 2},
                                    {"focus": "other"}])
def test_report_rejects_unsupported_schema_before_writing(tmp_path, update):
    value = report()
    value.update(update)
    with pytest.raises(ValueError):
        write_comparison_report(value, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_nonfinite_snapshot_does_not_publish_partial_reports(tmp_path):
    value = report()
    value["trials"][0]["metrics"]["speedup"] = float("nan")
    with pytest.raises(ValueError):
        write_comparison_report(value, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def _attempt(number, status, **values):
    return {"attempt": number, "status": status, "eligible": status == "completed",
            "gaps": [] if status == "completed" else ["final missing"],
            "wall_seconds": None, "started_at": None, "ended_at": None, "tokens": None,
            "native_session": None, **values}


def test_attempts_section_shows_failed_attempts_and_unknown_tokens(tmp_path):
    from pathlib import Path

    value = report()
    attempts = [_attempt(1, "blocked", started_at=100.0, wall_seconds=30.0, tokens=None),
                _attempt(2, "completed", started_at=200.0, ended_at=210.0, wall_seconds=10.0,
                         tokens=50)]
    value["trials"][0].update(attempts=attempts, attempt_accounting=attempt_accounting(attempts))
    paths = write_comparison_report(value, tmp_path)
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
    html = Path(paths["html"]).read_text(encoding="utf-8")
    for document in (markdown, html):
        assert "Attempts and wall time" in document
        assert "1: blocked; 2: completed" in document
        assert "final missing" in document
        assert "unknown tokens stay unknown" in document
    row = next(line for line in markdown.splitlines() if "1: blocked; 2: completed" in line)
    assert row == ("| task | on | 1 | 2 | 1 | 1: blocked; 2: completed | 10.00 | 110.00 "
                   "| unknown | partial |")
    # Older snapshots without accounting still render, with unknown attempt fields.
    legacy = next(line for line in markdown.splitlines() if line.startswith("| task | off | 1 |"))
    assert legacy == ("| task | off | 1 | unknown | unknown | unknown | unknown | unknown "
                      "| unknown | unknown |")


def test_attempt_accounting_keeps_unknown_bounds_and_partial_tokens():
    unknown_start = attempt_accounting([
        _attempt(1, "failed", ended_at=50.0, tokens=10),
        _attempt(2, "completed", started_at=60.0, ended_at=70.0, wall_seconds=10.0, tokens=5)])
    assert unknown_start["total_wall_seconds"] is None
    assert unknown_start["missing_reasons"]["total_wall_seconds"] == [
        "first_attempt_start_unknown"]
    assert unknown_start["success_wall_seconds"] == 10.0
    assert unknown_start["tokens"] == 15 and unknown_start["token_coverage"] == "complete"
    partial = attempt_accounting([
        _attempt(1, "blocked", started_at=0.0, tokens=None),
        _attempt(2, "completed", started_at=5.0, ended_at=9.0, wall_seconds=4.0, tokens=7)])
    assert partial["tokens"] is None and partial["observed_tokens"] == 7
    assert partial["token_coverage"] == "partial"
    assert partial["total_wall_seconds"] == 9.0 and partial["failed_attempts"] == 1
    failed_last = attempt_accounting([_attempt(1, "blocked", started_at=0.0, ended_at=3.0)])
    assert failed_last["success_wall_seconds"] is None
    assert failed_last["total_wall_seconds"] == 3.0
    assert failed_last["token_coverage"] == "unknown"
    reversed_window = attempt_accounting([_attempt(1, "completed", started_at=5.0,
                                                   ended_at=4.0, wall_seconds=1.0)])
    assert reversed_window["total_wall_seconds"] is None
    with pytest.raises(ValueError):
        attempt_accounting([_attempt(2, "completed")])
    with pytest.raises(ValueError):
        attempt_accounting([])
