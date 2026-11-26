"""Run the selected benchmark entry with the installed trial executor."""

import runpy
import sys
from functools import partial
from itertools import count
from pathlib import Path


def _nested_trial(execute_trial, directory, sequence, *args, **kwargs):
    return execute_trial(
        *args, launch_path=directory / f"launch-nested-{next(sequence):04d}.json", **kwargs
    )


def _run_entry(entry: str, arguments: list[str], *, launch_directory: Path | None = None) -> None:
    # Direct-file launch avoids importing a caller's cwd/inferrsi.py. Once the
    # bundled runner is selected, remove its directory so task imports cannot
    # resolve generic names such as project or candidates from Harness.
    runner = Path(__file__).resolve().parent
    sys.path[:] = [path for path in sys.path if Path(path).resolve() != runner]
    # Extended-path launches on Windows may leave cwd before PYTHONPATH. Select
    # this runner's package root explicitly before importing its executor.
    runtime_root = str(runner.parents[2])
    sys.path.insert(0, runtime_root)
    try:
        from inferrsi.harness.executor.trials.external import execute_trial
    finally:
        sys.path.remove(runtime_root)

    if launch_directory is not None:
        execute_trial = partial(_nested_trial, execute_trial, launch_directory, count(1))
    sys.argv = [entry, *arguments]
    sys.path.insert(0, str(Path(entry).parent))
    runpy.run_path(entry, run_name="__main__", init_globals={"execute_trial": execute_trial})


if __name__ == "__main__":
    if sys.argv[1] == "--session-launch-directory":
        _run_entry(sys.argv[3], sys.argv[4:], launch_directory=Path(sys.argv[2]))
    else:
        _run_entry(sys.argv[1], sys.argv[2:])
