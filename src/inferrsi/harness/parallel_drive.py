"""Drive one parallel round from a single command, then close it.

Each lane gets one worker. A worker keeps a work tree at ``round_dir/work/<lane>``
(copied from the incumbent once) and loops: run the lane's ``agent`` command,
submit the work tree, serve the ticket until it is no longer queued.

The agent command runs on the host with the caller's environment; it is not
confined. Placeholders: ``{work}`` is the work tree, ``{lane}`` the lane id and
``{results}`` a JSON file listing this lane's earlier receipts.

A worker stops when the agent exits non-zero, submit refuses (``unchanged`` means
the agent has nothing more to try), a ticket repeats, or serve returns anything
other than ``measured``. A lane that reaches its cap stops on the rejected receipt.
"""

import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from inferrsi.harness.parallel_close import close_round
from inferrsi.harness.parallel_round import RoundPlanError, prepare, serve_ticket, submit
from inferrsi.harness.round_budget import BudgetError, seconds_remaining
from inferrsi.infra.artifacts import write_json


def drive_round(
    spec: dict,
    incumbent: Path,
    round_dir: Path,
    output: Path,
    *,
    backend,
    poll_seconds: float = 5.0,
    clock=None,
) -> dict:
    """Prepare, run every lane until it stops, close, and write ``drive.json``."""
    plan = prepare(spec, incumbent, round_dir)
    missing = [lane["id"] for lane in plan["lanes"] if not lane.get("agent")]
    if missing:
        raise RoundPlanError(f"lanes without an agent command: {', '.join(missing)}")

    def current() -> datetime:
        if clock is not None:
            return clock()
        return datetime.now(timezone.utc)

    outcomes: dict[str, dict] = {}

    def work(lane: dict) -> None:
        try:
            outcomes[lane["id"]] = _drive_lane(
                round_dir, incumbent, lane, backend, poll_seconds, current
            )
        except Exception as exc:  # noqa: BLE001 - one lane's crash must not hide the others
            outcomes[lane["id"]] = {"stop": "error", "reason": repr(exc), "tickets": []}

    workers = [threading.Thread(target=work, args=(lane,)) for lane in plan["lanes"]]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    closed = close_round(round_dir, incumbent, output, backend=backend, clock=clock)
    body = {
        "round_digest": plan["round_digest"],
        "lanes": {lane_id: outcomes[lane_id] for lane_id in sorted(outcomes)},
        "close": closed,
    }
    write_json(round_dir / "drive.json", body)
    return body


def _drive_lane(round_dir, incumbent, lane, backend, poll_seconds, current) -> dict:
    lane_id = lane["id"]
    work = round_dir / "work" / lane_id
    if not work.exists():
        shutil.copytree(incumbent, work)
    history_path = round_dir / "history" / f"{lane_id}.json"
    history: list[dict] = []
    while True:
        write_json(history_path, history)
        try:
            remaining = seconds_remaining(lane["deadline_utc"], current())
        except BudgetError as exc:
            return _stop("deadline", str(exc), history)
        argv = [
            part.replace("{work}", str(work))
            .replace("{lane}", lane_id)
            .replace("{results}", str(history_path))
            for part in lane["agent"]
        ]
        try:
            finished = subprocess.run(argv, cwd=work, timeout=remaining, check=False)
        except subprocess.TimeoutExpired:
            return _stop("deadline", "agent ran past the lane deadline", history)
        except OSError as exc:
            return _stop("agent_failed", str(exc), history)
        if finished.returncode != 0:
            return _stop("agent_failed", f"agent exited {finished.returncode}", history)
        submitted = submit(round_dir, lane_id, incumbent, work, now=current())
        if not submitted["submitted"]:
            stop = "done" if submitted["reason"] == "unchanged" else "refused"
            return _stop(stop, submitted["reason"], history)
        ticket = submitted["ticket"]
        if any(item["ticket"] == ticket for item in history):
            return _stop("done", "agent resubmitted an earlier change", history)
        result = serve_ticket(round_dir, ticket, incumbent, backend=backend, clock=current)
        while result["status"] == "queued":
            time.sleep(poll_seconds)
            result = serve_ticket(round_dir, ticket, incumbent, backend=backend, clock=current)
        history.append(result)
        if result["status"] != "measured":
            write_json(history_path, history)
            return _stop(result["status"], result.get("reason", ""), history)


def _stop(stop: str, reason: str, history: list[dict]) -> dict:
    return {"stop": stop, "reason": reason, "tickets": [item["ticket"] for item in history]}
