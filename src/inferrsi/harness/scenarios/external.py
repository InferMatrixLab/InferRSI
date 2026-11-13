"""External benchmark/validator command scenario, independent of model and device."""

import json
from collections.abc import Callable
from pathlib import Path

from ...infra.artifacts import atomic_write_json as _write_json
from ...model.protocols.metrics import read_metric, validate_metric
from ..local_process import execute_command


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
            document = json.loads(result_path.read_text(encoding="utf-8"))
            # A reader is a conversion, not an exemption: the common metric
            # contract applies here, before the value enters the trial record.
            record["metric"] = validate_metric(metric_key, metric_reader(document, metric_key))
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
