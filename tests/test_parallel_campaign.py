"""Running synthetic cluster rounds under a campaign plan's round cap."""

import json
import sys
from pathlib import Path

import pytest

from inferrsi.harness.parallel_campaign import CampaignError, round_cap, run_campaign
from inferrsi.infra.confinement import FixtureBackend

pytest.importorskip("yaml")

BENCH = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "value = float(Path('knob.txt').read_text())\n"
    "Path(sys.argv[1]).write_text(json.dumps({'metrics': {'latency_ms': value}}))\n"
)
AGENT = (
    "from pathlib import Path\n"
    "knob = Path('knob.txt')\n"
    "knob.write_text(str(int(knob.read_text()) - 1))\n"
)
PLANNER = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "template, spec, number, last = sys.argv[1:5]\n"
    "if int(number) > int(last):\n"
    "    sys.exit(0)\n"
    "body = json.loads(Path(template).read_text())\n"
    "body['round_id'] = 'r' + number\n"
    "Path(spec).write_text(json.dumps(body))\n"
)


def _setup(tmp_path: Path, cap: str, last_round: int) -> tuple[Path, list[str], Path]:
    incumbent = tmp_path / "incumbent"
    incumbent.mkdir()
    (incumbent / "knob.txt").write_text("10", encoding="utf-8")
    (incumbent / "bench.py").write_text(BENCH, encoding="utf-8")
    agent = tmp_path / "agent.py"
    agent.write_text(AGENT, encoding="utf-8")
    template = tmp_path / "template.json"
    template.write_text(
        json.dumps(
            {
                "round_id": "r",
                "device_ids": ["cpu-0"],
                "metric": {"name": "latency_ms", "better": "lower"},
                "incumbent_id": "fixture",
                "protected": ["bench.py"],
                "build": [],
                "trial": [sys.executable, "bench.py", "{result}"],
                "lanes": [
                    {
                        "id": "L1",
                        "entry": "D-01",
                        "plane": "infra",
                        "globs": ["knob.txt"],
                        "cap": 1,
                        "per_attempt_worst_case": 1,
                        "deadline_utc": "2099-01-01T00:00:00+00:00",
                        "agent": [sys.executable, str(agent)],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    planner = tmp_path / "planner.py"
    planner.write_text(PLANNER, encoding="utf-8")
    campaign_plan = tmp_path / "campaign-plan.yaml"
    campaign_plan.write_text(f'budget:\n  round_cap: "{cap}"\n', encoding="utf-8")
    argv = [sys.executable, str(planner), str(template), "{spec}", "{round}", str(last_round)]
    return campaign_plan, argv, incumbent


def test_campaign_runs_round_cap_rounds_and_carries_the_incumbent(tmp_path):
    campaign_plan, planner, incumbent = _setup(tmp_path, "2", last_round=5)
    work = tmp_path / "campaign"
    result = run_campaign(
        campaign_plan, planner, incumbent, work, backend=FixtureBackend(), poll_seconds=0.01
    )
    assert result["stop"] == "round_cap"
    assert [item["choice"] for item in result["rounds"]] == ["lane", "lane"]
    assert (Path(result["incumbent"]) / "knob.txt").read_text(encoding="utf-8") == "8"
    assert (incumbent / "knob.txt").read_text(encoding="utf-8") == "10"
    assert json.loads((work / "campaign.json").read_text(encoding="utf-8")) == result


def test_campaign_stops_when_the_planner_writes_no_spec(tmp_path):
    campaign_plan, planner, incumbent = _setup(tmp_path, "5", last_round=1)
    result = run_campaign(
        campaign_plan,
        planner,
        incumbent,
        tmp_path / "campaign",
        backend=FixtureBackend(),
        poll_seconds=0.01,
    )
    assert result["stop"] == "planner_stopped"
    assert len(result["rounds"]) == 1
    assert (Path(result["incumbent"]) / "knob.txt").read_text(encoding="utf-8") == "9"


def test_round_cap_must_be_a_positive_whole_number(tmp_path):
    plan = tmp_path / "campaign-plan.yaml"
    for value in ('"<n>"', '"0"', '"2.5"', "true", "[]"):
        plan.write_text(f"budget:\n  round_cap: {value}\n", encoding="utf-8")
        with pytest.raises(CampaignError, match="round_cap"):
            round_cap(plan)
    plan.write_text("budget:\n  round_cap: 3\n", encoding="utf-8")
    assert round_cap(plan) == 3
