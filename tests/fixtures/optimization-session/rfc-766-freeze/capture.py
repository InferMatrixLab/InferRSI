"""Capture the RFC 766 recovery baseline from a normal, installed wheel."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digests(root):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def freeze(source, destination):
    shutil.copytree(source, destination)
    files = digests(source)
    assert digests(destination) == files
    write_json(destination.parent / (destination.name + ".sha256.json"), files)
    return files


class CoordinatorCrash(BaseException):
    """Interrupt just after a real execution receipt has been written."""


def test_capture_ordinary(session, monkeypatch, capsys):
    from inferrsi.apps.cli import main
    from inferrsi.harness import executor
    from tests.apps.test_optimization_session import round_arguments

    command = round_arguments(session, 2)
    prefix = ["benchmarks", "session"]
    target = ["--session", str(session)]
    original = executor.execute_ordinary

    def stop_after_execution(*args):
        original(*args)
        raise CoordinatorCrash()

    with monkeypatch.context() as patch:
        patch.setattr(executor, "execute_ordinary", stop_after_execution)
        with pytest.raises(CoordinatorCrash):
            main(command)
    capsys.readouterr()
    output = Path(os.environ["INFERRSI_RFC_766_EVIDENCE"])
    original_files = freeze(session, output / "ordinary-pending")
    assert main([*prefix, "status", *target]) == 0
    pending = json.loads(capsys.readouterr().out)
    assert digests(session) == original_files
    with pytest.raises(SystemExit) as denied:
        main(command)
    assert denied.value.code == 2
    rejection = capsys.readouterr().err
    assert digests(session) == original_files
    assert main([*prefix, "recover", *target]) == 0
    recovered = json.loads(capsys.readouterr().out)
    assert recovered["completed_rounds"] == 1 and recovered["best"]["score"] == 2
    assert (session / "calls.log").read_text().splitlines() == ["2"]
    assert main([*prefix, "status", *target]) == 0
    settled = json.loads(capsys.readouterr().out)
    assert settled["completed_rounds"] == 1
    write_json(
        output / "ordinary-receipt.json",
        {
            "pending_status": pending,
            "round_while_pending_exit": 2,
            "rejection": rejection,
            "recovered": recovered,
            "settled_status": settled,
            "candidate_process_log": ["2"],
            "settled_sha256": digests(session),
        },
    )


def test_capture_service(campaign, monkeypatch):
    from inferrsi.apps.delivery import project
    from inferrsi.harness.executor.serving import _attempt
    from tests.fixtures.service_reuse import begin, call, rejected, submit

    begin(campaign)
    root = campaign["root"]
    output = Path(os.environ["INFERRSI_RFC_766_EVIDENCE"])
    submit(campaign, version="missing-metric", a=90, missing_metric=True, expected=2)
    assert read_json(root / "plan.json")["schema_version"] == 3
    control = read_json(root / "state.json")
    assert control["state"] == "blocked" and control["pending"] is None
    control_files = freeze(root, output / "service-blocked-no-pending")
    control_status = call(campaign, "status", expected=2)
    _, control_delivery, _ = project(root, export_id="rfc-766-control")
    assert digests(root) == control_files

    original_write = _attempt.atomic_write_json
    checkpoint_path = None

    def stop_after_checkpoint(path, document):
        nonlocal checkpoint_path
        if path == checkpoint_path:
            return
        original_write(path, document)
        if (
            path.name == "execution.json"
            and document.get("checkpoint")
            and not document.get("capture")
        ):
            checkpoint_path = path
            raise CoordinatorCrash()

    with monkeypatch.context() as patch:
        patch.setattr(_attempt, "atomic_write_json", stop_after_checkpoint)
        with pytest.raises(CoordinatorCrash):
            submit(
                campaign, version="interrupted", a=110, retry=control["attempts"][-1]["attempt_id"]
            )
    campaign["capsys"].readouterr()
    state = read_json(root / "state.json")
    pending = state["pending"]
    assert state["state"] == "blocked" and pending
    retained = read_json(checkpoint_path)["checkpoint"]
    attempt_dir = root / pending["path"]
    assert retained["binding"] == read_json(attempt_dir / "request.json")
    assert retained["assessment"]["verdict"] == "FAIL" and retained["quality_score"] is None
    assert not (attempt_dir / "observation.json").exists()
    original_files = freeze(root, output / "service-blocked-pending")
    pending_status = call(campaign, "status", expected=2)
    _, delivery, _ = project(root, export_id="rfc-766-freeze")
    assert control_status["state"] == "blocked" and control_status["pending"] is None
    assert pending_status["state"] == "blocked"
    for key in ("attempt_id", "path", "kind"):
        assert pending_status["pending"][key] == pending[key]
    for bundle in (control_delivery, delivery):
        assert bundle["execution"]["state"] == "blocked"
        assert bundle["acceptance"]["status"] == "not_assessed"
        assert bundle["acceptance"]["delivery_accepted"] is False
        assert bundle["final"] is None
        assert "FINAL_NOT_RUN" in {gap["code"] for gap in bundle["gaps"]}
    assert digests(root) == original_files

    def service_identity(attempt):
        owner = read_json(root / attempt["path"] / "service/owner.json")
        assert owner["domain_empty"] is True and owner["returncode"] == 0
        return {key: owner[key] for key in ("service_id", "pid", "domain_empty")}

    baseline = next(item for item in state["attempts"] if item["kind"] == "baseline")
    owner, other_owner = service_identity(pending), service_identity(baseline)
    assert owner["service_id"] != other_owner["service_id"]
    proof = {
        "attempt_id": pending["attempt_id"],
        "observed_at": time.time(),
        "reason": "Local fixture verified no service owner remained after teardown",
        "cleanup_complete": True,
        "services": [owner],
    }
    cases = {
        "missing": None,
        "other-attempt": {**proof, "attempt_id": baseline["attempt_id"], "services": [other_owner]},
        "wrong-service": {**proof, "services": [other_owner]},
        "wrong-attempt-id": {**proof, "attempt_id": baseline["attempt_id"]},
    }
    command = ["campaign", "recover", "--session", str(root)]
    rejections = {}
    for name, bad_proof in cases.items():
        args = command.copy()
        if bad_proof is not None:
            path = output / (name + ".json")
            write_json(path, bad_proof)
            args.extend(["--cleanup-receipt", str(path)])
        assert rejected(args) == 2
        rejections[name] = campaign["capsys"].readouterr().err
        assert digests(root) == original_files
        assert not (attempt_dir / "observation.json").exists()

    proof_path = output / "matching-cleanup.json"
    write_json(proof_path, proof)
    owners_before = {path.relative_to(root) for path in root.rglob("owner.json")}
    first = call(campaign, "recover", "--cleanup-receipt", proof_path)
    assert first["latest_observation"]["assessment"] == retained["assessment"]
    assert {path.relative_to(root) for path in root.rglob("owner.json")} == owners_before
    first_files = digests(root)
    first_summary = read_json(root / "summary.json")
    repeat = call(campaign, "recover")
    assert repeat["latest_observation"]["assessment"] == retained["assessment"]
    repeat_files = digests(root)
    assert repeat_files.keys() == first_files.keys()
    rewritten = [path for path in first_files if repeat_files[path] != first_files[path]]
    assert set(rewritten) <= {"summary.json"}
    repeat_summary = read_json(root / "summary.json")
    write_json(
        output / "service-receipt.json",
        {
            "control_status": control_status,
            "control_bundle_v1": control_delivery,
            "pending_status": pending_status,
            "bundle_v1": delivery,
            "rejections": rejections,
            "first_recovery": first,
            "repeated_recovery": repeat,
            "settled_sha256": first_files,
            "repeated_sha256": repeat_files,
            "recovery_report_fields_changed": [
                key
                for key in first_summary.keys() | repeat_summary.keys()
                if first_summary.get(key) != repeat_summary.get(key)
            ],
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site", required=True, type=Path, help="isolated normal wheel installation"
    )
    parser.add_argument("--source", required=True, type=Path, help="frozen repository checkout")
    parser.add_argument(
        "--out", required=True, type=Path, help="new evidence directory outside checkout"
    )
    args = parser.parse_args()
    site, source, output = (p.resolve() for p in (args.site, args.source, args.out))
    if any(path.is_relative_to(source) for path in (site, output, Path.cwd().resolve())):
        parser.error(
            "installation, evidence directory and working directory must be outside the checkout"
        )
    output.mkdir(parents=True)
    tempfile.tempdir = str(output)
    sys.path[:0] = [str(site), str(source)]
    os.environ["PYTHONPATH"] = str(site)
    os.environ["INFERRSI_RFC_766_EVIDENCE"] = str(output)
    import inferrsi
    from tests.apps.test_optimization_session import session, task
    from tests.fixtures.service_reuse import campaign

    assert Path(inferrsi.__file__).resolve().is_relative_to(site)
    globals().update(session=session, task=task, campaign=campaign)
    return pytest.main(
        [
            str(Path(__file__).resolve()),
            "--rootdir",
            str(source),
            "-o",
            "pythonpath=",
            "--basetemp",
            str(output / "work"),
            "-q",
        ],
        plugins=[sys.modules[__name__]],
    )


if __name__ == "__main__":
    raise SystemExit(main())
