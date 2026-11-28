"""Replay RFC #762 frozen recovery using two independently installed InferRSI wheels.

Run with the repository test dependencies installed. Supply the baseline and
candidate wheel from the review and a new output directory. The output retains
the sessions, Compare arms and before/after-rejection file digests.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from functools import partial
from pathlib import Path


def benchmark_fixture(root):
    library = root / "library"
    task = library / "test-work"
    task.mkdir(parents=True)
    (library / "index.json").write_text(
        json.dumps({"schema_version": 1, "packages": [task.name]}),
        encoding="utf-8",
    )
    (task / "TASK.md").write_text(
        "Synthetic control exercising the real subprocess.\n", encoding="utf-8"
    )
    (task / "baseline.py").write_text("FACTOR = 1\n", encoding="utf-8")
    (task / "optimization.py").write_text(
        "import json\n"
        "def validate_arguments(args):\n    assert not args\n    return {}\n"
        "def arguments(candidate, output, settings):\n"
        "    return [str(candidate), str(output)]\n"
        "def assess(directory, settings, execution):\n"
        "    return json.loads((directory / 'measurement/result.json').read_text())\n",
        encoding="utf-8",
    )
    (task / "benchmark.py").write_text(
        "import json, runpy, sys\nfrom pathlib import Path\n"
        "value = runpy.run_path(sys.argv[1])['FACTOR']\n"
        "with Path('calls.log').open('a') as stream:\n    stream.write(f'{value}\\n')\n"
        "out = Path(sys.argv[2]); out.mkdir()\n"
        "(out/'result.json').write_text(json.dumps({'status':'completed', 'verdict':'PASS', "
        "'score':value}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    return task


_DRIVER = """
import json, sys
from pathlib import Path
location = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(location))
import inferrsi
from inferrsi.apps.cli import main
from inferrsi.benchmark import registry
assert Path(inferrsi.__file__).resolve().is_relative_to(location)
args = sys.argv[3:]
if args[0] == 'interrupt' or args[:2] == ['benchmarks', 'session']:
    registry._library_root = lambda: Path(sys.argv[2])
if args[0] == 'identify':
    print(json.dumps({'version': inferrsi.__version__, 'module': inferrsi.__file__}))
elif args[0] == 'inspect':
    from inferrsi.harness.manager import inspect_session_status
    print(json.dumps(inspect_session_status(Path(args[1]))))
elif args[0] == 'interrupt':
    from inferrsi.harness import executor
    execute = executor.execute_ordinary
    def interrupt(*args, **kwargs):
        execute(*args, **kwargs)
        raise KeyboardInterrupt('controlled interruption after workload receipt')
    executor.execute_ordinary = interrupt
    try:
        main(args[1:])
    except KeyboardInterrupt:
        print(json.dumps({'interrupted': True}))
    else:
        raise AssertionError('expected controlled interruption')
else:
    raise SystemExit(main(args))
"""


def run(root, task, install, *args, code=0):
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            _DRIVER,
            str(install),
            str(task.parent),
            *map(str, args),
        ],
        cwd=root,
        env={k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}},
        capture_output=True,
        encoding="utf-8",
        timeout=90,
    )
    assert result.returncode == code, (args, result.returncode, result.stderr, result.stdout)
    return result.stderr.strip() if code else json.loads(result.stdout)


def snapshot(directory):
    return {
        p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in directory.rglob("*")
        if p.is_file()
    }


def read(directory, relative):
    return json.loads((directory / relative).read_text(encoding="utf-8"))


def lifecycle(root, task, install, other, name, *, compatibility_view):
    invoke = partial(run, root, task)
    session = root / name
    prefix = ("benchmarks", "session")
    invoke(
        install,
        *prefix,
        "start",
        task.name,
        "--session",
        session,
        "--rounds",
        "3",
        "--max-minutes",
        "5",
        "--evaluation-timeout-seconds",
        "15",
        "--condition",
        "synthetic-release-boundary",
        "--evaluation-args",
        "",
    )
    proof = root / "profile.txt"
    proof.write_text(
        "Control scope: independently measured synthetic process invocation.\n", encoding="utf-8"
    )
    invoke(
        install,
        *prefix,
        "diagnose",
        "--session",
        session,
        "--bottleneck",
        "Control measurement overhead",
        "--evidence",
        proof,
    )
    working = session / "work/candidate.py"
    working.write_text("FACTOR = 2\n", encoding="utf-8")
    first = invoke(
        install,
        *prefix,
        "round",
        "--session",
        session,
        "--candidate",
        working,
        "--hypothesis",
        "The workload reports a second test factor",
    )
    assert first["completed_rounds"] == 1
    working.write_text("FACTOR = 3\n", encoding="utf-8")
    assert invoke(
        install,
        "interrupt",
        *prefix,
        "round",
        "--session",
        session,
        "--candidate",
        working,
        "--hypothesis",
        "The workload reports a third test factor",
    )
    initial = snapshot(session)
    state = read(session, "state.json")
    receipt = state["pending"]["path"] + "/execution/execution.json"
    assert read(session, receipt)["status"] == "completed"
    if compatibility_view:
        view = invoke(other, "inspect", session)
        assert view["read_only"] is True and view["completed_rounds"] == 1
        assert view["pending"] == state["pending"] and not view["can_finalize"]
    else:
        assert "Optimization runtime changed" in invoke(
            other, *prefix, "status", "--session", session, code=2
        )
    assert "Optimization runtime changed" in invoke(
        other, *prefix, "recover", "--session", session, code=2
    )
    rejected = snapshot(session)
    assert rejected == initial
    audit = write_json(
        root / f"{name}-trees.json", {"before": initial, "after_rejection": rejected}
    )
    recovered = invoke(install, *prefix, "recover", "--session", session)
    assert recovered["completed_rounds"] == 2 and recovered["best"]["score"] == 3
    rerun = invoke(install, *prefix, "recover", "--session", session)
    final = read(session, "state.json")
    after = snapshot(session)
    assert rerun["completed_rounds"] == 2
    assert final["deadline"] == state["deadline"] and final["rounds"][0] == state["rounds"][0]
    assert final["pending"] is None
    assert initial["plan.json"] == after["plan.json"] and initial[receipt] == after[receipt]
    calls = (session / "calls.log").read_text().splitlines()
    assert calls == ["2", "3"]
    return {
        "prior_round_retained": True,
        "deadline_preserved": True,
        "pending_completed": True,
        "wrong_install_tree_files_unchanged": len(initial),
        "calls": calls,
        "plan_sha256": initial["plan.json"],
        "execution_sha256": initial[receipt],
        "trees": audit,
    }


def compare_preflight(root, task, baseline, candidate):
    invoke = partial(run, root, task)
    output = root / "compare"
    prefix = ("benchmarks", "compare", "--output", output)
    initial = invoke(baseline, *prefix, "--environment-id", "software-control")
    arms = initial["trials"]
    plan = read(output, "experiment.json")
    assert len(arms) == 4 and plan["knowledge_files"]
    for trial in arms:
        runtime = output / trial["workspace"] / "runtime/inferrsi"
        expected = dict(plan["runtime_files"])
        if trial["condition"] == "on":
            expected.update(plan["knowledge_files"])
        assert snapshot(runtime) == expected
        identity = invoke(runtime.parent, "identify")
        assert identity["version"] == invoke(baseline, "identify")["version"]
    on, off = next(
        (on, off)
        for on, off in zip(arms[::2], arms[1::2])
        if on["condition"] == "on" and off["condition"] == "off"
    )
    first = invoke(baseline, *prefix, "--action", "dispatch", "--trial", on["id"])
    assert first["may_create"]
    state_before = (output / "state.json").read_bytes()
    lock = output / ".compare.lock"
    lock.unlink()
    for host_lock in (output / "jobs").rglob("*.lock"):
        host_lock.unlink()
    on_changed = output / on["workspace"] / "runtime/inferrsi/harness/manager/_state.py"
    shutil.copyfile(candidate / "inferrsi/harness/manager/_state.py", on_changed)
    knowledge_file = next(iter(plan["knowledge_files"]))
    injected = output / off["workspace"] / "runtime/inferrsi" / knowledge_file
    injected.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(baseline / "inferrsi" / knowledge_file, injected)
    original = snapshot(output)
    status = invoke(candidate, *prefix, "--action", "status")
    assert status["read_only"] and status["next_action"]["operation"] == "restore_frozen_runtime"
    assert status["runtime_issues"] == {on["id"]: "changed", off["id"]: "changed"}
    assert status["trials"][0]["state"] == "dispatching"
    for action in ("dispatch", "retry", "report"):
        failure = invoke(candidate, *prefix, "--action", action, "--trial", off["id"], code=2)
        assert "Frozen comparison runtime changed" in failure
    rejected = snapshot(output)
    assert rejected == original
    audit = write_json(
        root / "compare-trees.json", {"before": original, "after_rejection": rejected}
    )
    shutil.copyfile(baseline / "inferrsi/harness/manager/_state.py", on_changed)
    injected.unlink()
    status = invoke(candidate, *prefix, "--action", "status")
    assert "read_only" not in status
    assert (
        invoke(candidate, *prefix, "--action", "dispatch", "--trial", on["id"])["may_create"]
        is False
    )
    assert (
        invoke(candidate, *prefix, "--action", "dispatch", "--trial", off["id"], "--parallel")[
            "may_create"
        ]
        is True
    )
    assert (output / "state.json").read_bytes() == state_before
    assert read(output, "experiment.json") == plan
    return {
        "on_off_trials": len(arms),
        "wrong_runtime_tree_files_unchanged": len(original),
        "matching_prior_dispatch_reused": True,
        "matching_other_arm_dispatch": True,
        "new_native_agent_launched": False,
        "trees": audit,
    }


def write_json(path, data):
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def install_wheel(wheel, target):
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "--disable-pip-version-check",
            "--quiet",
            "install",
            "--no-deps",
            "--no-index",
            "--target",
            str(target),
            str(wheel),
        ],
        check=True,
    )
    return {"wheel": wheel.name, "sha256": digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-wheel", type=Path, required=True)
    parser.add_argument("--candidate-wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir()
    baseline = root / "baseline-install"
    candidate = root / "candidate-install"
    baseline_artifact = install_wheel(args.baseline_wheel.resolve(), baseline)
    candidate_artifact = install_wheel(args.candidate_wheel.resolve(), candidate)
    if baseline_artifact["sha256"] == candidate_artifact["sha256"]:
        parser.error("Supply different baseline and candidate wheels")

    task = benchmark_fixture(root)
    result = {
        "baseline": {
            **baseline_artifact,
            "version": run(root, task, baseline, "identify")["version"],
        },
        "candidate": {
            **candidate_artifact,
            "version": run(root, task, candidate, "identify")["version"],
        },
        "baseline_session": lifecycle(
            root, task, baseline, candidate, "baseline", compatibility_view=True
        ),
        "candidate_session": lifecycle(
            root, task, candidate, baseline, "candidate", compatibility_view=False
        ),
        "compare": compare_preflight(root, task, baseline, candidate),
    }
    write_json(root / "summary.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
