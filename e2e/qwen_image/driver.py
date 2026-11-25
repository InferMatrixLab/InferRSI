"""Opt-in Codex CLI host adapter. Sends exactly request.txt as the sole user turn."""

import json
import queue
import subprocess
import threading
import time
from pathlib import Path

from .retest import git, write


def launch(project, baseline_revision, output, *, executable, model, timeout):
    project, output = Path(project).resolve(), Path(output).resolve()
    head = git(project, "rev-parse", "HEAD").decode().strip()
    if head != baseline_revision:
        raise ValueError("Prepared project is not at the issue's pinned baseline")
    if git(project, "status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError("Prepare a clean, separate Codex project before this test")
    if output.exists() or output.is_relative_to(project):
        raise ValueError("Use a new private output directory outside the project")
    if timeout <= 0:
        raise ValueError("An explicit positive wall-clock budget is required")
    output.mkdir(parents=True)
    prompt = Path(__file__).with_name("request.txt").read_text(encoding="utf-8").strip()
    (output / "request.txt").write_text(prompt + "\n", encoding="utf-8")
    command = [str(executable)] if isinstance(executable, (str, Path)) else list(executable)
    version = subprocess.run([*command, "--version"], check=True,
                             capture_output=True, text=True).stdout.strip()
    argv = [*command, "exec", "--json", "--cd", str(project), "--model", model,
            "--output-last-message", str(output / "final-reply.txt"), "-"]
    started = time.time()
    write(output / "host.json", {
        "client": "Codex CLI", "version": version, "requested_model": model,
        "effective_model": "unknown unless exported by host",
        "baseline_revision": head, "started_at": started, "state": "running",
    })
    events = queue.Queue()
    # Credentials/configuration are inherited by Codex, never inspected or dumped.
    # No bypass flags, added optimization hints, resume prompt or automatic retry.
    with (output / "stderr.log").open("w", encoding="utf-8") as stderr:
        child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=stderr, text=True, encoding="utf-8", errors="replace")

        def consume():
            for line in child.stdout:
                events.put((time.time(), line))
            events.put(None)

        reader = threading.Thread(target=consume, daemon=True)
        reader.start()
        child.stdin.write(prompt)
        child.stdin.close()
        timed_out = False
        sequence = 0
        with (output / "events.jsonl").open("w", encoding="utf-8") as log:
            while True:
                remaining = started + timeout - time.time()
                if remaining <= 0:
                    timed_out = True
                    child.terminate()
                    break
                try:
                    item = events.get(timeout=min(remaining, 1))
                except queue.Empty:
                    continue
                if item is None:
                    break
                at, line = item
                sequence += 1
                log.write(json.dumps({"sequence": sequence, "received_at": at,
                                      "elapsed_seconds": at - started, "raw": line},
                                     ensure_ascii=False) + "\n")
                log.flush()
        try:
            returncode = child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            returncode = child.wait()
    receipt = {"client": "Codex CLI", "version": version, "requested_model": model,
               "baseline_revision": head, "started_at": started, "finished_at": time.time(),
               "elapsed_seconds": time.time() - started, "returncode": returncode,
               "state": "timed_out" if timed_out else "exited",
               "remote_cleanup": "unknown; observer must verify owned remote resources"}
    exported = []
    for line in (output / "events.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            exported.append(json.loads(json.loads(line)["raw"]))
        except (ValueError, TypeError):
            continue
    sessions = [event["thread_id"] for event in exported if event.get("type") == "thread.started"]
    receipt["native_session_ids"] = sessions
    receipt["native_turn_completed"] = (
        len(sessions) == 1 and any(e.get("type") == "turn.completed" for e in exported)
        and not any(e.get("type") in ("turn.failed", "error") for e in exported))
    write(output / "host.json", receipt)
    return receipt


def discover(parent, project, started):
    matches = []
    for path in Path(parent).glob("**/campaign.json"):
        try:
            campaign = json.loads(path.read_text(encoding="utf-8"))
            plan = json.loads(path.with_name("plan.json").read_text(encoding="utf-8"))
            state = json.loads(path.with_name("state.json").read_text(encoding="utf-8"))
            if (campaign.get("managed_optimization") is True and plan["task_source"] == "project"
                    and Path(plan["working_candidate"]).resolve() == Path(project).resolve()
                    and state["started_at"] >= started):
                matches.append(path.parent)
        except (OSError, ValueError, KeyError):
            continue
    if len(matches) != 1:
        raise ValueError("Expected one new campaign for this project; index all attempts")
    return matches[0]
