"""External command execution and retained trial facts, independent of model and device."""

import json
from collections.abc import Callable
from pathlib import Path

from ..atomic_json import atomic_write_json as _write_json
from ..local_process import execute_command


def execute_trial(
    command: tuple[str, ...],
    cwd: Path,
    trial_dir: Path,
    deadline: float,
    metric_key: str | None,
    *,
    metric: Callable[[dict, str], float] | None = None,
    environment: dict | None = None,
) -> dict:
    """Run one command and retain its record.

    ``metric(document, metric_key)`` is the caller's metric validation. Harness
    reads the result document and records the value or error that validation
    returns; it holds no metric rule of its own.
    """
    if metric_key is not None and metric is None:
        raise TypeError("execute_trial needs the caller's metric validation for metric_key")
    options = {"environment": environment} if environment is not None else {}
    record = execute_command(command, cwd, trial_dir, deadline, **options)
    result_path = Path(record["result_path"])
    if metric_key is not None:
        try:
            document = json.loads(result_path.read_text(encoding="utf-8"))
            record["metric"] = metric(document, metric_key)
        except (OSError, ValueError, TypeError, OverflowError) as exc:
            record["metric_error"] = str(exc)
    _write_json(trial_dir / "execution.json", record)
    return record


def collect_trial_checks(record: dict, keys: tuple[str, ...]) -> dict[str, bool | None]:
    """Snapshot only selected boolean attestations, never arbitrary result data.

    Missing/unreadable/non-boolean fields stay unknown. Adapters own the receipts
    proving these attestations; subprocess success cannot synthesize them.
    """
    checks: dict[str, bool | None] = dict.fromkeys(keys)
    try:
        payload = json.loads(Path(record["result_path"]).read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError, TypeError):
        return checks
    for key in keys:
        value = payload
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value[part]
        if isinstance(value, bool):
            checks[key] = value
    return checks
