"""Execute argv under a deadline; do not interpret benchmark or quality results."""

import os
import subprocess
import time
from pathlib import Path

from ..processes import _stop_tree, _WindowsJob


def execute_command(command: tuple[str, ...], cwd: Path, trial_dir: Path, deadline: float) -> dict:
    trial_dir.mkdir(parents=True)
    result_path = trial_dir / "result.json"
    argv = [arg.replace("{result}", str(result_path)) for arg in command]
    record = {
        "status": "pending",
        "argv": argv,
        "cwd": str(cwd),
        "returncode": None,
        "result_path": str(result_path),
        "stdout_path": str(trial_dir / "stdout.log"),
        "stderr_path": str(trial_dir / "stderr.log"),
        "metric": None,
        "metric_error": None,
    }
    started, process, windows_job = time.monotonic(), None, None
    try:
        remaining = deadline - started
        if remaining <= 0:
            record.update(
                status="timeout", error="whole-run deadline exhausted before command start"
            )
        else:
            environment = os.environ.copy()
            environment["OMNIRSI_RESULT_PATH"] = str(result_path)
            options = (
                {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                if os.name == "nt"
                else {"start_new_session": True}
            )
            if os.name == "nt":
                windows_job = _WindowsJob()
            with (
                (trial_dir / "stdout.log").open("wb") as stdout,
                (trial_dir / "stderr.log").open("wb") as stderr,
            ):
                process = subprocess.Popen(
                    argv,
                    cwd=cwd,
                    env=environment,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                    **options,
                )
                record["pid"] = process.pid
                record["process_group_id"] = process.pid if os.name != "nt" else None
                if windows_job is not None:
                    windows_job.attach(process)
                try:
                    process.wait(timeout=max(0.001, deadline - time.monotonic()))
                    record.update(
                        status="completed" if process.returncode == 0 else "failed",
                        returncode=process.returncode,
                    )
                except subprocess.TimeoutExpired:
                    _stop_tree(process, windows_job)
                    record.update(
                        status="timeout",
                        returncode=process.returncode,
                        error="whole-run deadline exceeded",
                    )
                except KeyboardInterrupt:
                    _stop_tree(process, windows_job)
                    record.update(
                        status="cancelled",
                        returncode=process.returncode,
                        error="interrupted by user",
                    )
    except (OSError, subprocess.SubprocessError) as exc:
        if process is not None and process.poll() is None:
            _stop_tree(process, windows_job)
        record.update(status="error", error=str(exc))
    finally:
        if windows_job is not None:
            windows_job.close()
        if process is not None and os.name != "nt":
            _stop_tree(process)
        record["elapsed_seconds"] = time.monotonic() - started
    return record
