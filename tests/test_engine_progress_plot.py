"""Check the copyable chart's data contract without requiring Matplotlib in CI."""

import csv
import importlib.util
from pathlib import Path

import pytest

ENGINE_TEMPLATE = Path(__file__).resolve().parents[1] / "docs/template/engine-repo"
SPEC = importlib.util.spec_from_file_location(
    "engine_progress_plot", ENGINE_TEMPLATE / "tools/plot_optimization_progress.py"
)
plot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plot)


def write_series(tmp_path, **changes):
    rows = [
        dict(
            day="0",
            phase="Bring-up",
            optimization="Baseline",
            throughput="100",
            verdict="PASS",
            evidence="evidence/example/results/baseline.json",
        ),
        dict(
            day="1",
            phase="Kernels",
            optimization="Trial",
            throughput="120",
            verdict="INCONCLUSIVE",
            evidence="evidence/example/results/trial.json",
        ),
    ]
    rows[1].update(changes)
    path = tmp_path / "progress.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_example_is_explicitly_illustrative_and_retains_negative_results():
    path = ENGINE_TEMPLATE / "docs/figures/optimization-progress.example.csv"
    with pytest.raises(ValueError, match="evidence"):
        plot.read_points(path)
    points = plot.read_points(path, illustrative=True)
    gains = [point["gain"] for point in points]
    assert gains == [1.0, 1.2, 1.4, 1.35, 1.8, 2.1, 2.1, 2.4]
    assert {point["verdict"] for point in points} == {"INCONCLUSIVE"}


def test_regression_and_failed_quality_are_not_promoted(tmp_path):
    points = plot.read_points(write_series(tmp_path, throughput="80", verdict="FAIL"))
    assert points[-1]["gain"] == 0.8
    assert points[-1]["verdict"] == "FAIL"


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"day": "0"}, "strictly increase"),
        ({"day": "nan"}, "finite"),
        ({"throughput": "0"}, "positive"),
        ({"throughput": "-2"}, "positive"),
        ({"throughput": "inf"}, "finite"),
        ({"throughput": "not measured"}, "numeric"),
        ({"phase": ""}, "phase"),
        ({"verdict": "validated"}, "PASS, FAIL or INCONCLUSIVE"),
        ({"evidence": ""}, "evidence"),
    ],
)
def test_invalid_measurement_rows_are_rejected(tmp_path, changes, reason):
    with pytest.raises(ValueError, match=reason):
        plot.read_points(write_series(tmp_path, **changes))


def test_baseline_and_schema_are_required(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("day,phase,optimization,throughput,verdict,evidence\n", encoding="utf-8")
    with pytest.raises(ValueError, match="at least"):
        plot.read_points(path)
    path.write_text("day,throughput\n0,100\n", encoding="utf-8")
    with pytest.raises(ValueError, match="requires columns"):
        plot.read_points(path)
