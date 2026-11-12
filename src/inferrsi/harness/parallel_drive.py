"""Drive one parallel round from a single command, then close it.

Like a round without a cluster, each lane hands in one candidate per round; a
retry belongs to the next round. Each lane gets one worker, all in parallel: copy
the incumbent to ``round_dir/work/<lane>``, run the lane's ``agent`` command
there once, submit the work tree, and serve the ticket until it is no longer
queued. When every lane is done, ``close`` picks the next incumbent.

The agent command runs on the host with the caller's environment; it is not
confined. Placeholders: ``{work}`` is the work tree and ``{lane}`` the lane id.

A lane's outcome is the serve status (``measured``, ``rejected``, ``unsettled``),
``unchanged`` when the agent changed nothing, ``refused`` when submit refused the
change, ``agent_failed``, ``deadline`` or ``error``.
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
    """Prepare, run one attempt on every lane in parallel, close, and write ``drive.json``."""
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
            outcomes[lane["id"]] = _outcome("error", repr(exc))

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
    try:
        remaining = seconds_remaining(lane["deadline_utc"], current())
    except BudgetError as exc:
        return _outcome("deadline", str(exc))
    argv = [part.replace("{work}", str(work)).replace("{lane}", lane_id) for part in lane["agent"]]
    try:
        finished = subprocess.run(argv, cwd=work, timeout=remaining, check=False)
    except subprocess.TimeoutExpired:
        return _outcome("deadline", "agent ran past the lane deadline")
    except OSError as exc:
        return _outcome("agent_failed", str(exc))
    if finished.returncode != 0:
        return _outcome("agent_failed", f"agent exited {finished.returncode}")
    submitted = submit(round_dir, lane_id, incumbent, work, now=current())
    if not submitted["submitted"]:
        status = "unchanged" if submitted["reason"] == "unchanged" else "refused"
        return _outcome(status, submitted["reason"])
    ticket = submitted["ticket"]
    result = serve_ticket(round_dir, ticket, incumbent, backend=backend, clock=current)
    while result["status"] == "queued":
        time.sleep(poll_seconds)
        result = serve_ticket(round_dir, ticket, incumbent, backend=backend, clock=current)
    return _outcome(result["status"], result.get("reason", ""), ticket)


def _outcome(status: str, reason: str, ticket: str | None = None) -> dict:
    return {"status": status, "reason": reason, "ticket": ticket}
