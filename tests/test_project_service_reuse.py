"""Fingerprint-free CPU orchestration controls; no real-model qualification."""

import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from inferrsi.apps.views import dashboard_data
from inferrsi.apps.cli import main
from inferrsi.apps.cli.arguments import parser
from inferrsi.harness import (
    candidates,
    optimization,
    optimization_session,
    project,
    project_service,
)
from inferrsi.harness.records import evidence, knowledge_capture
from inferrsi.infra import artifacts
from inferrsi.knowledge import knowledge_operations


@pytest.fixture(autouse=True)
def no_fingerprints(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("This test must not calculate or verify a file fingerprint")

    for module, name in (
        (candidates, "identity"),
        (artifacts, "sha256"),
        (artifacts, "digest"),
        (optimization, "sha256"),
        (optimization, "digest"),
        (optimization_session, "_runtime_identity"),
        (project, "sha256"),
        (knowledge_operations, "_hash"),
        (hashlib, "sha256"),
    ):
        monkeypatch.setattr(module, name, forbidden)
    for module, names in (
        (dashboard_data, ("file_ref", "read_object", "read_snapshot")),
        (evidence, ("file_ref", "read_object", "read_snapshot")),
        (knowledge_capture, ("store_capture", "verify_capture")),
    ):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    yield
    assert not calls, "A fingerprint call was attempted, even if execution caught its exception"


def commit(repo, **changes):
    config = {"version": "baseline", "a": 100, "b": 100, "quality": 1}
    config.update(changes)
    (repo / "engine.py").write_text("CONFIG = " + repr(config) + "\n", encoding="utf-8")
    for args in (
        ("add", "engine.py"),
        (
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Synthetic version",
        ),
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def settings():
    return {
        "schema_version": 1,
        "protocol_id": "synthetic-service-control",
        "conditions": {
            "id": "c0",
            "workload": "synthetic",
            "model": "synthetic",
            "precision": "integers",
            "topology": "one-cpu-process",
            "runtime": "stdlib",
            "timing_scope": "synthetic-value",
            "effective_config": {"mode": "fixture"},
        },
        "commands": {
            name: [
                "{python}",
                "{protocol}/protocol.py",
                name,
                "{candidate}",
                "{service_receipt}",
                "{result}",
            ]
            for name in (
                "precheck",
                "service",
                "ready",
                "warmup",
                "measure",
                "quality",
                "profile",
                "stop",
            )
        },
        "sampling": {
            "stage_timeout_seconds": 8,
            **{
                role: {"repetitions": 2, "warmups": 1}
                for role in ("baseline", "candidate", "final")
            },
        },
        "scenarios": [
            {"id": name, "workload": "synthetic-" + name, "requests": 2, "required_successes": 2}
            for name in ("a", "b")
        ],
        "objectives": [
            {
                "id": name,
                "scenario": name,
                "key": "latency",
                "unit": "ms",
                "domain": {"min": 0, "max": 10000},
                "direction": "minimize",
                "aggregate": "median",
                "threshold_type": "relative_percent",
                "gain": True,
                "gain_threshold": 4,
                "parent_regression_limit": 3,
                "cumulative_regression_limit": 3,
            }
            for name in ("a", "b")
        ],
        "ranking": ["a", "b"],
        "quality": {
            "mode": "absolute",
            "dataset": "synthetic",
            "scorer": "exact-v1",
            "samples": 2,
            "key": "quality",
            "direction": "maximize",
            "threshold": 1,
        },
        "stagnation": {"rounds": 2, "action": "advisory"},
    }


@pytest.fixture
def campaign(tmp_path, capsys):
    repo, protocol, root = (tmp_path / name for name in ("repo", "protocol", "campaign"))
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    commit(repo)
    protocol.mkdir()
    shutil.copyfile(
        Path(__file__).parent / "fixtures/service_reuse_protocol.py", protocol / "protocol.py"
    )
    instructions = tmp_path / "TASK.md"
    instructions.write_text("Synthetic service control; no model claims.")
    configuration = tmp_path / "evaluation.json"
    configuration.write_text(json.dumps(settings()))
    args = [
        "campaign",
        "start",
        "--session",
        str(root),
        "--repo",
        str(repo),
        "--include",
        "engine.py",
        "--protocol",
        str(protocol),
        "--instructions",
        str(instructions),
        "--evaluation-mode",
        "service_reuse",
        "--evaluation-config",
        str(configuration),
        "--rounds",
        "8",
        "--max-minutes",
        "10",
        "--evaluation-timeout-seconds",
        "25",
        "--final-reserve-seconds",
        "30",
    ]
    return {"repo": repo, "root": root, "start": args, "config": configuration, "capsys": capsys}


def call(campaign, action, *extra, expected=0):
    args = (
        campaign["start"]
        if action == "start"
        else ["campaign", action, "--session", str(campaign["root"]), *map(str, extra)]
    )
    assert main(args) == expected
    return json.loads(campaign["capsys"].readouterr().out)


def begin(campaign):
    result = call(campaign, "start")
    assert result["next_action"] == "campaign_baseline"
    assert not (campaign["root"] / "baseline").exists()
    result = call(campaign, "baseline")
    assert result["best"]["kind"] == "baseline"
    return result


def submit(campaign, *, expected=0, retry=None, **changes):
    commit(campaign["repo"], **changes)
    args = ["--candidate", campaign["repo"], "--hypothesis", "Synthetic committed candidate"]
    if retry:
        args += ["--retry-of", retry, "--repair-reason", "Investigated and repaired fixture"]
    return call(campaign, "round", *args, expected=expected)


def events(campaign, attempt):
    path = campaign["root"] / attempt["path"] / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_one_service_order_and_independent_final_ignores_workspace(campaign):
    begin(campaign)
    result = submit(campaign, version="accepted", a=95, b=102)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == "PASS"
    log = events(campaign, attempt)
    assert [row["stage"] for row in log] == [
        "ready",
        "warmup",
        "measure",
        "measure",
        "quality",
        "profile",
        "stop",
    ]
    assert len({row["service_id"] for row in log}) == 1
    assert attempt["execution"]["cleanup_verified"] is True
    (campaign["repo"] / "engine.py").write_text("raise RuntimeError('unsubmitted workspace')")
    final = call(campaign, "final", "--reason", "Synthetic search complete")
    assert final["state"] == "completed"
    assert final["final"]["assessment"]["verdict"] == "PASS"
    assert {row["version"] for row in events(campaign, final["final"])} == {"accepted"}
    assert "profile" not in [row["stage"] for row in events(campaign, final["final"])]
    project_service.no_fingerprints(optimization.read_records(campaign["root"])[2])


@pytest.mark.parametrize("failure", ["failed", "missing"])
def test_profile_failure_and_failed_repair_preserve_prior_selection(campaign, failure):
    begin(campaign)
    selected = submit(campaign, version="selected", a=90, b=100)["best"]
    broken = submit(
        campaign, version="profile-broken", a=80, b=100, profile_mode=failure, expected=2
    )
    old = broken["latest_observation"]
    assert old["assessment"]["verdict"] == "INCONCLUSIVE"
    assert old["assessment"]["quality_passed"] is True
    assert "profile" in old["assessment"]["reason"]
    assert broken["best"] == selected
    assert len(events(campaign, old)) == 7
    repaired = submit(campaign, version="repair-failed", a=70, b=120, retry=old["attempt_id"])
    assert repaired["latest_observation"]["assessment"]["verdict"] == "FAIL"
    assert repaired["best"] == selected
    assert project_service.read(campaign["root"] / old["path"] / "observation.json") == old
    final = call(campaign, "final", "--reason", "Repair rejected")
    assert final["final"]["revision"] == selected["revision"]
    assert {row["version"] for row in events(campaign, final["final"])} == {"selected"}


def test_conditions_refresh_cannot_finalize_without_new_acceptance(campaign):
    begin(campaign)
    selected = submit(campaign, version="old-selected", a=90)["best"]
    new = copy.deepcopy(settings()["conditions"])
    new.update(id="c1", runtime="changed-stdlib")
    path = campaign["root"].parent / "conditions.json"
    path.write_text(json.dumps(new))
    refreshed = call(
        campaign, "refresh-references", "--conditions", path, "--reason", "New test conditions"
    )
    assert refreshed["can_finalize"] is False
    assert refreshed["accepted_attempt_ids"] == []
    assert refreshed["best"] is None
    rejected = call(campaign, "final", "--reason", "References alone are insufficient")
    assert rejected["final"]["assessment"]["verdict"] == "INCONCLUSIVE"
    assert rejected["final"]["assessment"]["reason"] == "missing_current_conditions_acceptance"
    assert not (campaign["root"] / rejected["final"]["path"] / "service").exists()
    accepted = submit(campaign, version="new-selected", a=80)
    assert accepted["best"]["conditions"] == new
    assert accepted["best"]["revision"] != selected["revision"]
    final = call(campaign, "final", "--reason", "New conditions accepted")
    assert final["final"]["assessment"]["verdict"] == "PASS"


def test_stagnation_is_advisory_and_recover_does_not_retrigger(campaign):
    begin(campaign)
    submit(campaign, version="reject1", a=110)
    result = submit(campaign, version="reject2", a=111)
    assert result["state"] == "active"
    assert len(result["stagnation"]["events"]) == 1
    recovered = call(campaign, "recover")
    assert recovered["stagnation"] == result["stagnation"]
    improved = submit(campaign, version="gain", a=90)
    assert improved["stagnation"]["consecutive"] == 0


def test_baseline_selected_final_has_no_self_gain_requirement(campaign):
    begin(campaign)
    submit(campaign, version="no-improvement", a=100)
    final = call(campaign, "final", "--reason", "No candidate selected")
    assert final["final"]["assessment"]["verdict"] == "PASS"
    assert final["best"]["kind"] == "baseline"


def test_missing_performance_evidence_blocks_without_quality_or_profile(campaign):
    begin(campaign)
    result = submit(campaign, version="missing", a=90, missing_metric=True, expected=2)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == "INCONCLUSIVE"
    assert "quality" not in [row["stage"] for row in events(campaign, attempt)]
    assert "profile" not in [row["stage"] for row in events(campaign, attempt)]


def test_service_mode_cli_does_not_require_legacy_metric_arguments(campaign):
    args = parser().parse_args(campaign["start"])
    assert args.evaluation_mode == "service_reuse" and args.metric_key is None
    with pytest.raises(SystemExit):
        parser().parse_args(["benchmarks", "session", "baseline", "--session", "unused"])


def test_knowledge_and_dashboard_never_enter_legacy_fingerprint_readers(campaign):
    begin(campaign)
    context = call(
        campaign, "knowledge", "--query", "optimization", "--context-bytes", "65536", "--limit", "1"
    )
    assert context["context"]["contexts"]
    project_service.no_fingerprints(context)
    submit(campaign, version="selected", a=90)
    from inferrsi.apps.views.dashboard import dashboard_snapshot, render_dashboard

    snapshot = dashboard_snapshot(campaign["root"])
    project_service.no_fingerprints(snapshot)
    page = render_dashboard(snapshot)
    assert "Service-reuse optimization" in page and "Objective values" in page
    assert "sha256" not in page.lower()


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"quality": 0}, 0),
        ({"quality_rejected": True}, 0),
        ({"quality_missing": True}, 2),
        ({"functional_failure": True}, 0),
        ({"profile_mode": "empty"}, 2),
        ({"foreign_stage": "quality"}, 2),
    ],
)
def test_rejections_and_missing_stage_evidence_are_distinct(campaign, changes, expected):
    begin(campaign)
    result = submit(campaign, version="rejected", a=90, expected=expected, **changes)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == ("FAIL" if expected == 0 else "INCONCLUSIVE")
    assert result["best"]["kind"] == "baseline"
    if not changes.get("profile_mode"):
        assert not any(
            row["id"] == "profile" and row["status"] == "completed"
            for row in attempt["execution"]["steps"]
        )


def test_profile_timeout_retains_quality_and_stops_without_silent_retry(campaign):
    config = settings()
    config["sampling"]["stage_timeout_seconds"] = 1
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    result = submit(campaign, version="timeout", a=90, profile_mode="timeout", expected=2)
    attempt = result["latest_observation"]
    stage = next(row for row in attempt["execution"]["steps"] if row["id"] == "profile")
    assert stage["status"] == "timeout"
    assert attempt["assessment"]["quality_passed"] is True
    assert attempt["execution"]["cleanup_verified"] is True
    recovered = call(campaign, "recover", expected=2)
    assert recovered["latest_observation"] == attempt


def test_profile_interruption_is_inconclusive_with_verified_cleanup(campaign, monkeypatch):
    from inferrsi.harness.scenarios import external

    begin(campaign)
    original = external.execute_trial

    def interrupted(command, *args, **kwargs):
        if "profile" in command:
            raise KeyboardInterrupt()
        return original(command, *args, **kwargs)

    monkeypatch.setattr(external, "execute_trial", interrupted)
    result = submit(campaign, version="interrupted", a=90, expected=2)
    assert result["latest_observation"]["assessment"]["verdict"] == "INCONCLUSIVE"
    assert result["latest_observation"]["assessment"]["quality_passed"] is True
    assert result["latest_observation"]["execution"]["cleanup_verified"] is True


def test_incomplete_baseline_prevents_candidate_search(campaign):
    commit(campaign["repo"], missing_metric=True)
    call(campaign, "start")
    result = call(campaign, "baseline", expected=2)
    assert result["best"] is None and result["state"] == "blocked"
    assert (
        rejected(
            [
                "campaign",
                "round",
                "--session",
                str(campaign["root"]),
                "--candidate",
                str(campaign["repo"]),
                "--hypothesis",
                "must not start",
            ]
        )
        == 2
    )


def test_baseline_comparison_quality_and_pause_resume(campaign):
    config = settings()
    config["quality"].pop("threshold")
    config["quality"].update(mode="baseline_comparison", tolerance=0)
    config["stagnation"] = {"rounds": 1, "action": "pause"}
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    result = submit(campaign, version="worse-quality", a=90, quality=0)
    assert result["state"] == "paused"
    assert result["latest_observation"]["assessment"]["quality_passed"] is False
    resumed = call(campaign, "resume", "--reason", "Reviewed system-wide bottlenecks")
    repeated = call(campaign, "resume", "--reason", "Reviewed system-wide bottlenecks")
    assert resumed["stagnation"] == repeated["stagnation"]
    assert resumed["state"] == "active"


def test_accepted_but_unselected_candidate_keeps_its_verdict(campaign):
    config = settings()
    config["stagnation"] = {"rounds": 1, "action": "pause"}
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    rejected_round = submit(campaign, version="rejected", a=110)
    assert rejected_round["state"] == "paused"
    call(campaign, "resume", "--reason", "Try a second-objective gain")
    result = submit(campaign, version="second-objective-gain", a=102, b=90)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["eligible"] is True
    assert attempt["selected"] is False
    assert result["best"]["kind"] == "baseline"
    assert result["state"] == "active"
    assert result["stagnation"]["consecutive"] == 0
    assert result["stagnation"]["notified"] is False
    assert result["stagnation"]["events"] == rejected_round["stagnation"]["events"]


def test_screening_below_estimate_runs_formal_quality_and_profile_on_same_service(campaign):
    config = settings()
    config["screening"] = {
        "command": [arg.replace("measure", "screening") for arg in config["commands"]["measure"]],
        "estimated_gain": 50,
    }
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    result = submit(campaign, version="actual-gain", a=95)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == "PASS"
    log = events(campaign, attempt)
    assert [r["stage"] for r in log].count("screening") == 2
    assert len({r["service_id"] for r in log}) == 1


@pytest.mark.parametrize("damage", [None, "missing", "empty", "receipt", "binding", "artifacts"])
def test_recover_commits_existing_observation_once_without_remeasurement(
    campaign, monkeypatch, damage
):
    begin(campaign)
    selected = submit(campaign, version="previous-selection", a=95)["best"]
    previous = project_service.read(
        campaign["root"] / selected["path"].removesuffix("/candidate") / "observation.json"
    )
    original = optimization.atomic_write_json

    def fail_state_commit(path, data):
        if path.name == "state.json" and data.get("pending") is None and data.get("attempts"):
            if data["attempts"][-1]["kind"] == "round":
                raise OSError("synthetic coordinator state-write failure")
        return original(path, data)

    monkeypatch.setattr(optimization, "atomic_write_json", fail_state_commit)
    commit(campaign["repo"], version="recovery", a=90)
    assert (
        rejected(
            [
                "campaign",
                "round",
                "--session",
                str(campaign["root"]),
                "--candidate",
                str(campaign["repo"]),
                "--hypothesis",
                "Injected settlement interruption",
            ]
        )
        == 2
    )
    campaign["capsys"].readouterr()
    monkeypatch.setattr(optimization, "atomic_write_json", original)
    pending = project_service.read(campaign["root"] / "state.json")["pending"]
    observation_path = campaign["root"] / pending["path"] / "observation.json"
    observation = project_service.read(observation_path)
    profile = observation["execution"]["profile"]
    artifact = campaign["root"] / profile["artifacts"][0]
    if damage == "missing":
        artifact.unlink()
    elif damage == "empty":
        artifact.write_text("")
    elif damage == "receipt":
        (campaign["root"] / profile["result"]).write_text('{"status":"incomplete"}')
    elif damage == "binding":
        profile["binding"]["service_id"] = "another-service"
        profile["receipt"]["binding"] = profile["binding"]
        (campaign["root"] / profile["result"]).write_text(json.dumps(profile["receipt"]))
        observation_path.write_text(json.dumps(observation))
    elif damage == "artifacts":
        profile["artifacts"] = []
        observation_path.write_text(json.dumps(observation))
    result = call(campaign, "recover", expected=2 if damage else 0)
    attempt = result["latest_observation"]
    log = events(campaign, attempt)
    assert result["completed_rounds"] == (1 if damage else 2)
    assert len(log) == 7
    if damage:
        assert result["state"] == "blocked"
        assert attempt["assessment"]["verdict"] == "INCONCLUSIVE"
        assert attempt["assessment_before_settlement"]["verdict"] == "PASS"
        assert attempt["execution"]["assessment"]["verdict"] == "PASS"
        assert attempt["selected"] is False
        assert result["best"] == selected
        assert result["accepted_attempt_ids"] == [selected["attempt_id"]]
    else:
        assert attempt["assessment"]["verdict"] == "PASS"
        assert result["best"]["attempt_id"] == attempt["attempt_id"]
    assert project_service.read(
        campaign["root"] / previous["path"] / "observation.json"
    ) == previous
    again = call(campaign, "recover", expected=2 if damage else 0)
    assert again["latest_observation"] == attempt
    assert len(events(campaign, attempt)) == len(log)


@pytest.mark.parametrize("interrupted", [False, True])
@pytest.mark.parametrize("damage", ["profile", "configuration"])
def test_final_rechecks_selected_evidence_before_settlement(
    campaign, monkeypatch, interrupted, damage
):
    begin(campaign)
    selected = submit(campaign, version="selected", a=90)["best"]
    selected_attempt = project_service.read(
        campaign["root"] / selected["path"].removesuffix("/candidate") / "observation.json"
    )
    execute, write = optimization._service_execute, optimization.atomic_write_json

    def execute_then_damage(*args):
        result = execute(*args)
        assert result["assessment"]["verdict"] == "PASS"
        if not interrupted:
            damage_evidence()
        return result

    def damage_evidence():
        if damage == "profile":
            (campaign["root"] / selected["profile"]["artifacts"][0]).unlink()
        else:
            (campaign["root"] / selected["effective_config_path"]).write_text('{"mode":"altered"}')

    def fail_state_commit(path, data):
        if path.name == "state.json" and data.get("final") is not None:
            raise OSError("synthetic final state-write failure")
        return write(path, data)

    monkeypatch.setattr(optimization, "_service_execute", execute_then_damage)
    if interrupted:
        monkeypatch.setattr(optimization, "atomic_write_json", fail_state_commit)
        assert rejected(
            ["campaign", "final", "--session", str(campaign["root"]), "--reason", "Stop search"]
        ) == 2
        campaign["capsys"].readouterr()
        monkeypatch.setattr(optimization, "atomic_write_json", write)
        pending = project_service.read(campaign["root"] / "state.json")["pending"]
        assert project_service.read(
            campaign["root"] / pending["path"] / "observation.json"
        )["assessment"]["verdict"] == "PASS"
        damage_evidence()
        result = call(campaign, "recover", expected=2)
    else:
        result = call(campaign, "final", "--reason", "Stop search", expected=2)
    final = result["final"]
    assert result["state"] == "blocked"
    assert result["best"] == selected
    assert final["assessment"]["verdict"] == "INCONCLUSIVE"
    assert final["assessment"]["reason"] == (
        "missing_or_incompatible_selected_profile" if damage == "profile"
        else "unverifiable_selected_configuration"
    )
    assert final["assessment_before_settlement"]["verdict"] == "PASS"
    assert final["execution"]["assessment"]["verdict"] == "PASS"
    assert project_service.read(
        campaign["root"] / selected_attempt["path"] / "observation.json"
    ) == selected_attempt
    log = events(campaign, final)
    assert [row["stage"] for row in log] == [
        "ready", "warmup", "measure", "measure", "quality", "stop"
    ]
    again = call(campaign, "recover", expected=2)
    assert again["final"] == final
    assert events(campaign, final) == log


def test_final_cannot_use_deleted_profile_or_changed_retained_configuration(campaign):
    begin(campaign)
    selected = submit(campaign, version="selected", a=90)["best"]
    config_path = campaign["root"] / selected["effective_config_path"]
    config_path.write_text('{"mode":"altered"}')
    result = call(campaign, "final", "--reason", "Cannot establish selected configuration")
    assert result["final"]["assessment"]["reason"] == "unverifiable_selected_configuration"
    config_path.write_text(json.dumps(settings()["conditions"]["effective_config"]))
    (campaign["root"] / selected["profile"]["artifacts"][0]).unlink()
    result = call(campaign, "final", "--reason", "Cannot establish selected profile")
    assert result["final"]["assessment"]["reason"] == "missing_or_incompatible_selected_profile"


@pytest.mark.parametrize("block", ["commands", "sampling", "conditions", "quality", "stagnation"])
def test_invalid_protocol_containers_rejected_before_campaign_writes(campaign, block):
    config = settings()
    config[block] = []
    campaign["config"].write_text(json.dumps(config))
    assert rejected(campaign["start"]) == 2
    assert not campaign["root"].exists()


def rejected(arguments):
    with pytest.raises(SystemExit) as raised:
        main(arguments)
    return raised.value.code


def test_live_dashboard_state_has_no_content_fingerprint(campaign):
    import threading
    from urllib.request import urlopen

    from inferrsi.apps.views.dashboard_live import DashboardServer

    call(campaign, "start")
    server = DashboardServer(campaign["root"], None, 0)
    worker = threading.Thread(target=server.serve_forever)
    worker.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/api/state") as response:
            assert response.status == 200 and response.headers.get("ETag") is None
            project_service.no_fingerprints(json.load(response))
        with urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
            assert b"Service-reuse optimization" in response.read()
    finally:
        server.shutdown()
        worker.join()
        server.server_close()


@pytest.mark.parametrize("compatible", [True, False])
def test_existing_quality_reference_is_reused_only_when_compatible(campaign, compatible):
    config = settings()
    config["quality"].pop("threshold")
    config["quality"].update(
        mode="baseline_comparison", tolerance=0, reference_path="reference.json"
    )
    revision = subprocess.check_output(
        ["git", "-C", str(campaign["repo"]), "rev-parse", "HEAD"], text=True
    ).strip()
    reference = {
        "status": "completed",
        "revision": revision,
        "conditions": config["conditions"],
        "service_id": "previous-service",
        "run_id": "previous-run",
        "dataset": "synthetic",
        "scorer": "exact-v1" if compatible else "incompatible-scorer",
        "samples": 2,
        "quality": 1,
    }
    protocol = Path(campaign["start"][campaign["start"].index("--protocol") + 1])
    (protocol / "reference.json").write_text(json.dumps(reference))
    campaign["config"].write_text(json.dumps(config))
    call(campaign, "start")
    result = call(campaign, "baseline", expected=0 if compatible else 2)
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == ("PASS" if compatible else "INCONCLUSIVE")
    assert "quality" not in [row["stage"] for row in events(campaign, attempt)]


@pytest.mark.parametrize("same_version", [False, True])
def test_reference_refresh_uses_baseline_cache_without_testing_parent_quality(
    campaign, same_version
):
    config = settings()
    config["quality"].pop("threshold")
    config["quality"].update(
        mode="baseline_comparison", tolerance=0, reference_path="reference.json"
    )
    revision = subprocess.check_output(
        ["git", "-C", str(campaign["repo"]), "rev-parse", "HEAD"], text=True
    ).strip()
    reference = {
        "status": "completed", "revision": revision, "conditions": config["conditions"],
        "service_id": "previous-service", "run_id": "previous-run",
        "dataset": "synthetic", "scorer": "exact-v1", "samples": 2, "quality": 1,
    }
    protocol = Path(campaign["start"][campaign["start"].index("--protocol") + 1])
    (protocol / "reference.json").write_text(json.dumps(reference))
    campaign["config"].write_text(json.dumps(config))
    selected = begin(campaign)["best"]
    if not same_version:
        selected = submit(campaign, version="selected-parent", a=90)["best"]
        assert selected["revision"] != revision
    conditions = {**config["conditions"], "id": "c1", "runtime": "changed-stdlib"}
    conditions_path = campaign["root"].parent / "conditions.json"
    conditions_path.write_text(json.dumps(conditions))
    failed = call(
        campaign, "refresh-references", "--conditions", conditions_path,
        "--reason", "Changed conditions", expected=2,
    )["latest_observation"]
    assert failed["assessment"]["verdict"] == "INCONCLUSIVE"
    assert "incompatible baseline reference" in (
        failed["execution"]["runs"][0]["assessment"]["reason"]
    )
    repaired = campaign["root"].parent / "repaired-protocol"
    shutil.copytree(protocol, repaired)
    reference.update(conditions=conditions, service_id="new-service", run_id="new-run")
    (repaired / "reference.json").write_text(json.dumps(reference))
    result = call(
        campaign, "refresh-references", "--conditions", conditions_path,
        "--reason", "Refresh compatible references", "--retry-of", failed["attempt_id"],
        "--repair-reason", "Supplied compatible baseline quality evidence",
        "--repair-protocol", repaired,
    )
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == "PASS"
    references = attempt["execution"]["references"]
    assert [item["revision"] for item in references] == [revision, selected["revision"]]
    assert all(item["conditions"] == conditions for item in references)
    assert references[0]["quality_score"] == 1
    assert len(attempt["execution"]["runs"]) == (1 if same_version else 2)
    if same_version:
        assert references[0] == references[1]
    else:
        assert references[1]["quality_score"] is None
        assert references[1]["profile"] is None
        parent_run = attempt["execution"]["runs"][1]
        for name in ("quality", "profile"):
            assert next(step for step in parent_run["steps"] if step["id"] == name) == {
                "id": name, "status": "skipped", "reason": "performance_reference_only"
            }
    for reference in references:
        log_path = campaign["root"] / reference["path"].removesuffix("/candidate") / "events.jsonl"
        stages = [json.loads(line)["stage"] for line in log_path.read_text().splitlines()]
        assert stages == ["ready", "warmup", "measure", "measure", "stop"]
    assert result["best"] is None and result["can_finalize"] is False
    assert project_service.read(campaign["root"] / failed["path"] / "observation.json") == failed
    accepted = submit(campaign, version="current-conditions", a=80)
    assert accepted["latest_observation"]["assessment"]["verdict"] == "PASS"
    assert accepted["best"]["conditions"] == conditions


def test_execution_script_repair_is_retained_and_final_uses_selected_scripts(campaign):
    begin(campaign)
    selected = submit(campaign, version="selected", a=90)["best"]
    broken = submit(campaign, version="broken-profile", a=80, profile_mode="failed", expected=2)
    old = broken["latest_observation"]
    protocol = Path(campaign["start"][campaign["start"].index("--protocol") + 1])
    repaired = campaign["root"].parent / "repaired-protocol"
    shutil.copytree(protocol, repaired)
    path = repaired / "protocol.py"
    path.write_text(
        path.read_text().replace(
            'if phase == "service":',
            'raise RuntimeError("repaired script rejected")\nif phase == "service":',
        )
    )
    attempt = call(
        campaign,
        "round",
        "--candidate",
        campaign["repo"],
        "--hypothesis",
        "Execution repair",
        "--retry-of",
        old["attempt_id"],
        "--repair-reason",
        "Investigated fixture",
        "--repair-protocol",
        repaired,
        expected=2,
    )
    assert attempt["best"] == selected
    assert attempt["latest_observation"]["protocol_path"] != selected["protocol_path"]
    inspection = campaign["root"].parent / "cleanup.json"
    inspection.write_text(
        json.dumps(
            {
                "attempt_id": attempt["latest_observation"]["attempt_id"],
                "observed_at": 1,
                "reason": "Inspected failed precheck; no service started",
                "cleanup_complete": True,
                "services": [],
            }
        )
    )
    call(
        campaign,
        "resume",
        "--reason",
        "Abandon failed execution repair",
        "--cleanup-receipt",
        inspection,
    )
    result = call(campaign, "final", "--reason", "Retest retained selected script set")
    assert result["final"]["assessment"]["verdict"] == "PASS"
    assert result["final"]["protocol_path"] == selected["protocol_path"]


def test_round_usage_export_is_retained_without_fingerprint(campaign):
    begin(campaign)
    export = campaign["root"].parent / "usage.json"
    export.write_text('{"input_tokens":10,"output_tokens":2}')
    commit(campaign["repo"], version="usage", a=90)
    result = call(
        campaign,
        "round",
        "--candidate",
        campaign["repo"],
        "--hypothesis",
        "Usage evidence",
        "--usage-export",
        export,
    )
    summary = optimization.read_records(campaign["root"])[2]
    assert summary["usage"]["total_tokens"] == 12
    assert result["latest_observation"]["observations"]["usage_source"] == {"kind": "caller_export"}
    call(campaign, "recover")
    assert optimization.read_records(campaign["root"])[2]["usage"]["total_tokens"] == 12


def test_exact_round_policy_and_legacy_argument_validation(campaign):
    campaign["start"] += ["--round-mode", "exact"]
    begin(campaign)
    submit(campaign, version="one-of-eight", a=90)
    result = call(campaign, "final", "--reason", "Incomplete exact budget")
    assert result["final"]["assessment"]["reason"] == "incomplete_round_policy"
    assert result["state"] == "active"
    from inferrsi.harness.project import steps

    assert [
        step["side"]
        for step in steps(
            {
                "quality_command": ["quality"],
                "measure_command": ["measure"],
                "warmups": 0,
                "repetitions": 2,
            }
        )
        if step["phase"] == "measurement"
    ] == ["baseline", "candidate", "candidate", "baseline"]


def test_current_epoch_candidate_can_seed_selection_below_old_parent_rank(campaign):
    begin(campaign)
    old = submit(campaign, version="old-parent", a=90)["best"]
    conditions = copy.deepcopy(settings()["conditions"])
    conditions.update(id="c1", runtime="new-runtime")
    path = campaign["root"].parent / "conditions.json"
    path.write_text(json.dumps(conditions))
    call(campaign, "refresh-references", "--conditions", path, "--reason", "New runtime")
    result = submit(campaign, version="c1-accepted", a=92, b=90)
    assert result["best"]["revision"] != old["revision"]
    assert result["best"]["measurements"]["values"]["a"] > old["measurements"]["values"]["a"]
    assert result["best"]["attempt_id"] in result["accepted_attempt_ids"]


def test_missing_mode_marker_rejects_without_falling_back_to_file_fingerprints(campaign):
    call(campaign, "start")
    path = campaign["root"] / "plan.json"
    plan = json.loads(path.read_text())
    del plan["evaluation_mode"]
    path.write_text(json.dumps(plan))
    assert rejected(["campaign", "status", "--session", str(campaign["root"])]) == 2
    from inferrsi.apps.views.dashboard import dashboard_snapshot

    with pytest.raises(ValueError, match="Incompatible service campaign"):
        dashboard_snapshot(campaign["root"])


def test_final_checks_selected_revision_against_original_attempt(campaign):
    begin(campaign)
    submit(campaign, version="selected", a=90)
    path = campaign["root"] / "state.json"
    state = json.loads(path.read_text())
    state["best"]["revision"] = state["initial_reference"]["revision"]
    path.write_text(json.dumps(state))
    result = call(campaign, "final", "--reason", "Selected revision cannot be established")
    assert result["final"]["assessment"]["reason"] == "unverifiable_selected_attempt_binding"
    assert result["final"]["assessment"]["verdict"] == "INCONCLUSIVE"
    assert not (campaign["root"] / result["final"]["path"] / "service").exists()


@pytest.mark.parametrize("role", ["baseline", "candidate"])
def test_final_rebuilds_changed_retained_code_from_recorded_commit(campaign, role):
    begin(campaign)
    if role == "candidate":
        alternate = campaign["repo"].with_name("alternate-repo")
        shutil.copytree(campaign["repo"], alternate)
        campaign["repo"] = alternate
    result = submit(campaign, version="accepted", a=90 if role == "candidate" else 100)
    selected = result["best"]
    saved = campaign["root"] / selected["path"] / "engine.py"
    saved.unlink()
    saved.write_text("raise RuntimeError('changed retained source must never run')\n")
    # The current checkout and file set are not the authority for an older commit.
    (campaign["repo"] / "engine.py").unlink()
    result = call(campaign, "final", "--reason", "Verify original committed version")
    final = result["final"]
    assert final["assessment"]["verdict"] == "PASS"
    assert final["revision"] == selected["revision"]
    expected_version = "accepted" if role == "candidate" else "baseline"
    assert {row["version"] for row in events(campaign, final)} == {expected_version}
    assert "changed retained" not in (
        campaign["root"] / final["path"] / "candidate/engine.py"
    ).read_text()


def test_missing_authoritative_repository_cannot_run_retained_selection(campaign):
    begin(campaign)
    selected = submit(campaign, version="selected", a=90)["best"]
    shutil.rmtree(campaign["repo"] / ".git")
    result = call(campaign, "final", "--reason", "Source commit unavailable", expected=2)
    final = result["final"]
    assert final["assessment"]["verdict"] == "INCONCLUSIVE"
    assert result["best"] == selected
    assert not (campaign["root"] / final["path"] / "service").exists()


def test_whole_attempt_timeout_still_runs_bounded_stop(campaign):
    config = settings()
    config["sampling"]["stage_timeout_seconds"] = 8
    campaign["config"].write_text(json.dumps(config))
    index = campaign["start"].index("--evaluation-timeout-seconds")
    campaign["start"][index + 1] = "6"
    begin(campaign)
    result = submit(campaign, version="deadline", a=90, profile_mode="timeout", expected=2)
    attempt = result["latest_observation"]
    execution = attempt["execution"]
    steps = {row["id"]: row for row in execution["steps"]}
    assert steps["profile"]["status"] == "timeout"
    assert steps["stop"]["status"] == "completed"
    assert execution["cleanup_timeout_seconds"] == 8
    assert execution["cleanup_budget_scope"] == "separate_from_evaluation"
    assert execution["cleanup_verified"] is True
    assert attempt["assessment"]["verdict"] == "INCONCLUSIVE"
    assert attempt["assessment"]["quality_passed"] is True
    assert [row["stage"] for row in events(campaign, attempt)][-1] == "stop"


@pytest.mark.parametrize("attribute", ["export-ignore", "export-subst"])
def test_execution_preserves_tree_inputs_despite_export_attributes(campaign, attribute):
    repo = campaign["repo"]
    payload = repo / "inputs/payload.txt"
    payload.parent.mkdir()
    content = b"literal $Format:%s$\r\n\x00payload\n"
    payload.write_bytes(content)
    payload.chmod(0o755)
    (repo / ".gitattributes").write_text(f"inputs/payload.txt {attribute}\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitattributes", "inputs"], check=True)
    commit(repo)
    campaign["start"] += ["--include", "inputs"]
    baseline = begin(campaign)["latest_observation"]
    candidate = submit(campaign, version="accepted", a=90)["latest_observation"]
    final = call(campaign, "final", "--reason", "Verify exact committed inputs")["final"]
    assert final["assessment"]["verdict"] == "PASS"
    for attempt in (baseline, candidate, final):
        for directory in ("candidate", "workspace"):
            retained = campaign["root"] / attempt["path"] / directory / "inputs/payload.txt"
            assert retained.read_bytes() == content
            assert retained.stat().st_mode & 0o777 == 0o555


@pytest.mark.parametrize("invalid", ["missing", "symlink"])
def test_tree_snapshot_rejects_missing_or_special_declared_input(campaign, invalid):
    repo = campaign["repo"]
    if invalid == "symlink":
        (repo / invalid).symlink_to("engine.py")
        subprocess.run(["git", "-C", str(repo), "add", invalid], check=True)
        commit(repo)
    revision = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    destination = repo.parent / "snapshot"
    with pytest.raises(ValueError, match="missing|symbolic"):
        project_service.retain_revision(repo, destination, ["engine.py", invalid], revision)
    assert not destination.exists()


@pytest.mark.parametrize("rejections", [1, 2])
def test_refresh_resets_stagnation_without_erasing_history(campaign, rejections):
    begin(campaign)
    for index in range(rejections):
        before = submit(campaign, version=f"rejected-{index}", a=110)
    conditions = {**settings()["conditions"], "id": "new-conditions"}
    path = campaign["root"].parent / "conditions.json"
    path.write_text(json.dumps(conditions))
    refreshed = call(
        campaign, "refresh-references", "--conditions", path, "--reason", "Changed workload"
    )
    assert refreshed["stagnation"]["consecutive"] == 0
    assert refreshed["stagnation"]["notified"] is False
    assert refreshed["stagnation"]["events"] == before["stagnation"]["events"]
    after = submit(campaign, version="new-conditions-rejected", a=110)
    assert after["stagnation"]["consecutive"] == 1
    assert after["stagnation"]["events"] == before["stagnation"]["events"]


@pytest.mark.parametrize("round_mode", ["exact", "up_to"])
def test_refresh_without_round_capacity_preserves_finalizable_state(campaign, round_mode):
    campaign["start"][campaign["start"].index("--rounds") + 1] = "1"
    campaign["start"] += ["--round-mode", round_mode]
    begin(campaign)
    submit(campaign, version="selected", a=90)
    before = project_service.read(campaign["root"] / "state.json")
    conditions = {**settings()["conditions"], "id": "new-conditions"}
    path = campaign["root"].parent / "conditions.json"
    path.write_text(json.dumps(conditions))
    assert rejected([
        "campaign", "refresh-references", "--session", str(campaign["root"]),
        "--conditions", str(path), "--reason", "No acceptance capacity",
    ]) == 2
    assert "No round budget for current-conditions acceptance" in (
        campaign["capsys"].readouterr().err
    )
    assert project_service.read(campaign["root"] / "state.json") == before
    assert not (campaign["root"] / "references").exists()
    result = call(campaign, "final", "--reason", "Complete original conditions")
    assert result["final"]["assessment"]["verdict"] == "PASS"
