"""Project a single run's paired command events into reviewable work units."""

from datetime import datetime


def _timestamp(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed
        except ValueError:
            pass
    return None


def run_workflow(events: list[dict], lock: dict, run_state: str) -> dict:
    # Runner node identity is local to one run. A new run is a new attempt.
    pairs = {}
    for event in events:
        phase = event["phase"] or ""
        kind = phase.removesuffix("_end")
        if kind not in ("source_snapshot", "measurement", "quality_validation"):
            continue
        side, trial = event["side"], event["trial"]
        if kind == "measurement" and (side is None or trial is None):
            continue
        pair = pairs.setdefault((kind, side, trial), {})
        edge = "end" if phase.endswith("_end") else "start"
        previous = pair.get(edge)
        if previous is None:
            pair[edge] = event
        elif (previous["time"], previous["details"]) != (event["time"], event["details"]):
            pair["conflict"] = True

    nodes = []
    for (kind, side, trial), pair in pairs.items():
        start, end = pair.get("start", {}), pair.get("end", {})
        state = end.get("details", {}).get("state", "unknown")
        if pair.get("conflict"):
            state = "unknown"
        elif (
            not end
            and run_state == "running"
            and start.get("details", {}).get("state") == "running"
        ):
            state = "running"
        nodes.append(
            {
                "kind": kind,
                "side": side,
                "trial": trial,
                "state": state,
                "start": start.get("time"),
                "end": end.get("time"),
                "seconds": None
                if pair.get("conflict")
                else end.get("details", {}).get("elapsed_seconds"),
                "line": (end or start)["line"],
            }
        )
    nodes.sort(key=lambda n: (_timestamp(n["start"]) is None, _timestamp(n["start"]), n["line"]))

    repetitions = lock.get("repetitions")
    trials = repetitions * 2 if type(repetitions) is int and 0 <= repetitions <= 1_000_000 else None
    quality = None if "validation_command" not in lock else int(bool(lock["validation_command"]))
    groups = []
    for kind, total in (("measurement", trials), ("quality_validation", quality)):
        work = [n for n in nodes if n["kind"] == kind]
        states = {n["state"] for n in work}
        completed = sum(n["state"] == "completed" for n in work)
        if "unknown" in states or (total is not None and len(work) > total):
            state = "unknown"
        elif not work and total == 0:
            state = "not_configured"
        elif states.intersection({"failed", "error", "timeout", "cancelled"}):
            state = next(
                n["state"]
                for n in work
                if n["state"] in {"failed", "error", "timeout", "cancelled"}
            )
        elif "running" in states:
            state = "running"
        elif total and completed == total:
            state = "completed"
        elif not work and run_state in {"cancelled", "failed", "timeout", "crashed"}:
            state = "skipped"
        elif run_state == "running" and total is not None:
            state = "pending"
        else:
            state = "unknown"
        starts = [_timestamp(n["start"]) for n in work]
        ends = [_timestamp(n["end"]) for n in work]
        wall = None
        if (
            work
            and all(starts)
            and all(ends)
            and all(b >= a for a, b in zip(starts, ends))
            and "unknown" not in states
        ):
            wall = (max(ends) - min(starts)).total_seconds()
        groups.append(
            {
                "kind": kind,
                "completed": completed,
                "total": total,
                "state": state,
                "wall_seconds": wall,
            }
        )
    return {"nodes": nodes, "groups": groups}


def validation_progress(record: dict) -> dict | None:
    """Read only aggregate counters from a validator-owned snapshot."""
    unit = record.get("unit")
    done, total = record.get("completed"), record.get("total")
    if (unit not in ("samples", "cases", "manifests")
            or type(done) is not int or not 0 <= done <= 1_000_000
            or "total" not in record
            or (total is not None and (type(total) is not int or not done <= total <= 1_000_000))):
        return None
    return {"completed": done, "total": total, "unit": unit}
