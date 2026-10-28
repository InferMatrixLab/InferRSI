"""One AB/BA loop for every external scenario, target and backend."""

import json
import subprocess
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from ..infra.artifacts import atomic_write_json as _write_json
from ..infra.targets import repository_identity
from ..runspec import RunSpec
from .evaluation import evaluate
from .reporting import write_report
from .scenarios.external import execute_trial


def run_experiment(
    spec: RunSpec,
    environment: dict,
    *,
    execute: Callable[[tuple[str, ...], Path, Path, float, str | None], dict] = execute_trial,
    snapshot: Callable[[Path, Path | None], dict] = repository_identity,
) -> Path:
    """Run paired commands, preserve evidence and return a unique run directory."""
    spec.validate()
    started = time.monotonic()
    deadline = started + spec.max_minutes * 60
    run_dir = Path(spec.output_dir).resolve() / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:10]
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(run_dir / "run.lock.json", spec.to_dict())
    _write_json(run_dir / "environment.json", environment)
    baseline, candidate, validation = [], [], None
    before, after, source_checks = {}, {}, []
    # No state is claimed until the work that would establish it has finished.
    state, error = None, None

    def event(phase: str, **details: object) -> None:
        record = {"time": datetime.now(timezone.utc).isoformat(), "phase": phase, **details}
        with (run_dir / "events.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        _write_json(
            run_dir / "status.json", {"state": "running", "phase": phase, "run_dir": str(run_dir)}
        )

    def record_status(phase: str, **fields: object) -> None:
        _write_json(
            run_dir / "status.json",
            {
                "run_dir": str(run_dir),
                "elapsed_seconds": time.monotonic() - started,
                "phase": phase,
                **fields,
            },
        )

    repos = {
        "baseline": Path(spec.repo).resolve(),
        "candidate": Path(spec.candidate_repo or spec.repo).resolve(),
    }

    def execute_checked(
        command: tuple[str, ...], label: str, trial_dir: Path, metric_key: str | None
    ) -> dict:
        source_before = snapshot(repos[label], run_dir)
        record = execute(command, repos[label], trial_dir, deadline, metric_key)
        source_after = snapshot(repos[label], run_dir)
        check = {
            "path": str(trial_dir),
            "side": label,
            "before": source_before,
            "after": source_after,
        }
        source_checks.append(check)
        _write_json(trial_dir / "source.json", check)
        return record

    def terminate() -> None:
        """Write the terminal artifacts; a failure here is reported, not hidden."""
        nonlocal after
        try:
            after = {label: snapshot(repo, run_dir) for label, repo in repos.items()}
            _write_json(run_dir / "repositories.final.json", after)
            _write_json(run_dir / "source_checks.json", source_checks)
            identities = list(before.values()) + list(after.values())
            identities.extend(
                identity
                for check in source_checks
                for identity in (check["before"], check["after"])
            )
            known = bool(before) and all(item.get("available") for item in identities)
            unchanged = (
                known
                and all(
                    before[label]["snapshot_hash"] == after[label]["snapshot_hash"]
                    for label in repos
                )
                and all(
                    check["before"]["snapshot_hash"]
                    == check["after"]["snapshot_hash"]
                    == before[check["side"]]["snapshot_hash"]
                    for check in source_checks
                )
            )
            integrity = {
                "verified": bool(unchanged),
                "reason": "Git source snapshots unchanged"
                if unchanged
                else "Git source snapshot unavailable"
                if not known
                else "source changed during experiment",
                "command_checks": len(source_checks),
            }
            result = evaluate(spec, baseline, candidate, validation, integrity)
            if error:
                result["reasons"].append(error)
                result["verdict"] = "INCONCLUSIVE"
            _write_json(run_dir / "evaluation.json", result)
            event("complete", state=state, verdict=result["verdict"])
            record_status(
                "complete", state=state, verdict=result["verdict"], error=error
            )
            write_report(run_dir)
        except KeyboardInterrupt as exc:
            # Interruption during termination is outside the caller's own
            # KeyboardInterrupt handler, so the state must be persisted here:
            # otherwise it stays `running` (interrupted during the final snapshot)
            # or a premature `completed` (interrupted while writing the report).
            record_status(
                "termination",
                state="termination_failed",
                verdict=None,
                error=error,
                requested_state=state,
                termination_error=f"KeyboardInterrupt: {exc or 'interrupted during termination'}",
            )
            raise
        except Exception as exc:
            # The run did not reach a finished state. Every termination failure is
            # recorded, not only I/O-shaped ones: the hook and report paths are
            # caller-supplied, and an escaped RuntimeError would otherwise leave
            # `running` (or a premature `completed`) as the last persisted state.
            record_status(
                "termination",
                state="termination_failed",
                verdict=None,
                error=error,
                requested_state=state,
                termination_error=f"{type(exc).__name__}: {exc}",
            )
            raise

    stopped = None
    try:
        event("source_snapshot")
        before = {label: snapshot(repo, run_dir) for label, repo in repos.items()}
        _write_json(run_dir / "repositories.lock.json", before)
        commands = {"baseline": spec.baseline_command, "candidate": spec.candidate_command}
        for index in range(spec.repetitions):
            for label in ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline"):
                event("measurement", side=label, trial=index + 1)
                record = execute_checked(
                    commands[label],
                    label,
                    run_dir / label / f"trial-{index + 1:03d}",
                    spec.metric_key,
                )
                (baseline if label == "baseline" else candidate).append(record)
                if record["status"] == "cancelled":
                    raise KeyboardInterrupt
                if record["status"] != "completed":
                    stopped = record["status"]
                    break
            if stopped is not None:
                break
        if spec.validation_command is not None and stopped is None:
            event("quality_validation")
            validation = execute_checked(
                spec.validation_command, "candidate", run_dir / "validation", None
            )
            if validation["status"] != "completed":
                stopped = validation["status"]
        elif spec.validation_command is not None:
            validation = {"status": "skipped", "reason": "measurement did not complete"}
        if stopped is None:
            state = "completed"
        else:
            state = (
                "cancelled"
                if stopped == "cancelled"
                else "timeout"
                if stopped == "timeout"
                else "failed"
            )
    except KeyboardInterrupt:
        state, error = "cancelled", "interrupted by user"
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        state, error = "failed", str(exc)
    except BaseException as exc:
        # A hook failure outside the documented error contract still left a run
        # directory. Record the crash truthfully, then let the caller see it.
        event("crashed")
        record_status(
            "crashed", state="crashed", verdict=None, error=f"{type(exc).__name__}: {exc}"
        )
        raise
    terminate()
    return run_dir
