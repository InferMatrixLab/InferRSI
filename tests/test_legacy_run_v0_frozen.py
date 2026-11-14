# Old `run` exit codes and `evaluation.json` bytes, frozen before the split.
#
# The goldens in tests/fixtures/legacy_run_v0 were written by the chain as it
# stood before evaluation moved to Benchmark and composition moved to Apps. Each
# scenario enters through the unchanged `inferrsi.cli` `run` command, so the
# same file compares the chain before and after that move.

import contextlib
import io
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from inferrsi.cli import main

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDENS = FIXTURES / "legacy_run_v0"
_WRITE = "import sys; open(sys.argv[1], 'w', encoding='utf-8').write(sys.argv[2])"


def _metric(value: float, **evidence: bool) -> str:
    document = {"metrics": {"latency_ms": value}}
    if evidence:
        document["evidence"] = evidence
    return shlex.join([sys.executable, "-c", _WRITE, "{result}", json.dumps(document)])


def _exit(code: int) -> str:
    return shlex.join([sys.executable, "-c", f"import sys; sys.exit({code})"])


@dataclass(frozen=True)
class Scenario:
    exit_code: int
    baseline: str
    candidate: str
    validation: str | None = _exit(0)
    options: tuple[str, ...] = ()
    executor_error: str | None = None


SCENARIOS = {
    "pass": Scenario(0, _metric(100), _metric(80), options=("--repetitions", "2")),
    "pass-maximize": Scenario(0, _metric(100), _metric(120), options=("--direction", "maximize")),
    "pass-trial-check": Scenario(
        0,
        _metric(100, closed=True),
        _metric(80, closed=True),
        options=("--require-trial-check", "evidence.closed"),
    ),
    "fail-threshold": Scenario(
        1, _metric(100), _metric(80), options=("--min-improvement-pct", "21")
    ),
    "fail-regression": Scenario(1, _metric(100), _metric(120)),
    "fail-quality": Scenario(1, _metric(100), _metric(80), validation=_exit(7)),
    "incomplete-no-validation": Scenario(2, _metric(100), _metric(80), validation=None),
    # A failed gate and missing evidence together: missing evidence decides.
    "incomplete-over-regression": Scenario(2, _metric(100), _metric(120), validation=None),
    "incomplete-over-quality-fail": Scenario(2, _metric(100), _metric(0), validation=_exit(7)),
    "incomplete-metric-contract": Scenario(2, _metric(100), _metric(0)),
    "incomplete-trial-check": Scenario(
        2,
        _metric(100, closed=True),
        _metric(80, closed=False),
        options=("--require-trial-check", "evidence.closed"),
    ),
    "incomplete-run-error": Scenario(
        2, _metric(100), _metric(80), executor_error="executor unavailable"
    ),
}


def run_scenario(name: str, root: Path) -> tuple[int, bytes]:
    """Run one scenario through the CLI; return its exit code and evaluation bytes."""
    scenario = SCENARIOS[name]
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "core.hooksPath=" + str(root / "no-hooks"),
         "-c", "user.name=InferRSI Test", "-c", "user.email=test@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "--quiet", "--allow-empty", "-m", "fixture"],
        check=True,
    )
    arguments = [
        "run", "--repo", str(repo), "--repo-type", "vllm_omni", "--backend", "cpu",
        "--baseline-command", scenario.baseline, "--candidate-command", scenario.candidate,
        "--repetitions", "1", "--max-minutes", "1", "--output-dir", str(root / "runs"),
        *scenario.options,
    ]
    if scenario.validation is not None:
        arguments += ["--validation-command", scenario.validation]
    stream = io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(contextlib.redirect_stdout(stream))
        if scenario.executor_error is not None:
            stack.enter_context(
                patch("inferrsi.execution._execute", side_effect=OSError(scenario.executor_error))
            )
        code = main(arguments)
    printed = json.loads(stream.getvalue())
    run_dir = Path(printed["run_dir"])
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    evaluation = (run_dir / "evaluation.json").read_bytes()
    # The exit code is derived from the status verdict, which mirrors the evaluation.
    assert status["verdict"] == json.loads(evaluation)["verdict"] == printed["status"]["verdict"]
    assert (run_dir / "report.html").is_file()
    return code, evaluation


def _golden(name: str) -> bytes:
    return (GOLDENS / f"{name}.evaluation.json").read_bytes()


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_old_run_keeps_exit_code_and_evaluation_bytes(tmp_path, name):
    code, evaluation = run_scenario(name, tmp_path)
    assert code == SCENARIOS[name].exit_code
    # Text-mode writes use the platform newline; the goldens are stored with LF.
    assert evaluation.replace(b"\r\n", b"\n") == _golden(name)


def test_goldens_cover_each_exit_code_and_incomplete_precedence():
    verdicts = {name: json.loads(_golden(name)) for name in SCENARIOS}
    expected = {0: "PASS", 1: "FAIL", 2: "INCONCLUSIVE"}
    assert {scenario.exit_code for scenario in SCENARIOS.values()} == set(expected)
    for name, scenario in SCENARIOS.items():
        assert verdicts[name]["verdict"] == expected[scenario.exit_code], name
    assert {path.name for path in GOLDENS.glob("*.json")} == {
        f"{name}.evaluation.json" for name in SCENARIOS
    }
    # Failed gates stay listed first in `reasons`, yet missing evidence decides.
    regression = verdicts["incomplete-over-regression"]["reasons"]
    assert "measured gain" in regression[0]
    assert regression[-1] == "quality validation command was not supplied"
    quality = verdicts["incomplete-over-quality-fail"]["reasons"]
    assert quality[0] == "quality validation: failed"
    assert "finite and positive" in quality[1]
    assert verdicts["incomplete-run-error"]["reasons"][-1] == "executor unavailable"
