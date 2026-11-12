"""Run cluster rounds until the campaign plan's ``round_cap`` or the planner stops.

``round_cap`` is read from row 6 of the campaign plan (``budget.round_cap`` in
``campaign-plan.yaml``). Each round, the ``planner`` command (the decision agent)
writes the round spec for ``drive``; the next incumbent of one round is the
incumbent of the next. The planner stops the campaign by exiting 0 without
writing a spec, for example when the target is met or no direction is left.

The planner runs on the host with the caller's environment; it is not confined.
Placeholders: ``{incumbent}`` the current incumbent, ``{round}`` the round number
from 1, ``{previous}`` the previous round's ``drive.json`` (empty in round 1) and
``{spec}`` where the round spec must be written.
"""

import json
import subprocess
from pathlib import Path

from inferrsi.harness.parallel_drive import drive_round
from inferrsi.infra.artifacts import write_json


class CampaignError(RuntimeError):
    """The campaign cannot start as asked."""


def round_cap(campaign_plan: Path) -> int:
    """``budget.round_cap`` as a positive whole number."""
    try:
        import yaml
    except ImportError as exc:  # The base install stays PyYAML-free by contract.
        raise CampaignError(
            "Reading the campaign plan requires the 'skills' extra (PyYAML): "
            "python -m pip install '<inferrsi-checkout>[skills]'"
        ) from exc
    plan = yaml.safe_load(campaign_plan.read_text(encoding="utf-8"))
    value = (plan.get("budget") or {}).get("round_cap") if isinstance(plan, dict) else None
    text = str(value) if type(value) in (int, str) else ""
    if not text.isdigit() or int(text) < 1:
        raise CampaignError(f"budget.round_cap must be a positive whole number, got {value!r}")
    return int(text)


def run_campaign(
    campaign_plan: Path,
    planner: list[str],
    incumbent: Path,
    work_dir: Path,
    *,
    backend,
    poll_seconds: float = 5.0,
    clock=None,
) -> dict:
    """Run up to ``round_cap`` rounds and write ``campaign.json``."""
    cap = round_cap(campaign_plan)
    if not planner:
        raise CampaignError("campaign needs a planner command")
    if work_dir.exists() and any(work_dir.iterdir()):
        raise CampaignError(f"work dir {work_dir} already has files")
    work_dir.mkdir(parents=True, exist_ok=True)
    current = incumbent
    previous = ""
    rounds: list[dict] = []
    stop = {"stop": "round_cap", "reason": f"ran {cap} rounds"}
    for number in range(1, cap + 1):
        round_dir = work_dir / f"round-{number}"
        round_dir.mkdir()
        spec_path = round_dir / "spec.json"
        values = {
            "{incumbent}": str(current),
            "{round}": str(number),
            "{previous}": previous,
            "{spec}": str(spec_path),
        }
        argv = []
        for part in planner:
            for key, value in values.items():
                part = part.replace(key, value)
            argv.append(part)
        try:
            finished = subprocess.run(argv, cwd=work_dir, check=False)
        except OSError as exc:
            stop = {"stop": "planner_failed", "reason": str(exc)}
            break
        if finished.returncode != 0:
            stop = {"stop": "planner_failed", "reason": f"planner exited {finished.returncode}"}
            break
        if not spec_path.exists():
            stop = {"stop": "planner_stopped", "reason": f"no round spec for round {number}"}
            break
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        output = round_dir / "incumbent-next"
        driven = drive_round(
            spec,
            current,
            round_dir / "round",
            output,
            backend=backend,
            poll_seconds=poll_seconds,
            clock=clock,
        )
        rounds.append(
            {
                "round": number,
                "choice": driven["close"]["choice"],
                "chosen_tickets": driven["close"]["chosen_tickets"],
                "drive": str(round_dir / "round" / "drive.json"),
            }
        )
        current = output
        previous = str(round_dir / "round" / "drive.json")
    body = {"round_cap": cap, "rounds": rounds, **stop, "incumbent": str(current)}
    write_json(work_dir / "campaign.json", body)
    return body
