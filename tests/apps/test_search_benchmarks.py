import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from inferrsi.apps.cli.arguments import parser
from inferrsi.apps.workflows.search_benchmarks import EngineEvaluator, SkillEvaluator
from inferrsi.apps.workflows.search_roles import Snapshot
from inferrsi.apps.workflows.speculative_search import command
from inferrsi.benchmark.improvement import SelectionPolicy
from inferrsi.harness import candidates
from inferrsi.harness.artifact_primitives import digest
from inferrsi.harness.manager import EngineSearchPlan, read_engine_search, run_engine_search
from inferrsi.harness.manager.search.search_adapter import ArtifactAdapter, Edit
from inferrsi.harness.manager.search.search_campaign import (
    FinalAcceptance,
    finalize,
    import_qualified_root,
    learn,
    qualify_root,
)
from inferrsi.harness.manager.search.vats import Search, Settings
from inferrsi.harness.manager.search.work_control import WorkControl
from inferrsi.harness.run_store import RunStore
from inferrsi.harness.task_protocol import TaskProtocolError
from inferrsi.harness.trials.external import execute_trial
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


def engine_args(tmp_path, floor, *, cap=120, reserve=3):
    return parser().parse_args([
        "search", "engine", "--session", str(tmp_path / "session"),
        "--store", str(tmp_path / "store"), "--campaign", "cpu", "--task", "cpu",
        "--domain", "local", "--checkpoint", str(tmp_path / "initial.json"),
        "--edit", "increase", "candidate.py", "value = 1", "value = 2", "--max-seconds", str(cap),
        "--evaluation-seconds", "2", "--final-reserve-seconds", str(reserve),
        "--search-seconds", "15",
        "--preparation-seconds", "1", "--draft-seconds", "1", "--training-seconds", "2",
        "--candidates", "2", "--depth", "1", "--attempts", "2", "--steps", "2", "--plans", "2",
        "--targets", "1", "--groups", "2", "--rounds", "1", "--learning-rate", "0.01",
        "--final-scope", "held", "--minimum-final-score", floor,
    ])


def engine_plan(floor, *, cap=120, reserve=3):
    return EngineSearchPlan(
        campaign="cpu", task="cpu", domain="local",
        edits=(("increase", "candidate.py", "value = 1", "value = 2"),),
        max_seconds=cap, evaluation_seconds=2, final_reserve_seconds=reserve,
        search_seconds=15, preparation_seconds=1, draft_seconds=1, training_seconds=2,
        candidates=2, depth=1, attempts=2, steps=2, plans=2, targets=1,
        groups=2, rounds=1, learning_rate=0.01, seed=0, mode="reset",
        final_scope="held", minimum_final_score=floor,
    )


@pytest.mark.parametrize(
    ("cap", "reserve", "error"),
    [(66, 3, "Campaign cap must fund"), (120, 1, "Final reserve must cover")],
)
def test_engine_admission_precedes_checkpoint_and_store_creation(tmp_path, cap, reserve, error):
    def unexpected(*args):
        pytest.fail("the rejected plan touched its checkpoint or evaluator")

    with pytest.raises(ValueError, match=error):
        command(engine_args(tmp_path, "1", cap=cap, reserve=reserve))
    with pytest.raises(ValueError, match=error):
        run_engine_search(
            engine_plan(1, cap=cap, reserve=reserve), session=tmp_path / "direct",
            store=tmp_path / "direct-store", load_snapshot=unexpected, prepare_evaluator=unexpected,
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("floor", "expected", "promoted"),
    [("9007199254740992", 2**53, True), ("9.007199254740993e15", 2**53 + 1, False)],
)
def test_engine_cli_freezes_exact_final_score(tmp_path, monkeypatch, floor, expected, promoted):
    holdout_candidates = []

    class Evaluator:
        identity = "cpu-score-fixture"

        def __init__(self, task, frozen, **kwargs):
            frozen.mkdir()
            (frozen / "baseline.py").write_text("value = 1")

        def evaluate(self, candidate, check, output, deadline):
            if output.name.startswith("final-"):
                holdout_candidates.append(candidates.identity(candidate))
            output.mkdir(parents=True)
            return {"verdict": "PASS", "objective": 2**53, "cleanup_verified": True}

    monkeypatch.setattr("inferrsi.apps.workflows.search_benchmarks.EngineEvaluator", Evaluator)
    checkpoint = tmp_path / "initial.json"
    checkpoint.write_text(json.dumps(Snapshot((0,), (0,) * 8, (0,) * 8, "fixture").document()))
    session = str(tmp_path / "session")

    command(engine_args(tmp_path, floor))
    saved = command(parser().parse_args(["search", "status", "--session", session]))
    binding = saved["final_claim"]["binding"]
    assert binding["acceptance"] == {"version": 1, "minimum_objective": expected}
    assert binding["objective_check"] == "evaluation"
    assert saved["final_result"]["promoted"] is promoted
    winner = binding["candidate"]["artifact_digest"]
    assert holdout_candidates == [winner]

    direct_session = tmp_path / "direct"
    direct = run_engine_search(
        engine_plan(expected), session=direct_session, store=tmp_path / "direct-store",
        load_snapshot=lambda: Snapshot(**json.loads(checkpoint.read_text())),
        prepare_evaluator=lambda frozen: Evaluator("cpu", frozen),
    )
    assert direct == read_engine_search(direct_session)
    assert direct["final_claim"]["binding"]["candidate"]["artifact_digest"] == winner
    assert direct["final_result"]["promoted"] is promoted
    assert holdout_candidates == [winner, winner]


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
    directory = tmp_path / "artifacts"
    adapter = _skill_adapter(directory, comparator, split, task_count=1)
    source = tmp_path / "source"
    source.mkdir()
    (source / "skill.txt").write_text("old")
    root = adapter.import_root(source, snapshot="test-snapshot", context={})
    control = WorkControl(RunStore(tmp_path / "store", "skill-test"))
    before = control.create("campaign", {}, {"searches": {}}, cap_ms=10000, final_reserve_ms=3000,
                            deadline=time.time() + 10)
    kwargs = dict(holdout_scope=supplied_scope, acceptance=FinalAcceptance())
    if valid:
        development = _skill_adapter(directory, comparator, "development", task_count=1)
        _select_skill_root(control, "campaign", development, root)
        result = finalize(control, "campaign", adapter, root, **kwargs)
        assert result["verdict"] == "PASS" and result["promoted"]
        assert accesses == ["development", "holdout"]
        assert finalize(control, "campaign", adapter, root, **kwargs) == result
        assert accesses == ["development", "holdout"]
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


@pytest.fixture
def skill_splits(tmp_path):
    from tests.fixtures.harness_improvement_demo import configuration
    from tools import speculative_skill

    config, repo = configuration(tmp_path)
    comparison = {k: config[k] for k in ("skill", "skill_root", "model", "limits")}
    comparison.update(mode="update", client={"explicit": "preparation-only-test"},
                      snapshots={"baseline": {"git_revision": config["baseline"]}})

    def bind(name, dev, holdout, *, declared=None, pretty=False):
        directory = tmp_path / name
        directory.mkdir()
        splits = {}
        for split, cases in (("development", dev), ("holdout", holdout)):
            path = directory / (split + ".json")
            path.write_text(json.dumps(cases, sort_keys=pretty, indent=2 if pretty else None))
            splits[split] = {"path": str(path), "scope": name + split,
                             "sha256": speculative_skill.sha256(path), "task_count": len(cases),
                             "task_set_sha256": speculative_skill.task_set_sha256(cases)}
        if declared:
            splits["holdout"]["task_set_sha256"] = declared
        return speculative_skill.Comparator(
            repo, {"comparison": comparison, "allowed_paths": config["allowed_paths"],
                   "splits": splits}, directory / "baseline")

    return bind, config["development"], config["holdout"]


def _skill_adapter(directory, comparator, split, *, task_count=None):
    if task_count is None:
        task_count = comparator.config["splits"][split]["task_count"]
    evaluator = SkillEvaluator(
        comparator, split=split, policy=SelectionPolicy(1, 0), token_cap=1000,
        task_count=task_count,
    )
    return ArtifactAdapter(
        directory, [Edit("edit", "selected/SKILL.md", "old", "new")],
        {"evaluation": 3000}, evaluator, domain="skill-test",
    )


def _select_skill_root(control, campaign, development, root):
    snapshot = Snapshot((1.0,), (0.0,) * 8, (0.0,) * 8, "fixture")
    config = contract(checks=("evaluation",), objective_check="evaluation", max_attempts=1,
                      improver_snapshot=digest(snapshot.document()))
    qualified = qualify_root(control, campaign, development, root, config)
    search = Search(control, campaign, config.search_id, snapshot,
                    Settings(1, 1, 1, 1, 1, 1, 100, 100, 3000), development)
    search.start(qualified, seed=1, collect=False)
    assert search.run()["selected"] == root.candidate_id


@pytest.mark.parametrize("fault", ["empty", "other-candidate", "producer", "changed-content"])
def test_skill_final_rejects_unbound_candidate_before_holdout(tmp_path, fault):
    accesses = []

    def compare(*args, split):
        accesses.append(split)
        return skill_report(tokens=100), True

    comparator = SimpleNamespace(identity="frozen-comparator", holdout_scope="shared", run=compare)
    directory = tmp_path / "artifacts"
    dev = _skill_adapter(directory, comparator, "development", task_count=1)
    final = _skill_adapter(directory, comparator, "holdout", task_count=1)
    source = tmp_path / "source"
    source.mkdir()
    (source / "skill.txt").write_text("original")
    root = dev.import_root(source, snapshot="snapshot", context={})
    control = WorkControl(RunStore(tmp_path / "store", "skill-test"))
    control.create("campaign", {}, {"searches": {}}, cap_ms=10000, final_reserve_ms=3000,
                   deadline=time.time() + 30)
    if fault != "empty":
        _select_skill_root(control, "campaign", dev, root)
    supplied = root
    if fault == "other-candidate":
        # A retained copy with the same bytes still has a different candidate identity.
        supplied = replace(root, candidate_id="unselected")
        (directory / "candidates" / supplied.candidate_id).mkdir()
        (directory / "candidates" / supplied.candidate_id / "skill.txt").write_text("original")
    elif fault == "producer":
        supplied = replace(root, producer=replace(root.producer, snapshot="another-checkpoint"))
    elif fault == "changed-content":
        (dev.path(root) / "skill.txt").write_text("changed after selection")
    reopened = WorkControl(RunStore(control.store.root, control.store.namespace))
    with pytest.raises(ValueError):
        finalize(reopened, "campaign", final, supplied,
                 holdout_scope=comparator.holdout_scope, acceptance=FinalAcceptance())
    record = reopened.read("campaign")
    assert record["final_claim"] is None and record["final_result"] is None
    assert "stable" not in record["state"] and "holdout" not in accesses


def _skill_final(tmp_path, comparator, name):
    directory = tmp_path / name / "artifacts"
    adapter = _skill_adapter(directory, comparator, "holdout")
    development = _skill_adapter(directory, comparator, "development")
    source = comparator.export_root(tmp_path / name / "source")
    root = development.import_root(source, snapshot="test-snapshot", context={})
    control = WorkControl(RunStore(tmp_path / "store", "skill-test"))
    control.create(name, {}, {"searches": {}}, cap_ms=10000, final_reserve_ms=3000,
                   deadline=time.time() + 30)
    # These tests exercise the real holdout reader after a recorded development selection.
    report = skill_report()
    report["pairs"] *= development.evaluator.task_count
    with patch.object(comparator, "run", return_value=(report, True)):
        _select_skill_root(control, name, development, root)

    def run():
        return finalize(control, name, adapter, root, holdout_scope=comparator.holdout_scope,
                        acceptance=FinalAcceptance())

    return control, run


@pytest.mark.parametrize("fault", ["id-overlap", "content-overlap", "wrong-set", "changed-file"])
def test_skill_final_validates_actual_splits_only_after_claim(
    tmp_path, monkeypatch, skill_splits, fault
):
    from tools import speculative_skill

    bind, dev, holdout = skill_splits
    if fault == "id-overlap":
        holdout[0]["id"] = dev[0]["id"]
    if fault == "content-overlap":
        holdout[0] = {**dev[0], "id": "renamed", "split": "holdout", "provenance": "relabeled"}
    bound = bind("first", dev, holdout, declared="0" * 64 if fault == "wrong-set" else None)
    control, run = _skill_final(tmp_path, bound, "first")
    source = Path(bound.config["splits"]["holdout"]["path"])
    if fault == "changed-file":
        source.write_bytes(source.read_bytes() + b" ")
    read_bytes = Path.read_bytes
    accesses = []

    def read(path):
        if path == source:
            assert control.read("first")["final_claim"]["scope"] == bound.holdout_scope
            accesses.append(path)
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(speculative_skill.compare, "prepare",
                        lambda *args: pytest.fail("dispatched"))
    with pytest.raises(ValueError, match="overlap|task set|split changed"):
        run()
    assert accesses == [source]
    assert control.read("first")["final_claim"] is not None


def test_skill_final_reformatted_scope_and_single_read(tmp_path, monkeypatch, skill_splits):
    from tools import speculative_skill

    bind, dev, holdout = skill_splits
    first = bind("first", dev, holdout)
    second = bind("second", dev, [dict(case, id="renamed-" + case["id"], provenance="other")
                                  for case in reversed(holdout)], pretty=True)
    assert first.holdout_scope == second.holdout_scope
    first_raw = first.config["splits"]["holdout"]["sha256"]
    assert first_raw != second.config["splits"]["holdout"]["sha256"]
    control, run = _skill_final(tmp_path, first, "first")
    _, repeat = _skill_final(tmp_path, second, "second")
    source = Path(first.config["splits"]["holdout"]["path"])
    read_bytes = Path.read_bytes
    accesses = []

    def replace_after_read(path):
        value = read_bytes(path)
        if path == source:
            assert control.read("first")["final_claim"]["scope"] == first.holdout_scope
            source.write_text("[]")
            accesses.append(path)
        return value

    def prepare(config, *_):
        assert json.loads((config.parent / "tasks.json").read_text()) == holdout
        raise RuntimeError("verified tasks reached prepare")

    monkeypatch.setattr(Path, "read_bytes", replace_after_read)
    monkeypatch.setattr(speculative_skill.compare, "prepare", prepare)
    with pytest.raises(RuntimeError, match="verified tasks reached prepare"):
        run()
    assert accesses == [source]
    Path(second.config["splits"]["holdout"]["path"]).unlink()
    with pytest.raises(ValueError, match="already consumed"):
        repeat()
    assert control.read("second")["final_claim"] is None


def test_skill_legacy_holdout_migration_requires_consumed_authenticated_archive(
    tmp_path, skill_splits
):
    from tools import speculative_skill

    bind, dev, holdout = skill_splits
    old = bind("old", dev, holdout)
    second = bind("second", dev, list(reversed(holdout)), pretty=True)
    control, repeat = _skill_final(tmp_path, second, "second")
    old_hash = old.config["splits"]["holdout"]["sha256"]
    archive = Path(old.config["splits"]["holdout"]["path"])
    historic = control.create("historic", {}, {}, cap_ms=10000, final_reserve_ms=3000,
                              deadline=time.time() + 10)
    control.claim_final("historic", historic["revision"], "skill-data:" + old_hash, {})
    with pytest.raises(ValueError, match="Unmapped"):
        repeat()
    with pytest.raises(ValueError, match="consumed"):
        speculative_skill.migrate_holdout(control, "1" * 64, tmp_path / "must-not-open")
    with pytest.raises(ValueError, match="split changed"):
        speculative_skill.migrate_holdout(
            control, old_hash, second.config["splits"]["holdout"]["path"])
    with pytest.raises(ValueError, match="Unmapped"):
        repeat()
    assert speculative_skill.migrate_holdout(control, old_hash, archive) == second.holdout_scope
    with pytest.raises(ValueError, match="already consumed"):
        repeat()
    unrelated = bind("unrelated", dev, holdout[:1])
    control, final = _skill_final(tmp_path, unrelated, "unrelated")
    Path(unrelated.config["splits"]["holdout"]["path"]).unlink()
    with pytest.raises(FileNotFoundError):
        final()
    assert control.read("unrelated")["final_claim"]["scope"] == unrelated.holdout_scope


def test_skill_search_and_final_bind_the_actual_development_comparator(
    tmp_path, monkeypatch, skill_splits
):
    from tools import speculative_skill

    bind, dev, holdout = skill_splits
    first = bind("first", dev, holdout)
    swapped = bind("swapped", [dict(c, split="development") for c in holdout],
                   [dict(c, split="holdout") for c in dev])
    directory = tmp_path / "artifacts"
    development = _skill_adapter(directory, first, "development")
    final = _skill_adapter(directory, first, "holdout")
    substituted = _skill_adapter(directory, swapped, "holdout")
    root = development.import_root(first.export_root(tmp_path / "source"),
                                   snapshot="test-snapshot", context={})
    store = RunStore(tmp_path / "store", "skill-search")
    control = WorkControl(store)
    control.create("campaign", {}, {"searches": {}}, cap_ms=20000, final_reserve_ms=3000,
                   deadline=time.time() + 30)
    snapshot = Snapshot((1.0,), (0.0,) * 8, (0.0,) * 8, "fixture")
    settings = Settings(2, 1, 1, 1, 4, 5, 1000, 1000, 3000)
    config = contract(checks=("evaluation",), objective_check="evaluation", max_attempts=1,
                      improver_snapshot=digest(snapshot.document()))

    def prepare(config, repo, output):
        # Only the ordinary development qualification reaches this comparison.
        assert json.loads((config.parent / "tasks.json").read_text()) == dev
        plan = output / "plan" / "freeze.json"
        plan.parent.mkdir(parents=True)
        plan.write_text("{}")
        return speculative_skill.sha256(plan)

    report = skill_report()
    report["pairs"] *= len(dev)
    monkeypatch.setattr(speculative_skill.compare, "prepare", prepare)
    monkeypatch.setattr(speculative_skill, "execute_trial",
                        lambda *a, **kw: {"cleanup_verified": True})
    monkeypatch.setattr(speculative_skill.compare, "read_report", lambda _: report)
    # Missing held-out files prove that both development entry points reject the wrong role
    # before access and that qualifying a real development root never reads the holdout.
    Path(first.config["splits"]["holdout"]["path"]).unlink()
    Path(swapped.config["splits"]["holdout"]["path"]).unlink()
    with pytest.raises(ValueError, match="holdout-bound"):
        qualify_root(control, "campaign", final, root, config)
    with pytest.raises(ValueError, match="holdout-bound"):
        Search(control, "campaign", config.search_id, snapshot, settings, final)
    assert not control.read("campaign")["operations"]

    qualified = qualify_root(control, "campaign", development, root, config)
    reopened = WorkControl(RunStore(store.root, store.namespace))
    with pytest.raises(ValueError, match="frozen development experiment"):
        finalize(reopened, "campaign", substituted, root, holdout_scope=swapped.holdout_scope,
                 acceptance=FinalAcceptance())
    assert reopened.read("campaign")["final_claim"] is None

    # A second campaign can import the verified root, retaining its original physical
    # identity. Changing the development comparator before or after import is rejected.
    reopened.create("import", {}, {"searches": {}}, cap_ms=20000, final_reserve_ms=3000,
                    deadline=time.time() + 30)
    imported = import_qualified_root(qualified, replace(config, search_id="imported"))
    wrong = _skill_adapter(directory, swapped, "development")
    with pytest.raises(ValueError, match="Imported evidence"):
        Search(reopened, "import", "imported", snapshot, settings, wrong).start(imported, seed=1)
    search = Search(reopened, "import", "imported", snapshot, settings, development)
    search.start(imported, seed=1, collect=False)
    search.run()
    with pytest.raises(ValueError, match="frozen development experiment"):
        finalize(reopened, "import", substituted, root, holdout_scope=swapped.holdout_scope,
                 acceptance=FinalAcceptance())
    assert reopened.read("import")["final_claim"] is None
    # The original registered comparator reaches the missing input after consuming its claim.
    with pytest.raises(FileNotFoundError):
        finalize(reopened, "import", final, root, holdout_scope=first.holdout_scope,
                 acceptance=FinalAcceptance())
    assert reopened.read("import")["final_claim"]["scope"] == first.holdout_scope


def test_skill_carry_reuses_winning_child_verification(tmp_path):
    def compare(candidate, *args, split):
        assert split == "development"
        tokens = 90 if (candidate / "skill.txt").read_text() == "old" else 70
        return skill_report(tokens=tokens), True

    comparator = SimpleNamespace(identity="carry-comparator", run=compare)
    evaluator = SkillEvaluator(comparator, split="development", policy=SelectionPolicy(1, 0),
                               token_cap=1000, task_count=1)
    adapter = ArtifactAdapter(tmp_path / "artifacts", [Edit("edit", "skill.txt", "old", "new")],
                              {"evaluation": 300}, evaluator, domain="skill-carry")
    source = tmp_path / "source"
    source.mkdir()
    (source / "skill.txt").write_text("old")
    snapshot = Snapshot((1.0,), (0, 30, 60, 0, 0, 0, 0, 0), (0.0,) * 8, "fixture")
    root = adapter.import_root(source, snapshot=digest(snapshot.document()), context={})
    control = WorkControl(RunStore(tmp_path / "store", "skill-carry"))
    control.create("campaign", {}, {"searches": {}, "checkpoint": snapshot.document()},
                   cap_ms=30000, final_reserve_ms=3000, deadline=time.time() + 30)
    config = contract(checks=("evaluation",), objective_check="evaluation", max_candidates=2,
                      improver_snapshot=digest(snapshot.document()))
    initial = qualify_root(control, "campaign", adapter, root, config)
    settings = Settings(2, 1, 1, 1, 4, 5, 300, 300, 2000, exploration=0)
    learn(control, "campaign", adapter, initial, snapshot, settings, rounds=2, group_size=2,
          training_cap_ms=2000, learning_rate=0.01, seed=4, mode="carry")
    searches = control.read("campaign")["state"]["searches"]
    second_round = [r["tree"] for r in searches.values() if r["tree"]["root_id"] != "root"]
    assert len(second_round) == 2
    for state in second_round:
        winner = state["root_id"]
        receipt = next(r for r in state["receipts"] if r["attempt"]["candidate_id"] == winner)
        assert receipt["attempt"]["experiment_identity"] == comparator.identity
        assert not receipt["attempt"]["execution_key"].startswith("root-")
