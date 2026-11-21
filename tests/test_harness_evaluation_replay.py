"""Evaluation reentry is decided before preparation, target binding or a new launch."""

import sqlite3
from copy import deepcopy

import pytest

from inferrsi.harness import execution_service, run_store
from inferrsi.harness.api import Harness, LocalCpuTarget
from inferrsi.harness.errors import PublicError
from tests.test_benchmark_preparation import preparation as preparation
from tests.test_harness_entry_verification import evaluation as evaluation


def counts(case):
    with sqlite3.connect(case["store"].root / run_store.INDEX_NAME) as connection:
        return (connection.execute("SELECT count(*) FROM attempts").fetchone()[0],
                connection.execute("SELECT count(*) FROM records").fetchone()[0])


def replay_only(case, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("replay attempted artifact IO, source binding, clock reset or execution")

    class Never:
        open = forbidden

    monkeypatch.setattr(execution_service.local_process, "execute_command", forbidden)
    monkeypatch.setattr(execution_service.entry_code, "capture_module", forbidden)
    monkeypatch.setattr(execution_service, "_deadline_seconds", forbidden)
    retired = LocalCpuTarget("retired", "2", work_root=case["target"].work_root / "retired")
    return Harness(case["store"], retired, artifact_reader=Never())


def test_completed_evaluation_replays_the_original_ref_without_rebinding(evaluation, monkeypatch):
    case = evaluation
    saved = deepcopy(case["spec"])
    record = case["harness"].execute(saved)
    assert record["started"] is True and record["exit_code"] == 0
    case["modules"].joinpath("fixture_worker.py").unlink()
    replayed = replay_only(case, monkeypatch).execute(saved)
    assert replayed["record_ref"] == record["record_ref"]
    assert replayed["target_binding"] == record["target_binding"]
    assert replayed["request_digest"] == run_store.request_digest(saved)
    assert replayed["budget_admission"] == record["budget_admission"]
    assert saved == case["spec"]
    assert counts(case) == (1, 1)


@pytest.mark.parametrize("field", ["deadline", "budget", "prepared-ref"])
def test_changed_evaluation_digest_conflicts_without_any_binding(evaluation, monkeypatch, field):
    case = evaluation
    original = case["harness"].execute(case["spec"])
    changed = deepcopy(case["spec"])
    if field == "deadline":
        changed["deadline_utc"] = "2098-01-01T00:00:00Z"
    elif field == "budget":
        changed["budget"]["scope_id"] = "another-scope"
    else:
        changed["prepared_ref"]["artifact"]["sha256"] = "0" * 64
    with pytest.raises(PublicError) as caught:
        replay_only(case, monkeypatch).execute(changed)
    assert caught.value.code == "RequestConflict"
    assert counts(case) == (1, 1)
    assert case["store"].read(original["attempt_id"])["record_ref"] == original["record_ref"]


@pytest.mark.parametrize("live", [True, False], ids=["live-owner", "owner-gone"])
def test_existing_attempt_without_a_record_never_implicitly_starts(evaluation, monkeypatch, live):
    case = evaluation
    attempt = {key: case["spec"][key] for key in execution_service.ATTEMPT_FIELDS}
    claim = case["store"].claim(attempt, run_store.request_digest(case["spec"]))
    try:
        if not live:
            claim.release()
        with pytest.raises(PublicError) as caught:
            replay_only(case, monkeypatch).execute(case["spec"])
        assert caught.value.code == ("AttemptInProgress" if live else "RecoveryRequired")
        assert caught.value.latest_record_ref is None
        assert counts(case) == (1, 0)
    finally:
        claim.release()


def test_caller_mutation_during_preparation_read_cannot_change_the_saved_request(
    evaluation,
):
    case = evaluation
    original = deepcopy(case["spec"])

    class Mutating:
        def open(self, ref):
            case["spec"]["budget"]["scope_id"] = "mutated-caller"
            case["spec"]["output_root"] = "mutated-caller"
            return case["reader"].open(ref)

    harness = Harness(case["store"], case["target"], artifact_reader=Mutating())
    result = harness.execute(case["spec"])
    assert result["request_digest"] == run_store.request_digest(original)
    assert result["budget_admission"]["scope_id"] == original["budget"]["scope_id"]
    assert result["started"] is True and result["exit_code"] == 0
