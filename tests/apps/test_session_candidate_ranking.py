"""Freeze, deliver and resume an unregistered candidate ranking rule in each managed lane."""

import json

import pytest

from inferrsi.apps.cli import main
from inferrsi.knowledge import ranking_policy
from tests.apps import test_optimization_session as benchmark
from tests.apps import test_project_optimization as project_cli
from tests.apps.test_optimization_session import session as session  # noqa: F401
from tests.apps.test_optimization_session import task as task
from tests.apps.test_project_optimization import project as project
from tests.fixtures import service_reuse as service
from tests.fixtures.service_reuse import campaign as campaign

CANDIDATE = ranking_policy.RankingPolicy("trial-applicability-4", {"applicability": 4, "body": 0.5})


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_rule(directory, document):
    path = directory / "candidate-rule.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def files(root):
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def start_benchmark(task, root, *options):
    return main(["benchmarks", "session", "start", task.name, "--session", str(root),
                 "--rounds", "1", "--max-minutes", "5", "--evaluation-timeout-seconds", "15",
                 "--condition", "same CPU fixture", "--evaluation-args", "", *options])


@pytest.mark.parametrize("lane", ["abba", "benchmark", "service_reuse"])
def test_candidate_rule_is_frozen_delivered_and_resumed_without_registry(
    lane, request, tmp_path, capsys, monkeypatch,
):
    options = ("--ranking-policy-file", str(write_rule(tmp_path, CANDIDATE.receipt())))
    command = ["campaign"]
    if lane == "abba":
        project = request.getfixturevalue("project")
        root = project[-1]
        project_cli.start(project, capsys, extra=options)
        expected = CANDIDATE.receipt()
        operation = ["campaign", "round", "--session", str(root), "--candidate", str(project[0]),
                     "--hypothesis", "fixed candidate"]
    elif lane == "benchmark":
        task = request.getfixturevalue("task")
        root = tmp_path / "session"
        command = ["benchmarks", "session"]
        assert start_benchmark(task, root, *options) == 0
        capsys.readouterr()
        benchmark.diagnose(root, capsys)
        expected = CANDIDATE.receipt()
        operation = [*command, "recover", "--session", str(root)]
    else:
        campaign = request.getfixturevalue("campaign")
        root = campaign["root"]
        campaign["start"] += list(options)
        service.call(campaign, "start")
        service.diagnose(campaign)
        expected = CANDIDATE.configuration()
        operation = ["campaign", "baseline", "--session", str(root)]
        manifest = read(root / "campaign.json")
        assert manifest["ranking_policy"] == expected
        assert manifest["ranking_policy_source"] == "configuration"

    plan_path = root / "plan.json"
    plan = read(plan_path)
    assert plan["ranking_policy"] == expected
    assert plan["ranking_policy_source"] == "configuration"

    # Resume and delivery rebuild the rule from the plan, not from the installed registry.
    monkeypatch.setattr(ranking_policy, "MANAGED_RANKING_POLICIES", {})
    assert main(["find", "cgroupv2", "--session", str(root), "--limit", "1"]) == 0
    found = json.loads(capsys.readouterr().out)
    assert main(found["items"][0]["read_args"]) == 0
    returned = json.loads(capsys.readouterr().out)
    assert read(root / returned["reference"]["path"])["request"]["ranking_policy"] == expected
    retained = read(root / read(root / "state.json")["contexts"][0]["path"])
    assert retained["request"]["ranking_policy"] == expected
    if lane != "service_reuse":
        assert retained["retrieval"]["selection"]["ranking_policy"] == expected
    assert main([*command, "status", "--session", str(root)]) == 0
    capsys.readouterr()

    def refused_without_writes():
        before = files(root)
        with pytest.raises(SystemExit) as error:
            main(operation)
        assert error.value.code == 2
        assert "ranking policy" in capsys.readouterr().err.lower()
        assert files(root) == before

    original = plan_path.read_bytes()
    other = ranking_policy.RankingPolicy(CANDIDATE.policy_id, {"applicability": 5})
    for tampered in (
        {**plan, "ranking_policy": {**expected, "weights": other.configuration()["weights"]}},
        {**plan, "ranking_policy_source": "registry-free"},
        {k: v for k, v in plan.items() if k != "ranking_policy_source"},
    ):
        plan_path.write_text(json.dumps(tampered), encoding="utf-8")
        refused_without_writes()
    plan_path.write_bytes(original)
    with monkeypatch.context() as runtime:
        runtime.setattr(ranking_policy, "RANKING_VERSION", expected["version"] + 1)
        refused_without_writes()


@pytest.mark.parametrize("document, message", [
    ({**CANDIDATE.receipt(), "id": "default"}, "registered name"),
    (ranking_policy.RankingPolicy("applicability", {"body": 2}).configuration(), "registered name"),
    ({**CANDIDATE.receipt(), "weights": {**CANDIDATE.configuration()["weights"], "body": -1}},
     "weight for body"),
    ({**CANDIDATE.receipt(), "weights": {**CANDIDATE.configuration()["weights"], "body": 2.0}},
     "digest does not match"),
    ({**CANDIDATE.configuration(), "version": 2}, "version 2 differs"),
    ([CANDIDATE.configuration()], "JSON object"),
])
def test_invalid_candidate_rule_is_rejected_before_any_session_write(
    task, tmp_path, capsys, document, message,
):
    root = tmp_path / "session"
    with pytest.raises(SystemExit) as error:
        start_benchmark(task, root, "--ranking-policy-file", str(write_rule(tmp_path, document)))
    assert error.value.code == 2 and message in capsys.readouterr().err
    assert not root.exists()


def test_candidate_rule_file_must_be_json_and_exclusive_of_a_name(task, tmp_path, capsys):
    root = tmp_path / "session"
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not json", encoding="utf-8")
    for options, message in (
        (("--ranking-policy-file", str(malformed)), "JSON object"),
        (("--ranking-policy-file", str(tmp_path / "missing.json")), "regular JSON file"),
        (("--ranking-policy", "applicability", "--ranking-policy-file", str(malformed)),
         "not allowed with argument"),
    ):
        with pytest.raises(SystemExit) as error:
            start_benchmark(task, root, *options)
        assert error.value.code == 2 and message in capsys.readouterr().err
        assert not root.exists()
