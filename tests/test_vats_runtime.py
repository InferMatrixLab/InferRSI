import json
import sys
import time
from dataclasses import asdict, replace

import pytest

from inferrsi.apps.workflows.search_roles import Snapshot
from inferrsi.harness import search_tree as tree
from inferrsi.harness.artifact_primitives import digest
from inferrsi.harness.gvo import examples, train_group
from inferrsi.harness.run_store import RunStore
from inferrsi.harness.search_adapter import ArtifactAdapter, CommandEvaluator, Edit
from inferrsi.harness.search_campaign import (
    collect_group,
    finalize,
    import_qualified_root,
    qualify_root,
)
from inferrsi.harness.search_records import decode
from inferrsi.harness.vats import Search, Settings
from inferrsi.harness.work_control import WorkControl
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


def start_search_for_final(runtime, name="deploy", *, collect=False, forced=False, root_only=False):
    control, adapter, snapshot, settings, root = runtime
    configuration = replace(root.contract, search_id=name)
    if root_only:
        configuration = replace(configuration, max_attempts=len(root.attempts))
    initial = import_qualified_root(root, configuration)
    search = Search(control, "campaign", name, snapshot, settings, adapter)
    search.start(initial, seed=2, collect=collect, forced=forced)
    return search


@pytest.mark.parametrize("detach_parent", [False, True])
def test_final_access_is_frozen_and_export_retry_does_not_execute(runtime, detach_parent):
    control, adapter, _, _, _ = runtime
    search = start_search_for_final(runtime)
    selected = tree.accept(decode(search.run()["tree"]))
    assert selected.parent_id is not None
    if detach_parent:
        selected = replace(selected, parent_id=None)
    result = finalize(
        control,
        "campaign",
        adapter,
        selected,
        holdout_scope="test-final",
        accept_result=lambda results: all(r["verdict"] == "PASS" for r in results),
    )
    before = len(list((adapter.root / "executions").iterdir()))
    (adapter.path(selected) / "candidate.txt").unlink()
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


@pytest.mark.parametrize("stage", ["root-only", "active", "collecting", "forced"])
def test_final_requires_completed_unforced_deployment_before_claim(runtime, monkeypatch, stage):
    control, adapter, _, _, root = runtime
    if stage != "root-only":
        search = start_search_for_final(
            runtime, collect=stage == "collecting", forced=stage == "forced", root_only=True
        )
        if stage != "active":
            search.run()
    before = control.read("campaign")
    monkeypatch.setattr(adapter, "verify", lambda *args: pytest.fail("Unexpected final dispatch"))
    with pytest.raises(ValueError):
        finalize(control, "campaign", adapter, tree.accept(root), holdout_scope="held",
                 accept_result=bool)
    assert control.read("campaign") == before


@pytest.mark.parametrize("substitution", ["losing-root", "producer", "bytes"])
def test_final_authenticates_winner_before_claim(runtime, monkeypatch, substitution):
    control, adapter, _, _, root = runtime
    search = start_search_for_final(runtime)
    selected = tree.accept(decode(search.run()["tree"]))
    assert selected.candidate_id != root.root_id
    if substitution == "losing-root":
        selected = tree.accept(root)
    elif substitution == "producer":
        selected = replace(selected, producer=replace(selected.producer, revision="another"))
    else:
        (adapter.path(selected) / "candidate.txt").write_text("999")
    before = control.read("campaign")
    monkeypatch.setattr(adapter, "verify", lambda *args: pytest.fail("Unexpected final dispatch"))
    with pytest.raises(ValueError):
        finalize(control, "campaign", adapter, selected, holdout_scope="held", accept_result=bool)
    assert control.read("campaign") == before


def interrupt_after_last_final_receipt(control, adapter, monkeypatch):
    settle = control.settle

    def crash_after_last_receipt(campaign, operation, receipt, **options):
        op = control.read(campaign)["operations"][operation]
        if op["binding"]["check"] == tuple(adapter.checks)[-1]:
            raise RuntimeError("crash after final receipt")
        return settle(campaign, operation, receipt, **options)

    monkeypatch.setattr(control, "settle", crash_after_last_receipt)


def test_final_recovery_uses_receipt_and_frozen_deployment_with_identical_winners(
    runtime, monkeypatch
):
    control, adapter, _, _, root = runtime
    selected = tree.accept(root)
    for name in ("deploy-a", "deploy-b"):
        record = start_search_for_final(runtime, name, root_only=True).run()
        assert record["selected"] == selected.candidate_id
    kwargs = dict(holdout_scope="held", accept_result=bool)
    before = control.read("campaign")
    with pytest.raises(ValueError):
        finalize(control, "campaign", adapter, selected, **kwargs)
    assert control.read("campaign") == before

    interrupt_after_last_final_receipt(control, adapter, monkeypatch)
    with pytest.raises(RuntimeError, match="crash after final receipt"):
        finalize(control, "campaign", adapter, selected, deployment_search="deploy-a", **kwargs)
    reopened = WorkControl(RunStore(control.store.root, control.store.namespace))
    before = reopened.read("campaign")
    assert before["final_claim"]["binding"]["deployment_search"] == "deploy-a"
    assert before["final_result"] is None
    waiting = [key for key, op in before["operations"].items() if op["status"] == "launched"]
    assert len(waiting) == 1
    recoveries = []
    recover = adapter.recover

    def read_receipt(operation, pending):
        recoveries.append(operation)
        return recover(operation, pending)

    monkeypatch.setattr(adapter, "verify", lambda *args: pytest.fail("Final must not relaunch"))
    monkeypatch.setattr(adapter, "recover", read_receipt)
    with pytest.raises(ValueError):
        finalize(reopened, "campaign", adapter, selected, deployment_search="deploy-b", **kwargs)
    with pytest.raises(ValueError):
        finalize(reopened, "campaign", adapter, selected, **(kwargs | {"holdout_scope": "changed"}))
    different = replace(selected, producer=replace(selected.producer, revision="changed"))
    with pytest.raises(ValueError):
        finalize(reopened, "campaign", adapter, different, **kwargs)
    assert reopened.read("campaign") == before and not recoveries
    result = finalize(reopened, "campaign", adapter, selected, **kwargs)
    assert result["promoted"] and result["verdict"] == "PASS"
    assert finalize(reopened, "campaign", adapter, selected, **kwargs) == result
    assert recoveries == waiting


@pytest.mark.parametrize("has_deployment", [False, True])
def test_legacy_final_receipts_require_development_selection(runtime, monkeypatch, has_deployment):
    control, adapter, _, _, root = runtime
    selected = tree.accept(root)
    if has_deployment:
        record = start_search_for_final(runtime, root_only=True).run()
        assert record["selected"] == selected.candidate_id
    # The old binding had no deployment-search ID. Simulate a crash after the last receipt.
    scope = "legacy-held"
    binding = {
        "candidate": asdict(selected),
        "adapter": adapter.identity,
        "checks": adapter.checks,
        "scope": scope,
    }
    doc = control.claim_final("campaign", control.read("campaign")["revision"], scope, binding)
    for check, cap in adapter.checks.items():
        operation = "final-" + digest({"campaign": "campaign", "binding": binding, "check": check})
        control.claim(
            "campaign", doc["revision"], operation, category="final", final=True, cap_ms=cap,
            domains=(adapter.domain,), binding=binding | {"check": check},
        )
        claim = control.launch("campaign", operation)
        receipt = adapter.verify(selected, check, operation, claim["deadline"])
        assert receipt["verdict"] == "PASS"
        if check == tuple(adapter.checks)[-1]:
            break
        doc = control.settle(
            "campaign", operation, receipt, actual_ms=receipt["elapsed_ms"],
            cleanup_verified=receipt["cleanup_verified"],
        )
    reopened = WorkControl(RunStore(control.store.root, control.store.namespace))
    before = reopened.read("campaign")
    assert before["operations"][operation]["status"] == "launched"

    def assert_reservation_held():
        assert reopened.read("campaign") == before
        with reopened.store._connection() as db:
            lease = db.execute(
                "SELECT 1 FROM work_domains WHERE operation=?", (operation,)
            ).fetchone()
            assert lease is not None

    monkeypatch.setattr(adapter, "verify", lambda *args: pytest.fail("Legacy final must not rerun"))
    kwargs = dict(holdout_scope=scope, accept_result=bool)
    path = adapter.root / "receipts" / (operation + ".json")
    delayed = path.rename(path.with_suffix(".delayed"))
    with pytest.raises(ValueError, match="Unknown final"):
        finalize(reopened, "campaign", adapter, selected, **kwargs)
    assert_reservation_held()
    # A root and a final check really ran for the same bundle under the same evaluator.
    root_op = next(
        key for key, op in before["operations"].items()
        if op["category"] == "root" and op["binding"]["check"] == check
    )
    misplaced = json.loads((path.parent / (root_op + ".json")).read_text())
    genuine = json.loads(delayed.read_text())

    def historical(document):
        binding = {k: v for k, v in document["binding"].items() if k != "operation"}
        payload = {"binding": binding, "result": document["result"]}
        return {**payload, "digest": digest(payload)}

    old_misplaced, old_genuine = historical(misplaced), historical(genuine)
    assert old_misplaced["binding"] == old_genuine["binding"]
    assert misplaced["result"]["execution_sha256"] != genuine["result"]["execution_sha256"]
    for wrong in (misplaced, old_misplaced):
        path.write_text(json.dumps(wrong))
        with pytest.raises(ValueError):
            finalize(reopened, "campaign", adapter, selected, **kwargs)
        assert_reservation_held()
    assert misplaced["binding"]["operation"] == root_op
    assert genuine["binding"]["operation"] == operation

    # Matching a digest is insufficient if the archived transcript came from the root operation.
    execution = adapter.root / "executions" / operation / "execution.json"
    saved_execution = execution.rename(execution.with_suffix(".delayed"))
    source_execution = adapter.root / "executions" / root_op / "execution.json"
    execution.write_bytes(source_execution.read_bytes())
    path.write_text(json.dumps(old_misplaced))
    with pytest.raises(ValueError):
        finalize(reopened, "campaign", adapter, selected, **kwargs)
    assert_reservation_held()

    # The genuine historical receipt likewise needs its own retained execution transcript.
    execution.unlink()
    path.write_text(json.dumps(old_genuine))
    with pytest.raises(ValueError):
        finalize(reopened, "campaign", adapter, selected, **kwargs)
    assert_reservation_held()
    saved_execution.rename(execution)
    result = finalize(reopened, "campaign", adapter, selected, **kwargs)
    assert result["promoted"] is has_deployment
    assert result["verdict"] == ("PASS" if has_deployment else "INCONCLUSIVE")
    after = reopened.read("campaign")
    assert ("stable" in after["state"]) == has_deployment
    assert after["operations"][operation]["status"] == "settled"
    assert after["operations"][operation]["actual_ms"] == receipt["elapsed_ms"]
    assert after["spent_ms"] == before["spent_ms"] + receipt["elapsed_ms"]
    with reopened.store._connection() as db:
        lease = db.execute("SELECT 1 FROM work_domains WHERE operation=?", (operation,)).fetchone()
        assert lease is None
    assert finalize(reopened, "campaign", adapter, selected, **kwargs) == result
    assert reopened.read("campaign") == after


@pytest.mark.parametrize("last_receipt_settled", [False, True])
def test_final_reconciles_without_promoting_changed_winner_bytes(
    runtime, monkeypatch, last_receipt_settled
):
    control, adapter, _, _, root = runtime
    selected = tree.accept(root)
    start_search_for_final(runtime, root_only=True).run()

    def interrupt(*args, **kwargs):
        raise RuntimeError("crash before final promotion")

    if last_receipt_settled:
        monkeypatch.setattr(control, "finish_final", interrupt)
    else:
        interrupt_after_last_final_receipt(control, adapter, monkeypatch)
    kwargs = dict(holdout_scope="held", accept_result=bool)
    with pytest.raises(RuntimeError, match="crash"):
        finalize(control, "campaign", adapter, selected, **kwargs)
    before = control.read("campaign")
    held = [key for key, op in before["operations"].items() if op["status"] == "launched"]
    assert len(held) == (0 if last_receipt_settled else 1)
    (adapter.path(selected) / "candidate.txt").write_text("999")
    reopened = WorkControl(RunStore(control.store.root, control.store.namespace))
    monkeypatch.setattr(adapter, "verify", lambda *args: pytest.fail("Final must not rerun"))
    if held:
        # The other check's genuine receipt cannot release this operation's lease.
        receipts = adapter.root / "receipts"
        pending_receipt = receipts / (held[0] + ".json")
        original = pending_receipt.read_bytes()
        settled = next(
            key for key, op in before["operations"].items()
            if op["category"] == "final" and op["status"] == "settled"
        )
        pending_receipt.write_bytes((receipts / (settled + ".json")).read_bytes())
        with pytest.raises(ValueError):
            finalize(reopened, "campaign", adapter, selected, **kwargs)
        assert reopened.read("campaign") == before
        pending_receipt.write_bytes(original)
    result = finalize(reopened, "campaign", adapter, selected, **kwargs)
    assert result["verdict"] == "INCONCLUSIVE" and not result["promoted"]
    after = reopened.read("campaign")
    assert "stable" not in after["state"]
    assert all(op["status"] == "settled" for op in after["operations"].values())
    assert after["spent_ms"] == before["spent_ms"] + sum(
        after["operations"][key]["actual_ms"] for key in held
    )
    assert finalize(reopened, "campaign", adapter, selected, **kwargs) == result


@pytest.mark.parametrize("stage", ["root", "final"])
def test_qualification_recovers_expired_claim_without_adapter_access(runtime, monkeypatch, stage):
    control, adapter, _, _, root = runtime
    selected = tree.accept(root)
    campaign = "interrupted" if stage == "root" else "campaign"
    if stage == "root":
        control.create(
            campaign, {}, {}, cap_ms=20000, final_reserve_ms=8000, deadline=time.time() + 120
        )
    else:
        start_search_for_final(runtime, root_only=True).run()

    def qualify(authority):
        if stage == "root":
            return qualify_root(authority, campaign, adapter, selected, root.contract)
        return finalize(authority, campaign, adapter, selected, holdout_scope="held",
                        accept_result=bool)

    launch = control.launch
    interrupted = {}

    def crash(campaign, operation):
        op = control.read(campaign)["operations"][operation]
        if stage == "root" or op["binding"]["check"] == tuple(adapter.checks)[-1]:
            interrupted.update(operation=operation, deadline=op["deadline"])
            raise RuntimeError("interrupted before launch")
        return launch(campaign, operation)

    monkeypatch.setattr(control, "launch", crash)
    with pytest.raises(RuntimeError, match="interrupted"):
        qualify(control)
    calls = len(list((adapter.root / "executions").iterdir()))

    def no_adapter_access(*args):
        pytest.fail("An unlaunched check cannot have an adapter receipt")

    monkeypatch.setattr(adapter, "recover", no_adapter_access)
    monkeypatch.setattr(adapter, "verify", no_adapter_access)
    reopened = WorkControl(RunStore(control.store.root, control.store.namespace))
    with pytest.raises(ValueError, match="awaits launch"):
        qualify(reopened)
    monkeypatch.setattr(
        "inferrsi.harness.work_control.time.time", lambda: interrupted["deadline"] + 0.01
    )
    if stage == "root":
        with pytest.raises(ValueError, match="did not start"):
            qualify(reopened)
    else:
        final = qualify(reopened)
        assert final["verdict"] == "INCONCLUSIVE" and not final["promoted"]
        assert final["results"][-1]["not_started"] == "deadline"
        assert qualify(reopened) == final
    doc = reopened.read(campaign)
    op = doc["operations"][interrupted["operation"]]
    assert op["status"] == "settled" and op["actual_ms"] == 0
    assert op["receipt"] == {"not_started": "deadline"}
    assert len(list((adapter.root / "executions").iterdir())) == calls


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


def test_durable_accept_recovers_without_another_policy_decision(runtime, monkeypatch):
    control, adapter, snapshot, settings, root = runtime
    snapshot = replace(snapshot, policy=(0.0,) * 8)
    root = replace(root, contract=replace(
        root.contract, improver_snapshot=digest(snapshot.document())))
    search = Search(control, "campaign", "search", snapshot, settings, adapter)
    # This seed selects ACCEPT first, but would select DRAFT on a second decision.
    search.start(root, seed=7, collect=True)

    def crash(reason):
        assert reason == "accept"
        raise RuntimeError("crash after durable ACCEPT")

    monkeypatch.setattr(search, "finish", crash)
    with pytest.raises(RuntimeError, match="durable ACCEPT"):
        search.run()
    before = control.read("campaign")
    reopened = WorkControl(RunStore(control.store.root, control.store.namespace))
    resumed = Search(reopened, "campaign", "search", snapshot, settings, adapter)
    record = resumed.run()
    assert record["status"] == "complete" and record["stop_reason"] == "accept"
    assert record["selected"] == root.root_id
    assert record["trace"] == before["state"]["searches"]["search"]["trace"]
    assert reopened.read("campaign")["operations"] == before["operations"]
    assert reopened.read("campaign")["spent_ms"] == before["spent_ms"]
    after = reopened.read("campaign")
    assert resumed.run() == record
    assert reopened.read("campaign") == after


@pytest.mark.parametrize("kind", ["draft", "verify"])
@pytest.mark.parametrize("expire_campaign", [False, True])
@pytest.mark.parametrize("crash_before_launch", [False, True])
def test_expired_launch_recovers_unstarted_block_and_resumes(
    runtime, monkeypatch, kind, expire_campaign, crash_before_launch
):
    control, adapter, snapshot, settings, root = runtime
    search = Search(control, "campaign", root.contract.search_id, snapshot, settings, adapter)
    search.start(root, seed=2, collect=False)
    launch = control.launch
    interrupted = {}

    def expire(campaign, operation):
        doc = control.read(campaign)
        if not interrupted and doc["operations"][operation]["category"] == kind:
            interrupted.update(operation=operation, spent_ms=doc["spent_ms"])
            deadline = (
                doc["deadline"] if expire_campaign else doc["operations"][operation]["deadline"]
            )
            monkeypatch.setattr(
                "inferrsi.harness.work_control.time.time", lambda: deadline + 0.001
            )
            if crash_before_launch:
                raise RuntimeError("interrupted before launch")
        return launch(campaign, operation)

    monkeypatch.setattr(control, "launch", expire)
    with pytest.raises(RuntimeError if crash_before_launch else ValueError, match="before launch"):
        search.run()
    assert interrupted
    operation = interrupted["operation"]
    op = control.read("campaign")["operations"][operation]
    if crash_before_launch:
        assert op["status"] == "claimed" and op["receipt"] is None
    else:
        assert op["receipt"] == {"not_started": "deadline"}
    assert not (adapter.root / "executions" / operation).exists()

    def no_adapter_recovery(*args):
        pytest.fail("Conclusive no-launch recovery must use the durable control record")

    monkeypatch.setattr(adapter, "recover", no_adapter_recovery)
    reopened = WorkControl(RunStore(control.store.root, control.store.namespace))
    resumed = Search(reopened, "campaign", root.contract.search_id, snapshot, settings, adapter)
    resumed.recover()
    after = reopened.read("campaign")
    assert after["operations"][operation]["receipt"] == {"not_started": "deadline"}
    assert after["operations"][operation]["actual_ms"] == 0
    resumed.recover()
    assert reopened.read("campaign") == after
    if kind == "verify":
        state = decode(after["state"]["searches"][root.contract.search_id]["tree"])
        receipt = next(r for r in state.receipts if r.attempt.attempt_id == operation)
        assert receipt.verdict.value == "INCONCLUSIVE" and receipt.objective is None
        assert receipt.attempt.check_id in tree.missing_checks(state, receipt.attempt.candidate_id)
    record = resumed.run()
    assert record["status"] == "complete"
    if expire_campaign:
        assert record["stop_reason"] == "limit" and record["selected"] == root.root_id
        assert reopened.read("campaign")["spent_ms"] == interrupted["spent_ms"]
    else:
        assert len(reopened.read("campaign")["operations"]) > len(after["operations"])
        assert reopened.read("campaign")["spent_ms"] > interrupted["spent_ms"]
    assert record["pending"] is None and record["active_action"] is None
    assert record["block_stop_reason"] == "launch_deadline"
    with reopened.store._connection() as db:
        lease = db.execute("SELECT 1 FROM work_domains WHERE operation=?", (operation,)).fetchone()
        assert lease is None


@pytest.mark.parametrize("kind", ["draft", "verify"])
@pytest.mark.parametrize("cleanup_before_reopen", [False, True])
def test_overrun_cleanup_recovery_archives_work_without_adopting_output(
    runtime, monkeypatch, kind, cleanup_before_reopen
):
    control, adapter, snapshot, settings, root = runtime
    search = Search(control, "campaign", root.contract.search_id, snapshot, settings, adapter)
    search.start(root, seed=2, collect=False)
    settle = control.settle
    interrupted = {}

    def overrun(campaign, operation, receipt, **kwargs):
        doc = control.read(campaign)
        op = doc["operations"][operation]
        if op["category"] == kind:
            receipt = {**receipt, "elapsed_ms": op["cap_ms"] + 1, "cleanup_verified": False}
            interrupted.update(operation=operation, receipt=receipt)
            kwargs.update(actual_ms=receipt["elapsed_ms"], cleanup_verified=False)
        return settle(campaign, operation, receipt, **kwargs)

    monkeypatch.setattr(control, "settle", overrun)
    with pytest.raises(ValueError, match="cleanup remains unknown"):
        search.run()
    before, record, current = search.read()
    operation = interrupted["operation"]
    receipt = {**interrupted["receipt"], "cleanup_verified": True}
    assert before["blocked"] and before["operations"][operation]["status"] == "unknown"
    assert record["pending"]["operation"] == operation
    recoveries = []

    def recover(*args):
        recoveries.append(args)
        assert not cleanup_before_reopen
        return receipt

    monkeypatch.setattr(adapter, "recover", recover)
    if cleanup_before_reopen:
        settle("campaign", operation, receipt, actual_ms=receipt["elapsed_ms"],
               cleanup_verified=True,
               transition=lambda state: pytest.fail("Blocked work must not adopt output"))
    reopened = WorkControl(RunStore(control.store.root, control.store.namespace))
    resumed = Search(reopened, "campaign", root.contract.search_id, snapshot, settings, adapter)
    resumed.recover()
    after, archived, recovered = resumed.read()
    assert after["blocked"] and after["operations"][operation]["status"] == "settled"
    assert after["spent_ms"] == before["spent_ms"] + receipt["elapsed_ms"]
    assert archived["spent_ms"] == record["spent_ms"] + receipt["elapsed_ms"]
    assert archived["pending"] is None and archived["active_action"] is None
    assert archived["discarded_operations"] == [operation]
    assert archived["selected"] == record["selected"]
    assert recovered.candidates == current.candidates
    assert tree.accept(recovered) == tree.accept(current)
    if kind == "verify":
        rejected = next(r for r in recovered.receipts if r.attempt.attempt_id == operation)
        assert rejected.verdict.value == "INCONCLUSIVE" and rejected.objective is None
    assert len(recoveries) == (0 if cleanup_before_reopen else 1)
    with reopened.store._connection() as db:
        lease = db.execute("SELECT 1 FROM work_domains WHERE operation=?", (operation,)).fetchone()
        assert lease is None
    resumed.recover()
    with pytest.raises(ValueError, match="Campaign blocked"):
        resumed.run()
    assert reopened.read("campaign") == after
    with pytest.raises(ValueError, match="blocked"):
        reopened.claim("campaign", after["revision"], "another", category="verify", cap_ms=1,
                       domains=("other-device",), binding={})


@pytest.mark.parametrize("kind", ["draft", "verify"])
def test_unknown_launch_is_not_treated_as_conclusively_unstarted(runtime, monkeypatch, kind):
    control, adapter, snapshot, settings, root = runtime
    search = Search(control, "campaign", root.contract.search_id, snapshot, settings, adapter)
    search.start(root, seed=2, collect=False)
    launch = control.launch

    def crash_after_intent(campaign, operation):
        result = launch(campaign, operation)
        if result["category"] == kind:
            raise RuntimeError("lost after launch intent")
        return result

    monkeypatch.setattr(control, "launch", crash_after_intent)
    with pytest.raises(RuntimeError, match="lost after launch intent"):
        search.run()
    before = control.read("campaign")
    monkeypatch.setattr("inferrsi.harness.work_control.time.time", lambda: before["deadline"] + 1)
    with pytest.raises(ValueError, match="Unknown execution"):
        search.recover()
    assert control.read("campaign") == before
    assert search.read()[1]["pending"] is not None
    with pytest.raises(ValueError, match="unsettled"):
        search.finish("limit")


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
    with pytest.raises(ValueError, match="identical"):
        examples((records[0] | {"initial_conditions": "different-root-proof"}, records[1]))
    legacy = {k: v for k, v in records[0].items() if k != "initial_conditions"}
    with pytest.raises(ValueError, match="Legacy search"):
        examples((legacy, records[1]))


def test_legacy_search_can_be_exported_but_cannot_resume_without_initial_evidence(runtime):
    control, adapter, snapshot, settings, root = runtime
    search = Search(control, "campaign", root.contract.search_id, snapshot, settings, adapter)
    search.start(root, seed=0)

    def legacy(state):
        state["searches"][search.search_id].pop("initial_conditions")
        return state

    before = control.update("campaign", control.read("campaign")["revision"], legacy)
    with pytest.raises(ValueError, match="Legacy search"):
        search.run()
    assert control.read("campaign") == before


@pytest.mark.parametrize("change", ["receipt", "execution", "epoch"])
def test_initial_evidence_digest_ignores_only_receiving_ids(runtime, change):
    from inferrsi.harness.search_campaign import import_qualified_root

    control, adapter, snapshot, settings, root = runtime
    first = Search(control, "campaign", root.contract.search_id, snapshot, settings, adapter)
    first.start(root, seed=0)
    imported = import_qualified_root(root, replace(root.contract, search_id="same-proof"))
    second = Search(control, "campaign", "same-proof", snapshot, settings, adapter)
    second.start(imported, seed=1)
    assert first.read()[1]["initial_conditions"] == second.read()[1]["initial_conditions"]
    assert examples((first.finish("test"), second.finish("test")))[2]["returns"] == [0, 0]

    changed = import_qualified_root(root, replace(root.contract, search_id="changed-proof"))
    receipt = changed.receipts[0]
    if change == "receipt":
        receipt = replace(receipt, evidence_digest=digest("different real observation"))
    elif change == "execution":
        receipt = replace(receipt, attempt=replace(receipt.attempt, execution_key="another-run"))
    else:
        dependency = tree.Dependency("proof-epoch", 1)
        receipt = replace(receipt, attempt=replace(receipt.attempt, dependencies=(dependency,)))
        changed = replace(changed, dependencies=(dependency,))
    changed = replace(
        changed,
        receipts=(receipt, *changed.receipts[1:]),
        attempts=tuple(
            receipt.attempt if a.attempt_id == receipt.attempt.attempt_id else a
            for a in changed.attempts
        ),
    )
    third = Search(control, "campaign", "changed-proof", snapshot, settings, adapter)
    third.start(changed, seed=2)
    changed_root = tree.candidate(changed, changed.root_id)
    assert changed_root.artifact_digest == root.candidates[0].artifact_digest
    assert third.read()[1]["initial_conditions"] != first.read()[1]["initial_conditions"]
    with pytest.raises(ValueError, match="identical"):
        examples((first.read()[1], third.finish("test")))


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


def test_late_continuation_preserves_the_consumed_step_budget(runtime):
    from inferrsi.harness.gvo import suffix_examples
    from inferrsi.harness.search_continuations import continue_from
    from inferrsi.harness.vats import Action

    control, adapter, snapshot, settings, root = runtime
    settings = replace(settings, max_steps=2)
    source = Search(control, "campaign", "search", snapshot, settings, adapter)
    source.start(root, seed=12, collect=False)
    original = source.run()
    assert [s["action"]["kind"] for s in original["trace"]] == ["draft", "verify"]
    action = next(Action(**raw) for raw in original["trace"][1]["menu"]
                  if raw["kind"] == "draft")
    args = (source, 1, action.key, "late-suffix")
    record = continue_from(*args, copy_cap_ms=3000, seed=91)
    assert record["continuation"]["step"] == 1
    assert [s["action"]["kind"] for s in record["trace"]] == ["draft"]
    assert record["stop_reason"] == "limit" and record["selected"] == root.root_id
    assert record["gain"] == record["initial_gain"] == 0
    assert suffix_examples(record, expense_weight=0, elapsed_weight=0)[0][1] == 0
    before = control.read("campaign")
    assert continue_from(*args, copy_cap_ms=3000, seed=91) == record
    assert control.read("campaign") == before


def test_forced_accept_recovers_after_copy_without_dispatch(runtime, monkeypatch):
    from inferrsi.harness.search_continuations import continue_from
    from inferrsi.harness.vats import Action

    control, adapter, snapshot, settings, root = runtime
    source = Search(control, "campaign", "search", snapshot, settings, adapter)
    source.start(root, seed=12, collect=False)
    original = source.run()
    action = next(Action(**raw) for raw in original["trace"][0]["menu"]
                  if raw["kind"] == "accept")
    args = (source, 0, action.key, "accept-suffix")
    with monkeypatch.context() as patch:
        def crash(*args):
            raise RuntimeError("crash after continuation copy")

        patch.setattr(Search, "finish", crash)
        with pytest.raises(RuntimeError, match="continuation copy"):
            continue_from(*args, copy_cap_ms=3000, seed=91)
    before = control.read("campaign")
    record = continue_from(*args, copy_cap_ms=3000, seed=91)
    assert record["stop_reason"] == "forced_accept" and record["selected"] == root.root_id
    assert len(record["trace"]) == 1
    assert control.read("campaign")["operations"] == before["operations"]
    assert control.read("campaign")["spent_ms"] == before["spent_ms"]


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
