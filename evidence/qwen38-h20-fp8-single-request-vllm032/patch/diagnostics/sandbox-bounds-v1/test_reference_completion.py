"""Reference-completion checks only; no evaluator import or runtime execution."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).parent
    script = (root / "run-synthetic.sbatch").read_text()
    code = script.split("<<'PYREF'\n", 1)[1].split("\nPYREF", 1)[0]
    good = {"completed": True, "signal": "none", "exit_code": 0, "job_id": "42"}
    slurm = "JobId=42 JobState=COMPLETED ExitCode=0:0\n"
    cases = [
        (good, slurm, "0", True),
        ({**good, "completed": False}, slurm, "0", False),
        ({**good, "completed": 1}, slurm, "0", False),
        ({**good, "signal": "TERM", "exit_code": 143}, slurm, "143", False),
        ({**good, "exit_code": False}, slurm, "0", False),
        ({**good, "job_id": "41"}, slurm, "0", False),
        (good, slurm.replace("COMPLETED", "TIMEOUT"), "0", False),
        (good, slurm.replace("0:0", "0:15"), "0", False),
        (good, slurm.replace("JobId=42", "JobId=41"), "0", False),
        (good, slurm + "JobState=COMPLETED\n", "0", False),
        (good, slurm + "JobState=\n", "0", False),
        (good, slurm + "JobId=\n", "0", False),
        (good, slurm + "ExitCode=\n", "0", False),
        (good, slurm, "1", False),
        (None, slurm, "0", False),
        ('{"completed":false,"completed":true,"signal":"none","exit_code":0,"job_id":"42"}', slurm, "0", False),
        ('{"completed":true,"signal":"none","exit_code":143,"exit_code":0,"job_id":"42"}', slurm, "0", False),
        ('{"completed":true,"signal":"none","exit_code":0,"job_id":"41","job_id":"42"}', slurm, "0", False),
    ]
    with tempfile.TemporaryDirectory(prefix="reference-test-", dir=root) as temporary:
        reference = Path(temporary)
        for terminal, scheduler, marker, expected in cases:
            path = reference / "terminal-status.json"
            if terminal is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(terminal if isinstance(terminal, str) else json.dumps(terminal))
            (reference / "slurm-final.private.txt").write_text(scheduler)
            (reference / "exit-code").write_text(marker)
            result = subprocess.run([sys.executable, "-IBO", "-c", code, str(reference), "42"],
                                    capture_output=True, check=False, timeout=5)
            if (result.returncode == 0) != expected:
                raise RuntimeError("Reference completion check mismatch")
    print(json.dumps({"reference_completion_cases": len(cases), "optimized_python": True}))


if __name__ == "__main__":
    main()
