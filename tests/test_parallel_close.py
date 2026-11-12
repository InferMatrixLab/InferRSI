"""Closing a synthetic round. Metric figures here are fixture inputs, not measurements."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from inferrsi.harness.parallel_close import CloseError, close_round
from inferrsi.harness.parallel_round import prepare, serve_ticket, submit
from inferrsi.infra.confinement import FixtureBackend

WHEN = datetime(2026, 10, 30, tzinfo=timezone.utc)
BENCH = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "a = float(Path('knobs/a.txt').read_text())\n"
    "b = float(Path('knobs/b.txt').read_text())\n"
    "both = 100 if a != 10 and b != 10 else 0\n"
    "value = a + b + (both if Path('clash').exists() else 0)\n"
    "Path(sys.argv[1]).write_text(json.dumps({'metrics': {'score': value}}))\n"
)


def _tree(root: Path, *, clash: bool = False) -> None:
    (root / "knobs").mkdir(parents=True)
    (root / "knobs" / "a.txt").write_text("10", encoding="utf-8")
    (root / "knobs" / "b.txt").write_text("10", encoding="utf-8")
    (root / "bench.py").write_text(BENCH, encoding="utf-8")
    if clash:
        (root / "clash").write_text("", encoding="utf-8")


def _lane(lane_id: str, glob: str) -> dict:
    return {
        "id": lane_id,
        "entry": f"D-{lane_id}",
        "plane": "infra",
        "globs": [glob],
        "cap": 3,
        "per_attempt_worst_case": 1,
        "deadline_utc": "2099-01-01T00:00:00+00:00",
    }


def _round(tmp_path, *, better="lower", margin=0, clash=False):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent, clash=clash)
    round_dir = tmp_path / "round"
    spec = {
        "round_id": "r1",
        "device_ids": ["cpu-0", "cpu-1"],
        "metric": {"name": "score", "better": better, "margin": margin},
        "incumbent_id": "fixture-incumbent",
        "protected": ["bench.py", "clash"],
        "build": [],
        "trial": [sys.executable, "bench.py", "{result}"],
        "lanes": [_lane("L1", "knobs/a.txt"), _lane("L2", "knobs/b.txt")],
    }
    prepare(spec, incumbent, round_dir)
    return incumbent, round_dir


def _try(tmp_path, incumbent, round_dir, lane_id, knob, value) -> dict:
    work = tmp_path / f"work-{lane_id}-{value}"
    _tree(work, clash=(incumbent / "clash").exists())
    (work / "knobs" / knob).write_text(value, encoding="utf-8")
    ticket = submit(round_dir, lane_id, incumbent, work, now=WHEN)["ticket"]
    return serve_ticket(round_dir, ticket, incumbent, backend=FixtureBackend(), now=WHEN)


def _knobs(root: Path) -> tuple[str, str]:
    return (
        (root / "knobs" / "a.txt").read_text(encoding="utf-8"),
        (root / "knobs" / "b.txt").read_text(encoding="utf-8"),
    )


def test_no_passing_lane_keeps_the_incumbent(tmp_path):
    incumbent, round_dir = _round(tmp_path)
    assert _try(tmp_path, incumbent, round_dir, "L1", "a.txt", "12")["status"] == "measured"
    closed = close_round(round_dir, incumbent, tmp_path / "next", backend=FixtureBackend())
    assert closed["choice"] == "kept_incumbent"
    assert closed["lanes"]["L1"]["passed"] is False
    assert _knobs(tmp_path / "next") == ("10", "10")


def test_one_passing_lane_takes_its_best_ticket(tmp_path):
    incumbent, round_dir = _round(tmp_path)
    _try(tmp_path, incumbent, round_dir, "L1", "a.txt", "9")
    best = _try(tmp_path, incumbent, round_dir, "L1", "a.txt", "7")
    closed = close_round(round_dir, incumbent, tmp_path / "next", backend=FixtureBackend())
    assert closed["choice"] == "lane"
    assert closed["chosen_tickets"] == [best["ticket"]]
    assert closed["composite"] is None
    assert _knobs(tmp_path / "next") == ("7", "10")
    assert set(closed["files"]) == {"bench.py", "knobs/a.txt", "knobs/b.txt"}


def test_margin_filters_small_gains(tmp_path):
    incumbent, round_dir = _round(tmp_path, margin=0.1)
    _try(tmp_path, incumbent, round_dir, "L1", "a.txt", "9")
    closed = close_round(round_dir, incumbent, tmp_path / "next", backend=FixtureBackend())
    assert closed["choice"] == "kept_incumbent"


def test_two_passing_lanes_stack_when_the_composite_is_better(tmp_path):
    incumbent, round_dir = _round(tmp_path)
    _try(tmp_path, incumbent, round_dir, "L1", "a.txt", "8")
    _try(tmp_path, incumbent, round_dir, "L2", "b.txt", "7")
    closed = close_round(round_dir, incumbent, tmp_path / "next", backend=FixtureBackend())
    assert closed["passing"] == ["L2", "L1"]
    assert closed["composite"]["status"] == "measured"
    assert closed["composite"]["candidate"] == 15
    assert closed["choice"] == "composite"
    assert _knobs(tmp_path / "next") == ("8", "7")


def test_a_worse_composite_falls_back_to_the_best_single_lane(tmp_path):
    incumbent, round_dir = _round(tmp_path, clash=True)
    _try(tmp_path, incumbent, round_dir, "L1", "a.txt", "8")
    _try(tmp_path, incumbent, round_dir, "L2", "b.txt", "7")
    closed = close_round(round_dir, incumbent, tmp_path / "next", backend=FixtureBackend())
    assert closed["composite"]["candidate"] == 115
    assert closed["choice"] == "lane"
    assert _knobs(tmp_path / "next") == ("10", "7")


def test_higher_is_better_picks_the_larger_score(tmp_path):
    incumbent, round_dir = _round(tmp_path, better="higher")
    _try(tmp_path, incumbent, round_dir, "L1", "a.txt", "8")
    _try(tmp_path, incumbent, round_dir, "L2", "b.txt", "13")
    closed = close_round(round_dir, incumbent, tmp_path / "next", backend=FixtureBackend())
    assert closed["passing"] == ["L2"]
    assert _knobs(tmp_path / "next") == ("10", "13")


def test_close_is_idempotent_and_refuses_a_non_empty_output(tmp_path):
    incumbent, round_dir = _round(tmp_path)
    _try(tmp_path, incumbent, round_dir, "L1", "a.txt", "8")
    _try(tmp_path, incumbent, round_dir, "L2", "b.txt", "7")
    first = close_round(round_dir, incumbent, tmp_path / "next", backend=FixtureBackend())

    class Refuses:
        name = "refuses"

        def run(self, *args, **kwargs):
            raise AssertionError("close measured twice")

    again = close_round(round_dir, incumbent, tmp_path / "next", backend=Refuses())
    assert again == first
    assert json.loads((round_dir / "close.json").read_text(encoding="utf-8")) == first
    taken = tmp_path / "taken"
    taken.mkdir()
    (taken / "x").write_text("", encoding="utf-8")
    (round_dir / "close.json").unlink()
    with pytest.raises(CloseError, match="already has files"):
        close_round(round_dir, incumbent, taken, backend=FixtureBackend())
