"""Synthetic parallel round. Latency figures here are fixture inputs, not measurements."""

import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from inferrsi.apps.parallel_round import close_round, serve_ticket
from inferrsi.harness import parallel_round
from inferrsi.harness.confinement import (
    ConfinementUnavailable,
    FixtureBackend,
    UnreapedCommand,
    UnshareBackend,
    namespaces_available,
)
from inferrsi.harness.device_lease import DeviceLease, LeaseError
from inferrsi.harness.parallel_round import (
    RoundPlanError,
    _read_nofollow,
    _ticket_metadata_path,
    _tree_digest,
    hold_devices,
    materialize,
    prepare,
    submit,
    ticket_status,
)

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


def test_submit_rejects_new_protected_and_cross_lane_owned_paths(tmp_path):
    """prepare only sees the incumbent; submit must police concrete new paths."""
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(
        _spec(
            protected=["new/protected.txt"],
            lanes=[
                {
                    "id": "L1",
                    "entry": "D-01",
                    "plane": "infra",
                    "globs": ["new/*"],
                    "cap": 2,
                    "per_attempt_worst_case": 1,
                    "deadline_utc": "2099-01-01T00:00:00+00:00",
                },
                {
                    "id": "L2",
                    "entry": "D-02",
                    "plane": "harness",
                    "globs": ["new/*.txt"],
                    "cap": 2,
                    "per_attempt_worst_case": 1,
                    "deadline_utc": "2099-01-01T00:00:00+00:00",
                },
            ],
        ),
        incumbent,
        round_dir,
    )
    work = tmp_path / "work"
    shutil.copytree(incumbent, work)
    (work / "new").mkdir()
    (work / "new" / "protected.txt").write_text("x", encoding="utf-8")
    for lane_id in ("L1", "L2"):
        refused = submit(round_dir, lane_id, incumbent, work)
        assert refused["submitted"] is False
        assert refused["reason"] == "protected"
        assert refused["rejected"] == ["new/protected.txt"]
    (work / "new" / "protected.txt").unlink()
    (work / "new" / "shared.txt").write_text("y", encoding="utf-8")
    for lane_id in ("L1", "L2"):
        refused = submit(round_dir, lane_id, incumbent, work)
        assert refused["submitted"] is False
        assert refused["reason"] == "overlap"
        assert refused["rejected"] == ["new/shared.txt"]
    assert not (round_dir / "outbox").exists()


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
    assert measured["improvement_pct"] == pytest.approx(20)
    assert measured["verdict"] == "INCONCLUSIVE"
    assert (Path(measured["run_dir"]) / "evaluation.json").exists()
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


def test_prepare_rejects_bad_repeats_and_timeout(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    base = {"name": "latency_ms", "better": "lower"}
    for extra, message in (
        ({"repeats": 0}, "repeats"),
        ({"repeats": True}, "repeats"),
        ({"margin": 0.03}, "metric needs"),
        ({"spread": 1}, "metric needs"),
        ({"min_improvement_pct": -1}, "min_improvement_pct"),
        ({"min_improvement_pct": float("nan")}, "min_improvement_pct"),
    ):
        with pytest.raises(RoundPlanError, match=message):
            prepare(_spec(metric={**base, **extra}), incumbent, tmp_path / "round-metric")
    for timeout in (0, -1, "30", float("inf")):
        with pytest.raises(RoundPlanError, match="command_timeout_seconds"):
            prepare(_spec(command_timeout_seconds=timeout), incumbent, tmp_path / "round-t")
    for overrides, message in (
        ({"validation": "pytest"}, "validation"),
        ({"validation": []}, "validation"),
        ({"device_model": ""}, "device_model"),
    ):
        with pytest.raises(RoundPlanError, match=message):
            prepare(_spec(**overrides), incumbent, tmp_path / "round-fields")
    plan = prepare(_spec(), incumbent, tmp_path / "round-defaults")
    assert plan["metric"] == {**base, "repeats": 1, "min_improvement_pct": 0}
    assert plan["validation"] is None
    assert plan["device_model"] is None
    assert plan["command_timeout_seconds"] == 30


def test_prepare_rejects_bad_device_paths_and_env(tmp_path):
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
    values = {"candidate": [8, 100, 9], "baseline": [10, 10, 1000]}
    order = []

    class Recording:
        name = "recording"

        def run(self, argv, *args, **kwargs):
            del args, kwargs
            result = Path(argv[-1])
            side = result.parent.parent.name
            order.append(f"{side}-{result.parent.name}")
            body = {"metrics": {"latency_ms": values[side].pop(0)}}
            result.write_text(json.dumps(body), encoding="utf-8")
            return {"status": "completed", "stdout": "", "stderr": ""}

    measured = serve_ticket(round_dir, ticket, incumbent, backend=Recording(), now=WHEN)
    assert order == [
        "baseline-trial-001",
        "candidate-trial-001",
        "candidate-trial-002",
        "baseline-trial-002",
        "baseline-trial-003",
        "candidate-trial-003",
    ]
    assert measured["candidate_samples"] == [8, 100, 9]
    assert measured["candidate"] == 9
    assert measured["incumbent"] == 10
    assert measured["improvement_pct"] == pytest.approx(10)


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
    assert measured["improvement_pct"] == pytest.approx(-20)


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
    assert "must be a number" in result["reason"]
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
    _ticket_metadata_path(overlay).write_text(
        json.dumps({"ticket": ticket, "lane_id": "L1", "files": {}, "deleted": ["knobs/a.txt"]}),
        encoding="utf-8",
    )
    served = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert served["status"] == "rejected"
    assert served["reason"] == "deletion"
    assert not (round_dir / "candidates").exists()


def test_changed_root_manifest_is_the_project_file(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    (incumbent / "manifest.json").write_bytes(b'{"project":"incumbent"}\n')
    round_dir = tmp_path / "round"
    prepare(
        _spec(
            lanes=[
                {
                    "id": "L1",
                    "entry": "D-01",
                    "plane": "infra",
                    "globs": ["manifest.json"],
                    "cap": 1,
                    "per_attempt_worst_case": 1,
                    "deadline_utc": "2099-01-01T00:00:00+00:00",
                }
            ]
        ),
        incumbent,
        round_dir,
    )
    work = tmp_path / "work"
    _tree(work, "10")
    payload = b'{"project":"candidate"}\n'
    (work / "manifest.json").write_bytes(payload)
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    overlay = round_dir / "outbox" / ticket
    assert (overlay / "manifest.json").read_bytes() == payload
    record = json.loads(_ticket_metadata_path(overlay).read_text(encoding="utf-8"))
    assert record["ticket"] == ticket
    assert record["files"].keys() == {"manifest.json"}
    assert _ticket_metadata_path(overlay).read_bytes() != payload
    destination = tmp_path / "materialized"
    materialize(incumbent, [overlay], destination)
    assert (destination / "manifest.json").read_bytes() == payload


def test_unchanged_manifest_files_reach_the_successor(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    root_manifest = b'{"role":"root"}\n'
    nested_manifest = b'{"role":"nested"}\n'
    (incumbent / "manifest.json").write_bytes(root_manifest)
    (incumbent / "pkg").mkdir()
    (incumbent / "pkg" / "manifest.json").write_bytes(nested_manifest)
    round_dir = tmp_path / "round"
    prepare(_sum_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    shutil.copytree(incumbent, work)
    (work / "knobs" / "a.txt").write_text("8", encoding="utf-8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    overlay = round_dir / "outbox" / ticket
    materialized = tmp_path / "materialized"
    materialize(incumbent, [overlay], materialized)
    assert (materialized / "knobs" / "a.txt").read_text(encoding="utf-8") == "8"
    assert (materialized / "manifest.json").read_bytes() == root_manifest
    assert (materialized / "pkg" / "manifest.json").read_bytes() == nested_manifest
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["status"] == "measured"
    assert measured["verdict"] == "PASS"
    closed = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert closed["accepted"] is True
    successor = Path(closed["successor"])
    assert (successor / "knobs" / "a.txt").read_text(encoding="utf-8") == "8"
    assert (successor / "knobs" / "b.txt").read_text(encoding="utf-8") == "10"
    assert (successor / "manifest.json").read_bytes() == root_manifest
    assert (successor / "pkg" / "manifest.json").read_bytes() == nested_manifest


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
    moments = [WHEN, WHEN, datetime(2100, 1, 1, tzinfo=timezone.utc)]

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
    moments = [WHEN, WHEN, WHEN, WHEN + timedelta(seconds=1), WHEN + timedelta(seconds=11)]

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


def _one_ticket(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    return incumbent, round_dir, ticket


def _phases(round_dir):
    ledger = json.loads((round_dir / "ledgers" / "L1.json").read_text(encoding="utf-8"))
    return [entry["phase"] for entry in ledger["entries"]]


def test_restart_after_reserve_resumes_the_same_attempt(tmp_path, monkeypatch):
    incumbent, round_dir, ticket = _one_ticket(tmp_path)

    def crash(*args, **kwargs):
        del args, kwargs
        raise KeyboardInterrupt

    monkeypatch.setattr(parallel_round, "seconds_remaining", crash)
    with pytest.raises(KeyboardInterrupt):
        serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert _phases(round_dir) == ["reserved"]
    monkeypatch.undo()
    result = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert result["status"] == "measured"
    assert _phases(round_dir) == ["finished"]


def test_restart_after_finish_writes_a_receipt_without_rerunning(tmp_path):
    incumbent, round_dir, ticket = _one_ticket(tmp_path)
    first = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert first["status"] == "measured"
    (round_dir / "results" / f"{ticket}.json").unlink()

    class MustNotRun:
        name = "must-not-run"

        def run(self, *args, **kwargs):
            raise AssertionError("a finished attempt was launched again")

    second = serve_ticket(round_dir, ticket, incumbent, backend=MustNotRun(), now=WHEN)
    assert second["status"] == "unsettled"
    assert second["reason"] == "finished execution was not settled"
    assert _phases(round_dir) == ["finished"]


def test_a_queued_ticket_past_its_deadline_is_rejected_without_a_reservation(tmp_path):
    incumbent, round_dir, ticket = _one_ticket(tmp_path)
    leases = DeviceLease(round_dir / "leases")
    held = [leases.acquire("cpu-0"), leases.acquire("cpu-1")]
    try:
        queued = serve_ticket(
            round_dir, ticket, incumbent, backend=FixtureBackend(), clock=lambda: WHEN
        )
        assert queued["status"] == "queued"
        late = datetime(2100, 1, 1, tzinfo=timezone.utc)
        rejected = serve_ticket(
            round_dir, ticket, incumbent, backend=FixtureBackend(), clock=lambda: late
        )
    finally:
        for lease in held:
            lease.release()
    assert rejected["status"] == "rejected"
    assert "deadline" in rejected["reason"]
    assert ticket_status(round_dir, ticket)["status"] == "rejected"
    assert not (round_dir / "ledgers" / "L1.json").exists()


def test_an_unreaped_command_quarantines_its_device(tmp_path):
    incumbent, round_dir, ticket = _one_ticket(tmp_path)

    class Unreaped:
        name = "unreaped"

        def run(self, *args, **kwargs):
            del args, kwargs
            raise UnreapedCommand("namespace command outlived its deadline")

    result = serve_ticket(round_dir, ticket, incumbent, backend=Unreaped(), now=WHEN)
    assert result["status"] == "unsettled"
    assert result["devices"] == ["cpu-0"]
    assert (round_dir / "leases" / "cpu-0.quarantined").exists()
    with pytest.raises(LeaseError, match="quarantined"):
        DeviceLease(round_dir / "leases").acquire("cpu-0")
    plan = json.loads((round_dir / "round-plan.json").read_text(encoding="utf-8"))
    assert hold_devices(round_dir, plan, 2) is None
    held = hold_devices(round_dir, plan, 1)
    assert [device for device, _lease in held] == ["cpu-1"]
    for _device, lease in held:
        lease.release()
    (round_dir / "leases" / "cpu-0.quarantined").unlink()
    DeviceLease(round_dir / "leases").acquire("cpu-0").release()


def test_reading_a_fifo_does_not_block(tmp_path):
    os.mkfifo(tmp_path / "pipe")
    found = []
    reader = threading.Thread(target=lambda: found.append(_read_nofollow(tmp_path, "pipe")))
    reader.daemon = True
    reader.start()
    reader.join(timeout=5)
    assert not reader.is_alive()
    assert found == [None]


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
    assert "result.json" in result["reason"]
    assert ticket_status(round_dir, ticket)["status"] == "unsettled"


def _git_tree(root: Path, knob: str) -> None:
    _tree(root, knob)
    for argv in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "incumbent"],
    ):
        subprocess.run(["git", "-C", str(root), *argv], check=True)


def test_a_git_incumbent_with_validation_gets_a_verdict(tmp_path):
    incumbent = tmp_path / "incumbent"
    _git_tree(incumbent, "10")
    work = tmp_path / "work"
    _tree(work, "8")
    passing = [sys.executable, "-c", "pass"]
    for threshold, verdict in ((3, "PASS"), (25, "FAIL")):
        round_dir = tmp_path / f"round-{threshold}"
        metric = {"name": "latency_ms", "better": "lower", "min_improvement_pct": threshold}
        prepare(_spec(metric=metric, validation=passing), incumbent, round_dir)
        ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
        measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
        assert measured["status"] == "measured"
        assert measured["verdict"] == verdict, measured["reasons"]
        assert measured["improvement_pct"] == pytest.approx(20)


def test_a_failing_validation_is_a_measured_fail(tmp_path):
    incumbent = tmp_path / "incumbent"
    _git_tree(incumbent, "10")
    round_dir = tmp_path / "round"
    failing = [sys.executable, "-c", "raise SystemExit(1)"]
    prepare(_spec(validation=failing), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["status"] == "measured"
    assert measured["verdict"] == "FAIL"
    ledger = json.loads((round_dir / "ledgers" / "L1.json").read_text(encoding="utf-8"))
    assert [entry["phase"] for entry in ledger["entries"]] == ["finished"]


def test_device_model_checks_the_held_devices_before_reserving(tmp_path, monkeypatch):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(device_ids=["0", "1"], device_model="L20X"), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    seen = []

    def busy(*, count, device_model):
        seen.append((count, device_model, os.environ.get("CUDA_VISIBLE_DEVICES")))
        raise ValueError("An allocated GPU already has a compute process")

    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.setattr("inferrsi.apps.parallel_round.qualify_devices", busy)
    queued = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert queued["status"] == "queued"
    assert "compute process" in queued["reason"]
    assert seen == [(1, "L20X", "0")]
    assert "CUDA_VISIBLE_DEVICES" not in os.environ
    assert not (round_dir / "ledgers").exists()
    DeviceLease(round_dir / "leases").acquire("0").release()

    monkeypatch.setattr("inferrsi.apps.parallel_round.qualify_devices", lambda **kwargs: [])
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["status"] == "measured"


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


SUM_BENCH = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "a = float(Path('knobs/a.txt').read_text())\n"
    "b = float(Path('knobs/b.txt').read_text())\n"
    "body = {'metrics': {'latency_ms': a + b}, 'synthetic': True}\n"
    "Path(sys.argv[1]).write_text(json.dumps(body))\n"
)


def _sum_tree(root: Path, a: str, b: str) -> None:
    (root / "knobs").mkdir(parents=True)
    (root / "knobs" / "a.txt").write_text(a, encoding="utf-8")
    (root / "knobs" / "b.txt").write_text(b, encoding="utf-8")
    (root / "bench.py").write_text(SUM_BENCH, encoding="utf-8")


def _sum_spec(**overrides):
    return _spec(
        build=[],
        trial=[sys.executable, "bench.py", "{result}"],
        validation=[sys.executable, "-c", "pass"],
        **overrides,
    )


def test_close_composes_pass_lanes_once_and_writes_a_successor(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    round_dir = tmp_path / "round"
    prepare(_sum_spec(), incumbent, round_dir)
    for lane_id, knob, value in (("L1", "a.txt", "8"), ("L2", "b.txt", "8")):
        work = tmp_path / f"work-{lane_id}"
        _sum_tree(work, "10", "10")
        (work / "knobs" / knob).write_text(value, encoding="utf-8")
        ticket = submit(round_dir, lane_id, incumbent, work, now=WHEN)["ticket"]
        measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
        assert measured["status"] == "measured"
        assert measured["verdict"] == "PASS"
    closed = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert closed["status"] == "closed"
    assert closed["composition"] == "joint-single-rerun"
    assert closed["accepted"] is True
    assert closed["retained"] is False
    assert [item["lane_id"] for item in closed["composed"]] == ["L1", "L2"]
    successor = Path(closed["successor"])
    assert (successor / "knobs" / "a.txt").read_text(encoding="utf-8") == "8"
    assert (successor / "knobs" / "b.txt").read_text(encoding="utf-8") == "8"
    assert closed["improvement_pct"] == pytest.approx(20)
    again = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert again == closed


def test_close_with_no_pass_lanes_retains_the_incumbent(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    round_dir = tmp_path / "round"
    prepare(_sum_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _sum_tree(work, "12", "10")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["verdict"] == "FAIL"
    closed = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert closed["accepted"] is False
    assert closed["retained"] is True
    assert closed["composed"] == []
    assert closed["successor"] is None
    assert not (round_dir / "successor").exists()


def test_close_refuses_while_a_ticket_is_unsettled(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(build=[]), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]

    class Empty(FixtureBackend):
        def run(self, *args, **kwargs):
            del args, kwargs
            return {"status": "completed", "stdout": "", "stderr": "", "returncode": 0}

    unsettled = serve_ticket(round_dir, ticket, incumbent, backend=Empty(), now=WHEN)
    assert unsettled["status"] == "unsettled"
    refused = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert refused["status"] == "refused"
    assert "unsettled" in refused["reason"]
    assert not (round_dir / "close.json").exists()


def test_build_planted_git_hooks_do_not_run_on_the_host(tmp_path):
    canary = tmp_path / "hook-ran"
    hook = tmp_path / "evil-hook.py"
    hook.write_text(
        f"from pathlib import Path\nPath({str(canary)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    incumbent = tmp_path / "incumbent"
    _git_tree(incumbent, "10")
    plant = (
        "from pathlib import Path\n"
        "root = Path('.git')\n"
        "root.mkdir(exist_ok=True)\n"
        f"(root / 'config').write_text('[diff]\\n\\texternal = {sys.executable} {hook}\\n')\n"
    )
    round_dir = tmp_path / "round"
    prepare(
        _spec(
            build=[sys.executable, "-c", plant],
            validation=[sys.executable, "-c", "pass"],
        ),
        incumbent,
        round_dir,
    )
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["status"] == "measured", measured
    assert not canary.exists()
    assert "diff" in (round_dir / "candidates" / ticket / ".git" / "config").read_text(
        encoding="utf-8"
    )


def test_validation_confinement_failure_stays_unsettled(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(
        _spec(build=[], validation=[sys.executable, "-c", "pass"]),
        incumbent,
        round_dir,
    )
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]

    class BoomValidation(FixtureBackend):
        def run(self, argv, cwd, writable, readable, deadline, **kwargs):
            if writable and Path(writable[0]).name == "validation":
                raise ConfinementUnavailable("device node missing")
            return super().run(argv, cwd, writable, readable, deadline, **kwargs)

    result = serve_ticket(round_dir, ticket, incumbent, backend=BoomValidation(), now=WHEN)
    assert result["status"] == "unsettled"
    assert "device node missing" in result["reason"]
    ledger = json.loads((round_dir / "ledgers" / "L1.json").read_text(encoding="utf-8"))
    assert [entry["phase"] for entry in ledger["entries"]] == ["claimed"]


COMBO_BENCH = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "a = float(Path('knobs/a.txt').read_text())\n"
    "b = float(Path('knobs/b.txt').read_text())\n"
    "value = 30.0 if a != 10 and b != 10 else a + b\n"
    "body = {'metrics': {'latency_ms': value}, 'synthetic': True}\n"
    "Path(sys.argv[1]).write_text(json.dumps(body))\n"
)


def _combo_lane():
    return [
        {
            "id": "L1",
            "entry": "D-01",
            "plane": "infra",
            "globs": ["knobs/*.txt"],
            "cap": 2,
            "per_attempt_worst_case": 1,
            "deadline_utc": "2099-01-01T00:00:00+00:00",
        }
    ]


def test_one_winner_per_lane_is_promoted_when_the_joint_passes(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    round_dir = tmp_path / "round"
    prepare(_sum_spec(lanes=_combo_lane()), incumbent, round_dir)
    works = (("a", "a.txt", "8"), ("b", "b.txt", "6"))
    measured_by_knob = {}
    for name, knob, value in works:
        work = tmp_path / f"work-{name}"
        _sum_tree(work, "10", "10")
        (work / "knobs" / knob).write_text(value, encoding="utf-8")
        ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
        measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
        assert measured["verdict"] == "PASS"
        measured_by_knob[knob] = measured
    winner = measured_by_knob["b.txt"]
    loser = measured_by_knob["a.txt"]
    assert winner["improvement_pct"] > loser["improvement_pct"]
    closed = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert closed["accepted"] is True
    assert [item["ticket"] for item in closed["composed"]] == [winner["ticket"]]
    assert [item["ticket"] for item in closed["dropped"]] == [loser["ticket"]]
    successor = Path(closed["successor"])
    assert (successor / "knobs" / "a.txt").read_text(encoding="utf-8") == "10"
    assert (successor / "knobs" / "b.txt").read_text(encoding="utf-8") == "6"
    assert not (round_dir / "knowledge" / "joint-failure.json").exists()


def test_joint_failure_of_lane_winners_writes_the_summary(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    (incumbent / "bench.py").write_text(COMBO_BENCH, encoding="utf-8")
    round_dir = tmp_path / "round"
    prepare(_sum_spec(), incumbent, round_dir)
    tickets = []
    for lane_id, knob in (("L1", "a.txt"), ("L2", "b.txt")):
        work = tmp_path / f"work-{lane_id}"
        _sum_tree(work, "10", "10")
        (work / "bench.py").write_text(COMBO_BENCH, encoding="utf-8")
        (work / "knobs" / knob).write_text("8", encoding="utf-8")
        ticket = submit(round_dir, lane_id, incumbent, work, now=WHEN)["ticket"]
        measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
        assert measured["verdict"] == "PASS"
        tickets.append(ticket)
    closed = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert closed["accepted"] is False
    assert closed["retained"] is True
    assert closed["dropped"] == []
    assert not (round_dir / "successor").exists()
    note = json.loads((round_dir / "knowledge" / "joint-failure.json").read_text(encoding="utf-8"))
    assert note["kind"] == "inferrsi.parallel_round.joint_failure"
    assert note["verdict"] == "FAIL"
    assert {item["ticket"] for item in note["tickets"]} == set(tickets)
    assert {item["lane_id"] for item in note["tickets"]} == {"L1", "L2"}


def test_successor_keeps_the_frozen_incumbent_bytes(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    original = (incumbent / "bench.py").read_text(encoding="utf-8")
    round_dir = tmp_path / "round"
    prepare(_sum_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _sum_tree(work, "8", "10")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["verdict"] == "PASS"

    class EditDuringClose(FixtureBackend):
        def run(self, *args, **kwargs):
            (incumbent / "knobs" / "b.txt").write_text("99", encoding="utf-8")
            (incumbent / "bench.py").write_text("mutated\n", encoding="utf-8")
            return super().run(*args, **kwargs)

    closed = close_round(round_dir, incumbent, backend=EditDuringClose(), now=WHEN)
    assert closed["accepted"] is True
    successor = Path(closed["successor"])
    assert (successor / "knobs" / "a.txt").read_text(encoding="utf-8") == "8"
    assert (successor / "knobs" / "b.txt").read_text(encoding="utf-8") == "10"
    assert (successor / "bench.py").read_text(encoding="utf-8") == original
    assert (incumbent / "knobs" / "b.txt").read_text(encoding="utf-8") == "99"


def test_joint_confinement_failure_does_not_seal_the_round(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    round_dir = tmp_path / "round"
    prepare(_sum_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _sum_tree(work, "8", "10")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["verdict"] == "PASS"

    class Boom(FixtureBackend):
        def run(self, *args, **kwargs):
            del args, kwargs
            raise ConfinementUnavailable("namespace command failed")

    refused = close_round(round_dir, incumbent, backend=Boom(), now=WHEN)
    assert refused["status"] == "refused"
    assert "namespace command failed" in refused["reason"]
    assert not (round_dir / "close.json").exists()
    closed = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert closed["accepted"] is True
    assert (round_dir / "close.json").exists()


def test_joint_build_confinement_failure_does_not_seal_the_round(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    round_dir = tmp_path / "round"
    spec = _sum_spec()
    spec["build"] = [sys.executable, "-c", "pass"]
    prepare(spec, incumbent, round_dir)
    work = tmp_path / "work"
    _sum_tree(work, "8", "10")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["verdict"] == "PASS"

    class Boom(FixtureBackend):
        def run(self, *args, **kwargs):
            del args, kwargs
            raise ConfinementUnavailable("mount failed")

    refused = close_round(round_dir, incumbent, backend=Boom(), now=WHEN)
    assert refused["status"] == "refused"
    assert "mount failed" in refused["reason"]
    assert not (round_dir / "close.json").exists()


@pytest.mark.skipif(not namespaces_available(), reason="user namespaces are unavailable")
def test_unshare_failing_validation_is_a_measured_fail(tmp_path):
    incumbent = tmp_path / "incumbent"
    _git_tree(incumbent, "10")
    round_dir = tmp_path / "round"
    failing = [sys.executable, "-c", "raise SystemExit(1)"]
    prepare(_spec(validation=failing), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=UnshareBackend(), now=WHEN)
    assert measured["status"] == "measured", measured
    assert measured["verdict"] == "FAIL"
    ledger = json.loads((round_dir / "ledgers" / "L1.json").read_text(encoding="utf-8"))
    assert [entry["phase"] for entry in ledger["entries"]] == ["finished"]
    closed = close_round(round_dir, incumbent, backend=UnshareBackend(), now=WHEN)
    assert closed["status"] == "closed"
    assert closed["retained"] is True
    assert (round_dir / "close.json").exists()


def test_submit_streams_a_file_larger_than_one_chunk(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "10")
    payload = b"x" * (1024 * 1024) + b"TAIL"
    big = work / "knobs" / "a.txt"
    big.write_bytes(payload)
    big.chmod(0o755)
    submitted = submit(round_dir, "L1", incumbent, work, now=WHEN)
    assert submitted["submitted"] is True
    stored = round_dir / "outbox" / submitted["ticket"] / "knobs" / "a.txt"
    assert stored.read_bytes() == payload
    assert stored.stat().st_mode & 0o111
    assert not (round_dir / "submit-staging").exists()


def test_metadata_write_failure_retries_without_a_false_success(tmp_path, monkeypatch):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    real = parallel_round.write_json
    failed = {"once": False}

    def write_json(path, value):
        if not failed["once"] and Path(path).parent.name == "outbox":
            failed["once"] = True
            raise OSError("no space left on device")
        real(path, value)

    monkeypatch.setattr(parallel_round, "write_json", write_json)
    refused = submit(round_dir, "L1", incumbent, work, now=WHEN)
    assert refused["submitted"] is False
    assert refused["ticket"] is None
    outbox = round_dir / "outbox"
    assert not outbox.exists() or list(outbox.iterdir()) == []
    accepted = submit(round_dir, "L1", incumbent, work, now=WHEN)
    assert accepted["submitted"] is True
    ticket = accepted["ticket"]
    metadata = _ticket_metadata_path(round_dir / "outbox" / ticket)
    assert json.loads(metadata.read_text(encoding="utf-8"))["ticket"] == ticket
    assert (round_dir / "outbox" / ticket / "knobs" / "a.txt").read_text(encoding="utf-8") == "8"
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["status"] == "measured", measured
    metadata.unlink()
    repaired = submit(round_dir, "L1", incumbent, work, now=WHEN)
    assert repaired["submitted"] is True
    assert repaired["ticket"] == ticket
    assert json.loads(metadata.read_text(encoding="utf-8"))["lane_id"] == "L1"


def test_retry_repairs_a_payload_that_does_not_match_the_manifest(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    submitted = submit(round_dir, "L1", incumbent, work, now=WHEN)
    ticket = submitted["ticket"]
    stored = round_dir / "outbox" / ticket / "knobs" / "a.txt"
    stored.write_text("truncated", encoding="utf-8")
    repaired = submit(round_dir, "L1", incumbent, work, now=WHEN)
    assert repaired["submitted"] is True
    assert repaired["ticket"] == ticket
    assert stored.read_text(encoding="utf-8") == "8"
    stored.unlink()
    replaced = submit(round_dir, "L1", incumbent, work, now=WHEN)
    assert replaced["submitted"] is True
    assert replaced["ticket"] == ticket
    assert stored.read_text(encoding="utf-8") == "8"


def test_serve_rejects_a_truncated_payload_without_retrying_submit(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    (round_dir / "outbox" / ticket / "knobs" / "a.txt").write_text("truncated", encoding="utf-8")

    class MustNotRun(FixtureBackend):
        def run(self, *args, **kwargs):
            del args, kwargs
            raise AssertionError("serve ran a command for a truncated payload")

    served = serve_ticket(round_dir, ticket, incumbent, backend=MustNotRun(), now=WHEN)
    assert served["status"] == "rejected"
    assert served["reason"] == "payload does not match the ticket manifest: knobs/a.txt"
    assert not (round_dir / "candidates" / ticket).exists()
    assert not (round_dir / "results" / f"{ticket}.json").exists()
    assert not (round_dir / "ledgers" / "L1.json").exists()


def test_close_refuses_a_truncated_payload_without_measuring_it(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    round_dir = tmp_path / "round"
    prepare(_sum_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _sum_tree(work, "8", "10")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["verdict"] == "PASS"
    (round_dir / "outbox" / ticket / "knobs" / "a.txt").write_text("truncated", encoding="utf-8")

    class MustNotRun(FixtureBackend):
        def run(self, *args, **kwargs):
            del args, kwargs
            raise AssertionError("close ran a command for a truncated payload")

    refused = close_round(round_dir, incumbent, backend=MustNotRun(), now=WHEN)
    assert refused["status"] == "refused"
    assert refused["reason"] == "payload does not match the ticket manifest: knobs/a.txt"
    assert not (round_dir / "close.json").exists()
    assert not (round_dir / "successor").exists()
    assert not (round_dir / "candidates" / "joint-close").exists()


def test_submit_refuses_a_file_that_changes_after_the_scan(tmp_path, monkeypatch):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _tree(work, "8")
    real = parallel_round._snapshot

    def snapshot(root):
        hashes, blocked = real(root)
        if root == work:
            (work / "knobs" / "a.txt").write_text("mutated", encoding="utf-8")
        return hashes, blocked

    monkeypatch.setattr(parallel_round, "_snapshot", snapshot)
    refused = submit(round_dir, "L1", incumbent, work, now=WHEN)
    assert refused["submitted"] is False
    assert refused["reason"] == "changed during submit"
    assert refused["rejected"] == ["knobs/a.txt"]
    assert not (round_dir / "outbox").exists()


def test_submit_refuses_an_executable_bit_that_changes_after_the_scan(tmp_path, monkeypatch):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    script = incumbent / "build.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o644)
    round_dir = tmp_path / "round"
    prepare(
        _spec(
            lanes=[
                {
                    "id": "L1",
                    "entry": "D-01",
                    "plane": "infra",
                    "globs": ["build.sh"],
                    "cap": 2,
                    "per_attempt_worst_case": 1,
                    "deadline_utc": "2099-01-01T00:00:00+00:00",
                }
            ]
        ),
        incumbent,
        round_dir,
    )
    work = tmp_path / "work"
    _tree(work, "10")
    copied = work / "build.sh"
    copied.write_text(script.read_text(encoding="utf-8") + "echo x\n", encoding="utf-8")
    copied.chmod(0o644)
    real = parallel_round._snapshot

    def snapshot(root):
        hashes, blocked = real(root)
        if root == work:
            copied.chmod(0o755)
        return hashes, blocked

    monkeypatch.setattr(parallel_round, "_snapshot", snapshot)
    refused = submit(round_dir, "L1", incumbent, work, now=WHEN)
    assert refused["submitted"] is False
    assert refused["reason"] == "changed during submit"
    assert refused["rejected"] == ["build.sh"]
    assert not (round_dir / "outbox").exists()


def test_executable_bit_is_part_of_identity_and_the_entrypoint_runs(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    script = incumbent / "build.sh"
    script.write_text("#!/bin/sh\necho built > build-stamp\n", encoding="utf-8")
    script.chmod(0o644)
    plain = _tree_digest(incumbent)
    script.chmod(0o755)
    assert _tree_digest(incumbent) != plain
    script.chmod(0o644)
    round_dir = tmp_path / "round"
    prepare(
        _spec(
            lanes=[
                {
                    "id": "L1",
                    "entry": "D-01",
                    "plane": "infra",
                    "globs": ["build.sh"],
                    "cap": 2,
                    "per_attempt_worst_case": 1,
                    "deadline_utc": "2099-01-01T00:00:00+00:00",
                }
            ],
            build=["./build.sh"],
            validation=[sys.executable, "-c", "pass"],
        ),
        incumbent,
        round_dir,
    )
    work = tmp_path / "work"
    _tree(work, "10")
    copied = work / "build.sh"
    copied.write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
    copied.chmod(0o755)
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    stored = round_dir / "outbox" / ticket / "build.sh"
    assert stored.stat().st_mode & 0o111
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["status"] == "measured", measured
    candidate = round_dir / "candidates" / ticket
    assert (candidate / "build.sh").stat().st_mode & 0o111
    assert (candidate / "build-stamp").read_text(encoding="utf-8").strip() == "built"


def test_joint_build_nonzero_exit_closes_with_the_returncode(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    round_dir = tmp_path / "round"
    spec = _sum_spec()
    spec["build"] = [sys.executable, "-c", "pass"]
    prepare(spec, incumbent, round_dir)
    work = tmp_path / "work"
    _sum_tree(work, "8", "10")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["verdict"] == "PASS"

    class JointBuildFailed(FixtureBackend):
        def run(self, argv, cwd, writable, readable, deadline, **kwargs):
            if Path(cwd).name == "joint-close":
                return {"status": "failed", "returncode": 2, "stdout": "", "stderr": "cc failed"}
            return super().run(argv, cwd, writable, readable, deadline, **kwargs)

    closed = close_round(round_dir, incumbent, backend=JointBuildFailed(), now=WHEN)
    assert closed["status"] == "closed"
    assert closed["retained"] is True
    assert closed["accepted"] is False
    assert closed["stage"] == "build"
    assert closed["returncode"] == 2
    assert not (round_dir / "successor").exists()
    again = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert again == closed


def test_successor_keeps_files_the_build_wrote_into_the_measured_tree(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    round_dir = tmp_path / "round"
    spec = _sum_spec()
    spec["build"] = [
        sys.executable,
        "-c",
        "from pathlib import Path; Path('knobs/generated.txt').write_text('from-build')",
    ]
    prepare(spec, incumbent, round_dir)
    work = tmp_path / "work"
    _sum_tree(work, "8", "10")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["verdict"] == "PASS"
    closed = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert closed["accepted"] is True
    successor = Path(closed["successor"])
    assert (successor / "knobs" / "a.txt").read_text(encoding="utf-8") == "8"
    assert (successor / "knobs" / "generated.txt").read_text(encoding="utf-8") == "from-build"


def test_promotion_does_not_publish_or_follow_repository_metadata(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("SECRET-OUTSIDE", encoding="utf-8")
    round_dir = tmp_path / "round"
    spec = _sum_spec()
    spec["build"] = [
        sys.executable,
        "-c",
        "import os; from pathlib import Path; "
        "git = Path('.git'); git.mkdir(); (git / 'config').write_text('planted-git'); "
        f"os.symlink({str(outside)!r}, git / 'leak'); "
        "Path('knobs/generated.txt').write_text('from-build')",
    ]
    prepare(spec, incumbent, round_dir)
    work = tmp_path / "work"
    _sum_tree(work, "8", "10")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["verdict"] == "PASS"
    closed = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert closed["accepted"] is True
    successor = Path(closed["successor"])
    assert (successor / "knobs" / "generated.txt").read_text(encoding="utf-8") == "from-build"
    assert (successor / "knobs" / "a.txt").read_text(encoding="utf-8") == "8"
    assert not (successor / ".git").exists()
    published = [
        path.read_text(encoding="utf-8")
        for path in successor.rglob("*")
        if path.is_file()
    ]
    assert all("SECRET-OUTSIDE" not in text for text in published)
    assert outside.read_text(encoding="utf-8") == "SECRET-OUTSIDE"


def test_promotion_refuses_a_symlink_without_following_it(tmp_path):
    source = tmp_path / "source"
    _tree(source, "8")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("SECRET-OUTSIDE", encoding="utf-8")
    (source / "knobs" / "leak").symlink_to(outside)
    destination = tmp_path / "successor"
    with pytest.raises(ValueError, match="knobs/leak"):
        parallel_round._promote_snapshot(source, destination, "unused")
    assert not destination.exists()
    assert outside.read_text(encoding="utf-8") == "SECRET-OUTSIDE"


def test_promotion_refuses_a_file_changed_after_measurement(tmp_path, monkeypatch):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    round_dir = tmp_path / "round"
    prepare(_sum_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _sum_tree(work, "8", "10")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["verdict"] == "PASS"
    real = parallel_round._run_experiment

    def run_experiment(*args, **kwargs):
        path = real(*args, **kwargs)
        target = round_dir / "candidates" / "joint-close" / "knobs" / "a.txt"
        target.write_text("changed-after-measure", encoding="utf-8")
        return path

    monkeypatch.setattr(parallel_round, "_run_experiment", run_experiment)
    refused = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert refused["status"] == "refused"
    assert refused["reason"] == "promoted tree does not match the measured snapshot"
    assert not (round_dir / "successor").exists()
    assert not (round_dir / "close.json").exists()
    joint = round_dir / "candidates" / "joint-close" / "knobs" / "a.txt"
    assert joint.read_text(encoding="utf-8") == "changed-after-measure"


def test_submit_refuses_while_close_runs_and_after_it_finishes(tmp_path):
    incumbent = tmp_path / "incumbent"
    _sum_tree(incumbent, "10", "10")
    round_dir = tmp_path / "round"
    prepare(_sum_spec(), incumbent, round_dir)
    work = tmp_path / "work"
    _sum_tree(work, "8", "10")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["verdict"] == "PASS"
    started = threading.Event()
    release = threading.Event()

    class Blocking(FixtureBackend):
        def run(self, argv, cwd, writable, readable, deadline, **kwargs):
            started.set()
            assert release.wait(10)
            return super().run(argv, cwd, writable, readable, deadline, **kwargs)

    holder: dict = {}

    def go() -> None:
        holder["result"] = close_round(round_dir, incumbent, backend=Blocking(), now=WHEN)

    thread = threading.Thread(target=go)
    thread.start()
    assert started.wait(10)
    later = tmp_path / "later"
    _sum_tree(later, "7", "10")
    refused = submit(round_dir, "L1", incumbent, later, now=WHEN)
    assert refused["submitted"] is False
    assert refused["reason"] == "round closing"
    release.set()
    thread.join(10)
    assert holder["result"]["status"] == "closed"
    after = submit(round_dir, "L1", incumbent, later, now=WHEN)
    assert after["submitted"] is False
    assert after["reason"] == "round closed"


def test_changed_incumbent_bytes_are_refused(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, "10")
    linked = tmp_path / "linked"
    _tree(linked, "10")
    (linked / "knobs" / "a.txt").unlink()
    (linked / "knobs" / "a.txt").symlink_to(incumbent / "knobs" / "a.txt")
    with pytest.raises(RoundPlanError, match="unreadable"):
        prepare(_spec(), linked, tmp_path / "round-link")
    round_dir = tmp_path / "round"
    prepare(_spec(), incumbent, round_dir)
    (incumbent / "knobs" / "a.txt").write_text("11", encoding="utf-8")
    work = tmp_path / "work"
    _tree(work, "8")
    refused = submit(round_dir, "L1", incumbent, work, now=WHEN)
    assert refused["submitted"] is False
    assert refused["reason"] == "incumbent tree does not match the frozen digest"
    assert not (round_dir / "outbox").exists()
    (incumbent / "knobs" / "a.txt").write_text("10", encoding="utf-8")
    ticket = submit(round_dir, "L1", incumbent, work, now=WHEN)["ticket"]
    (incumbent / "knobs" / "a.txt").write_text("11", encoding="utf-8")
    served = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert served["status"] == "rejected"
    assert served["reason"] == "incumbent tree does not match the frozen digest"
    assert not (round_dir / "results" / f"{ticket}.json").exists()
    (incumbent / "knobs" / "a.txt").write_text("10", encoding="utf-8")
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["status"] == "measured"
    (incumbent / "knobs" / "b.txt").write_text("11", encoding="utf-8")
    closed = close_round(round_dir, incumbent, backend=FixtureBackend(), now=WHEN)
    assert closed["status"] == "refused"
    assert closed["reason"] == "incumbent tree does not match the frozen digest"
    assert not (round_dir / "close.json").exists()
