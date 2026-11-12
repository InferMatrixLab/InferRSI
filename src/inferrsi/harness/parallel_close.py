"""Close one parallel round: pick passing lanes and write the next incumbent.

A lane passes when its best measured ticket beats the incumbent by at least
``metric.margin`` (relative gain). With two or more passing lanes, their overlays
are stacked and measured against the incumbent once more. The stack is chosen only
if its gain is at least the best single lane's gain; otherwise the best single lane
is. The extra measurement is not charged to any lane's attempt budget.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from inferrsi.harness.parallel_round import (
    MeasurementError,
    _snapshot,
    compare,
    hold_devices,
    materialize,
    summarize,
)
from inferrsi.harness.round_budget import BudgetError
from inferrsi.infra.artifacts import write_json
from inferrsi.infra.confinement import ConfinementUnavailable


class CloseError(RuntimeError):
    """The round cannot be closed as asked."""


def _score(result: dict) -> float:
    relative = result.get("relative_gain")
    return result["gain"] if relative is None else relative


def _passes(result: dict, margin: float) -> bool:
    relative = result.get("relative_gain")
    return result["gain"] > 0 and (relative is None or relative >= margin)


def _best_per_lane(round_dir: Path) -> dict[str, dict]:
    best: dict[str, dict] = {}
    for path in sorted((round_dir / "results").glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("status") != "measured":
            continue
        lane_id = result.get("lane_id")
        if lane_id is None:
            manifest = round_dir / "outbox" / result["ticket"] / "manifest.json"
            lane_id = json.loads(manifest.read_text(encoding="utf-8"))["lane_id"]
        if lane_id not in best or _score(result) > _score(best[lane_id]):
            best[lane_id] = {**result, "lane_id": lane_id}
    return best


def close_round(round_dir: Path, incumbent: Path, output: Path, *, backend, clock=None) -> dict:
    """Write the next incumbent to ``output`` and ``close.json``. Repeated calls return
    the first decision without measuring again."""
    record_path = round_dir / "close.json"
    if record_path.exists():
        return json.loads(record_path.read_text(encoding="utf-8"))
    if output.exists() and any(output.iterdir()):
        raise CloseError(f"output {output} already has files")

    def current() -> datetime:
        if clock is not None:
            return clock()
        return datetime.now(timezone.utc)

    plan = json.loads((round_dir / "round-plan.json").read_text(encoding="utf-8"))
    margin = plan["metric"]["margin"]
    lane_count = {lane["id"]: lane["device_count"] for lane in plan["lanes"]}
    best = _best_per_lane(round_dir)
    passing = sorted(
        (result for result in best.values() if _passes(result, margin)),
        key=_score,
        reverse=True,
    )
    composite = None
    chosen = passing[:1]
    if len(passing) >= 2:
        composite = _measure_composite(
            round_dir, plan, incumbent, passing, lane_count, backend=backend, current=current
        )
        if composite.get("status") == "measured" and _score(composite) >= _score(passing[0]):
            chosen = passing
    overlays = [round_dir / "outbox" / result["ticket"] for result in chosen]
    if output.exists():
        output.rmdir()
    materialize(incumbent, overlays, output)
    hashes, _blocked = _snapshot(output)
    body = {
        "round_digest": plan["round_digest"],
        "metric": plan["metric"],
        "lanes": {
            lane_id: {
                "ticket": result["ticket"],
                "gain": result["gain"],
                "relative_gain": result.get("relative_gain"),
                "passed": _passes(result, margin),
            }
            for lane_id, result in sorted(best.items())
        },
        "passing": [result["lane_id"] for result in passing],
        "composite": composite,
        "choice": ("kept_incumbent" if not chosen else "composite" if len(chosen) > 1 else "lane"),
        "chosen_tickets": [result["ticket"] for result in chosen],
        "output": str(output),
        "files": hashes,
    }
    write_json(record_path, body)
    return body


def _measure_composite(
    round_dir: Path,
    plan: dict,
    incumbent: Path,
    passing: list[dict],
    lane_count: dict[str, int],
    *,
    backend,
    current,
) -> dict:
    count = max(lane_count[result["lane_id"]] for result in passing)
    held = hold_devices(round_dir, plan, count)
    if held is None:
        return {"status": "unsettled", "reason": f"could not hold {count} free devices"}
    devices = [device for device, _lease in held]
    composite = round_dir / "close" / "composite"
    try:
        materialize(
            incumbent, [round_dir / "outbox" / result["ticket"] for result in passing], composite
        )
        candidate_samples, incumbent_samples = compare(
            plan,
            composite,
            incumbent,
            round_dir / "close" / "trials",
            devices,
            None,
            backend=backend,
            current=current,
        )
    except (ConfinementUnavailable, BudgetError, MeasurementError) as exc:
        return {"status": "unsettled", "reason": str(exc), "devices": devices}
    finally:
        for _device, lease in held:
            lease.release()
    return {
        "status": "measured",
        "tickets": [result["ticket"] for result in passing],
        **summarize(plan, candidate_samples, incumbent_samples),
        "devices": devices,
    }
