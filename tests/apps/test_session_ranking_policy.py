"""Exercise frozen ranking through each managed CLI and its real delivery or assessor."""

import json
import sys

import pytest

from inferrsi.apps.cli import main
from inferrsi.harness import project_service, task_protocol
from inferrsi.knowledge import ranking_policy
from tests.apps import test_optimization_session as benchmark
from tests.apps import test_project_optimization as project_cli
from tests.apps.test_optimization_session import task as task
from tests.apps.test_project_optimization import project as project
from tests.fixtures import service_reuse as service
from tests.fixtures.service_reuse import campaign as campaign


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("lane", ["abba", "benchmark", "service_reuse"])
def test_managed_policy_binds_delivery_and_guards_resume(lane, request, tmp_path, capsys,
                                                       monkeypatch):
    rule = ranking_policy.managed_ranking_policy("applicability")
    command = ["campaign"]
    if lane == "abba":
        project = request.getfixturevalue("project")
        root = project[-1]
        project_cli.start(project, capsys, extra=("--ranking-policy", rule.policy_id))
        expected = rule.receipt()
        operation = ["campaign", "round", "--session", str(root), "--candidate", str(project[0]),
                     "--hypothesis", "fixed candidate"]
    elif lane == "benchmark":
        task = request.getfixturevalue("task")
        root = tmp_path / "session"
        command = ["benchmarks", "session"]
        assert main([*command, "start", task.name, "--session", str(root), "--rounds", "1",
                     "--max-minutes", "5", "--evaluation-timeout-seconds", "15", "--condition",
                     "same CPU fixture", "--evaluation-args", "", "--ranking-policy",
                     rule.policy_id]) == 0
        capsys.readouterr()
        benchmark.diagnose(root, capsys)
        expected = rule.receipt()
        operation = [*command, "recover", "--session", str(root)]
    else:
        campaign = request.getfixturevalue("campaign")
        root = campaign["root"]
        campaign["start"] += ["--ranking-policy", rule.policy_id]
        service.call(campaign, "start")
        service.diagnose(campaign)
        expected = rule.configuration()
        operation = ["campaign", "baseline", "--session", str(root)]

    plan_path = root / "plan.json"
    plan = read(plan_path)
    assert plan["ranking_policy"] == expected
    assert main([*command, "knowledge", "--session", str(root), "--query", "cgroupv2",
                 "--limit", "1", "--context-bytes", "65536"]) == 0
    context = json.loads(capsys.readouterr().out)["context"]
    assert context["request"]["ranking_policy"] == expected
    assert context["contexts"]
    retained = read(root / read(root / "state.json")["contexts"][0]["path"])
    assert retained["request"]["ranking_policy"] == expected
    if lane != "service_reuse":
        assert retained["retrieval"]["selection"]["ranking_policy"] == expected
    else:
        assert read(root / "campaign.json")["ranking_policy"] == expected
        project_service.no_fingerprints(retained)

    def refused_without_writes():
        before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
        with pytest.raises(SystemExit) as error:
            main(operation)
        assert error.value.code == 2
        assert "ranking policy" in capsys.readouterr().err.lower()
        assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before

    # JSON field order is immaterial to either integrity scheme.
    plan["ranking_policy"]["weights"] = dict(reversed(expected["weights"].items()))
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    assert main([*command, "status", "--session", str(root)]) == 0
    capsys.readouterr()
    with monkeypatch.context() as runtime:
        changed = ranking_policy.RankingPolicy(rule.policy_id, {"applicability": 4})
        runtime.setattr(ranking_policy, "MANAGED_RANKING_POLICIES", {rule.policy_id: changed})
        refused_without_writes()
    with monkeypatch.context() as runtime:
        runtime.setattr(ranking_policy, "RANKING_VERSION", expected["version"] + 1)
        refused_without_writes()
    if lane == "service_reuse":
        manifest_path = root / "campaign.json"
        manifest = read(manifest_path)
        drifted_manifest = {**manifest, "ranking_policy": changed.configuration()}
        manifest_path.write_text(json.dumps(drifted_manifest), encoding="utf-8")
        refused_without_writes()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    for incomplete in (
        {k: v for k, v in expected.items() if k != "version"},
        {**expected, "weights": {k: v for k, v in expected["weights"].items() if k != "body"}},
        {**expected, "version": True},
        {**expected, "id": "unavailable"},
        {**expected, "weights": {**expected["weights"], "unknown": 1}},
    ):
        plan["ranking_policy"] = incomplete
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        refused_without_writes()

    # A historical plan with no binding requires its original runtime.
    del plan["ranking_policy"]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    if lane == "service_reuse":
        manifest = read(root / "campaign.json")
        del manifest["ranking_policy"]
        (root / "campaign.json").write_text(json.dumps(manifest), encoding="utf-8")
    refused_without_writes()


def test_packaged_assessor_receives_identical_evidence_across_policies(task, tmp_path, capsys,
                                                                     monkeypatch):
    calls = []
    real_run = task_protocol.run

    def observe(frozen, source_hash, operation, *, launch_directory=None, **inputs):
        if operation == "assess":
            assert set(inputs) == {"directory", "settings", "execution"}
            directory = inputs["directory"]
            calls.append((source_hash, inputs["settings"], inputs["execution"]["status"],
                          (directory / "candidate.py").read_bytes(),
                          read(directory / "measurement/result.json")))
        return real_run(frozen, source_hash, operation, launch_directory=launch_directory, **inputs)

    monkeypatch.setattr(task_protocol, "run", observe)
    outcomes = []
    for name in ("default", "applicability"):
        root = tmp_path / name
        options = [] if name == "default" else ["--ranking-policy", name]
        assert main(["benchmarks", "session", "start", task.name, "--session", str(root),
                     "--rounds", "1", "--max-minutes", "5", "--evaluation-timeout-seconds", "15",
                     "--condition", "same CPU fixture", "--evaluation-args", "", *options]) == 0
        capsys.readouterr()
        assert read(root / "plan.json")["ranking_policy"] == (
            ranking_policy.managed_ranking_policy(name).receipt()
        )
        benchmark.diagnose(root, capsys)
        benchmark.submit(root, 2, capsys)
        outcomes.append(read(root / "state.json")["rounds"][0]["assessment"])
    assert len(calls) == 2 and calls[0] == calls[1]
    assert outcomes[0] == outcomes[1]
    assert outcomes[0]["verdict"] == "PASS"


def test_project_assessor_uses_the_same_measurements_quality_and_threshold(project, capsys):
    arms = []
    for name in ("default", "applicability"):
        arm = (*project[:3], project[-1].parent / name)
        project_cli.start(arm, capsys, extra=("--ranking-policy", name))
        arms.append(arm)

    evidence = []
    for arm in arms:
        code, result = project_cli.submit(arm, capsys, 20)
        assert code == 0
        observation = result["latest_observation"]
        assessment = observation["assessment"]
        assert assessment["verdict"] == "PASS" and assessment["quality_passed"]
        directory = arm[-1] / read(arm[-1] / "state.json")["rounds"][0]["path"]
        samples = {p.parent.name: read(p) for p in (directory / "execution").glob("*/result.json")}
        assert {"metric": 20} in samples.values() and {"correct": True} in samples.values()
        evidence.append((read(arm[-1] / "plan.json")["evaluation_settings"], samples,
                         assessment["verdict"], assessment["score"], assessment["quality_passed"]))
    assert evidence[0] == evidence[1]


@pytest.mark.skipif(sys.platform == "win32", reason="service fixture needs POSIX process ownership")
@pytest.mark.parametrize(("screen_reject", "quality_score", "verdict"),
                         [(True, 1, "PASS"), (False, 0, "FAIL")])
def test_service_screening_and_formal_gates_across_policies(campaign, screen_reject, quality_score,
                                                           verdict):
    config = service.settings()
    config["screening"] = {
        "command": [arg.replace("measure", "screening") for arg in config["commands"]["measure"]],
        "estimated_gain": 50,
    }
    campaign["config"].write_text(json.dumps(config), encoding="utf-8")
    arms = []
    for name in ("default", "applicability"):
        root = campaign["root"].parent / name
        start = [str(root) if arg == str(campaign["root"]) else arg for arg in campaign["start"]]
        arm = {**campaign, "root": root, "start": [*start, "--ranking-policy", name]}
        service.begin(arm)
        arms.append(arm)

    service.commit(campaign["repo"], version="fixed", a=90, screen_reject=screen_reject,
                   quality=quality_score)
    evidence = []
    for arm in arms:
        result = service.call(arm, "round", "--candidate", campaign["repo"],
                              "--hypothesis", "fixed CPU fixture")
        attempt = result["latest_observation"]
        assert attempt["execution"]["screening"]["passed"] is (not screen_reject)
        steps = attempt["execution"]["steps"]
        measured = [s["result"]["scenarios"] for s in steps if s["id"].startswith("measure-")]
        quality, = [s["result"] for s in steps if s["id"] == "quality"]
        assert len(measured) == 2 and attempt["assessment"]["verdict"] == verdict
        assert attempt["assessment"]["quality_passed"] is bool(quality_score)
        reference = read(arm["root"] / "state.json")["initial_reference"]
        quality_inputs = {key: quality[key] for key in ("dataset", "scorer", "samples", "quality")}
        evidence.append((read(arm["root"] / "frozen/evaluation.json"), measured,
                         quality["binding"]["revision"], quality["binding"]["conditions"],
                         quality_inputs, reference["measurements"], reference["quality_score"],
                         attempt["assessment"]))
    assert evidence[0] == evidence[1]
