"""Bounded, read-only subprocess probes without importing target runtimes."""

import shutil
import subprocess
from pathlib import Path


def probe_command(argv: list[str]) -> dict:
    if not Path(argv[0]).is_file() and shutil.which(argv[0]) is None:
        return {"argv": argv, "returncode": None, "stdout": "", "stderr": "Executable not found"}
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace"
        )
        return {
            "argv": argv,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": argv, "returncode": None, "stdout": "", "stderr": str(exc)}
