import json
import time
from types import SimpleNamespace

import pytest

from inferrsi.apps.cli.arguments import parser
from inferrsi.apps.search_benchmarks import EngineEvaluator, SkillEvaluator
from inferrsi.apps.speculative_search import command
from inferrsi.benchmark.improvement import SelectionPolicy


def skill_report(base_tokens=100, tokens=80, *, verdict="PASS", outcome="unchanged"):
    def trial(count, result):
        return {
            "verdict": result,
            "elapsed_seconds": 1,
            "observations": {
                "usage": None
                if count is None
                else {"input_tokens": count, "output_tokens": 0, "cached_input_tokens": 0},
                "tool_calls": 0,
            },
        }

    return {
        "status": {"execution_state": "completed"},
        "pairs": [
            {
                "baseline": trial(base_tokens, "PASS"),
                "candidate": trial(tokens, verdict),
                "outcome": outcome,
            }
        ],
    }


@pytest.mark.parametrize(
    "report,split,verdict",
    [
        (skill_report(), "development", "PASS"),
        (skill_report(tokens=1, verdict="FAIL", outcome="regression"), "development", "FAIL"),
        (skill_report(base_tokens=None), "development", "INCONCLUSIVE"),
        (skill_report(tokens=None), "development", "INCONCLUSIVE"),
        (skill_report(tokens=101), "holdout", "FAIL"),
        (skill_report(tokens=100), "holdout", "PASS"),
    ],
)
def test_skill_quality_unknown_usage_and_independent_holdout_gates(report, split, verdict):
    comparator = SimpleNamespace(identity="explicit-comparator", run=lambda *a, **k: (report, True))
    evaluator = SkillEvaluator(
        comparator, split=split, policy=SelectionPolicy(1, 0), token_cap=1000, task_count=1
    )
    result = evaluator.evaluate(None, "evaluation", None, time.time() + 1)
    assert result["verdict"] == verdict
    assert (result["objective"] is not None) == (verdict == "PASS")


def test_engine_uses_frozen_complete_task_protocol_and_rejects_mutation(tmp_path):
    evaluator = EngineEvaluator(
        "qwen21-denoise-npu",
        tmp_path / "frozen",
        arguments=["--pairs", "1", "--samples", "1", "--warmups", "0"],
    )
    assert evaluator.plan["evaluation_settings"] == {"pairs": 1, "samples": 1, "warmups": 0}
    (evaluator.frozen / "reference.py").write_text("changed reference")
    with pytest.raises(ValueError, match="resources changed"):
        evaluator.evaluate(tmp_path, "evaluation", tmp_path / "output", time.time() + 1)
    assert not (tmp_path / "output").exists()


def test_cli_requires_explicit_shared_store_and_read_commands_do_not_create_one(tmp_path):
    args = parser().parse_args(["search", "status", "--session", str(tmp_path / "absent")])
    with pytest.raises(FileNotFoundError):
        command(args)
    assert not (tmp_path / "absent").exists()
    with pytest.raises(SystemExit):
        parser().parse_args(["search", "engine", "--session", str(tmp_path / "run")])


def test_engine_rejects_frozen_resource_mutation_during_evaluation(tmp_path, monkeypatch):
    evaluator = EngineEvaluator(
        "qwen21-denoise-npu",
        tmp_path / "frozen",
        arguments=["--pairs", "1", "--samples", "1", "--warmups", "0"],
    )
    source = tmp_path / "candidate"
    source.mkdir()
    (source / "candidate.py").write_text("unchanged candidate")

    def mutated_execution(*args, **kwargs):
        (evaluator.frozen / "reference.py").write_text("changed reference")
        return {"status": "completed", "returncode": 0, "cleanup_verified": True}

    monkeypatch.setattr("inferrsi.apps.search_benchmarks.execute_trial", mutated_execution)
    with pytest.raises(ValueError, match="resources changed during"):
        evaluator.evaluate(source, "evaluation", tmp_path / "output", time.time() + 1)


def test_engine_protocol_stages_share_the_original_deadline(tmp_path, monkeypatch):
    evaluator = EngineEvaluator(
        "qwen21-denoise-npu", tmp_path / "frozen",
        arguments=["--pairs", "1", "--samples", "1", "--warmups", "0"],
    )
    source = tmp_path / "candidate"
    source.mkdir()
    (source / "candidate.py").write_text("candidate")
    clock = [100.0]
    observed = []
    monkeypatch.setattr("inferrsi.apps.search_benchmarks.time.time", lambda: clock[0])
    monkeypatch.setattr("inferrsi.apps.search_benchmarks.time.monotonic", lambda: clock[0] + 1000)

    def protocol(root, digest, operation, *, deadline, **kwargs):
        observed.append((operation, deadline, deadline - (clock[0] + 1000)))
        if operation == "arguments":
            clock[0] += 2
            return []
        clock[0] += 1
        return {"verdict": "INCONCLUSIVE", "score": None}

    def execute(command, cwd, output, deadline, *args, **kwargs):
        observed.append(("execution", deadline, deadline - (clock[0] + 1000)))
        output.mkdir(parents=True)
        (output / "execution.json").write_text("{}")
        clock[0] += 3
        return {"status": "completed", "returncode": 0, "cleanup_verified": True}

    monkeypatch.setattr("inferrsi.apps.search_benchmarks.task_protocol.run", protocol)
    monkeypatch.setattr("inferrsi.apps.search_benchmarks.execute_trial", execute)
    evaluator.evaluate(source, "evaluation", tmp_path / "output", 110.0)
    assert observed == [("arguments", 1110.0, 10.0), ("execution", 1110.0, 8.0),
                        ("assess", 1110.0, 5.0)]


def test_skill_comparator_preparation_does_not_access_holdout(tmp_path):
    from tests.fixtures.harness_improvement_demo import configuration
    from tools.speculative_skill import Comparator

    config, repo = configuration(tmp_path)
    comparison = {k: config[k] for k in ("skill", "skill_root", "model", "limits")}
    comparison.update(
        mode="update",
        client={"explicit": "preparation-only-test"},
        snapshots={"baseline": {"git_revision": config["baseline"]}},
    )

    def descriptor(split):
        return {
            "path": str(tmp_path / (split + ".json")),
            "sha256": split,
            "scope": split,
            "task_count": 3,
        }

    bound = Comparator(
        repo,
        {
            "comparison": comparison,
            "allowed_paths": config["allowed_paths"],
            "splits": {s: descriptor(s) for s in ("development", "holdout")},
        },
        tmp_path / "baseline-snapshot",
    )
    exported = bound.export_root(tmp_path / "candidate")
    assert (exported / "selected/SKILL.md").is_file()
    assert not (tmp_path / "holdout.json").exists()
    assert not (tmp_path / "development.json").exists()
    # The prepared adapter still fails before provider access if its split is missing.
    with pytest.raises(FileNotFoundError):
        bound.run(exported, tmp_path / "run", time.time() + 1, split="development")
    json.dumps(bound.config)
