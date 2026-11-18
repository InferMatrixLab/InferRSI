import json
import sys
import time
from dataclasses import asdict, replace

import pytest

from inferrsi.harness import search_tree as tree
from inferrsi.harness.artifact_primitives import digest
from inferrsi.harness.gvo import examples, train_group
from inferrsi.harness.run_store import RunStore
from inferrsi.harness.search_adapter import ArtifactAdapter, CommandEvaluator, Edit
from inferrsi.harness.search_campaign import collect_group, finalize, qualify_root
from inferrsi.harness.search_records import decode
from inferrsi.harness.vats import Search, Settings
from inferrsi.harness.work_control import WorkControl
from inferrsi.model.search_roles import Snapshot
from tests.fixtures.speculative_search import contract


@pytest.fixture
def runtime(tmp_path):
    grader = tmp_path / "grader.py"
    grader.write_text("""import json, pathlib, sys
value = int((pathlib.Path(sys.argv[1]) / "candidate.txt").read_text())
check = sys.argv[2]
out = {"verdict": "PASS" if value > 0 else "FAIL"}
if value > 0 and check == "objective":
    out["objective"] = value
pathlib.Path(sys.argv[3]).write_text(json.dumps(out))
""")
    source = tmp_path / "baseline"
    source.mkdir()
    (source / "candidate.txt").write_text("1")
    evaluator = CommandEvaluator(
        {
            check: (sys.executable, str(grader), "{candidate}", check, "{result}")
            for check in ("quality", "objective")
        },
        [grader],
    )
    adapter = ArtifactAdapter(
        tmp_path / "artifacts",
        (
            Edit("improve", "candidate.txt", "1", "3"),
            Edit("break", "candidate.txt", "1", "-1"),
            Edit("repair", "candidate.txt", "-1", "4"),
        ),
        {"quality": 3000, "objective": 3000},
        evaluator,
        domain="cpu-tests",
    )
    snapshot = Snapshot(
        (1.0, 0.0, 0.0),
        (-1.0, 3.0, 6.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        (0.0,) * 8,
        "test-initial-checkpoint",
    )
    settings = Settings(5, 1, 2, 2, 40, 50, 3000, 3000, 40000)
    control = WorkControl(RunStore(tmp_path / "store", "search-test"))
    control.create(
        "campaign",
        {"adapter": adapter.identity, "settings": asdict(settings)},
        {"searches": {}, "checkpoint": snapshot.document()},
        cap_ms=120000,
        final_reserve_ms=12000,
        deadline=time.time() + 120,
    )
    root = adapter.import_root(source, snapshot=digest(snapshot.document()), context={})
    initial = qualify_root(
        control, "campaign", adapter, root, contract(improver_snapshot=digest(snapshot.document()))
    )
    return control, adapter, snapshot, settings, initial


def test_real_process_search_group_training_checkpoint_and_fresh_search(runtime):
    control, adapter, snapshot, settings, root = runtime
    records = collect_group(
        control, "campaign", adapter, root, snapshot, settings, group_id="first", size=2, seed=12
    )
    assert all(record["status"] == "complete" for record in records)
    assert all(tree.accept(decode(record["tree"])) for record in records)
    assert any(len(record["tree"]["candidates"]) > 1 for record in records)
    actors, values, group = examples(records)
    assert actors and values and len(group["advantages"]) == 2
    trained = train_group(
        control, "campaign", records, snapshot, snapshot, cap_ms=5000, learning_rate=0.01
    )
    assert trained.document() == control.read("campaign")["state"]["checkpoint"]
    assert trained.scorer != snapshot.scorer
    next_records = collect_group(
        control, "campaign", adapter, root, trained, settings, group_id="next", size=2, seed=42
    )
    assert all(record["snapshot"] == digest(trained.document()) for record in next_records)
    assert control.read("campaign")["spent_ms"] > 0


def test_final_access_is_frozen_and_export_retry_does_not_execute(runtime):
    control, adapter, snapshot, settings, root = runtime
    records = collect_group(
        control, "campaign", adapter, root, snapshot, settings, group_id="first", size=2, seed=4
    )
    selected = tree.accept(decode(records[0]["tree"]))
    result = finalize(
        control,
        "campaign",
        adapter,
        selected,
        holdout_scope="test-final",
        accept_result=lambda results: all(r["verdict"] == "PASS" for r in results),
    )
    before = len(list((adapter.root / "executions").iterdir()))
    assert (
        finalize(
            control,
            "campaign",
            adapter,
            selected,
            holdout_scope="test-final",
            accept_result=lambda results: False,
        )
        == result
    )
    assert len(list((adapter.root / "executions").iterdir())) == before
    assert control.read("campaign")["state"]["stable"]["candidate_id"] == selected.candidate_id


def test_resume_after_receipt_before_state_commit_never_executes_twice(runtime, monkeypatch):
    control, adapter, snapshot, settings, root = runtime
    search = Search(control, "campaign", root.contract.search_id, snapshot, settings, adapter)
    search.start(root, seed=2, collect=False)
    original = control.settle
    failed = False

    def crash(campaign, operation, receipt, **kwargs):
        nonlocal failed
        if receipt.get("candidate") and not failed:
            failed = True
            raise RuntimeError("crash before commit")
        return original(campaign, operation, receipt, **kwargs)

    monkeypatch.setattr(control, "settle", crash)
    with pytest.raises(RuntimeError, match="crash"):
        search.run()
    assert search.read()[1]["pending"] is not None
    monkeypatch.setattr(control, "settle", original)
    before = len(list((adapter.root / "candidates").iterdir()))
    search.recover()
    assert search.read()[1]["pending"] is None
    assert len(list((adapter.root / "candidates").iterdir())) == before


def test_gvo_rejects_shared_tree_leaves_forced_and_changed_start_conditions(runtime):
    control, adapter, snapshot, settings, root = runtime
    records = collect_group(
        control, "campaign", adapter, root, snapshot, settings, group_id="group", size=2, seed=2
    )
    with pytest.raises(ValueError, match="distinct"):
        examples((records[0], records[0]))
    with pytest.raises(ValueError, match="Forced"):
        examples((records[0] | {"forced": True}, records[1]))
    with pytest.raises(ValueError, match="identical"):
        examples((records[0] | {"settings": "other"}, records[1]))


def test_snapshot_change_on_resume_is_rejected(runtime):
    control, adapter, snapshot, settings, root = runtime
    Search(control, "campaign", "search", snapshot, settings, adapter).start(root, seed=0)
    changed = replace(snapshot, policy=(2.0,) * 8)
    with pytest.raises(ValueError, match="Frozen"):
        Search(control, "campaign", "search", changed, settings, adapter).run()


def test_persisted_search_has_only_real_check_results(runtime):
    control, adapter, snapshot, settings, root = runtime
    records = collect_group(
        control, "campaign", adapter, root, snapshot, settings, group_id="group", size=2, seed=5
    )
    serialized = json.dumps(control.read("campaign"), allow_nan=False)
    assert serialized
    for record in records:
        state = decode(record["tree"])
        for node in tree.complete_candidates(state):
            assert all(
                r.verdict.value == "PASS" for r in tree.evidence(state, node.candidate_id).values()
            )


def test_paid_continuations_are_metered_matched_and_excluded_from_actors(runtime):
    from inferrsi.harness.search_continuations import continue_from, paired_targets
    from inferrsi.harness.vats import Action

    control, adapter, snapshot, settings, root = runtime
    records = collect_group(
        control, "campaign", adapter, root, snapshot, settings, group_id="natural", size=2, seed=12
    )
    source = Search(control, "campaign", "natural-0", snapshot, settings, adapter)
    menu = [Action(**a) for a in records[0]["trace"][0]["menu"]]
    accept = next(a for a in menu if a.kind == "accept")
    draft = next(a for a in menu if a.kind == "draft")
    before = control.read("campaign")["spent_ms"]
    suffixes = [
        continue_from(source, 0, a.key, f"suffix-{i}", copy_cap_ms=3000, seed=91)
        for i, a in enumerate((accept, draft))
    ]
    assert control.read("campaign")["spent_ms"] > before
    assert all(s["forced"] and s["status"] == "complete" for s in suffixes)
    pair = paired_targets(suffixes, expense_weight=0.1, elapsed_weight=0)
    assert len(pair) == 3
    assert any(
        op["category"] == "continuation_copy"
        for op in control.read("campaign")["operations"].values()
    )
    with pytest.raises(ValueError, match="Forced"):
        examples(suffixes)
    trained = train_group(
        control,
        "campaign",
        records,
        snapshot,
        snapshot,
        cap_ms=5000,
        learning_rate=0.01,
        scorer_continuations=suffixes,
        scorer_pairs=(suffixes,),
    )
    assert trained.scorer != snapshot.scorer


def test_root_invalidation_is_persisted_and_cannot_return_an_invalid_root(runtime):
    control, adapter, snapshot, settings, root = runtime
    dependency = tree.Dependency("environment", 0)
    nodes = tuple(replace(n, dependencies=(dependency,)) for n in root.candidates)
    attempts = tuple(replace(a, dependencies=(dependency,)) for a in root.attempts)
    by_id = {a.attempt_id: a for a in attempts}
    receipts = tuple(replace(r, attempt=by_id[r.attempt.attempt_id]) for r in root.receipts)
    initial = replace(
        root, candidates=nodes, attempts=attempts, receipts=receipts, dependencies=(dependency,)
    )
    search = Search(control, "campaign", "search", snapshot, settings, adapter)
    search.start(initial, seed=1)
    search.invalidate("environment")
    assert search.read()[1]["selected"] is None
    assert search.read()[1]["status"] == "blocked"
    with pytest.raises(ValueError, match="root evidence"):
        search.run()


def test_late_draft_after_root_receipt_invalidation_is_charged_without_admission(
    runtime, monkeypatch
):
    control, adapter, snapshot, settings, root = runtime
    dependency = tree.Dependency("root-proof", 0)
    attempts = tuple(replace(a, dependencies=(dependency,)) for a in root.attempts)
    by_id = {a.attempt_id: a for a in attempts}
    initial = replace(
        root,
        attempts=attempts,
        dependencies=(dependency,),
        receipts=tuple(replace(r, attempt=by_id[r.attempt.attempt_id]) for r in root.receipts),
    )
    search = Search(control, "campaign", "search", snapshot, settings, adapter)
    search.start(initial, seed=2, collect=False)
    original = control.settle
    injected = False

    def invalidate_first(campaign, operation, receipt, **kwargs):
        nonlocal injected
        if receipt.get("candidate") and not injected:
            injected = True
            search.invalidate("root-proof")
        return original(campaign, operation, receipt, **kwargs)

    monkeypatch.setattr(control, "settle", invalidate_first)
    with pytest.raises(ValueError, match="root evidence"):
        search.run()
    assert injected
    doc, record, state = search.read()
    assert record["pending"] is None and record["selected"] is None
    assert len(state.candidates) == 1
    assert all(op["status"] == "settled" for op in doc["operations"].values())
    assert record["rejected_drafts"] and record["spent_ms"] > 0


def test_training_rejects_unretained_search_labels(runtime):
    control, adapter, snapshot, settings, root = runtime
    records = collect_group(
        control, "campaign", adapter, root, snapshot, settings, group_id="natural", size=2, seed=12
    )
    altered = (records[0] | {"gain": 999}, records[1])
    with pytest.raises(ValueError, match="retained"):
        train_group(
            control, "campaign", altered, snapshot, snapshot, cap_ms=5000, learning_rate=0.01
        )


@pytest.mark.parametrize("mode", ["reset", "carry"])
def test_outer_loop_resume_reuses_trained_checkpoints_and_frozen_roots(runtime, mode):
    from inferrsi.harness.search_campaign import learn

    control, adapter, snapshot, settings, root = runtime
    settings = replace(settings, search_ms=10000, max_steps=3)
    args = dict(rounds=2, group_size=2, training_cap_ms=5000, learning_rate=0.01, seed=8, mode=mode)
    trained = learn(control, "campaign", adapter, root, snapshot, settings, **args)
    before = control.read("campaign")
    resumed = learn(control, "campaign", adapter, root, snapshot, settings, **args)
    assert resumed == trained
    assert control.read("campaign") == before
    with pytest.raises(ValueError, match="starting conditions"):
        learn(control, "campaign", adapter, root, snapshot, settings, **(args | {"seed": 9}))
