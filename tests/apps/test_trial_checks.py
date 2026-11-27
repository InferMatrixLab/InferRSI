"""Required trial checks govern execution, adjudication, and reporting."""

import json
import subprocess
import sys
from dataclasses import replace

import pytest

from inferrsi.apps.cli.arguments import make_spec, parser
from inferrsi.apps.legacy.evaluation import evaluate
from inferrsi.apps.legacy.reporting import write_report
from inferrsi.apps.legacy.run import run_experiment
from inferrsi.apps.views.summary_chart import SpecError, spec_from_evaluation
from inferrsi.contracts import RunSpec
from inferrsi.harness.executor.trials.external import collect_trial_checks


def evaluated_pair(checks, side="candidate"):
    spec = RunSpec(repo=".", repetitions=1, required_trial_checks=("evidence.closed",))
    trials = {
        name: [{"status": "completed", "metric": metric, "trial_checks": {"evidence.closed": True}}]
        for name, metric in (("baseline", 100), ("candidate", 80))
    }
    trials[side][0]["trial_checks"] = checks
    return evaluate(
        spec, trials["baseline"], trials["candidate"], {"status": "completed"}, {"verified": True}
    )


@pytest.mark.parametrize("value", [None, False, "true", 1, {}, []])
@pytest.mark.parametrize("side", ["baseline", "candidate"])
def test_unqualified_trial_cannot_publish_gain(value, side):
    result = evaluated_pair({"evidence.closed": value}, side)
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["improvement_pct"] is None
    assert any(f"{side} trial 1: required check evidence.closed" in r for r in result["reasons"])


@pytest.mark.parametrize("payload", [None, [], "invalid", {"evidence": {"closed": 1}}])
def test_unreadable_or_non_boolean_result_stays_unknown(tmp_path, payload):
    result = tmp_path / "result.json"
    if payload is not None:
        result.write_text(payload if isinstance(payload, str) else json.dumps(payload))
    assert collect_trial_checks({"result_path": str(result)}, ("evidence.closed",)) == {
        "evidence.closed": None
    }


def test_cli_to_trial_evidence_and_verdict(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Synthetic Contributor",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--allow-empty",
            "--quiet",
            "-m",
            "fixture",
        ],
        check=True,
    )
    args = parser().parse_args(
        [
            "run",
            "--repo",
            str(repo),
            "--baseline-command",
            "unused",
            "--candidate-command",
            "unused",
            "--repetitions",
            "1",
            "--require-trial-check",
            "evidence.closed",
            "--require-trial-check",
            "evidence.requests_complete",
            "--output-dir",
            str(tmp_path / "runs"),
        ]
    )
    spec = make_spec(args)
    assert RunSpec.from_dict(spec.to_dict()) == spec

    def command(metric, checks):
        return (
            sys.executable,
            "-c",
            "import json,sys; open(sys.argv[1], 'w').write(sys.argv[2])",
            "{result}",
            json.dumps({"metrics": {"latency_ms": metric}, "evidence": checks}),
        )

    checks = {"closed": True, "requests_complete": True}
    spec = replace(
        spec,
        baseline_command=command(100, checks),
        candidate_command=command(80, checks),
        validation_command=(sys.executable, "-c", "pass"),
    )
    path = run_experiment(spec, {"backend": "cpu"})
    read = lambda relative: json.loads((path / relative).read_text())  # noqa: E731
    assert read("evaluation.json")["verdict"] == "PASS"
    assert read("run.lock.json")["required_trial_checks"] == list(spec.required_trial_checks)
    assert read("candidate/trial-001/execution.json")["trial_checks"] == {
        "evidence.closed": True,
        "evidence.requests_complete": True,
    }
    # A successful subprocess and faster metric cannot override a missing receipt.
    path = run_experiment(replace(spec, candidate_command=command(80, {})), {"backend": "cpu"})
    result = json.loads((path / "evaluation.json").read_text())
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["improvement_pct"] is None


@pytest.mark.parametrize("keys", ["closed", ("",), ("a..b",), ("a", "a"), (1,), ([1],)])
def test_invalid_check_keys_rejected(tmp_path, keys):
    spec = RunSpec(
        repo=str(tmp_path),
        baseline_command=("true",),
        candidate_command=("true",),
        required_trial_checks=keys,
    )
    with pytest.raises(ValueError, match="required_trial_checks"):
        spec.validate()


def persist_report(directory, evaluation):
    (directory / "evaluation.json").write_text(json.dumps(evaluation), encoding="utf-8")
    return write_report(directory).read_text(encoding="utf-8")


@pytest.mark.parametrize("campaign", [False, True])
@pytest.mark.parametrize(
    ("checks", "side"),
    [
        pytest.param(checks, side, id=f"{label}-{side}")
        for checks, label in (
            ({}, "missing"),
            ({"evidence.closed": False}, "false"),
            ({"evidence.closed": "true"}, "not-boolean"),
        )
        for side in ("baseline", "candidate")
    ] + [pytest.param({"evidence.closed": True}, "candidate", id="qualified-candidate")],
)
def test_trial_evidence_controls_report_chart(tmp_path, checks, side, campaign):
    if campaign:
        historical = json.dumps(spec_from_evaluation(evaluated_pair({"evidence.closed": True})))
        specification = tmp_path / "summary-chart.json"
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
