"""Real CPU service lifecycle under a staged campaign."""

import json
import time

import pytest

from inferrsi.apps.delivery import project
from tests.fixtures.service_reuse import begin, call, diagnose, settings, submit
from tests.fixtures.service_reuse import campaign as campaign


def configure(campaign, *, limit=5, boundaries=(3,), pause=False):
    args = campaign["start"]
    args[args.index("--rounds") + 1] = str(limit)
    args.append("--allow-final-continuation")
    protocol = campaign["config"].parent / "protocol"
    quick = settings()
    if pause:
        quick["stagnation"]["action"] = "pause"
    rows = []
    for i, n in enumerate(boundaries):
        name = "formal" if i == len(boundaries) - 1 else str(i)
        target = {**quick, "protocol_id": name}
        target["commands"] = dict(target["commands"])
        target["commands"].pop("profile")
        (protocol / (name + ".json")).write_text(json.dumps(target))
        rows.append(
            dict(
                stage_id=name,
                after_completed_rounds=n,
                evaluation_config="./" + name + ".json",
                switch_timeout_seconds=25,
                first_round_timeout_seconds=15,
            )
        )
    quick["staged_evaluation"] = dict(
        initial_stage_id="quick", formal_stage_id="formal", transitions=rows
    )
    campaign["config"].write_text(json.dumps(quick))


@pytest.mark.parametrize("limit,boundaries", [(3, (3,)), (5, (2, 2)), (5, (3, 2)), (5, (True,))])
def test_unreachable_plan(campaign, limit, boundaries):
    configure(campaign, limit=limit, boundaries=boundaries)
    with pytest.raises(SystemExit):
        call(campaign, "start")
    assert not campaign["root"].exists()


def test_switch_and_continue(campaign, monkeypatch):
    configure(campaign)
    objectives = settings()["objectives"]
    objectives[0]["gain_threshold"] = 10
    change_formal(campaign, objectives=objectives)
    begin(campaign)
    submit(campaign, version="one", a=93, b=103)
    second = submit(campaign, version="two", a=89, b=106)
    assessment = second["latest_observation"]["assessment"]
    assert assessment["verdict"] == "PASS"
    guard = assessment["performance"]["metrics"]["b"]
    assert -3 < guard["parent_change"] < 0 and "initial_change" not in guard
    assert "cumulative_regression_limit" not in guard["thresholds"]
    before = submit(campaign, version="three", a=84)
    assert before["pending_stage"] == "formal"
    assert before["final_block_reason"] == "mandatory_stage_pending"
    switch = call(campaign, "refresh-references", "--next-stage", "--reason", "planned")
    assert switch["reference_epoch"] == 1, switch["latest_observation"]
    assert switch["stage_id"] == "formal" and switch["allocated_rounds"] == 3
    assert switch["stage_protocol"] == "frozen/protocol/formal.json"
    assert switch["final_attempts"] == [] and not (campaign["root"] / "final").exists()
    assert switch["best"] is None and not switch["can_finalize"]
    backfill = call(campaign, "profile", "--round", "1")
    assert backfill["cleanup_verified"]
    summary = json.loads((campaign["root"] / "summary.json").read_text())
    assert summary["stage_id"] == summary["protocol_id"] == "formal"
    assert not summary["final_assessment"]
    refresh = switch["latest_observation"]
    assert [r["binding"]["revision"] for r in refresh["execution"]["runs"]] == [
        before["comparison_parent"]["revision"]
    ]
    assert not (campaign["root"] / refresh["path"] / "baseline").exists()
    assert switch["initial_reference"] == before["initial_reference"]
    assert switch["comparison_parent"]["stage_id"] == "formal"
    from inferrsi.apps.views.dashboard import dashboard_snapshot
    from tests.apps.test_project_service_reuse import read_first_hit

    diagnose(campaign)
    read_first_hit(campaign, "prefix cache")
    first = submit(campaign, version="four", a=75, final_a=79)
    assert first["can_finalize"], first["latest_observation"]
    search, read = first["latest_observation"]["contexts"]
    assert read["search_ref"] == search["path"]
    assert all(c["stage_id"] == "formal" and c["reference_epoch"] == 1 for c in (search, read))
    dashboard = dashboard_snapshot(campaign["root"])["data"]
    assert dashboard["service_optimization"]["protocol_id"] == "formal"
    assert dashboard["candidates"][0]["service_attempt"]["stage_id"] == "quick"
    last = dashboard["candidates"][-1]["service_attempt"]
    assert last["stage_protocol"] == switch["stage_protocol"]
    failed = call(campaign, "final", "--reason", "first independent run")
    assert failed["stage_final"]["verdict"] == "FAIL" and failed["remaining_rounds"] == 1
    baseline = failed["final"]["execution"]["final_baseline"]
    assert baseline["revision"] == before["initial_reference"]["revision"]
    assert baseline["stage_id"] == "formal" and baseline["quality_score"] is None
    assert baseline["binding"]["run_id"] != before["initial_reference"]["binding"]["run_id"]
    metric = failed["stage_final"]["performance"]["metrics"]["a"]
    assert 4 < metric["parent_change"] < metric["thresholds"]["gain_threshold"] == 10
    from tests.fixtures.service_reuse import commit

    commit(campaign["repo"], version="five", a=65)
    args = (
        "--candidate",
        campaign["repo"],
        "--hypothesis",
        "fix",
        "--continue-after-final",
        failed["final"]["attempt_id"],
        "--continuation-reason",
        "fix",
    )
    from inferrsi.harness.manager import _state

    class Interrupted(BaseException):
        pass

    def interrupt(*args):
        raise Interrupted

    with monkeypatch.context() as patch:
        patch.setattr(_state, "_service_execute", interrupt)
        with pytest.raises(Interrupted):
            call(campaign, "round", *args)
    state = call(campaign, "status")
    pending = state["pending"]
    assert state["allocated_rounds"] == 5 and state["completed_rounds"] == 4
    assert not (campaign["root"] / pending["path"] / "request.json").exists()
    proof = campaign["root"].parent / "cleanup.json"
    proof.write_text(
        json.dumps(
            {
                "attempt_id": pending["attempt_id"],
                "observed_at": time.time(),
                "cleanup_complete": True,
                "services": [],
                "reason": "No launch",
            }
        )
    )
    recovered = call(campaign, "recover", "--cleanup-receipt", proof, expected=2)
    assert recovered["completed_rounds"] == 4
    with pytest.raises(SystemExit):
        call(campaign, "round", *args)
    campaign["capsys"].readouterr()
    again = call(
        campaign,
        "round",
        *args[:4],
        "--retry-of",
        pending["attempt_id"],
        "--repair-reason",
        "Verified cleanup",
    )
    assert again["completed_rounds"] == 5 and again["stage_final"] is None
    assert call(campaign, "recover")["completed_rounds"] == 5
    # Snapshot after the cutoff still attributes the first FAIL to its original run.
    from types import SimpleNamespace

    with monkeypatch.context() as patch:
        patch.setattr(_state, "time", SimpleNamespace(time=lambda: time.time() + 10000))
        expired = call(campaign, "status")
        assert expired["final_block_reason"] == "deadline_exhausted"
        assert expired["stage_final"] is None and expired["final_attempts"][0]["verdict"] == "FAIL"
        _, snapshot, _ = project(
            campaign["root"], export_id="deadline", observed_at=time.time() + 10000
        )
        assert snapshot["execution"]["final_block_reason"] == "deadline_exhausted"
        assert snapshot["final"] is None and snapshot["final_attempts"][0]["verdict"] == "FAIL"
    final = call(campaign, "final", "--reason", "second independent run")
    assert [a["verdict"] for a in final["final_attempts"]] == ["FAIL", "PASS"]
    assert all(a["protocol_id"] == "formal" for a in final["final_attempts"])
    _, report, _ = project(campaign["root"], export_id="staged")
    assert all(a["stage_id"] == "formal" for a in report["final_attempts"])


def change_formal(campaign, **values):
    path = campaign["config"].parent / "protocol/formal.json"
    settings = json.loads(path.read_text())
    settings.update(values)
    path.write_text(json.dumps(settings))
    return settings


def switch(campaign, *extra, expected=0):
    return call(
        campaign,
        "refresh-references",
        "--next-stage",
        "--reason",
        "boundary",
        *extra,
        expected=expected,
    )


@pytest.mark.parametrize("field", ["scenarios", "objectives"])
def test_reordering_does_not_add_a_constraint(tmp_path, field):
    from inferrsi.harness.executor import service_stage_descriptor

    formal = settings()
    extra = {**formal, field: list(reversed(formal[field]))}
    (tmp_path / "extra.json").write_text(json.dumps(extra))
    row = dict(stage_id="extra", evaluation_config="extra.json", switch_timeout_seconds=25,
               first_round_timeout_seconds=15)
    with pytest.raises(ValueError, match="must extend"):
        service_stage_descriptor(row, formal, tmp_path, appended=True)


def test_cross_epoch_pause_with_original_commit_as_parent(campaign):
    configure(campaign, boundaries=(2,), pause=True)
    begin(campaign)
    submit(campaign, version="slow1", a=110)
    assert submit(campaign, version="slow2", a=120)["state"] == "paused"
    with pytest.raises(SystemExit):
        switch(campaign)
    campaign["capsys"].readouterr()
    call(campaign, "resume", "--reason", "Two rejected quick candidates")
    entered = switch(campaign)
    assert len(entered["latest_observation"]["execution"]["runs"]) == 1
    assert entered["stagnation"]["consecutive"] == 0 and not entered["stagnation"]["notified"]
    diagnose(campaign)
    assert submit(campaign, version="slow3", a=130)["state"] == "active"
    assert submit(campaign, version="slow4", a=140)["state"] == "paused"
    events = call(campaign, "recover")["stagnation"]["events"]
    assert [item["round"] for item in events] == [2, 4]
    assert call(campaign, "recover")["stagnation"]["events"] == events


def test_reference_retry_requires_verified_parent_cleanup(campaign, monkeypatch):
    from inferrsi.harness import executor

    configure(campaign, limit=2, boundaries=(1,))
    quality = {**settings()["quality"], "threshold": 2}
    change_formal(campaign, quality=quality)
    begin(campaign)
    submit(campaign, version="fast", a=90)
    original = executor.execute_service_attempt

    class Crash(BaseException):
        pass

    def crash(root, directory, plan, job, deadline):
        if job.get("reference_kind") == "stage_parent":
            raise Crash
        return original(root, directory, plan, job, deadline)

    with monkeypatch.context() as patch:
        patch.setattr(executor, "execute_service_attempt", crash)
        with pytest.raises(Crash):
            switch(campaign)
    pending = call(campaign, "status")["pending"]
    failed = call(campaign, "recover", expected=2)
    assert failed["reference_epoch"] == 0 and failed["stage_id"] == "quick"
    assert not failed["can_finalize"] and failed["allocated_rounds"] == 1
    assert failed["latest_observation"]["execution"]["references"] == []
    with pytest.raises(SystemExit):
        switch(campaign, "--retry-of", pending["attempt_id"], "--repair-reason", "reconcile")
    campaign["capsys"].readouterr()
    proof = campaign["root"].parent / "cleanup.json"
    directory = campaign["root"] / pending["path"]
    assert not (directory / "parent/service/owner.json").exists()
    proof.write_text(
        json.dumps(
            {
                "attempt_id": pending["attempt_id"],
                "observed_at": time.time(),
                "reason": "Inspected",
                "cleanup_complete": True,
                "services": [],
            }
        )
    )
    entered = switch(
        campaign,
        "--retry-of",
        pending["attempt_id"],
        "--repair-reason",
        "reconcile",
        "--cleanup-receipt",
        proof,
    )
    runs = entered["latest_observation"]["execution"]["runs"]
    assert [r["assessment"]["quality_passed"] for r in runs] == [False]
    assert entered["comparison_parent"]["quality_score"] == 1
    from inferrsi.harness import evaluator

    child = (campaign["root"] / entered["comparison_parent"]["path"]).parent
    assert evaluator.service_reference_result(
        campaign["root"], child, {}, {}, {**runs[0], "assessment": "malformed"}
    ) == (True, False)
    assert entered["reference_epoch"] == call(campaign, "recover")["reference_epoch"] == 1
    diagnose(campaign)
    result = submit(campaign, version="under-gate", a=80)
    assert result["latest_observation"]["assessment"]["verdict"] == "FAIL"
    closed = call(campaign, "final", "--reason", "limit reached")
    assert closed["state"] == "completed" and closed["stage_outcome"] == "INCONCLUSIVE"


def prepare_append(campaign, limit, *, final_a=80):
    configure(campaign, limit=limit)
    campaign["start"].remove("--allow-final-continuation")
    formal = settings()
    formal["scenarios"] = formal["scenarios"][:1]
    formal["objectives"] = formal["objectives"][:1]
    formal["ranking"] = ["a"]
    formal = change_formal(
        campaign, **{k: formal[k] for k in ("scenarios", "objectives", "ranking")}
    )
    extra = {
        **formal,
        "protocol_id": "extra",
        "scenarios": settings()["scenarios"],
        "objectives": [*formal["objectives"], {**settings()["objectives"][1], "gain": False}],
    }
    tmp = campaign["config"].parent
    protocol = tmp / "protocol"
    (protocol / "extra.json").write_text(json.dumps(extra))
    (protocol / "weakened.json").write_text(
        json.dumps({**extra, "quality": {**extra["quality"], "threshold": 0}})
    )
    row = {
        "stage_id": "extra",
        "evaluation_config": "extra.json",
        "switch_timeout_seconds": 30,
        "first_round_timeout_seconds": 15,
    }
    path = tmp / "append.json"
    path.write_text(json.dumps(row))
    begin(campaign)
    submit(campaign, version="quick-a", a=98)
    submit(campaign, version="quick-b", a=96)
    submit(campaign, version="first", a=90)
    switch(campaign)
    diagnose(campaign)
    submit(campaign, version="second", a=80, final_a=final_a)
    args = ("refresh-references", "--stage-config", path, "--reason", "extra workload")
    return args, row, extra


def test_failed_final_cannot_reopen_by_appending(campaign):
    args, _, _ = prepare_append(campaign, limit=5, final_a=100)
    failed = call(campaign, "final", "--reason", "formal")
    assert failed["stage_outcome"] == "FAIL" and not failed["can_continue"]
    before = (campaign["root"] / "state.json").read_bytes()
    with pytest.raises(SystemExit):
        call(campaign, *args)
    assert "Campaign completed" in campaign["capsys"].readouterr().err
    assert (campaign["root"] / "state.json").read_bytes() == before


def test_switch_without_final_then_evaluate_added_guard(campaign):
    args, _, _ = prepare_append(campaign, limit=5)
    entered = call(campaign, *args)
    assert entered["stage_id"] == "extra" and entered["final_attempts"] == []
    assert not (campaign["root"] / "final").exists()
    diagnose(campaign)
    submit(campaign, version="third", a=70, final_b=110)
    result = call(campaign, "final", "--reason", "check added workload")
    assert result["stage_outcome"] == "FAIL"
    metrics = result["stage_final"]["performance"]["metrics"]
    assert metrics["a"]["gain_passed"] and not metrics["b"]["limits_passed"]
    assert [a["stage_id"] for a in result["final_attempts"]] == ["extra"]


@pytest.mark.parametrize("limit", [4, 5])
def test_append_admission(campaign, limit, monkeypatch):
    args, row, extra = prepare_append(campaign, limit)
    tmp = campaign["config"].parent
    path = tmp / "append.json"
    if limit == 4:
        with pytest.raises(SystemExit):
            call(campaign, *args)
        campaign["capsys"].readouterr()
        assert call(campaign, "status")["can_finalize"]
        return
    path.write_text(json.dumps({**row, "evaluation_config": "weakened.json"}))
    with pytest.raises(SystemExit):
        call(campaign, *args)
    assert "preserve all existing acceptance gates" in campaign["capsys"].readouterr().err
    (tmp / "only-beside-descriptor.json").write_text(json.dumps(extra))
    path.write_text(json.dumps({**row, "evaluation_config": "only-beside-descriptor.json"}))
    with pytest.raises(SystemExit):
        call(campaign, *args)
    assert "Missing, symbolic or oversized JSON" in campaign["capsys"].readouterr().err
    # Only the retained copy of the declared protocol can supply the appended config.
    (tmp / "protocol" / "extra.json").unlink()
    path.write_text(json.dumps({**row, "switch_timeout_seconds": 99999}))
    with pytest.raises(SystemExit):
        call(campaign, *args)
    campaign["capsys"].readouterr()
    assert call(campaign, "status")["can_finalize"]
    path.write_text(json.dumps(row))
    # Stop after the parent receipts are durable but before the switch is committed.
    from inferrsi.harness.manager import _state

    closed = call(campaign, "final", "--reason", "formal")
    formal_id = closed["final"]["attempt_id"]
    execute = _state._service_execute

    class Interrupted(BaseException):
        pass

    def interrupt(*args):
        assert execute(*args)["assessment"]["verdict"] == "PASS"
        raise Interrupted

    with monkeypatch.context() as patch:
        patch.setattr(_state, "_service_execute", interrupt)
        with pytest.raises(Interrupted):
            call(campaign, *args)
    waiting = call(campaign, "status")
    assert waiting["pending_stage"] == "extra" and waiting["stage_final"] is None
    assert waiting["final"]["attempt_id"] == formal_id
    summary = json.loads((campaign["root"] / "summary.json").read_text())
    assert summary["final_assessment"] is None
    assert summary["final_block_reason"] == "mandatory_stage_pending"
    assert summary["retained_final_attempt_id"] == formal_id
    _, exported, _ = project(campaign["root"], export_id="pending-extra")
    assert exported["final"] is None
    assert exported["execution"]["final_block_reason"] == "mandatory_stage_pending"
    assert exported["final_attempts"][0]["stage_id"] == "formal"
    cancelled = call(
        campaign, "resume", "--reason", "Cancel interrupted switch after verified cleanup"
    )
    assert cancelled["latest_observation"]["assessment"]["reason"] == "stage_switch_cancelled"
    assert cancelled["stage_id"] == "formal" and cancelled["reference_epoch"] == 1
    assert call(campaign, "status")["pending_stage"] == "extra"
    augmented = switch(campaign)
    assert augmented["stage_id"] == "extra" and not augmented["can_finalize"]
    diagnose(campaign)
    submit(campaign, version="third", a=70)
    final = call(campaign, "final", "--reason", "extra")
    assert final["stage_final"]["verdict"] == "PASS"
    _, report, _ = project(campaign["root"], export_id="extra-final")
    assert [a["current"] for a in report["final_attempts"]] == [False, True]
    for attempt in final["final_attempts"]:
        frozen = campaign["root"] / attempt["stage_protocol"]
        raw = frozen.read_bytes()
        changed = json.loads(raw)
        changed["quality"]["threshold"] += 1
        frozen.chmod(0o644)
        frozen.write_text(json.dumps(changed))
        with pytest.raises(ValueError, match="differs from the frozen descriptor"):
            project(campaign["root"], export_id="changed-protocol")
        frozen.write_bytes(raw)


@pytest.mark.parametrize("missing", [True, False])
def test_switch_quality_uses_remeasured_parent(campaign, missing):
    configure(campaign, limit=2, boundaries=(1,))
    quality = settings()["quality"]
    del quality["threshold"]
    quality.update(mode="baseline_comparison", tolerance=0)
    change_formal(campaign, quality=quality)
    protocol = campaign["config"].parent / "protocol/protocol.py"
    original = protocol.read_text()
    # The quick scorer accepts the parent. The formal scorer returns a lower score or no score.
    marker = 'if config.get("quality_rejected"):'
    protocol.write_text(
        original.replace(
            marker,
            """
                if request.get("stage_id") == "formal" and config["version"] == "fast":
                    body["quality"] = 0
                    if config.get("missing_formal_score"):
                        del body["quality"]
                """
            + marker,
        )
    )
    begin(campaign)
    submit(campaign, version="fast", a=90, missing_formal_score=missing)
    entered = switch(campaign, expected=2 if missing else 0)
    if missing:
        assert entered["stage_id"] == "quick" and entered["pending_stage"] == "formal"
        assert entered["latest_observation"]["execution"]["references"] == []
        return
    assert entered["initial_reference"]["quality_score"] == 1
    assert entered["comparison_parent"]["quality_score"] == 0
    assert len(entered["latest_observation"]["execution"]["runs"]) == 1
    diagnose(campaign)
    candidate = submit(campaign, version="still-low", a=80, quality=0)
    assert candidate["latest_observation"]["assessment"]["verdict"] == "PASS"


def test_first_round_retry_budget(campaign, monkeypatch):
    from types import SimpleNamespace

    from inferrsi.harness.manager import _state

    configure(campaign, limit=2, boundaries=(1,))
    change_formal(campaign, commands=settings()["commands"])
    begin(campaign)
    submit(campaign, version="quick", a=90)
    entered = switch(campaign)
    diagnose(campaign)
    failed = submit(campaign, version="missing", a=80, quality_missing=True, expected=2)
    attempt = failed["latest_observation"]
    assert failed["completed_rounds"] == 1 and failed["stage_completed_rounds"] == 0
    assert attempt["stage_timeout_seconds"] == 15
    args = (
        "round",
        "--candidate",
        campaign["repo"],
        "--hypothesis",
        "retry",
        "--retry-of",
        attempt["attempt_id"],
        "--repair-reason",
        "fix scorer input",
    )
    instant = time.time() + entered["remaining_search_seconds"] - 5
    with monkeypatch.context() as patch:
        patch.setattr(_state, "time", SimpleNamespace(time=lambda: instant))
        with pytest.raises(SystemExit):
            call(campaign, *args)
        assert "first stage round" in campaign["capsys"].readouterr().err
        assert call(campaign, "status", expected=2)["allocated_rounds"] == 2
    repaired = submit(
        campaign, version="repaired", a=80, profile_mode="failed", retry=attempt["attempt_id"]
    )
    assert repaired["can_finalize"] and repaired["profiling_error"]["status"] == "failed"
    assert repaired["stage_completed_rounds"] == 1 and repaired["allocated_rounds"] == 2


@pytest.mark.parametrize("broken,target", [(False, 20), (False, 35), (True, 20)])
def test_final_reads_original_commit_under_final_protocol(campaign, monkeypatch, broken, target):
    from tests.fixtures import service_reuse

    configure(campaign, limit=2, boundaries=(1,))
    approve = service_reuse.approved_start
    monkeypatch.setattr(service_reuse, "approved_start", lambda args: approve(args, overrides={
        "protocol.target_kind": "relative_improvement_pct", "protocol.target_value": target,
    }))
    protocol = campaign["config"].parent / "protocol/protocol.py"
    marker = 'if config.get("missing_metric"):'
    protocol.write_text(protocol.read_text().replace(marker, (
        'if request.get("stage_id") == "formal" and config["version"] == "baseline":\n'
        '                    body["scenarios"]["a"]["latency"] = 120\n'
        + ('                    del body["scenarios"]["a"]["latency"]\n' if broken else '')
        + '                ' + marker
    )))
    quick = begin(campaign)
    submit(campaign, version="one", a=90)
    entered = switch(campaign)
    assert entered["comparison_parent"]["quality_score"] == 1
    diagnose(campaign)
    submit(campaign, version="two", a=85)
    result = call(campaign, "final", "--reason", "fresh baseline", expected=2 if broken else 0)
    final = result["final"]
    directory = campaign["root"] / final["path"]
    if broken:
        assert final["assessment"]["reason"] == "unverifiable_final_baseline"
        assert final["assessment"]["verdict"] == "INCONCLUSIVE"
        assert not (directory / "request.json").exists()
        return
    baseline = final["execution"]["final_baseline"]
    assert baseline["measurements"]["values"]["a"] == 120
    assert quick["initial_reference"]["measurements"]["values"]["a"] == 100
    assert final["parent"]["measurements"]["values"]["a"] == 90
    assert final["assessment"]["verdict"] == ("PASS" if target == 20 else "FAIL")
    if target == 35:
        assert final["assessment"]["reason"] == "final_performance_target_not_met"
    assert baseline["binding"]["service_id"] != final["execution"]["binding"]["service_id"]
    assert result["completed_rounds"] == 2


def test_older_frozen_staged_plan_replays_its_original_comparisons(campaign, monkeypatch):
    from inferrsi.harness import executor

    configure(campaign, limit=2, boundaries=(1,))
    prepare = executor.prepare_service

    def previous_plan(*args):
        plan = prepare(*args)
        del plan["stage_parent_only"]
        return plan

    with monkeypatch.context() as patch:
        patch.setattr(executor, "prepare_service", previous_plan)
        begin(campaign)
    submit(campaign, version="one", a=90)
    entered = switch(campaign)
    assert len(entered["latest_observation"]["execution"]["runs"]) == 2
    diagnose(campaign)
    selected = submit(campaign, version="two", a=80)
    assert selected["latest_observation"]["assessment"]["performance"]["metrics"]["a"][
        "initial_change"
    ] == 20
    final = call(campaign, "final", "--reason", "replay frozen rules")["final"]
    assert final["assessment"]["verdict"] == "PASS" and "final_baseline" not in final["execution"]
