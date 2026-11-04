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


def flat_chain_spec():
    return {
        "layout": "chain",
        "title": "Flat campaign",
        "metrics": [{"key": "m", "label": "m"}],
        "baseline": {"label": "b", "metrics": {"m": 100.0}},
        "axis": {"step": 0.25},
        "points": [
            {"label": "base", "values": {"m": 100.0}, "baseline": True},
            {"label": "step A", "values": {"m": 100.0}},
        ],
    }


def flat_branch_spec():
    return {
        "layout": "branch",
        "title": "All-flat screens",
        "metrics": [{"key": "m", "label": "m"}],
        "baseline": {"label": "b", "metrics": {"m": 100.0}},
        "trials": [
            {"group": "K", "label": "a", "values": {"m": 100.0}, "status": "flat"},
            {"group": "K", "label": "b", "values": {"m": 100.0}, "status": "flat"},
        ],
    }


@pytest.mark.parametrize("builder", [flat_chain_spec, flat_branch_spec])
def test_equal_values_still_draw_a_flat_figure(builder):
    """Two equal measurements are a valid result, not a reason to refuse."""
    spec = builder()
    svg = summary_chart.build_svg(spec)
    assert "polyline" in svg or "circle" in svg
    assert "1.00\u00d7" in svg or "+0.0%" in svg


def test_a_flat_run_draws_a_figure_through_the_report(tmp_path):
    (tmp_path / "evaluation.json").write_text(
        json.dumps(evaluation(baseline={"median": 100.0}, candidate={"median": 100.0})),
        encoding="utf-8",
    )
    report = write_report(tmp_path).read_text(encoding="utf-8")
    assert "No gain figure" not in report
    assert '<figure class="summary-chart">' in report
    assert (tmp_path / "summary-chart.svg").is_file()


@pytest.mark.parametrize("value", [0, 0.0, -1, float("inf"), float("nan"), "x", True, None])
@pytest.mark.parametrize("name", ["step", "tick"])
def test_invalid_axis_spacing_is_a_field_error(value, name):
    spec = chain_spec() if name == "step" else branch_spec()
    spec["axis"] = {name: value}
    with pytest.raises(summary_chart.SpecError, match=f"axis\\.{name}"):
        summary_chart.build_svg(spec)


@pytest.mark.parametrize("bad_axis", [{"step": 0}, {"step": "x"}, {"step": -0.5}])
def test_a_bad_spacing_never_aborts_report_generation(tmp_path, bad_axis):
    """The figure is optional, so a bad spec must not stop the report."""
    spec = chain_spec()
    spec["axis"] = bad_axis
    (tmp_path / "summary-chart.json").write_text(json.dumps(spec), encoding="utf-8")
    (tmp_path / "evaluation.json").write_text(json.dumps(evaluation()), encoding="utf-8")
    report = write_report(tmp_path).read_text(encoding="utf-8")
    assert "No gain figure" in report
    assert "axis.step" in report
    assert "<h2>Evaluation</h2>" in report


def test_dense_footers_stagger_instead_of_colliding():
    """A long chain keeps every step label, alternating rows when space is tight."""
    points = [
        {"phase": "B", "label": f"step {index}", "values": {"m": 100.0 + index * 30.0}}
        for index in range(1, 13)
    ]
    spec = {
        "layout": "chain",
        "title": "12 steps",
        "metrics": [{"key": "m", "label": "m"}],
        "baseline": {"label": "base", "metrics": {"m": 100.0}},
        "points": [{"phase": "B", "label": "base", "values": {"m": 100.0}, "baseline": True}]
        + points,
    }
    svg = summary_chart.build_svg(spec)
    root = ET.fromstring(svg)
    labels = [node for node in root.iter(f"{NS}text") if (node.text or "").startswith("step ")]
    assert len(labels) == len(points)
    # Two distinct baselines prove the rows alternate rather than overprint.
    assert len({node.get("y") for node in labels}) == 2


def test_a_short_chain_keeps_one_footer_row():
    root = ET.fromstring(summary_chart.build_svg(chain_spec()))
    labels = [
        node
        for node in root.iter(f"{NS}text")
        if node.text in {point["label"] for point in chain_spec()["points"]}
    ]
    assert len({node.get("y") for node in labels}) == 1


def test_the_right_gutter_fits_the_longest_reference_caption():
    spec = chain_spec()
    caption_text = "a very long peer target caption"
    spec["references"] = [{"label": caption_text, "metric": "C32", "value": 2400.0}]
    root = ET.fromstring(summary_chart.build_svg(spec))
    width = float(root.get("width"))
    caption = next(node for node in root.iter(f"{NS}text") if node.text == caption_text)
    assert float(caption.get("x")) + summary_chart._text_width(caption.text, 8.8) <= width
