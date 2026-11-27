"""Corroborate the static session closure using real paths in an installed wheel."""

import json
import subprocess
import sys
import sysconfig
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
SESSION_TESTS = "tests/apps/test_optimization_session.py"
SERVICE_TESTS = "tests/apps/test_project_service_reuse.py"
CASES = {
    "standard": (
        SESSION_TESTS, "final_report_error_preserves_execution_outcome_and_can_be_exported_later",
    ),
    "recover": (SESSION_TESTS, "recovery_counts_an_interrupted_round_once_and_keeps_every_step"),
    "service": (SERVICE_TESTS, "one_service_order_and_independent_final_ignores_workspace"),
}


def observe(case, output):
    import pytest

    from inferrsi.harness.manager import _session
    from inferrsi.harness.manager._runtime import included_module

    path = Path(_session.__file__).resolve()
    assert path.is_relative_to(sysconfig.get_path("purelib")), path
    root = path.parents[2]
    modules, phases = set(), set()
    active = None

    def profile(frame, event, _):
        nonlocal active
        if event == "return" and frame is active:
            active = None
        if event != "call":
            return
        name = frame.f_globals.get("__name__", "")
        function = frame.f_code.co_name
        if (name, function) == ("inferrsi.harness.manager._session", "run_session"):
            active = frame
            phases.add(frame.f_locals["request"].action)
        if (name, function) == ("inferrsi.apps.delivery", "export_bundle"):
            phases.add("export")
        if active is not None and included_module(name):
            modules.add(name)

    filename, node = CASES[case]
    sys.setprofile(profile)
    try:
        result = pytest.main(["-o", "pythonpath=.", f"{filename}::test_{node}"])
    finally:
        sys.setprofile(None)
    assert result == 0, (case, result)
    expected = {"round", "final", "status", "export"}
    if case == "recover":
        expected.add("recover")
    assert expected <= phases, (case, expected - phases)
    observed = {Path(sys.modules[name].__file__).resolve().relative_to(root).as_posix()
                for name in modules}
    assert observed
    Path(output).write_text(json.dumps(sorted(observed)), encoding="utf-8")


def check(cases):
    from inferrsi.harness.manager import session_runtime_identity

    union = set()
    with TemporaryDirectory() as directory:
        for case in cases:
            output = Path(directory) / f"{case}.json"
            subprocess.run([sys.executable, "-I", __file__, "--observe", case, str(output)],
                           cwd=ROOT, check=True)
            union.update(json.loads(output.read_text(encoding="utf-8")))
    missing = union.difference(session_runtime_identity())
    assert not missing, f"Installed session modules outside the frozen identity: {sorted(missing)}"
    print(f"{len(union)} observed session modules covered across {', '.join(cases)}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--observe"]:
        observe(*sys.argv[2:])
    else:
        check(sys.argv[1:] or list(CASES))
