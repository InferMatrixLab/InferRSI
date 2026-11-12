"""Synthetic parallel round. Latency figures here are fixture inputs, not measurements."""

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from inferrsi.harness.parallel_round import (
    RoundPlanError,
    prepare,
    serve_ticket,
    submit,
    ticket_status,
)
from inferrsi.infra.confinement import (
    ConfinementUnavailable,
    FixtureBackend,
    namespaces_available,
)
from inferrsi.infra.device_lease import DeviceLease, LeaseError

WHEN = datetime(2026, 10, 30, tzinfo=timezone.utc)
BENCH = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "value = float(Path('knobs/a.txt').read_text())\n"
    "body = {'metrics': {'latency_ms': value}, 'synthetic': True}\n"
    "Path(sys.argv[1]).write_text(json.dumps(body))\n"
)


def _tree(root: Path, knob: str) -> None:
    (root / "knobs").mkdir(parents=True)
    (root / "knobs" / "a.txt").write_text(knob, encoding="utf-8")
    (root / "knobs" / "b.txt").write_text("10", encoding="utf-8")
    (root / "bench.py").write_text(BENCH, encoding="utf-8")


def _spec(**overrides):
    lanes = overrides.pop(
        "lanes",
        [
            {
                "id": "L1",
                "entry": "D-01",
                "plane": "infra",
                "globs": ["knobs/a.txt"],
                "cap": 2,
                "per_attempt_worst_case": 1,
                "deadline_utc": "2099-01-01T00:00:00+00:00",
            },
            {
                "id": "L2",
                "entry": "D-02",
                "plane": "harness",
                "globs": ["knobs/b.txt"],
                "cap": 2,
                "per_attempt_worst_case": 1,
                "deadline_utc": "2099-01-01T00:00:00+00:00",
            },
        ],
    )
    spec = {
        "round_id": "r1",
        "device_ids": ["cpu-0", "cpu-1"],
        "metric": {"name": "latency_ms", "better": "lower"},
        "incumbent_id": "fixture-incumbent",
        "protected": ["bench.py"],
        "build": [sys.executable, "-c", "open('build-stamp','w').write('ok')"],
        "trial": [sys.executable, "bench.py", "{result}"],
        "lanes": lanes,
    }
    spec.update(overrides)
    return spec


def test_prepare_rejects_overlapping_globs_protected_paths_and_shared_entries(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    overlap = _spec(
        lanes=[
            {
                "id": "L1",
                "entry": "D-01",
                "plane": "infra",
                "globs": ["knobs/*.txt"],
                "cap": 1,
                "per_attempt_worst_case": 1,
                "deadline_utc": "2099-01-01T00:00:00+00:00",
            },
            {
                "id": "L2",
                "entry": "D-02",
                "plane": "harness",
                "globs": ["knobs/a.txt"],
                "cap": 1,
                "per_attempt_worst_case": 1,
                "deadline_utc": "2099-01-01T00:00:00+00:00",
            },
        ]
    )
    with pytest.raises(RoundPlanError, match="overlaps"):
        prepare(overlap, incumbent, tmp_path / "round-overlap")
    protected = _spec(
        lanes=[
            {
                "id": "L1",
                "entry": "D-01",
                "plane": "infra",
                "globs": ["bench.py"],
                "cap": 1,
                "per_attempt_worst_case": 1,
                "deadline_utc": "2099-01-01T00:00:00+00:00",
            }
        ]
    )
    with pytest.raises(RoundPlanError, match="protected"):
        prepare(protected, incumbent, tmp_path / "round-protected")
    shared = _spec()
    shared["lanes"][1]["entry"] = "D-01"
    with pytest.raises(RoundPlanError, match="pursue"):
        prepare(shared, incumbent, tmp_path / "round-shared")
    many = _spec()
    many["lanes"][0]["plane"] = ["infra", "harness"]
    with pytest.raises(RoundPlanError, match="exactly one plane"):
        prepare(many, incumbent, tmp_path / "round-plane")


def test_prepare_rejects_bad_devices_and_metric(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    for devices in ([], ["cpu-0", "cpu-0"], ["a/b"], "cpu-0", ["."], [".."], ["0,1", "2"]):
        with pytest.raises(RoundPlanError, match="device_ids"):
            prepare(_spec(device_ids=devices), incumbent, tmp_path / "round-devices")
    for lane_id in (".", ".."):
        dotted = _spec()
        dotted["lanes"][0]["id"] = lane_id
        with pytest.raises(RoundPlanError, match="own id"):
            prepare(dotted, incumbent, tmp_path / "round-lane-id")
    for metric in (
        None,
        {"name": "latency_ms"},
        {"name": "", "better": "lower"},
        {"name": "latency_ms", "better": "faster"},
        {"name": "latency_ms", "better": ["lower"]},
    ):
        with pytest.raises(RoundPlanError, match="metric"):
            prepare(_spec(metric=metric), incumbent, tmp_path / "round-metric")


def test_prepare_records_plan_cap_and_deadline(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    plan = prepare(_spec(), incumbent, tmp_path / "round")
    written = json.loads((tmp_path / "round" / "round-plan.json").read_text(encoding="utf-8"))
    assert written["lanes"][0]["cap"] == 2
    assert written["lanes"][0]["deadline_utc"].startswith("2099-")
    assert written["round_digest"] == plan["round_digest"]
    assert len(written["round_digest"]) == 64


def test_submit_rejects_paths_outside_the_lane_and_is_idempotent(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    (work / "README").write_text("extra", encoding="utf-8")
    rejected = submit(round_dir, "L1", incumbent, work)
    assert rejected["submitted"] is False
    assert rejected["outside"] == ["README"]
    assert not (round_dir / "outbox").exists()
    (work / "README").unlink()
    first = submit(round_dir, "L1", incumbent, work)
    second = submit(round_dir, "L1", incumbent, work)
    assert first["submitted"] is True
    assert first["ticket"] == second["ticket"]


def test_serve_records_a_synthetic_gain_and_a_held_device_stays_queued(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work)["ticket"]
    leases = DeviceLease(round_dir / "leases")
    held = [leases.acquire("cpu-0"), leases.acquire("cpu-1")]
    queued = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert queued["status"] == "queued"
    assert ticket_status(round_dir, ticket)["status"] == "queued"
    assert not (round_dir / "ledgers").exists()
    for lease in held:
        lease.release()
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["synthetic"] is True
    assert measured["metric"] == "latency_ms"
    assert measured["candidate"] == 8
    assert measured["incumbent"] == 10
    assert measured["gain"] == 2
    assert measured["devices"] == ["cpu-0"]
    assert measured["confinement"] == "fixture"
    assert (round_dir / "candidates" / ticket / "build-stamp").read_text(encoding="utf-8") == "ok"


def test_prepare_rejects_bad_device_counts_and_lanes_that_need_more_devices(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    for count in (0, -1, True, "2"):
        spec = _spec()
        spec["lanes"][0]["device_count"] = count
        with pytest.raises(RoundPlanError, match="device_count"):
            prepare(spec, incumbent, tmp_path / "round-count")
    spec = _spec(device_ids=["0", "1", "2"])
    spec["lanes"][1]["device_count"] = 3
    with pytest.raises(RoundPlanError, match="4 devices in total"):
        prepare(spec, incumbent, tmp_path / "round-demand")
    spec["lanes"][1]["device_count"] = 2
    plan = prepare(spec, incumbent, tmp_path / "round-fits")
    assert [lane["device_count"] for lane in plan["lanes"]] == [1, 2]


def test_a_lane_needing_two_devices_waits_until_it_can_hold_both(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    stamp_device = "import sys; open('build-stamp', 'w').write(sys.argv[1])"
    spec = _spec(
        device_ids=["0", "1", "2"],
        build=[sys.executable, "-c", stamp_device, "{device}"],
    )
    spec["lanes"][0]["device_count"] = 2
    prepare(spec, incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    leases = DeviceLease(round_dir / "leases")
    held = [leases.acquire("0"), leases.acquire("1")]
    queued = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert queued["status"] == "queued"
    assert not (round_dir / "ledgers").exists()
    leases.acquire("2").release()
    held.pop().release()
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    held[0].release()
    assert measured["status"] == "measured"
    assert measured["devices"] == ["1", "2"]
    stamp = round_dir / "candidates" / ticket / "build-stamp"
    assert stamp.read_text(encoding="utf-8") == "1,2"


def test_prepare_rejects_bad_repeats_margin_and_timeout(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    base = {"name": "latency_ms", "better": "lower"}
    for extra, message in (
        ({"repeats": 0}, "repeats"),
        ({"repeats": True}, "repeats"),
        ({"margin": -0.1}, "margin"),
        ({"margin": float("nan")}, "margin"),
        ({"spread": 1}, "metric needs"),
    ):
        with pytest.raises(RoundPlanError, match=message):
            prepare(_spec(metric={**base, **extra}), incumbent, tmp_path / "round-metric")
    for timeout in (0, -1, "30", float("inf")):
        with pytest.raises(RoundPlanError, match="command_timeout_seconds"):
            prepare(_spec(command_timeout_seconds=timeout), incumbent, tmp_path / "round-t")
    plan = prepare(_spec(), incumbent, tmp_path / "round-defaults")
    assert plan["metric"] == {**base, "repeats": 1, "margin": 0}
    assert plan["command_timeout_seconds"] == 30


def test_prepare_rejects_bad_device_paths_env_and_agent(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    for overrides, message in (
        ({"device_paths": {"cpu-0": ["/dev/a"]}}, "every device id"),
        ({"device_paths": {"cpu-0": ["dev/a"], "cpu-1": []}}, "absolute host paths"),
        ({"device_paths": {"cpu-0": ["/"], "cpu-1": []}}, "absolute host paths"),
        ({"shared_device_paths": ["/dev/../etc"]}, "absolute host paths"),
        ({"runtime_paths": "/usr/lib64"}, "absolute host paths"),
        ({"env": {"CUDA_VISIBLE_DEVICES": 0}}, "env"),
    ):
        with pytest.raises(RoundPlanError, match=message):
            prepare(_spec(**overrides), incumbent, tmp_path / "round-paths")
    lanes = _spec()["lanes"]
    lanes[0]["agent"] = "claude -p"
    with pytest.raises(RoundPlanError, match="agent must be a list"):
        prepare(_spec(lanes=lanes), incumbent, tmp_path / "round-agent")


def test_serve_passes_only_the_held_device_nodes_and_env(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(
        _spec(
            build=[],
            device_paths={"cpu-0": ["/dev/fake0"], "cpu-1": ["/dev/fake1"]},
            shared_device_paths=["/dev/fakectl"],
            runtime_paths=["/opt/driver"],
            env={"CUDA_VISIBLE_DEVICES": "{device}"},
        ),
        incumbent,
        round_dir,
    )
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    seen = []

    class Recording:
        name = "recording"

        def run(self, argv, *args, **kwargs):
            del args
            seen.append(kwargs)
            body = {"metrics": {"latency_ms": 8 if "candidate" in argv[-1] else 10}}
            Path(argv[-1]).write_text(json.dumps(body), encoding="utf-8")
            return {"status": "completed", "stdout": "", "stderr": ""}

    with DeviceLease(round_dir / "leases").acquire("cpu-0"):
        measured = serve_ticket(round_dir, ticket, incumbent, backend=Recording(), now=WHEN)
    assert measured["devices"] == ["cpu-1"]
    assert seen[0]["devices"] == (Path("/dev/fakectl"), Path("/dev/fake1"))
    assert seen[0]["runtime"] == (Path("/opt/driver"),)
    assert seen[0]["env"] == {"CUDA_VISIBLE_DEVICES": "cpu-1"}


def test_repeats_alternate_abba_and_report_medians(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    metric = {"name": "latency_ms", "better": "lower", "repeats": 3}
    prepare(_spec(metric=metric, build=[]), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    values = {"candidate": [8, 100, 9], "incumbent": [10, 10, 1000]}
    order = []

    class Recording:
        name = "recording"

        def run(self, argv, *args, **kwargs):
            del args, kwargs
            result = Path(argv[-1])
            order.append(result.stem)
            side = result.stem.split("-")[0]
            body = {"metrics": {"latency_ms": values[side].pop(0)}}
            result.write_text(json.dumps(body), encoding="utf-8")
            return {"status": "completed", "stdout": "", "stderr": ""}

    measured = serve_ticket(round_dir, ticket, incumbent, backend=Recording(), now=WHEN)
    assert order == [
        "candidate-0", "incumbent-0", "incumbent-1", "candidate-1", "candidate-2", "incumbent-2"
    ]
    assert measured["candidate_samples"] == [8, 100, 9]
    assert measured["candidate"] == 9
    assert measured["incumbent"] == 10
    assert measured["gain"] == 1
    assert measured["relative_gain"] == pytest.approx(0.1)


def test_higher_is_better_metric_reports_gain_in_the_better_direction(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(metric={"name": "latency_ms", "better": "higher"}), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["status"] == "measured"
    assert measured["better"] == "higher"
    assert measured["gain"] == -2


def test_serve_uses_a_free_device_and_passes_its_identity_to_the_commands(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    stamp_device = "import sys; open('build-stamp', 'w').write(sys.argv[1])"
    spec = _spec(
        device_ids=["gpu-0", "gpu-1"],
        build=[sys.executable, "-c", stamp_device, "{device}"],
    )
    prepare(spec, incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    held = DeviceLease(round_dir / "leases").acquire("gpu-0")
    try:
        measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    finally:
        held.release()
    assert measured["status"] == "measured"
    assert measured["devices"] == ["gpu-1"]
    stamp = round_dir / "candidates" / ticket / "build-stamp"
    assert stamp.read_text(encoding="utf-8") == "gpu-1"


def test_a_busy_lane_stays_queued_without_touching_its_ledger(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(device_ids=["gpu-0", "gpu-1"]), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    held = DeviceLease(round_dir / "lane-locks").acquire("L1")
    try:
        queued = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    finally:
        held.release()
    assert queued["status"] == "queued"
    assert not (round_dir / "ledgers").exists()
    assert not (round_dir / "results").exists()


def test_a_non_numeric_metric_is_an_unsettled_receipt(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]

    class WritesText:
        name = "text"

        def run(self, argv, *args, **kwargs):
            del args, kwargs
            if argv[-1].endswith(".json"):
                body = {"metrics": {"latency_ms": "fast"}}
                Path(argv[-1]).write_text(json.dumps(body), encoding="utf-8")
            return {"status": "completed", "stdout": "", "stderr": ""}

    result = serve_ticket(round_dir, ticket, incumbent, backend=WritesText(), now=WHEN)
    assert result["status"] == "unsettled"
    assert "not a finite number" in result["reason"]
    ledger = json.loads((round_dir / "ledgers" / "L1.json").read_text(encoding="utf-8"))
    assert [entry["phase"] for entry in ledger["entries"]] == ["claimed"]


def test_two_acquires_do_not_share_one_device(tmp_path):
    lease = DeviceLease(tmp_path)
    held = lease.acquire("cpu-0")
    failed = threading.Event()

    def other() -> None:
        try:
            lease.acquire("cpu-0")
        except LeaseError:
            failed.set()

    thread = threading.Thread(target=other)
    thread.start()
    thread.join(2)
    assert failed.is_set()
    held.release()
    lease.acquire("cpu-1").release()


def test_submit_rejects_symlink_without_reading_the_target(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    canary = tmp_path / "canary.txt"
    canary.write_text("CANARY-SECRET", encoding="utf-8")
    work = tmp_path / "work"
    _tree(work, "8")
    (work / "knobs" / "a.txt").unlink()
    (work / "knobs" / "a.txt").symlink_to(canary)
    rejected = submit(round_dir, "L1", incumbent, work, now=WHEN)
    assert rejected["submitted"] is False
    assert rejected["reason"] == "symlink"
    assert rejected["ticket"] is None
    assert not (round_dir / "outbox").exists()
    assert "CANARY-SECRET" not in json.dumps(rejected)


def test_in_scope_deletion_is_rejected_before_hashing_and_serve_does_not_run(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    (work / "knobs" / "a.txt").unlink()
    rejected = submit(round_dir, "L1", incumbent, work, now=WHEN)
    assert rejected == {
        "submitted": False,
        "outside": [],
        "deleted": ["knobs/a.txt"],
        "rejected": [],
        "ticket": None,
        "reason": "deletion",
    }
    ticket = "crafted-ticket"
    overlay = round_dir / "outbox" / ticket
    overlay.mkdir(parents=True)
    (overlay / "manifest.json").write_text(
        json.dumps({"ticket": ticket, "lane_id": "L1", "files": {}, "deleted": ["knobs/a.txt"]}),
        encoding="utf-8",
    )
    served = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert served["status"] == "rejected"
    assert served["reason"] == "deletion"
    assert not (round_dir / "candidates").exists()


def test_submit_after_deadline_is_refused_on_a_fresh_read(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    spec = _spec()
    spec["lanes"][0]["deadline_utc"] = "2020-01-01T00:00:00+00:00"
    round_dir = tmp_path / "round"
    prepare(spec, incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    first = submit(round_dir, "L1", incumbent, work, now=WHEN)
    second = submit(round_dir, "L1", incumbent, work, now=WHEN)
    assert first["submitted"] is False and second["submitted"] is False
    assert "deadline" in first["reason"]
    assert not (round_dir / "outbox").exists()


def test_launch_after_deadline_cancels_before_claim(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    moments = [WHEN, datetime(2100, 1, 1, tzinfo=timezone.utc)]

    def clock():
        return moments.pop(0) if len(moments) > 1 else moments[0]

    rejected = serve_ticket(
        round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN, clock=clock
    )
    assert rejected["status"] == "rejected"
    assert "deadline" in rejected["reason"]
    ledger = json.loads((round_dir / "ledgers" / "L1.json").read_text(encoding="utf-8"))
    assert ledger["entries"][-1]["phase"] == "cancelled"
    assert not (round_dir / "candidates" / ticket / "build-stamp").exists()


def test_deadline_expiring_between_build_and_candidate_stops_the_trial(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    spec = _spec()
    deadline = (WHEN + timedelta(seconds=10)).isoformat()
    for lane in spec["lanes"]:
        lane["deadline_utc"] = deadline
    round_dir = tmp_path / "round"
    prepare(spec, incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    moments = [WHEN, WHEN, WHEN + timedelta(seconds=1), WHEN + timedelta(seconds=11)]

    def clock():
        return moments.pop(0)

    class Counting:
        name = "counting"

        def __init__(self) -> None:
            self.calls = 0

        def run(self, *args, **kwargs):
            del args, kwargs
            self.calls += 1
            return {"status": "completed", "returncode": 0, "stdout": "", "stderr": ""}

    backend = Counting()
    rejected = serve_ticket(round_dir, ticket, incumbent, backend=backend, now=WHEN, clock=clock)
    assert rejected["status"] == "unsettled"
    assert "deadline" in rejected["reason"]
    assert backend.calls == 1
    ledger = json.loads((round_dir / "ledgers" / "L1.json").read_text(encoding="utf-8"))
    assert [entry["phase"] for entry in ledger["entries"]] == ["claimed"]
    assert ticket_status(round_dir, ticket)["status"] == "unsettled"


def test_namespace_timeout_after_claim_is_an_unsettled_receipt(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]

    class TimesOut:
        name = "timeout"

        def run(self, *args, **kwargs):
            del args, kwargs
            raise subprocess.TimeoutExpired(["build"], 1)

    result = serve_ticket(round_dir, ticket, incumbent, backend=TimesOut(), now=WHEN)
    assert result["status"] == "unsettled"
    assert "timed out" in result["reason"]
    assert result["reason"].startswith("build")
    ledger = json.loads((round_dir / "ledgers" / "L1.json").read_text(encoding="utf-8"))
    assert [entry["phase"] for entry in ledger["entries"]] == ["claimed"]
    assert ticket_status(round_dir, ticket)["status"] == "unsettled"


def test_failure_after_claim_stays_unsettled_across_restart(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]

    class StopAfterClaim:
        name = "stop"

        def run(self, *args, **kwargs):
            del args, kwargs
            raise ConfinementUnavailable("stopped after claim")

    first = serve_ticket(
        round_dir, ticket, incumbent, backend=StopAfterClaim(), now=WHEN
    )
    assert first["status"] == "unsettled"
    ledger_path = round_dir / "ledgers" / "L1.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert [entry["phase"] for entry in ledger["entries"]] == ["claimed"]
    (round_dir / "results" / f"{ticket}.json").unlink()
    second = serve_ticket(
        round_dir, ticket, incumbent, backend=StopAfterClaim(), now=WHEN
    )
    assert second["status"] == "unsettled"
    reloaded = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert [entry["phase"] for entry in reloaded["entries"]] == ["claimed"]
    assert reloaded["entries"][0]["worst_case"] == ledger["entries"][0]["worst_case"]


def test_completed_trial_without_a_latency_file_is_unsettled(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]

    class CompletesWithoutResult:
        name = "empty"

        def run(self, *args, **kwargs):
            del args, kwargs
            return {"status": "completed", "stdout": "", "stderr": ""}

    result = serve_ticket(
        round_dir, ticket, incumbent, backend=CompletesWithoutResult(), now=WHEN
    )
    assert result["status"] == "unsettled"
    assert "readable latency_ms result" in result["reason"]
    assert ticket_status(round_dir, ticket)["status"] == "unsettled"


def test_serve_cli_runs_without_a_caller_supplied_clock(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    tool = Path(__file__).parents[1] / "tools" / "parallel_round.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(tool),
            "serve",
            "--round-dir",
            str(round_dir),
            "--ticket",
            ticket,
            "--incumbent",
            str(incumbent),
        ],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    body = json.loads(completed.stdout)
    assert body["ticket"] == ticket
    if namespaces_available():
        assert body["status"] == "measured"
    else:
        assert body["status"] == "unsettled"
        assert body["reason"] == "confinement backend unavailable"
