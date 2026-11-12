"""Driving a synthetic round end to end. Metric figures here are fixture inputs."""

import json
import sys
from pathlib import Path

import pytest

from inferrsi.harness.parallel_drive import drive_round
from inferrsi.harness.parallel_round import RoundPlanError
from inferrsi.infra.confinement import FixtureBackend, UnshareBackend, namespaces_available

BENCH = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "a = float(Path('knobs/a.txt').read_text())\n"
    "b = float(Path('knobs/b.txt').read_text())\n"
    "Path(sys.argv[1]).write_text(json.dumps({'metrics': {'latency_ms': a + b}}))\n"
)
AGENT = (
    "import sys\n"
    "from pathlib import Path\n"
    "if sys.argv[2] == 'fail':\n"
    "    sys.exit(3)\n"
    "if sys.argv[2] != 'same':\n"
    "    Path(sys.argv[1]).write_text(sys.argv[2])\n"
    "Path(sys.argv[3]).mkdir(parents=True, exist_ok=True)\n"
    "Path(sys.argv[3], 'ran').open('a').write('x')\n"
)


def _tree(root: Path) -> None:
    (root / "knobs").mkdir(parents=True)
    (root / "knobs" / "a.txt").write_text("10", encoding="utf-8")
    (root / "knobs" / "b.txt").write_text("10", encoding="utf-8")
    (root / "bench.py").write_text(BENCH, encoding="utf-8")


def _lane(lane_id: str, knob: str, value: str, tmp_path: Path) -> dict:
    agent = tmp_path / "agent.py"
    agent.write_text(AGENT, encoding="utf-8")
    return {
        "id": lane_id,
        "entry": f"D-{lane_id}",
        "plane": "infra",
        "globs": [f"knobs/{knob}"],
        "cap": 4,
        "per_attempt_worst_case": 1,
        "deadline_utc": "2099-01-01T00:00:00+00:00",
        "agent": [
            sys.executable,
            str(agent),
            f"knobs/{knob}",
            value,
            str(tmp_path / "calls" / "{lane}"),
        ],
    }


def _spec(lanes: list[dict]) -> dict:
    return {
        "round_id": "r1",
        "device_ids": ["cpu-0", "cpu-1"],
        "metric": {"name": "latency_ms", "better": "lower", "repeats": 2},
        "incumbent_id": "fixture-incumbent",
        "protected": ["bench.py"],
        "build": [],
        "trial": [sys.executable, "bench.py", "{result}"],
        "lanes": lanes,
    }


def _knobs(root: Path) -> tuple[str, str]:
    return (
        (root / "knobs" / "a.txt").read_text(encoding="utf-8"),
        (root / "knobs" / "b.txt").read_text(encoding="utf-8"),
    )


def test_drive_runs_each_lane_once_and_closes_on_the_stacked_change(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent)
    round_dir = tmp_path / "round"
    lanes = [_lane("L1", "a.txt", "8", tmp_path), _lane("L2", "b.txt", "7", tmp_path)]
    driven = drive_round(
        _spec(lanes),
        incumbent,
        round_dir,
        tmp_path / "next",
        backend=FixtureBackend(),
        poll_seconds=0.01,
    )
    assert {lane: item["status"] for lane, item in driven["lanes"].items()} == {
        "L1": "measured",
        "L2": "measured",
    }
    for lane in ("L1", "L2"):
        assert (tmp_path / "calls" / lane / "ran").read_text(encoding="utf-8") == "x"
    assert len(list((round_dir / "results").glob("*.json"))) == 2
    assert driven["close"]["choice"] == "composite"
    assert driven["close"]["composite"]["candidate"] == 15
    assert _knobs(tmp_path / "next") == ("8", "7")
    assert _knobs(incumbent) == ("10", "10")
    assert json.loads((round_dir / "drive.json").read_text(encoding="utf-8")) == driven


def test_a_failing_agent_stops_only_its_lane(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent)
    lanes = [_lane("L1", "a.txt", "8", tmp_path), _lane("L2", "b.txt", "fail", tmp_path)]
    driven = drive_round(
        _spec(lanes),
        incumbent,
        tmp_path / "round",
        tmp_path / "next",
        backend=FixtureBackend(),
        poll_seconds=0.01,
    )
    assert driven["lanes"]["L2"] == {
        "status": "agent_failed",
        "reason": "agent exited 3",
        "ticket": None,
    }
    assert driven["close"]["choice"] == "lane"
    assert _knobs(tmp_path / "next") == ("8", "10")


def test_an_agent_without_changes_leaves_the_incumbent(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent)
    driven = drive_round(
        _spec([_lane("L1", "a.txt", "same", tmp_path)]),
        incumbent,
        tmp_path / "round",
        tmp_path / "next",
        backend=FixtureBackend(),
        poll_seconds=0.01,
    )
    assert driven["lanes"]["L1"]["status"] == "unchanged"
    assert driven["close"]["choice"] == "kept_incumbent"
    assert _knobs(tmp_path / "next") == ("10", "10")


def test_drive_needs_an_agent_command_on_every_lane(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent)
    lane = _lane("L1", "a.txt", "8", tmp_path)
    del lane["agent"]
    with pytest.raises(RoundPlanError, match="without an agent"):
        drive_round(
            _spec([lane]),
            incumbent,
            tmp_path / "round",
            tmp_path / "next",
            backend=FixtureBackend(),
        )


@pytest.mark.skipif(not namespaces_available(), reason="user namespaces are unavailable")
def test_drive_under_real_namespaces(tmp_path):
    incumbent = tmp_path / "incumbent"
    _tree(incumbent)
    lanes = [_lane("L1", "a.txt", "8", tmp_path), _lane("L2", "b.txt", "7", tmp_path)]
    driven = drive_round(
        _spec(lanes),
        incumbent,
        tmp_path / "round",
        tmp_path / "next",
        backend=UnshareBackend(),
        poll_seconds=0.01,
    )
    assert driven["close"]["choice"] == "composite"
    assert driven["close"]["composite"]["candidate"] == 15
    assert _knobs(tmp_path / "next") == ("8", "7")
