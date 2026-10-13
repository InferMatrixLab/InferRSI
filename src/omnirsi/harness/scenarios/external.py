"""External benchmark/validator command scenario, independent of model and device."""

import json
from collections.abc import Callable
from pathlib import Path

from ...infra.artifacts import atomic_write_json as _write_json
from ...infra.executors.local import execute_command
from ..evaluation import read_metric


def execute_trial(
    command: tuple[str, ...],
    cwd: Path,
    trial_dir: Path,
    deadline: float,
    metric_key: str | None,
    *,
    metric_reader: Callable[[dict, str], float] = read_metric,
) -> dict:
    record = execute_command(command, cwd, trial_dir, deadline)
    result_path = Path(record["result_path"])
    if metric_key is not None:
        try:
            record["metric"] = metric_reader(
                json.loads(result_path.read_text(encoding="utf-8")), metric_key
            )
        except (OSError, ValueError, TypeError, OverflowError) as exc:
            record["metric_error"] = str(exc)
    _write_json(trial_dir / "execution.json", record)
    return record
