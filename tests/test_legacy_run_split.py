# Acceptance for the old run/evaluate split: the removed Harness edges, the
# injected runner ports, Benchmark's own v0 rules, and the composed old entries.

import importlib
import importlib.util
import inspect
import json
import pickle
import subprocess
import sys
import time
from dataclasses import fields

import pytest

from inferrsi.apps.legacy import evaluation as legacy_evaluation
from inferrsi.apps.legacy import reporting as legacy_reporting
from inferrsi.apps.legacy import run as legacy_run
from inferrsi.benchmark import legacy_run_v0, metrics, sampling
from inferrsi.contracts import RunSpec, claim
from inferrsi.harness import atomic_json
from inferrsi.harness.runner import run_experiment
from inferrsi.harness.scenarios.external import execute_trial
from inferrsi.infra import artifacts, targets
from tests._gate_policy_support import ROOT, _scan, _walk

GRAPH = _scan(ROOT, frozenset())
# The local process domain that Harness still borrows until it owns that code.
PROCESS_DOMAIN = {
    "inferrsi.infra", "inferrsi.infra.executors", "inferrsi.infra.executors.local",
}


def _outside(module: str, *prefixes: str) -> set[str]:
    return {name for name in GRAPH.edges[module] if name.startswith(prefixes)}


def _reached(module: str) -> set[str]:
    return set(_walk(module, GRAPH.edges, lambda node: False)[0])


def test_moved_harness_modules_are_gone_without_shells():
    for name in ("evaluation", "reporting", "scenarios.media"):
        assert f"inferrsi.harness.{name}" not in GRAPH.trees


def test_runner_and_external_lost_their_model_artifact_and_target_edges():
    assert _outside("inferrsi.harness.runner", "inferrsi.model", "inferrsi.infra") == set()
    assert _outside("inferrsi.harness.scenarios.external", "inferrsi.model") == set()
    assert _outside("inferrsi.harness.scenarios.external", "inferrsi.infra") <= PROCESS_DOMAIN
    assert _outside("inferrsi.harness.atomic_json", "inferrsi.") == {"inferrsi.harness"}
    # Transitively the old chain keeps only the process domain, and no new core.
    for module in ("inferrsi.harness.runner", "inferrsi.harness.scenarios.external"):
        reached = _reached(module)
        assert {n for n in reached if n.startswith(("inferrsi.model", "inferrsi.infra"))} <= (
            PROCESS_DOMAIN
        )
        assert not {n for n in reached if n.startswith(
            ("inferrsi.benchmark", "inferrsi.apps", "inferrsi.knowledge"))}


def test_benchmark_rules_import_only_the_metric_contract():
    # #498 slice 1 moved the metric contract into Benchmark.
    assert _outside("inferrsi.benchmark.legacy_run_v0", "inferrsi.") == {
        "inferrsi.benchmark", "inferrsi.benchmark.metrics",
    }
    assert _outside("inferrsi.benchmark.sampling", "inferrsi.") == {"inferrsi.benchmark"}
    # The v0 labels are Benchmark's own and equal the legacy vocabulary.
    assert {legacy_run_v0.PASS, legacy_run_v0.FAIL, legacy_run_v0.INCONCLUSIVE} == {
        verdict.value for verdict in claim.Verdict
    }


def test_runner_ports_are_all_injected():
    parameters = inspect.signature(run_experiment).parameters
    for name in ("execute", "snapshot", "assess", "report"):
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert parameters[name].default is inspect.Parameter.empty


def test_runner_records_the_injected_assessment_without_judging(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    spec = RunSpec(
        repo=str(repo), baseline_command=("baseline",), candidate_command=("candidate",),
        validation_command=("validate",), repetitions=1, output_dir=str(tmp_path / "runs"),
        max_minutes=1,
    )
    received, reported = [], []

    def execute(command, cwd, trial_dir, deadline, metric_key):
        trial_dir.mkdir(parents=True)  # The real executor creates the trial directory.
        return {"status": "completed", "command": list(command), "metric_key": metric_key}

    def assess(baseline, candidate, validation, integrity, error):
        received.append((baseline, candidate, validation, integrity, error))
        return {"verdict": "ANY-LABEL", "note": "from the injected port"}

    run_dir = run_experiment(
        spec, {}, execute=execute,
        snapshot=lambda path, exclude: {"available": True, "snapshot_hash": "fixed"},
        assess=assess, report=reported.append,
    )
    (baseline, candidate, validation, integrity, error), = received
    assert [trial["command"] for trial in baseline + candidate] == [["baseline"], ["candidate"]]
    assert validation["metric_key"] is None and error is None
    assert integrity == {"verified": True, "reason": "Git source snapshots unchanged",
                         "command_checks": 3}
    assert json.loads((run_dir / "evaluation.json").read_text(encoding="utf-8")) == {
        "verdict": "ANY-LABEL", "note": "from the injected port",
    }
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert (status["state"], status["verdict"]) == ("completed", "ANY-LABEL")
    assert reported == [run_dir]


def _result_command(document: object) -> tuple[str, ...]:
    code = "import sys; open(sys.argv[1], 'w', encoding='utf-8').write(sys.argv[2])"
    return (sys.executable, "-c", code, "{result}", json.dumps(document))


def test_harness_trial_needs_the_callers_metric_validation(tmp_path):
    trial = tmp_path / "trial"
    with pytest.raises(TypeError, match="metric validation"):
        execute_trial(_result_command({}), tmp_path, trial, time.monotonic() + 30, "metrics.x")
    assert not trial.exists()  # Refused before any process started.


def test_harness_trial_records_what_the_injected_validation_returns(tmp_path):
    seen = []

    def accept(document, key):
        seen.append((document, key))
        return 7.5

    def reject(document, key):
        raise ValueError("outside the contract")

    command, deadline = _result_command({"raw": 3}), time.monotonic() + 60
    accepted = execute_trial(command, tmp_path, tmp_path / "a", deadline, "raw", metric=accept)
    rejected = execute_trial(command, tmp_path, tmp_path / "b", deadline, "raw", metric=reject)
    unread = execute_trial(command, tmp_path, tmp_path / "c", deadline, None)
    assert seen == [({"raw": 3}, "raw")]
    assert (accepted["metric"], accepted["metric_error"]) == (7.5, None)
    assert (rejected["metric"], rejected["metric_error"]) == (None, "outside the contract")
    assert (unread["metric"], unread["metric_error"]) == (None, None)
    for name, record in (("a", accepted), ("b", rejected), ("c", unread)):
        assert json.loads((tmp_path / name / "execution.json").read_text("utf-8")) == record


@pytest.mark.parametrize("value", [
    {}, [], {"verdict": "PASS", "values": [1.0, 2, None, True]},
    {"文本": "未转义 ✓", "nested": {"path": "C:\\runs\\a", "quote": "\"", "line": "a\nb"}},
    {"float": 1e-308, "large": 1e308, "negative": -0.0},
])
def test_harness_writer_bytes_equal_the_infra_writer(tmp_path, value):
    atomic_json.atomic_write_json(tmp_path / "harness.json", value)
    artifacts.atomic_write_json(tmp_path / "infra.json", value)
    assert (tmp_path / "harness.json").read_bytes() == (tmp_path / "infra.json").read_bytes()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["harness.json", "infra.json"]


def test_sampling_sha256_matches_the_infra_hasher(tmp_path):
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"inferrsi-b01-sampling-pin")
    assert sampling._sha256(path) == artifacts.sha256(path)


def test_harness_writer_rejects_nan_and_leaves_no_file(tmp_path):
    for writer in (atomic_json.atomic_write_json, artifacts.atomic_write_json):
        with pytest.raises(ValueError):
            writer(tmp_path / "value.json", {"metric": float("nan")})
    assert list(tmp_path.iterdir()) == []


def _trials(value: float) -> list[dict]:
    return [{"status": "completed", "metric": value}]


def test_old_evaluate_entry_converts_the_spec_and_returns_the_benchmark_result():
    spec = RunSpec(repo=".", repetitions=1, metric_key="m.latency", metric_unit="s",
                   comparison_scope="scope", direction="maximize", min_improvement_pct=5.0,
                   required_trial_checks=("evidence.closed",))
    rules = legacy_evaluation.run_rules(spec)
    assert {field.name: getattr(rules, field.name) for field in fields(rules)} == {
        "repetitions": 1, "required_trial_checks": ("evidence.closed",),
        "metric_key": "m.latency", "metric_unit": "s", "comparison_scope": "scope",
        "direction": "maximize", "min_improvement_pct": 5.0,
    }
    arguments = (_trials(100), _trials(120), {"status": "completed"}, {"verified": True})
    assert legacy_evaluation.evaluate(spec, *arguments) == legacy_run_v0.evaluate(
        rules, *arguments
    )


def test_run_error_is_missing_evidence_listed_last():
    rules = legacy_evaluation.run_rules(RunSpec(repo=".", repetitions=1))
    arguments = (_trials(100), _trials(80), {"status": "completed"}, {"verified": True})
    assert legacy_run_v0.evaluate(rules, *arguments)["verdict"] == "PASS"
    assert legacy_run_v0.evaluate(rules, *arguments, run_error="")["verdict"] == "PASS"
    stopped = legacy_run_v0.evaluate(rules, *arguments, run_error="executor unavailable")
    assert (stopped["verdict"], stopped["reasons"]) == ("INCONCLUSIVE", ["executor unavailable"])
    regressed = legacy_run_v0.evaluate(
        rules, _trials(100), _trials(120), {"status": "completed"}, {"verified": True},
        run_error="interrupted by user",
    )
    assert regressed["verdict"] == "INCONCLUSIVE"
    assert "measured gain" in regressed["reasons"][0]
    assert regressed["reasons"][-1] == "interrupted by user"


def test_trial_metric_applies_the_contract_to_any_reader():
    assert legacy_run_v0.trial_metric({"metrics": {"latency_ms": 5}}, "metrics.latency_ms") == 5.0
    assert legacy_run_v0.trial_metric({}, "k", reader=lambda document, key: 2) == 2.0
    with pytest.raises(ValueError, match="finite and positive"):
        legacy_run_v0.trial_metric({}, "k", reader=lambda document, key: 0.0)


@pytest.mark.parametrize("name", ["evaluation", "execution", "reporting"])
def test_retired_root_entries_no_longer_import(name):
    # #412 R1 deleted the three root forwarders with no alias behind them.
    retired = f"inferrsi.{name}"
    assert importlib.util.find_spec(retired) is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(retired)
    assert retired not in sys.modules
    assert not hasattr(sys.modules["inferrsi"], name)


def test_canonical_entries_hold_the_objects_the_root_entries_forwarded():
    assert legacy_evaluation._summary is legacy_run_v0._summary
    assert legacy_evaluation.read_metric is metrics.read_metric
    assert legacy_evaluation.evaluate.__module__ == "inferrsi.apps.legacy.evaluation"
    assert legacy_reporting.write_report.__module__ == "inferrsi.apps.legacy.reporting"
    assert legacy_run.execute_trial.__module__ == "inferrsi.apps.legacy.run"
    assert legacy_run.repository_identity is targets.repository_identity
    assert legacy_run.write_report is legacy_reporting.write_report
    # The two-argument entry that root ``execution`` defined is this one function now.
    assert legacy_run.run_experiment.__module__ == "inferrsi.apps.legacy.run"
    parameters = inspect.signature(legacy_run.run_experiment).parameters
    assert list(parameters) == ["spec", "environment", "execute", "snapshot"]
    for port in ("execute", "snapshot"):
        assert parameters[port].kind is inspect.Parameter.KEYWORD_ONLY
        assert parameters[port].default is None
    # A pickle that names the retired entry no longer loads; the canonical one does.
    with pytest.raises(ModuleNotFoundError):
        pickle.loads(b"cinferrsi.execution\nrun_experiment\n.")
    assert pickle.loads(pickle.dumps(legacy_run.run_experiment)) is legacy_run.run_experiment


def _port_spec(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return RunSpec(
        repo=str(repo), baseline_command=("baseline",), candidate_command=("candidate",),
        repetitions=1, output_dir=str(tmp_path / "runs"), max_minutes=1,
    )


def test_two_argument_run_reads_both_ports_from_the_module_on_each_call(tmp_path, monkeypatch):
    # The retired root entry looked up its executor and snapshot when it was called.
    # The canonical entry keeps that: replacing either name here changes the next run.
    calls = []

    def execute(command, cwd, trial_dir, deadline, metric_key):
        trial_dir.mkdir(parents=True)
        calls.append(("execute", tuple(command)))
        return {"status": "completed", "command": list(command), "metric": 1.0}

    def snapshot(path, exclude=None):
        calls.append(("snapshot", str(path)))
        return {"available": True, "snapshot_hash": "fixed"}

    monkeypatch.setattr(legacy_run, "execute_trial", execute)
    monkeypatch.setattr(legacy_run, "repository_identity", snapshot)
    monkeypatch.setattr(legacy_run, "write_report", lambda run_dir: None)
    run_dir = legacy_run.run_experiment(_port_spec(tmp_path), {"backend": "cpu"})
    assert [call for call in calls if call[0] == "execute"] == [
        ("execute", ("baseline",)), ("execute", ("candidate",)),
    ]
    assert [call for call in calls if call[0] == "snapshot"]
    assert json.loads((run_dir / "status.json").read_text(encoding="utf-8"))["state"] == (
        "completed"
    )


def test_an_explicit_port_wins_over_the_module_name(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("the module-level port must not run when one is passed")

    seen = []

    def execute(command, cwd, trial_dir, deadline, metric_key):
        trial_dir.mkdir(parents=True)
        seen.append(tuple(command))
        return {"status": "completed", "command": list(command), "metric": 1.0}

    monkeypatch.setattr(legacy_run, "execute_trial", forbidden)
    monkeypatch.setattr(legacy_run, "repository_identity", forbidden)
    monkeypatch.setattr(legacy_run, "write_report", lambda run_dir: None)
    legacy_run.run_experiment(
        _port_spec(tmp_path), {}, execute=execute,
        snapshot=lambda path, exclude=None: {"available": True, "snapshot_hash": "fixed"},
    )
    assert seen == [("baseline",), ("candidate",)]


def test_a_failing_module_level_executor_is_recorded_not_swallowed(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("executor unavailable")

    monkeypatch.setattr(legacy_run, "execute_trial", unavailable)
    monkeypatch.setattr(
        legacy_run, "repository_identity",
        lambda path, exclude=None: {"available": True, "snapshot_hash": "fixed"},
    )
    run_dir = legacy_run.run_experiment(_port_spec(tmp_path), {"backend": "cpu"})
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    evaluation = json.loads((run_dir / "evaluation.json").read_text(encoding="utf-8"))
    assert status["state"] == "failed"
    assert evaluation["verdict"] == "INCONCLUSIVE"
    assert "executor unavailable" in evaluation["reasons"]


def test_cli_import_loads_no_benchmark_and_no_old_run_composition():
    # Only the `run` command loads the old run and its Benchmark gates.
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import inferrsi.apps.cli; "
        "print(sorted(name for name in sys.modules if name.startswith(('inferrsi.benchmark', "
        "'inferrsi.execution', 'inferrsi.evaluation', 'inferrsi.reporting', "
        "'inferrsi.inspection', 'inferrsi.apps.legacy.run', "
        "'inferrsi.apps.legacy.evaluation'))))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(ROOT.parent)], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"
