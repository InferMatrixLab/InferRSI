"""Profile-only recovery uses the capture's own receipts and original round inputs."""

import json
import time
from types import SimpleNamespace

import pytest
from test_project_service_reuse import begin, call, settings, submit
from test_project_service_reuse import campaign as campaign

from inferrsi.harness import optimization, service_backfill
from inferrsi.harness import project_service as service
from inferrsi.harness.atomic_json import atomic_write_json


@pytest.mark.parametrize("proven", [0, 3])
def test_delayed_recover_only_accounts_for_durable_backfill_progress(campaign, monkeypatch, proven):
    begin(campaign)
    attempt = submit(campaign, version="profile-target", a=90)["latest_observation"]
    root = campaign["root"]
    original = service.read(root / "state.json")
    original_plan = service.read(root / "plan.json")
    now = time.time()

    def crash(root, directory, plan, pending, deadline):
        binding = {
            **attempt["execution"]["binding"],
            "attempt_id": pending["attempt_id"],
            "service_id": "capture-service",
            "run_id": "capture-run",
        }
        atomic_write_json(directory / "request.json", binding)
        (directory / "execution/profile").mkdir(parents=True)
        (directory / "execution/profile/stderr.log").write_text("Profiler driver interrupted")
        atomic_write_json(
            directory / "execution/execution.json",
            {
                "status": "running",
                "binding": binding,
                "capture": {
                    "id": pending["attempt_id"],
                    "started_at": now,
                    "elapsed_seconds": proven,
                },
                "steps": [{"id": "profile", "status": "running"}],
            },
        )
        raise SystemExit(75)

    monkeypatch.setattr(service, "execute", crash)
    with pytest.raises(SystemExit) as stopped:
        call(campaign, "profile", "--round", 1)
    assert stopped.value.code == 75
    pending = service.read(root / "state.json")["pending"]
    capture = pending["attempt_id"]
    evidence = root / "inspection.json"
    atomic_write_json(
        evidence,
        {
            "attempt_id": capture,
            "observed_at": now + 60,
            "reason": "Checked all processes",
            "cleanup_complete": True,
            "services": [],
        },
    )
    monkeypatch.setattr(time, "time", lambda: now + 60)
    recovered = call(campaign, "recover", "--cleanup-receipt", evidence, expected=130)
    assert recovered["profiling_error"]["status"] == "interrupted"
    assert "not recorded" in recovered["profiling_error"]["message"]
    assert "Profiler driver interrupted" in recovered["profiling_error"]["message"]
    assert (root / recovered["profiling_error"]["log"]).is_file()
    status = call(campaign, "recover")
    state = service.read(root / "state.json")
    assert state["attempts"] == original["attempts"] and state["best"] == original["best"]
    assert state["pending"] is None
    assert state["profiling_accounting"] == {
        **original["profiling_accounting"],
        capture: {"started_at": now, "elapsed_seconds": proven},
    }
    elapsed = sum(entry["elapsed_seconds"] for entry in state["profiling_accounting"].values())
    assert status["remaining_seconds"] == pytest.approx(original["deadline"] - now - 60 + elapsed)
    assert status["remaining_seconds"] - status["remaining_search_seconds"] == pytest.approx(
        original_plan["final_reserve_seconds"]
    )
    assert not (root / attempt["path"] / "backfills/index.json").exists()


def test_backfill_timeout_in_readiness_preserves_inline_and_runs_cleanup(campaign):
    config = settings()
    config["sampling"]["profile_timeout_seconds"] = 2
    campaign["config"].write_text(json.dumps(config))
    script = campaign["root"].parent / "protocol/protocol.py"
    script.write_text(
        script.read_text().replace(
            'if phase == "ready":',
            'if phase == "ready" and "backfills" in attempt.parts:\n'
            '        time.sleep(30)\n    if phase == "ready":',
        )
    )
    begin(campaign)
    attempt = submit(campaign, version="timeout-at-ready", a=90)["latest_observation"]
    result = call(campaign, "profile", "--round", 1, expected=2)
    assert result["cleanup_verified"] is True
    assert result["profiling_error"]["stage"] == "ready"
    assert result["profiling_error"]["status"] == "timed_out"
    assert result["profiling"] == attempt["profiling"]
    path = campaign["root"] / attempt["path"] / "backfills" / result["capture_id"]
    steps = service.read(path / "execution/execution.json")["steps"]
    assert any(step["id"] == "stop" and step["status"] == "completed" for step in steps)


@pytest.mark.parametrize("input_name", ["effective-config.json", "request.json", "conditions"])
def test_backfill_rejects_incompatible_or_unverifiable_inputs(campaign, input_name):
    begin(campaign)
    target = submit(campaign, version="bound-candidate", a=90)["latest_observation"]
    root = campaign["root"]
    if input_name == "conditions":
        path = root / "state.json"
        data = service.read(path)
        data["conditions"]["topology"] = "different topology"
    else:
        path = root / target["path"] / input_name
        data = service.read(path)
        data["mode" if input_name == "effective-config.json" else "run_id"] = "unexpected"
    atomic_write_json(path, data)
    result = call(campaign, "profile", "--round", 1, expected=2)
    assert "Cannot reproduce" in result["profiling_error"]["message"]
    assert "capture_id" not in result
    assert not (root / target["path"] / "backfills").exists()


def test_older_compatible_epoch_can_be_profiled_without_enabling_final(campaign):
    begin(campaign)
    target = submit(campaign, version="historical", a=90)["latest_observation"]
    root = campaign["root"]
    conditions = {**target["conditions"], "id": "later", "effective_config": {"mode": "later"}}
    path = root.parent / "new-conditions.json"
    atomic_write_json(path, conditions)
    call(campaign, "refresh-references", "--conditions", path, "--reason", "New configuration")
    capture = call(campaign, "profile", "--round", 1)
    receipt = service.read(root / capture["profiling"]["result"])
    assert receipt["binding"]["conditions"] == target["conditions"]
    assert receipt["binding"]["effective_config"] == target["conditions"]["effective_config"]
    status = call(campaign, "status")
    assert status["can_finalize"] is False and status["accepted_attempt_ids"] == []


def test_damaged_most_recent_capture_falls_back_to_earlier_published_capture(campaign):
    begin(campaign)
    target = submit(campaign, version="reprofile", a=90)["latest_observation"]
    first = call(campaign, "profile", "--round", 1)["profiling"]
    second = call(campaign, "profile", "--round", 1)
    path = campaign["root"] / target["path"] / "backfills" / second["capture_id"]
    execution = path / "execution/execution.json"
    atomic_write_json(execution, {**service.read(execution), "profile": ["invalid"]})
    status = call(campaign, "status")
    assert status["latest_observation"]["profiling"] == first
    assert status["can_finalize"] is True


def test_recover_after_index_publication_commits_same_capture_once(campaign, monkeypatch):
    begin(campaign)
    target = submit(campaign, version="publish-once", a=90)["latest_observation"]
    root = campaign["root"]

    def crash_at_state_commit(path, value):
        if path == root / "state.json" and value["pending"] is None:
            raise SystemExit(75)
        atomic_write_json(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(service_backfill, "atomic_write_json", crash_at_state_commit)
        with pytest.raises(SystemExit) as stopped:
            call(campaign, "profile", "--round", 1)
        assert stopped.value.code == 75
    capture_id = service.read(root / "state.json")["pending"]["attempt_id"]
    index = root / target["path"] / "backfills/index.json"
    assert service.read(index)["captures"] == [capture_id]
    recovered = call(campaign, "recover")
    assert recovered["capture_id"] == capture_id and recovered["profiling"]["available"]
    call(campaign, "recover")
    state = service.read(root / "state.json")
    assert state["pending"] is None and capture_id in state["profiling_accounting"]
    assert service.read(index)["captures"] == [capture_id]


@pytest.mark.parametrize("crash", [None, "after_index", "before_commit"])
def test_backfill_publication_charges_only_proven_work(campaign, monkeypatch, crash):
    begin(campaign)
    target = submit(campaign, version="publish-clock", a=90)["latest_observation"]
    root = campaign["root"]
    before = service.read(root / "state.json")
    if crash is None:
        before["deadline"] = time.time() + 40
        atomic_write_json(root / "state.json", before)
    offset = 0
    validations = []
    clock = SimpleNamespace(time=lambda: time.time() + offset, monotonic=lambda: offset)
    monkeypatch.setattr(service_backfill, "time", clock)
    monkeypatch.setattr(optimization, "time", clock)
    validate = service_backfill._validated
    load = optimization._load
    selected_evidence = optimization._service_selected_evidence_reason

    def slow_selected_evidence(*args):
        nonlocal offset
        offset += 45
        return selected_evidence(*args)

    def slow_load(*args, **kwargs):
        nonlocal offset
        offset += 2
        return load(*args, **kwargs)

    def slow_validation(*args):
        nonlocal offset
        validations.append(args[-1])
        offset += 45
        return validate(*args)

    def slow_write(path, document):
        nonlocal offset
        if path.name == "index.json":
            offset += 7
        if path == root / "summary.json":
            offset += 4
        if crash == "before_commit" and path == root / "state.json" and document["pending"] is None:
            raise SystemExit(75)
        atomic_write_json(path, document)
        if crash == "after_index" and path.name == "index.json":
            raise SystemExit(75)

    with monkeypatch.context() as hooks:
        hooks.setattr(optimization, "_load", slow_load)
        hooks.setattr(optimization, "_service_selected_evidence_reason", slow_selected_evidence)
        hooks.setattr(service_backfill, "_validated", slow_validation)
        hooks.setattr(service_backfill, "atomic_write_json", slow_write)
        if crash:
            with pytest.raises(SystemExit):
                call(campaign, "profile", "--round", 1)
            capture_id = service.read(root / "state.json")["pending"]["attempt_id"]
            offset += 120  # No work ran while the coordinator was offline.
            hooks.setattr(optimization, "_load", load)
            hooks.setattr(service_backfill, "atomic_write_json", atomic_write_json)
            recovered = call(campaign, "recover")
            assert recovered["capture_id"] == capture_id
        else:
            capture_id = call(campaign, "profile", "--round", 1)["capture_id"]
    execution = service.read(
        root / target["path"] / "backfills" / capture_id / "execution/execution.json"
    )
    # Validation was checkpointed before publication. The index write's duration
    # is unknown if its caller crashed before persisting the next checkpoint.
    credit = {None: 103, "after_index": 137, "before_commit": 193}[crash]
    assert execution["publication_elapsed_seconds"] == credit
    assert validations == [capture_id] * (2 if crash else 1)
    state = service.read(root / "state.json")
    ledger = state["profiling_accounting"]
    assert set(ledger) == set(before["profiling_accounting"]) | {capture_id}
    assert ledger[capture_id]["elapsed_seconds"] == pytest.approx(
        execution["capture"]["elapsed_seconds"] + credit
    )
    assert state["deadline"] == before["deadline"]
    if crash is None:
        assert clock.time() >= before["deadline"]
        summary = service.read(root / "summary.json")
        assert summary["final_block_reason"] is None
        assert summary["wall_elapsed_seconds"] >= 99  # Includes report evidence verification.
        assert call(campaign, "status")["can_finalize"]
    status = call(campaign, "recover")
    assert service.read(root / "state.json")["profiling_accounting"] == ledger
    assert status["remaining_seconds"] == pytest.approx(
        before["deadline"] + sum(row["elapsed_seconds"] for row in ledger.values()) - clock.time(),
        abs=0.2,
    )
    assert status["remaining_seconds"] - status["remaining_search_seconds"] == pytest.approx(30)


@pytest.mark.parametrize("phase", ["during_validation", "before_index", "after_index", "report"])
def test_publication_interruption_respects_index_commit(campaign, monkeypatch, phase):
    begin(campaign)
    target = submit(campaign, version="cancel-publish", a=90)["latest_observation"]
    root = campaign["root"]
    old = call(campaign, "profile", "--round", 1)
    validate = service_backfill._validated
    interrupted = False

    def validate_or_cancel(*args):
        nonlocal interrupted
        if phase == "during_validation" and args[-1] != old["capture_id"] and not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        return validate(*args)

    def write_or_cancel(path, document):
        nonlocal interrupted
        if phase == "before_index" and path.name == "index.json" and not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        if phase == "report" and path == root / "summary.json" and not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        if phase == "during_validation" and interrupted and path == root / "state.json":
            raise SystemExit(75)  # Cancellation is durable even before campaign settlement.
        atomic_write_json(path, document)
        if phase == "after_index" and path.name == "index.json" and not interrupted:
            interrupted = True
            raise KeyboardInterrupt

    with monkeypatch.context() as patch:
        patch.setattr(service_backfill, "_validated", validate_or_cancel)
        patch.setattr(service_backfill, "atomic_write_json", write_or_cancel)
        if phase == "during_validation":
            with pytest.raises(SystemExit):
                call(campaign, "profile", "--round", 1)
        else:
            result = call(campaign, "profile", "--round", 1, expected=130)
    if phase == "during_validation":
        result = call(campaign, "recover", expected=130)
    assert interrupted
    error = result["profiling_error"]
    assert error["stage"] == "publication" and error["status"] == "interrupted"
    backfills = root / target["path"] / "backfills"
    published = phase in ("after_index", "report")
    captures = service.read(backfills / "index.json")["captures"]
    capture = result["capture_id"]
    assert captures == ([old["capture_id"], capture] if published else [old["capture_id"]])
    execution = service.read(backfills / capture / "execution/execution.json")
    assert execution["publication_interruption" if published else "profiling_error"] == error
    assert (capture in result["profiling"]["result"]) == published
    assert call(campaign, "recover")["profiling_error"] == error
    assert call(campaign, "status")["latest_observation"]["profiling"] == result["profiling"]
