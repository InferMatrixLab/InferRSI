"""Synthetic parallel round. Latency figures here are fixture inputs, not measurements."""

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from inferrsi.harness.parallel_round import (
    RoundPlanError,
    prepare,
    serve_ticket,
    submit,
    ticket_status,
)
from inferrsi.infra.confinement import FixtureBackend
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
        "device_id": "cpu-0",
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
    held = DeviceLease(round_dir / "leases").acquire("cpu-0")
    queued = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert queued["status"] == "queued"
    assert ticket_status(round_dir, ticket)["status"] == "queued"
    assert not (round_dir / "ledgers").exists()
    held.release()
    measured = serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)
    assert measured["synthetic"] is True
    assert measured["candidate_latency_ms"] == 8
    assert measured["incumbent_latency_ms"] == 10
    assert measured["gain_ms"] == 2
    assert measured["confinement"] == "fixture"
    assert (round_dir / "candidates" / ticket / "build-stamp").read_text(encoding="utf-8") == "ok"


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
