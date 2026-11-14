"""Qualification evidence must survive CLI, execution and adjudication."""

import json
import subprocess
import sys
from dataclasses import replace

import pytest

from inferrsi.apps.legacy.evaluation import evaluate
from inferrsi.apps.legacy.run import run_experiment
from inferrsi.arguments import make_spec, parser
from inferrsi.harness.scenarios.external import collect_trial_checks
from inferrsi.runspec import RunSpec


@pytest.mark.parametrize("value", [None, False, "true", 1, {}, []])
@pytest.mark.parametrize("side", ["baseline", "candidate"])
def test_unqualified_trial_cannot_publish_gain(value, side):
    spec = RunSpec(repo=".", repetitions=1, required_trial_checks=("evidence.closed",))
    trials = {
        name: [{"status": "completed", "metric": metric, "trial_checks": {"evidence.closed": True}}]
        for name, metric in (("baseline", 100), ("candidate", 80))
    }
    trials[side][0]["trial_checks"]["evidence.closed"] = value
    result = evaluate(
        spec, trials["baseline"], trials["candidate"], {"status": "completed"}, {"verified": True}
    )
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
