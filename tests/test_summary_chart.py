"""The campaign gain figure validates its input, plots both layouts and lands in reports."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from inferrsi import summary_chart
from inferrsi.reporting import write_report

PROJECT = Path(__file__).resolve().parents[1]
EXAMPLES = PROJECT / "evidence" / "_template" / "results"
NS = "{http://www.w3.org/2000/svg}"


def load(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def chain_spec():
    return load("summary-chart.example.json")


def branch_spec():
    return load("summary-chart-branch.example.json")


def texts(spec):
    root = ET.fromstring(summary_chart.build_svg(spec))
    return [node.text for node in root.iter(f"{NS}text") if node.text]


def evaluation(**overrides):
    value = {
        "verdict": "FAIL",
        "metric_key": "metrics.latency_ms",
        "metric_unit": "ms",
        "direction": "minimize",
        "baseline": {"median": 100.0, "values": [99.0, 100.0, 101.0]},
        "candidate": {"median": 80.0, "values": [79.0, 80.0, 81.0]},
        "improvement_pct": 20.0,
        "measurement_method": "Alternating AB/BA sequential trials.",
        "statistical_significance": "not established",
    }
    value.update(overrides)
    return value


def test_chain_draws_one_line_with_a_marker_per_step():
    spec = chain_spec()
    root = ET.fromstring(summary_chart.build_svg(spec))
    lines = list(root.iter(f"{NS}polyline"))
    assert len(lines) == len(spec["metrics"])
    markers = [node for node in root.iter(f"{NS}circle")]
    assert len(markers) >= len(spec["points"]) * len(spec["metrics"])
    assert lines[0].get("points").count(" ") == len(spec["points"]) - 1


def test_chain_labels_every_step_with_its_running_multiple():
    spec = chain_spec()
    baseline = spec["baseline"]["metrics"]
    rendered = texts(spec)
    for point in spec["points"]:
        assert point["label"] in rendered
        multiple = point["values"]["C32"] / baseline["C32"]
        assert any(text.startswith(f"{multiple:.2f}×") for text in rendered)


def test_chain_phase_bands_cover_the_declared_stages():
    rendered = texts(chain_spec())
    for phase in chain_spec()["phases"]:
        assert phase in rendered


def test_branch_keeps_no_gain_and_loss_rows_visible():
    spec = branch_spec()
    rendered = texts(spec)
    assert sum(text.endswith("×") for text in rendered) == 2
    assert any("C16 -4.0%" in text for text in rendered)


def test_branch_and_chain_markdown_match_their_values():
    chain_table = summary_chart.build_markdown(chain_spec())
    assert "| Stage | Step |" in chain_table
    assert chain_table.count("\n| ") == len(chain_spec()["points"]) + 2
    branch_table = summary_chart.build_markdown(branch_spec())
    assert "| Group | Trial |" in branch_table
    assert "regressed" in branch_table


def test_malformed_specs_fail_with_a_named_field():
    broken = chain_spec()
    del broken["points"][1]["values"]["C16"]
    with pytest.raises(summary_chart.SpecError, match="points\\[1\\].values"):
        summary_chart.build_svg(broken)

    duplicate = branch_spec()
    duplicate["trials"].append(dict(duplicate["trials"][0]))
    with pytest.raises(summary_chart.SpecError, match="duplicate trial"):
        summary_chart.build_svg(duplicate)

    bad_layout = chain_spec()
    bad_layout["layout"] = "spiral"
    with pytest.raises(summary_chart.SpecError, match="layout"):
        summary_chart.build_svg(bad_layout)


def test_report_renders_the_figure_without_a_separate_command(tmp_path):
    (tmp_path / "evaluation.json").write_text(json.dumps(evaluation()), encoding="utf-8")
    (tmp_path / "status.json").write_text(json.dumps({"state": "completed"}), encoding="utf-8")
    report = write_report(tmp_path).read_text(encoding="utf-8")
    assert (tmp_path / "summary-chart.svg").is_file()
    assert '<figure class="summary-chart">' in report
    # 80 ms against a 100 ms baseline reads as 0.80x on the figure.
    assert "0.80\u00d7" in report


def test_report_prefers_a_committed_campaign_spec(tmp_path):
    spec = chain_spec()
    spec["title"] = "Committed campaign figure"
    (tmp_path / "summary-chart.json").write_text(json.dumps(spec), encoding="utf-8")
    (tmp_path / "evaluation.json").write_text(json.dumps(evaluation()), encoding="utf-8")
    report = write_report(tmp_path).read_text(encoding="utf-8")
    assert "Committed campaign figure" in report
    assert spec["points"][-1]["label"] in report


def test_report_says_why_no_figure_is_drawn(tmp_path):
    (tmp_path / "evaluation.json").write_text(
        json.dumps({"verdict": "INCONCLUSIVE", "baseline": {}, "candidate": {}}), encoding="utf-8"
    )
    report = write_report(tmp_path).read_text(encoding="utf-8")
    assert "No gain figure" in report
    assert not (tmp_path / "summary-chart.svg").exists()


def test_cli_writes_svg_and_markdown(tmp_path, capsys):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(branch_spec()), encoding="utf-8")
    destination = tmp_path / "figure.svg"
    table = tmp_path / "figure.md"
    code = summary_chart.main([str(spec), "-o", str(destination), "--markdown", str(table)])
    assert code == 0
    assert destination.read_text(encoding="utf-8").startswith("<?xml")
    assert table.is_file()
    assert "figure.svg" in capsys.readouterr().out


def test_cli_reports_a_specification_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"title": "x"}), encoding="utf-8")
    assert summary_chart.main([str(bad)]) == 2


def test_overflowing_ratios_are_rejected_not_crashed():
    spec = chain_spec()
    spec["points"][1]["values"]["C16"] = 1e308
    spec["baseline"]["metrics"]["C16"] = 1e-308
    with pytest.raises(summary_chart.SpecError, match="not finite"):
        summary_chart.build_svg(spec)


def test_overflow_in_a_report_still_produces_an_artifact(tmp_path):
    (tmp_path / "evaluation.json").write_text(
        json.dumps(
            evaluation(
                baseline={"median": 1e-308},
                candidate={"median": 1e308},
            )
        ),
        encoding="utf-8",
    )
    report = write_report(tmp_path).read_text(encoding="utf-8")
    assert "No gain figure" in report
