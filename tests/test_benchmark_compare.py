"""Real campaign subprocesses with synthetic host receipts; no Agent/device launch."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.workflows import benchmark_compare as compare
from inferrsi.benchmark import registry
from inferrsi.harness import agent_sessions
from inferrsi.harness.optimization_session import _runtime_identity


@pytest.fixture
def experiment(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source/inferrsi"
    source.mkdir(parents=True)
    from importlib.resources import files

    actual = Path(str(files("inferrsi")))
    for name in _runtime_identity():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(actual / name, target)
    corpus = source / "knowledge/data"
    corpus.mkdir(parents=True)
    (corpus / "synthetic.txt").write_text("Test knowledge", encoding="utf-8")
    task = source / "benchmark/tasks/test-work"
    task.mkdir(parents=True)
    (task / "task.json").write_text('{"devices":1}', encoding="utf-8")
    (task / "TASK.md").write_text("Synthetic task", encoding="utf-8")
    (task / "baseline.py").write_text("FACTOR = 1\n", encoding="utf-8")
    (task / "optimization.py").write_text(
        "import json\n"
        "def validate_arguments(arguments):\n    assert not arguments\n    return {}\n"
        "def arguments(candidate, output, settings):\n"
        "    return [str(candidate), str(output)]\n"
        "def assess(directory, settings, execution):\n"
        "    return json.loads((directory/'measurement/result.json').read_text())\n",
        encoding="utf-8",
    )
    (task / "benchmark.py").write_text(
        "import json,runpy,sys\nfrom pathlib import Path\n"
        "value=runpy.run_path(sys.argv[1])['FACTOR']\n"
        "out=Path(sys.argv[2]);out.mkdir()\n"
        "if 'final' in out.parts and Path('final-score.json').exists():\n"
        "    value=json.loads(Path('final-score.json').read_text())\n"
        "(out/'result.json').write_text(json.dumps({'status':'completed','verdict':'PASS',"
        "'score':value,'speedup':value}))\n", encoding="utf-8",
    )
    monkeypatch.setattr(compare, "files", lambda _: source)
    monkeypatch.setattr(compare, "task_resources", lambda _: task)
    monkeypatch.setattr(registry, "task_resources", lambda _: task)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"tasks": ["test-work"], "rounds": 1, "max_minutes": 5,
        "evaluation_timeout_seconds": 15, "final_reserve_seconds": 15,
        "job_max_minutes": 10, "task_arguments": {"test-work": ""},
        "model": "synthetic-model", "effort": "high", "environment_id": "test-environment"}),
        encoding="utf-8")
    root = tmp_path / "comparison"
    assert main(["benchmarks", "compare", "--config", str(config), "--output", str(root)]) == 0
    initial = json.loads(capsys.readouterr().out)
    return root, initial, capsys


def operation(experiment, action, trial=None, *arguments):
    root, _, capsys = experiment
    argv = ["benchmarks", "compare", "--output", str(root), "--action", action]
    if trial:
        argv += ["--trial", trial]
    assert main([*argv, *arguments]) == 0
    return json.loads(capsys.readouterr().out)


def finish(experiment, trial, *, factor=2, final=True, model="synthetic-model", usage=True,
           final_score=None, legacy_session_id=None, python=None, environment_digest="a" * 64,
           knowledge=False):
    root, _, capsys = experiment
    dispatch = operation(experiment, "dispatch", trial)
    assert dispatch["may_create"]
    prompt = dispatch["handoff"]["prompt"]
    command = json.loads(re.search(r"Start argv .*?: (\[.*\])\n", prompt).group(1))
    receipt = root / (trial + "-receipt.json")
    receipt.write_text('{"synthetic_host_creation":true}', encoding="utf-8")
    session_id = legacy_session_id or trial
    if legacy_session_id:
        agent_sessions.bind(root / "jobs" / trial, host="synthetic", session_id=session_id,
                            receipt=receipt)
    else:
        operation(experiment, "bind", trial, "--host", "synthetic", "--session-id", session_id,
                  "--receipt", str(receipt))
    if python:
        command[command.index("--python") + 1] = python
    assert main(command[4:]) == 0
    start = json.loads(capsys.readouterr().out)
    campaign = Path(start["session"])
    assert start["next_action"] == "record_bottleneck_diagnosis"
    evidence = campaign.parent / "baseline-profile.txt"
    evidence.write_text("Synthetic workload: reference operation accounts for 80% of runtime.",
                        encoding="utf-8")
    assert main(["benchmarks", "session", "diagnose", "--session", str(campaign),
                 "--bottleneck", "Dominant reference operation", "--evidence", str(evidence)]) == 0
    diagnosis = json.loads(capsys.readouterr().out)["diagnosis"]
    if knowledge:
        assert main(["benchmarks", "session", "knowledge", "--session", str(campaign),
                     "--query", "cache per-step masks ran out of device memory",
                     "--context-bytes", "8192", "--limit", "1"]) == 0
        capture = json.loads(capsys.readouterr().out)["context"]
        assert capture["contexts"]
        binding = capture["diagnosis_binding"]
        assert binding["diagnosis_id"] == diagnosis["id"]
        assert binding["started_at"] >= diagnosis["recorded_at"]
    candidate = Path(start["working_candidate"])
    (campaign / candidate).write_text(f"FACTOR = {factor}\n", encoding="utf-8")
    assert main(["benchmarks", "session", "round", "--session", str(campaign),
                 "--candidate", str(campaign / candidate), "--hypothesis", "Synthetic hypothesis",
                 "--strategy", "Synthetic strategy"]) == 0
    capsys.readouterr()
    if final:
        if final_score is not None:
            (campaign / "final-score.json").write_text(json.dumps(final_score))
        assert main(["benchmarks", "session", "final", "--session", str(campaign)]) == 0
        capsys.readouterr()
    observation = {"host": "synthetic", "host_id": None, "session_id": session_id,
        "state": "completed", "native_receipt": {"synthetic_host_terminal": True},
        "benchmark_observation": {"model": model, "effort": "high",
            "environment_id": "test-environment", "environment_fingerprint": environment_digest,
            "knowledge_policy_violation": False}}
    if usage:
        observation.update(usage_scope="session_total", usage={"input_tokens": 100,
                                                               "output_tokens": 20})
    receipt.write_text(json.dumps(observation), encoding="utf-8")
    operation(experiment, "record", trial, "--observation", str(receipt))
    trial_result = operation(experiment, "collect", trial)["trial"]
    assert trial_result["trace"][0]["diagnosis_id"] == diagnosis["id"]
    return campaign, trial_result


def test_default_cli_requires_environment_and_discovers_both_tasks(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert main(["benchmarks", "compare"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "configuration_required"
    assert result["resolved_config"]["tasks"] == list(compare.DEFAULT_TASKS)
    assert result["resolved_config"]["rounds"] == 8
    assert not list(tmp_path.iterdir())


def test_real_default_preparation_and_off_runtime_boots(tmp_path, capsys):
    root = tmp_path / "real-corpus-comparison"
    assert main(["benchmarks", "compare", "--environment-id", "software-control",
                 "--output", str(root)]) == 0
    prepared = json.loads(capsys.readouterr().out)
    assert len(prepared["trials"]) == 4
    assert {trial["task"] for trial in prepared["trials"]} == set(compare.DEFAULT_TASKS)
    off = next(trial for trial in prepared["trials"] if trial["condition"] == "off")
    runtime = compare._io_path(root / off["workspace"] / "runtime")
    environment = {**os.environ, "PYTHONPATH": str(runtime), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-B", "-m", "inferrsi", "benchmarks", "--help"],
                            cwd=tmp_path, env=environment, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert b"compare" in result.stdout


def test_prepare_failure_does_not_publish_partial_experiment(experiment, monkeypatch):
    root, _, _ = experiment
    from inferrsi.apps.cli.arguments import parser

    def interrupted(*_):
        raise OSError("Synthetic copy failure")

    monkeypatch.setattr(compare, "_copy_runtime", interrupted)
    output = root.parent / "interrupted"
    with pytest.raises(OSError, match="copy failure"):
        compare.prepare(parser().parse_args([
            "benchmarks", "compare", "--config", str(root.parent / "config.json"),
            "--output", str(output)]))
    assert not output.exists()
    assert not list(root.parent.glob(".compare-*"))


def test_cli_overrides_config_and_reports_sources(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"rounds":2,"policy":{"tolerances":{"speedup":0.01}}}')
    from inferrsi.apps.cli.arguments import parser

    resolved, sources = compare.resolve_config(parser().parse_args([
        "benchmarks", "compare", "--config", str(config), "--rounds", "4"]))
    assert resolved["rounds"] == 4 and sources["rounds"] == "cli"
    assert resolved["policy"]["tolerances"]["speedup"] == 0.01
    assert resolved["policy"]["tolerances"]["wall_seconds"] == 0


@pytest.mark.parametrize("field,value", [("rounds", True), ("repeats", 0),
    ("max_minutes", float("inf")), ("task_arguments", []), ("unexpected", 1)])
def test_invalid_configuration_rejected(tmp_path, field, value):
    from inferrsi.apps.cli.arguments import parser

    config = tmp_path / "bad.json"
    config.write_text(json.dumps({field: value}))
    with pytest.raises(ValueError):
        compare.resolve_config(parser().parse_args([
            "benchmarks", "compare", "--config", str(config)]))


def test_preparation_separates_corpus_and_preserves_shared_runtime(experiment):
    root, initial, _ = experiment
    assert len(initial["trials"]) == 2
    assert initial["next_action"]["operation"] == "dispatch"
    for trial in initial["trials"]:
        corpus = root / trial["workspace"] / "runtime/inferrsi/knowledge/data"
        assert corpus.exists() is (trial["condition"] == "on")
    status = operation(experiment, "status")
    assert [trial["state"] for trial in status["trials"]] == ["pending", "pending"]


def test_dispatch_once_and_serial_order(experiment):
    first, second = [trial["id"] for trial in experiment[1]["trials"]]
    assert operation(experiment, "dispatch", first)["may_create"]
    assert not operation(experiment, "dispatch", first)["may_create"]
    with pytest.raises(ValueError, match="next declared"):
        compare.dispatch(experiment[0], second)
    assert operation(experiment, "dispatch", second, "--parallel")["may_create"]
    assert not operation(experiment, "dispatch", second, "--parallel")["may_create"]


def test_binding_is_idempotent_for_one_trial_and_rejects_reuse(experiment):
    root, initial, capsys = experiment
    first, second = [trial["id"] for trial in initial["trials"]]
    operation(experiment, "dispatch", first)
    operation(experiment, "dispatch", second, "--parallel")
    receipt = root / "receipt.json"
    receipt.write_text('{"synthetic_host_creation":true}', encoding="utf-8")
    arguments = ["--host", "synthetic", "--session-id", "shared", "--receipt", str(receipt)]
    first_bind = operation(experiment, "bind", first, *arguments)
    assert operation(experiment, "bind", first, *arguments) == first_bind
    with pytest.raises(SystemExit) as error:
        operation(experiment, "bind", second, *arguments, "--host-id", "local")
    assert error.value.code == 2
    assert f"already bound to trial {first}" in capsys.readouterr().err
    assert operation(experiment, "status")["trials"][1]["host"]["native_session"] is None


def test_full_pair_collects_independent_finals_trace_and_report(experiment):
    first, second = [trial["id"] for trial in experiment[1]["trials"]]
    _, on = finish(experiment, first)
    assert on["eligible"] and on["metrics"]["speedup"] == 2
    assert on["trace"][0]["strategy"] == "Synthetic strategy"
    assert on["trace"][0]["knowledge_refs"] is None
    assert on["metrics"]["tokens"] == 120
    executable = Path(sys.executable)
    python_alias = os.sep.join((str(executable.parent), ".", executable.name))
    _, off = finish(experiment, second, factor=1.5, python=python_alias)
    assert off["eligible"] and off["knowledge_deliveries"] == []
    report = operation(experiment, "report")
    assert report["assessment"]["counts"]["eligible_pairs"] == 1
    assert all(Path(path).is_file() for path in report["reports"].values())
    assert report["next_action"]["operation"] == "completed"
    assert operation(experiment, "status")["next_action"]["operation"] == "completed"


def test_report_excludes_legacy_duplicate_bindings(experiment):
    first, second = [trial["id"] for trial in experiment[1]["trials"]]
    finish(experiment, first)
    finish(experiment, second, legacy_session_id=first)
    report = operation(experiment, "report")
    assert report["assessment"]["counts"]["eligible_pairs"] == 0
    document = json.loads(Path(report["reports"]["json"]).read_text(encoding="utf-8"))
    for trial in document["trials"]:
        assert not trial["eligible"]
        assert "Native session is bound to multiple comparison trials" in trial["gaps"]


def test_report_excludes_different_observed_environments(experiment):
    first, second = [trial["id"] for trial in experiment[1]["trials"]]
    finish(experiment, first)
    finish(experiment, second, environment_digest="b" * 64)
    report = operation(experiment, "report")
    assert report["assessment"]["counts"]["eligible_pairs"] == 0
    document = json.loads(Path(report["reports"]["json"]).read_text(encoding="utf-8"))
    assert all("Paired actual Agent/environment settings differ" in trial["gaps"]
               for trial in document["trials"])


def test_missing_final_is_not_replaced_by_best_round(experiment):
    trial = experiment[1]["trials"][0]["id"]
    _, result = finish(experiment, trial, final=False)
    assert not result["eligible"]
    assert result["metrics"]["speedup"] is None
    report = operation(experiment, "report")
    assert report["assessment"]["conclusion"]["kind"] == "insufficient_evidence"


def test_valid_final_regression_remains_a_measurement(experiment):
    trial = experiment[1]["trials"][0]["id"]
    _, result = finish(experiment, trial, final_score=0.98)
    assert result["eligible"]
    assert result["metrics"]["speedup"] == 0.98
    assert result["final"]["speedup"] == 0.98
    assert result["trace"][0]["best_speedup"] == 2


def test_missing_usage_stays_unknown(experiment):
    trial = experiment[1]["trials"][0]["id"]
    _, result = finish(experiment, trial, usage=False)
    assert result["eligible"] and result["metrics"]["tokens"] is None


def test_changed_evidence_after_collection_invalidates_report(experiment):
    trial = experiment[1]["trials"][0]["id"]
    campaign, result = finish(experiment, trial)
    assert result["eligible"]
    (campaign / "frozen/baseline.py").write_text("CHANGED = True\n")
    result = operation(experiment, "report")
    document = json.loads(Path(result["reports"]["json"]).read_text(encoding="utf-8"))
    assert not document["trials"][0]["eligible"]
    assert result["assessment"]["conclusion"]["kind"] == "insufficient_evidence"


@pytest.mark.parametrize("damage", ["missing-summary", "blank-summary", "later-reference",
                                    "later-recorded-at", "knowledge-rebound"])
def test_report_rejects_incomplete_or_rebound_diagnosis(experiment, damage):
    first = experiment[1]["trials"][0]["id"]
    campaign, collected = finish(experiment, first, knowledge=damage == "knowledge-rebound")
    assert collected["eligible"]
    path = campaign / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    diagnosis = state["diagnoses"][0]
    round_record = state["rounds"][0]
    later = round_record["started_at"] + 1
    if damage == "missing-summary":
        diagnosis.pop("measurement_summary")
    elif damage == "blank-summary":
        diagnosis["measurement_summary"] = " "
    elif damage in ("later-reference", "knowledge-rebound"):
        state["diagnoses"].append({**diagnosis, "id": "diagnosis-later", "recorded_at": later})
        record = state["contexts"][0] if damage == "knowledge-rebound" else round_record
        record["diagnosis_id"] = "diagnosis-later"
    else:
        diagnosis["recorded_at"] = later
    path.write_text(json.dumps(state), encoding="utf-8")
    result = operation(experiment, "report")
    document = json.loads(Path(result["reports"]["json"]).read_text(encoding="utf-8"))
    assert not document["trials"][0]["eligible"]
    assert result["assessment"]["conclusion"]["kind"] == "insufficient_evidence"


def test_actual_model_mismatch_cannot_pass(experiment):
    trial = experiment[1]["trials"][0]["id"]
    _, result = finish(experiment, trial, model="other-model")
    assert not result["eligible"]
    assert any("model" in reason for reason in result["gaps"])


def test_changed_frozen_runtime_rejects_resume(experiment):
    root, initial, _ = experiment
    runtime = root / initial["trials"][1]["workspace"] / "runtime/inferrsi"
    (runtime / "knowledge/data").mkdir()
    (runtime / "knowledge/data/injected.txt").write_text("Unexpected corpus")
    with pytest.raises(ValueError, match="runtime changed"):
        compare.status(root)


def test_round_cannot_cite_undelivered_knowledge(experiment):
    root, _, capsys = experiment
    campaign = root / "citation-control"
    assert main(["benchmarks", "session", "start", "test-work", "--session", str(campaign),
                 "--rounds", "1", "--max-minutes", "5", "--evaluation-timeout-seconds", "15",
                 "--condition", "citation-control", "--evaluation-args", ""]) == 0
    capsys.readouterr()
    round_args = ["benchmarks", "session", "round", "--session", str(campaign),
                  "--candidate", str(campaign / "work/candidate.py"), "--hypothesis", "Test"]
    knowledge_args = ["benchmarks", "session", "knowledge", "--session", str(campaign),
                      "--query", "implementation option", "--context-bytes", "1024"]
    for arguments in (knowledge_args, round_args):
        with pytest.raises(SystemExit) as error:
            main(arguments)
        assert error.value.code == 2
        assert "Record measured bottleneck evidence" in capsys.readouterr().err
    evidence = root / "control-profile.txt"
    evidence.write_text("Synthetic measurement: reference operation took 4 ms.", encoding="utf-8")
    assert main(["benchmarks", "session", "diagnose", "--session", str(campaign),
                 "--bottleneck", "Reference operation", "--evidence", str(evidence)]) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit) as error:
        main([*round_args, "--knowledge-ref", "knowledge/missing.json"])
    assert error.value.code == 2
    assert "delivered context" in capsys.readouterr().err
    assert json.loads((campaign / "state.json").read_text())["rounds"] == []
