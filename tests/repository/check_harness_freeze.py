"""Replay the component migration's immutable baseline using its installed wheel."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from importlib.metadata import distribution
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/optimization-session/component-freeze"
AUDITED_CLI = """
import json, runpy, sys
from pathlib import Path
log = Path(sys.argv.pop(1))
def audit(event, args):
    if event == "subprocess.Popen":
        with log.open("a", encoding="utf-8") as out:
            out.write(json.dumps(str(args[1])) + "\\n")
sys.addaudithook(audit)
runpy.run_module("inferrsi", run_name="__main__", alter_sys=True)
"""


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(path, pattern="*"):
    return {p.relative_to(path).as_posix(): digest(p) for p in path.rglob(pattern) if p.is_file()}


def unpack(name, destination, manifest):
    archive = FIXTURES / name
    assert digest(archive) == manifest["samples"][name], name
    with zipfile.ZipFile(archive) as packed:
        for member in packed.namelist():
            assert (destination / member).resolve().is_relative_to(destination), member
        packed.extractall(destination)


def cli(root, command, action, *args, expected=0, children=0):
    log = root.parent / "child-processes.jsonl"
    log.write_bytes(b"")
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            AUDITED_CLI,
            str(log),
            *command,
            action,
            "--session",
            str(root),
            *map(str, args),
        ],
        capture_output=True,
        cwd=root.parent,
        timeout=60,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        },
    )
    launches = [json.loads(line) for line in log.read_bytes().splitlines()]
    assert result.returncode == expected, (
        command,
        action,
        result.stdout[-1200:],
        result.stderr[-1500:],
    )
    assert len(launches) == children, (action, launches, children)
    if children:
        assert all("protocol_child.py" in launch for launch in launches), launches
    if expected:
        assert b"cleanup" in (result.stdout + result.stderr).lower()
        return None
    return json.loads(result.stdout)


def ordinary(root, command, packaged):
    original = files(root)
    state = read(root / "state.json")
    assert state["pending"] and not state["rounds"]
    cli(root, command, "status")
    assert files(root) == original
    outcome = cli(root, command, "recover", children=int(packaged))
    assert outcome["completed_rounds"] == 1
    assert outcome["latest_observation"]["assessment"]["verdict"] == "PASS"
    settled = read(root / "state.json")
    assert settled["pending"] is None and len(settled["rounds"]) == 1
    assert settled["deadline"] == state["deadline"]
    if packaged:
        attempt = root / state["pending"]["path"]
        for relative in (
            "protocol-arguments-0001.json",
            "execution/launch-task.json",
            "protocol-assess-0001.json",
        ):
            receipt = read(attempt / relative)
            assert receipt["spawned"] and receipt["pid"] > 0 and receipt["status"] == "completed"
            assert receipt["state"] == "ended" and len(receipt["argv_sha256"]) == 64
        assert read(attempt / "execution/execution.json")["returncode"] == 0
        launches = [
            p
            for p in files(root).keys() - original.keys()
            if Path(p).name.startswith("protocol-") and p.endswith(".json")
        ]
        assert [Path(p).name for p in launches] == ["protocol-assess-0001.json"], launches
        assert (root / "calls.log").read_text().splitlines() == ["2"]
    summary = read(root / "summary.json")
    before_repeat = files(root)
    again = cli(root, command, "recover")
    assert again["latest_observation"] == outcome["latest_observation"]
    after_repeat = files(root)
    assert before_repeat.keys() == after_repeat.keys()
    assert {p for p in before_repeat if before_repeat[p] != after_repeat[p]} <= {"summary.json"}
    after_summary = read(root / "summary.json")
    assert summary.keys() == after_summary.keys()
    assert {k for k in summary if summary[k] != after_summary[k]} <= {"wall_elapsed_seconds"}


def service(root, name, proofs):
    command = ["campaign"]
    original = files(root)
    state = read(root / "state.json")
    events = files(root, "events.jsonl")
    cli(root, command, "status")
    assert files(root) == original
    pending = state["pending"]
    if name == "service-cleanup-pending.zip":
        attempt = root / pending["path"]
        checkpoint = read(attempt / "execution/execution.json")["checkpoint"]
        assert checkpoint["assessment"]["verdict"] == "FAIL" and checkpoint["quality_score"] is None
        stages = [
            json.loads(line)["stage"]
            for line in (attempt / "events.jsonl").read_bytes().splitlines()
        ]
        assert stages.count("measure") == 2 and "quality" not in stages
        for args in (
            [],
            ["--cleanup-receipt", proofs / "wrong-attempt.json"],
            ["--cleanup-receipt", proofs / "wrong-owner.json"],
            ["--cleanup-receipt", proofs / "wrong-attempt-only.json"],
        ):
            cli(root, command, "recover", *args, expected=2)
            assert not (attempt / "observation.json").exists()
            assert files(root) == original
        outcome = cli(root, command, "recover", "--cleanup-receipt", proofs / "cleanup.json")
        obs = outcome["latest_observation"]
        assert (
            obs["attempt_id"] == pending["attempt_id"]
            and obs["assessment"] == checkpoint["assessment"]
        )
        assert (
            read(attempt / "observation.json")["execution"]["checkpoint"]["binding"]
            == checkpoint["binding"]
        )
        assert outcome["completed_rounds"] == 1
    else:
        outcome = cli(root, command, "recover")
        assert outcome["latest_observation"]["assessment"]["verdict"] == "PASS"
        assert outcome["completed_rounds"] == (2 if pending else 1)

    settled = read(root / "state.json")
    accepted = state["accepted_attempt_ids"].copy()
    accounting = state.get("profiling_accounting", {}).copy()
    if name == "service-pending.zip":
        attempt_id = pending["attempt_id"]
        accepted.append(attempt_id)
        execution = read(root / pending["path"] / "execution/execution.json")
        capture = execution["capture"]
        assert capture["id"] == attempt_id and attempt_id not in accounting
        accounting[attempt_id] = {k: capture[k] for k in ("started_at", "elapsed_seconds")}
    assert settled["accepted_attempt_ids"] == accepted
    assert settled["pending"] is None and len(settled["attempts"]) == len(state["attempts"]) + bool(
        pending
    )
    assert settled["deadline"] == state["deadline"]
    assert settled.get("profiling_accounting", {}) == accounting
    if name == "service-cleanup-pending.zip":
        assert len(settled["recovery_events"]) == len(state["recovery_events"]) + 1
    state_digest = digest(root / "state.json")
    again = cli(root, command, "recover")
    assert again["latest_observation"] == outcome["latest_observation"]
    assert digest(root / "state.json") == state_digest
    assert files(root, "events.jsonl") == events


def check_install(manifest, wheel):
    from inferrsi import __file__ as package_file
    from inferrsi.harness.optimization_session import _runtime_identity
    from inferrsi.resources.repository_packs import REPO_TYPES, repository_pack

    package = Path(package_file).resolve().parent
    dist = distribution("inferrsi")
    assert package == dist.locate_file("inferrsi").resolve(), "Install a non-editable wheel"
    assert dist.version == manifest["runtime_version"], (dist.version, manifest["runtime_version"])
    assert _runtime_identity() == read(FIXTURES / "runtime-sources.json"), (
        "Ordinary plan fingerprint differs"
    )
    packs = manifest["repository_packs"]
    assert set(REPO_TYPES) == packs.keys()
    for kind in REPO_TYPES:
        path = package / "harness/data/repo_packs" / kind / "pack.json"
        assert digest(path) == packs[kind] and repository_pack(kind) == read(path)
    with zipfile.ZipFile(wheel) as packed:
        members = [
            n for n in packed.namelist() if n.startswith("inferrsi/") and not n.endswith("/")
        ]
        assert len(members) == manifest["installed_package_files"]
        for name in members:
            assert packed.read(name) == (package.parent / name).read_bytes(), name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel", required=True, type=Path, help="The baseline wheel installed in this interpreter"
    )
    args = parser.parse_args()
    manifest = read(FIXTURES / "manifest.json")
    check_install(manifest, args.wheel)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp).resolve()
        proofs = work / "proofs"
        unpack("cleanup-proofs.zip", proofs, manifest)
        assert files(proofs) == manifest["cleanup_proofs"]
        for name, entry in (
            ("ordinary-packaged.zip", ["benchmarks", "session"]),
            ("ordinary-packaged.zip", ["campaign"]),
            ("ordinary-ab-ba.zip", ["campaign"]),
        ):
            root = work / (name + "-" + entry[0])
            unpack(name, root, manifest)
            ordinary(root, entry, name == "ordinary-packaged.zip")
        for name in ("service-settled.zip", "service-pending.zip", "service-cleanup-pending.zip"):
            root = work / name
            unpack(name, root, manifest)
            service(root, name, proofs)
    print(f"Verified six independent replays with {args.wheel.name} (sha256 {digest(args.wheel)})")


if __name__ == "__main__":
    main()
