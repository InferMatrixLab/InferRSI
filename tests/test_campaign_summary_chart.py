"""The campaign summary chart is generic, validated and reproducible."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tools import campaign_summary_chart as chart

PROJECT = Path(__file__).resolve().parents[1]
EXAMPLE = PROJECT / "evidence" / "_template" / "results" / "summary-chart.example.json"
NS = "{http://www.w3.org/2000/svg}"


def spec():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def svg_root(specification):
    return ET.fromstring(chart.build_svg(specification))


def texts(root):
    return [node.text for node in root.iter(f"{NS}text") if node.text]


def test_example_renders_every_trial_with_its_gain():
    specification = spec()
    root = svg_root(specification)
    baseline = specification["baseline"]["metrics"]
    rendered = texts(root)
    for trial in specification["trials"]:
        assert trial["label"] in rendered
        gain = trial["values"]["C32"] / baseline["C32"] - 1
        assert any(text.startswith(f"{gain * 100:+.1f}%") for text in rendered)


def test_no_gain_and_negative_trials_are_marked_not_hidden():
    root = svg_root(spec())
    rendered = texts(root)
    # A flat screen and a screen that loses at C16 both carry the x marker.
    assert sum(text.endswith("×") for text in rendered) == 2
    # The label metric gains at C32; the C16 loss is spelled out beside it.
    assert any("-4.0%" in text for text in rendered)


def test_axis_spans_every_value_including_references():
    specification = spec()
    root = svg_root(specification)
    ticks = [t for t in texts(root) if t.endswith("%")]
    assert ticks[0].startswith("-")
    gain = specification["references"][0]["value"] / specification["baseline"]["metrics"]["C32"]
    assert max(float(t.rstrip("%")) for t in ticks) >= (gain - 1) * 100


def test_markdown_table_carries_the_same_values():
    specification = spec()
    table = chart.build_markdown(specification)
    for trial in specification["trials"]:
        assert trial["label"] in table
    assert table.count("\n| ") == len(specification["trials"]) + 2


def test_malformed_specs_fail_with_a_message():
    broken = spec()
    del broken["baseline"]["metrics"]["C16"]
    with pytest.raises(chart.SpecError, match="baseline.metrics"):
        chart.build_svg(broken)

    duplicate = spec()
    duplicate["trials"].append(dict(duplicate["trials"][0]))
    with pytest.raises(chart.SpecError, match="duplicate trial"):
        chart.build_svg(duplicate)

    unknown_metric = spec()
    unknown_metric["label_metric"] = "C128"
    with pytest.raises(chart.SpecError, match="label_metric"):
        chart.build_svg(unknown_metric)


def test_cli_writes_svg_and_markdown(tmp_path, capsys):
    destination = tmp_path / "figure.svg"
    table = tmp_path / "figure.md"
    code = chart.main([str(EXAMPLE), "-o", str(destination), "--markdown", str(table)])
    assert code == 0
    assert destination.read_text(encoding="utf-8").startswith("<?xml")
    assert table.read_text(encoding="utf-8").startswith("**")
    assert "figure.svg" in capsys.readouterr().out


def test_cli_reports_a_specification_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"title": "x"}), encoding="utf-8")
    assert chart.main([str(bad)]) == 2
