"""Reports must obey the evaluator's trial checks before plotting either input."""

import json

import pytest

from inferrsi.apps.legacy.evaluation import evaluate
from inferrsi.apps.legacy.reporting import write_report
from inferrsi.runspec import RunSpec
from inferrsi.summary_chart import SpecError, spec_from_evaluation


def evaluated_pair(checks, side="candidate"):
    spec = RunSpec(repo=".", repetitions=1, required_trial_checks=("evidence.closed",))
    arms = {
        label: [{"status": "completed", "metric": value,
                 "trial_checks": {"evidence.closed": True}}]
        for label, value in (("baseline", 100), ("candidate", 80))
    }
    arms[side][0]["trial_checks"] = checks
    return evaluate(spec, arms["baseline"], arms["candidate"],
                    {"status": "completed"}, {"verified": True})


def persist_report(directory, evaluation):
    (directory / "evaluation.json").write_text(json.dumps(evaluation), encoding="utf-8")
    return write_report(directory).read_text(encoding="utf-8")


@pytest.mark.parametrize("campaign", [False, True])
@pytest.mark.parametrize("side", ["baseline", "candidate"])
@pytest.mark.parametrize("checks", [
    {}, {"evidence.closed": False}, {"evidence.closed": "true"}, {"evidence.closed": True},
], ids=["missing", "false", "not-boolean", "qualified"])
def test_trial_evidence_controls_report_chart(tmp_path, checks, side, campaign):
    historical = json.dumps(spec_from_evaluation(evaluated_pair({"evidence.closed": True})))
    specification = tmp_path / "summary-chart.json"
    if campaign:
        specification.write_text(historical, encoding="utf-8")

    result = evaluated_pair(checks, side)
    html = persist_report(tmp_path, result)
    svg = tmp_path / "summary-chart.svg"
    if checks.get("evidence.closed") is True:
        assert result["verdict"] == "PASS"
        assert "0.80×" in html
        assert "0.80×" in svg.read_text(encoding="utf-8")
    else:
        assert result["verdict"] == "INCONCLUSIVE"
        assert result["improvement_pct"] is None
        assert "raw measurements" in html
        assert "required trial checks" in html
        assert "<svg" not in html
        assert "0.80×" not in html
        assert not svg.exists()
        assert "&quot;median&quot;: 100" in html
        assert "&quot;median&quot;: 80" in html
    if campaign:
        assert specification.read_text(encoding="utf-8") == historical


@pytest.mark.parametrize("campaign", [False, True])
def test_rebuilding_unqualified_report_removes_previous_chart(tmp_path, campaign):
    qualified = evaluated_pair({"evidence.closed": True})
    if campaign:
        (tmp_path / "summary-chart.json").write_text(
            json.dumps(spec_from_evaluation(qualified)), encoding="utf-8"
        )
    assert "0.80×" in persist_report(tmp_path, qualified)
    assert (tmp_path / "summary-chart.svg").is_file()

    html = persist_report(tmp_path, evaluated_pair({}))
    assert "<svg" not in html
    assert 'href="./summary-chart.svg"' not in html
    assert not (tmp_path / "summary-chart.svg").exists()


def test_direct_chart_conversion_requires_qualified_trial_evidence():
    result = evaluated_pair({})
    with pytest.raises(SpecError, match="required trial checks"):
        spec_from_evaluation(result)
