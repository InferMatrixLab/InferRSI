import json
import sys
import time
from types import SimpleNamespace

import pytest

from inferrsi.apps.cli.arguments import parser
from inferrsi.apps.workflows.search_benchmarks import EngineEvaluator, SkillEvaluator
from inferrsi.apps.workflows.speculative_search import command
from inferrsi.benchmark.improvement import SelectionPolicy
from inferrsi.harness.run_store import RunStore
from inferrsi.harness.search_adapter import ArtifactAdapter, Edit
from inferrsi.harness.search_campaign import finalize, qualify_root
from inferrsi.harness.task_protocol import TaskProtocolError
from inferrsi.harness.trials.external import execute_trial
from inferrsi.harness.work_control import WorkControl
from tests.fixtures.speculative_search import contract


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

    monkeypatch.setattr(
        "inferrsi.apps.workflows.search_benchmarks.execute_trial", mutated_execution
    )
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
    monkeypatch.setattr("inferrsi.apps.workflows.search_benchmarks.time.time", lambda: clock[0])
    monkeypatch.setattr(
        "inferrsi.apps.workflows.search_benchmarks.time.monotonic", lambda: clock[0] + 1000
    )

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

    monkeypatch.setattr("inferrsi.apps.workflows.search_benchmarks.task_protocol.run", protocol)
    monkeypatch.setattr("inferrsi.apps.workflows.search_benchmarks.execute_trial", execute)
    evaluator.evaluate(source, "evaluation", tmp_path / "output", 110.0)
    assert observed == [("arguments", 1110.0, 10.0), ("execution", 1110.0, 8.0),
                        ("assess", 1110.0, 5.0)]


def test_engine_known_timeout_settles_usage_and_releases_domain(tmp_path, monkeypatch):
    evaluator = EngineEvaluator(
        "qwen21-denoise-npu", tmp_path / "frozen",
        arguments=["--pairs", "1", "--samples", "1", "--warmups", "0"],
    )
    executions = []

    def timeout(command, cwd, output, deadline, *args, **kwargs):
        # Exercise real process cleanup without model/device execution.
        result = execute_trial((sys.executable, "-c", "import time; time.sleep(60)"),
                               cwd, output, deadline, *args, **kwargs)
        executions.append(result)
        return result

    monkeypatch.setattr("inferrsi.apps.workflows.search_benchmarks.execute_trial", timeout)
    source = tmp_path / "source"
    source.mkdir()
    (source / "candidate.py").write_text("value = 1\n")
    adapter = ArtifactAdapter(tmp_path / "artifacts", [Edit("edit", "candidate.py", "1", "2")],
                              {"evaluation": 2000}, evaluator, domain="cpu-timeout-test")
    root = adapter.import_root(source, snapshot="test-snapshot", context={})
    control = WorkControl(RunStore(tmp_path / "store", "timeout-test"))
    control.create("campaign", {}, {"searches": {}}, cap_ms=20000, final_reserve_ms=3000,
                   deadline=time.time() + 20)
    configuration = contract(checks=("evaluation",), objective_check="evaluation")
    with pytest.raises(ValueError, match="Root lacks complete"):
        qualify_root(control, "campaign", adapter, root, configuration)
    assert executions[0]["status"] == "timeout" and executions[0]["cleanup_verified"] is True
    reopened = WorkControl(RunStore(control.store.root, control.store.namespace))
    doc = reopened.read("campaign")
    operation, settled = next(iter(doc["operations"].items()))
    assert settled["status"] == "settled" and settled["actual_ms"] > 0
    assert doc["spent_ms"] == settled["actual_ms"]
    assert settled["receipt"]["verdict"] == "INCONCLUSIVE"
    assert settled["receipt"]["cleanup_verified"] is True
    assert adapter.recover(operation, {"kind": "verify", "binding": settled["binding"]}) == (
        settled["receipt"])
    with reopened.store._connection() as db:
        assert db.execute("SELECT 1 FROM work_domains").fetchone() is None
    # Deadline overruns remain blocking; a clean timeout is not a free retry.
    assert doc["blocked"]


@pytest.mark.parametrize("stage", ["arguments", "assess"])
@pytest.mark.parametrize("protocol_cleanup", [True, False, None])
@pytest.mark.parametrize("task_cleanup", [True, False, None])
def test_engine_protocol_timeout_preserves_cleanup_facts(
    tmp_path, monkeypatch, stage, protocol_cleanup, task_cleanup
):
    evaluator = EngineEvaluator(
        "qwen21-denoise-npu", tmp_path / "frozen",
        arguments=["--pairs", "1", "--samples", "1", "--warmups", "0"],
    )
    source = tmp_path / "source"
    source.mkdir()
    (source / "candidate.py").write_text("candidate")

    def protocol(root, digest, operation, **kwargs):
        if operation == stage:
            raise TaskProtocolError(
                "timeout", "injected timeout", cleanup_verified=protocol_cleanup)
        return []

    def execute(command, cwd, output, *args, **kwargs):
        output.mkdir(parents=True)
        (output / "execution.json").write_text("{}")
        return {"status": "completed", "returncode": 0, "cleanup_verified": task_cleanup}

    monkeypatch.setattr("inferrsi.apps.workflows.search_benchmarks.task_protocol.run", protocol)
    monkeypatch.setattr("inferrsi.apps.workflows.search_benchmarks.execute_trial", execute)
    result = evaluator.evaluate(source, "evaluation", tmp_path / "output", time.time() + 10)
    assert result["verdict"] == "INCONCLUSIVE" and result["objective"] is None
    assert result["cleanup_verified"] is (
        protocol_cleanup is True and (stage == "arguments" or task_cleanup is True)
    )
    assert (result["execution_sha256"] is None) == (stage == "arguments")


@pytest.mark.parametrize("split, declared_scope, supplied_scope, valid", [
    ("development", "skill-data:holdout", "skill-data:holdout", False),
    ("holdout", None, "skill-data:holdout", False),
    ("holdout", "skill-data:holdout", "replacement-label", False),
    ("holdout", "skill-data:holdout", "skill-data:holdout", True),
])
def test_skill_final_requires_holdout_before_claim_or_access(
    tmp_path, split, declared_scope, supplied_scope, valid
):
    accesses = []

    def compare(*args, split, **kwargs):
        accesses.append(split)
        return skill_report(tokens=100), True

    comparator = SimpleNamespace(identity="test-comparator", run=compare,
                                 holdout_scope=declared_scope)
    evaluator = SkillEvaluator(comparator, split=split, policy=SelectionPolicy(1, 0),
                               token_cap=1000, task_count=1)
    adapter = ArtifactAdapter(tmp_path / "artifacts", [Edit("edit", "skill.txt", "old", "new")],
                              {"evaluation": 3000}, evaluator, domain="skill-test")
    source = tmp_path / "source"
    source.mkdir()
    (source / "skill.txt").write_text("old")
    root = adapter.import_root(source, snapshot="test-snapshot", context={})
    control = WorkControl(RunStore(tmp_path / "store", "skill-test"))
    before = control.create("campaign", {}, {}, cap_ms=10000, final_reserve_ms=3000,
                            deadline=time.time() + 10)
    kwargs = dict(holdout_scope=supplied_scope, accept_result=lambda results: True)
    if valid:
        result = finalize(control, "campaign", adapter, root, **kwargs)
        assert result["verdict"] == "PASS" and result["promoted"]
        assert accesses == ["holdout"]
        assert finalize(control, "campaign", adapter, root, **kwargs) == result
        assert accesses == ["holdout"]
    else:
        with pytest.raises(ValueError, match="holdout-bound"):
            finalize(control, "campaign", adapter, root, **kwargs)
        assert control.read("campaign") == before and not accesses


@pytest.mark.parametrize("indexed", [False, True])
def test_skill_comparator_preparation_does_not_access_holdout(tmp_path, indexed):
    from tests.fixtures.harness_improvement_demo import configuration
    from tests.fixtures.skill_eval_compare_support import git
    from tools.speculative_skill import Comparator

    config, repo = configuration(tmp_path)
    prefix = "selected"
    if indexed:
        # Match the categorized, single-file metadata catalog introduced in #516.
        prefix = "playbooks/testing/selected"
        library = repo / "library"
        target = library / prefix
        target.parent.mkdir(parents=True)
        (library / "selected").rename(target)
        (target / "metadata.json").unlink()
        metadata = {"references": ["../../../shared/notes.md"]}
        skill = target / "SKILL.md"
        skill.write_text(
            "---\nname: selected\ndescription: indexed snapshot fixture\n"
            "metadata:\n  inferrsi: |\n    " + json.dumps(metadata) + "\n---\nOld body\n",
            encoding="utf-8",
        )
        (library / "skill-index.json").write_text(json.dumps({
            "schema_version": 1,
            "skills": {"selected": {"path": prefix, "backend": "common"}},
        }), encoding="utf-8")
        git(repo, "add", "library")
        git(repo, "commit", "--quiet", "-m", "Fixture indexed catalog")
        config["baseline"] = git(repo, "rev-parse", "HEAD")
        config["allowed_paths"] = [f"{prefix}/SKILL.md", f"{prefix}/resource.txt"]
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
    assert (exported / prefix / "SKILL.md").read_bytes() == bound.original[f"{prefix}/SKILL.md"]
    assert (exported / "shared/notes.md").is_file()
    assert "skill-index.json" not in bound.original
    assert not (tmp_path / "holdout.json").exists()
    assert not (tmp_path / "development.json").exists()
    # The prepared adapter still fails before provider access if its split is missing.
    # Materializing an edit before that failure also exercises the indexed reader.
    (exported / prefix / "SKILL.md").write_bytes(
        bound.original[f"{prefix}/SKILL.md"].replace(b"Old body", b"Edited body")
    )
    head_before = git(repo, "rev-parse", "HEAD")
    with pytest.raises(FileNotFoundError):
        bound.run(exported, tmp_path / "run", time.time() + 1, split="development")
    assert git(repo, "rev-parse", "HEAD") == head_before
    assert git(repo, "status", "--porcelain") == ""
    json.dumps(bound.config)
