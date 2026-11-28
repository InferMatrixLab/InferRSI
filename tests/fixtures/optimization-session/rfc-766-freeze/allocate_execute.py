import hashlib
import importlib.metadata
import json
import os
import sys
import textwrap
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, value):
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def snapshot(root):
    return {
        str(path.relative_to(root)): digest(path.read_bytes()) if path.is_file() else None
        for path in root.rglob("*")
    }


phase, site_arg, wheel_arg, commit = sys.argv[1:]
site = Path(site_arg).resolve()
wheel = Path(wheel_arg).resolve()
run = Path.cwd().resolve()
assert sys.flags.isolated
assert not run.is_relative_to(site.parent / "src")
sys.path.insert(0, str(site))

import inferrsi  # noqa: E402
from inferrsi.harness.api import Harness  # noqa: E402

installed = Path(inferrsi.__file__).resolve()
assert installed.is_relative_to(site)
common = {
    "source_commit": commit,
    "package_version": importlib.metadata.version("inferrsi"),
    "wheel": wheel.name,
    "wheel_sha256": digest(wheel.read_bytes()),
    "harness_source": str(installed),
    "process_pid": os.getpid(),
}
namespace = "rfc-766-cpu-preflight"
receipts = run.parent / "receipts"
context_file = run / "attempt-context.json"
capabilities = ["local-process-tree"]

if phase == "allocate":
    watched = {"subprocess.Popen", "os.system", "os.startfile", "sqlite3.connect"}
    audited = []
    sys.addaudithook(lambda event, args: audited.append(event) if event in watched else None)
    before = snapshot(run)
    assert not before, before
    context = Harness(None, None).allocate(
        run_id="run-rfc766",
        owner=namespace,
        target_request={
            "target_id": "cpu-rfc766",
            "executor_kind": "local_cpu",
            "config_revision": "1",
        },
        deadline_utc="2099-01-01T00:00:00Z",
        resources={"cpu_count": 1, "memory_bytes": None, "required_capabilities": capabilities},
        budget={
            "policy_ref": None,
            "scope_id": "rfc766-cpu",
            "declared_by": namespace,
            "dimensions": [],
            "required_enforcement": [],
        },
    )
    after = snapshot(run)
    assert before == after and not audited, (before, after, audited)
    assert context["request_id"] == context["attempt_id"] and context["run_id"] == "run-rfc766"
    assert context["resources"]["required_capabilities"] == capabilities
    save_json(context_file, context)
    save_json(
        receipts / "allocate.json",
        {
            **common,
            "entrypoint": "inferrsi.harness.api.Harness.allocate",
            "attempt_id": context["attempt_id"],
            "context_sha256": digest(context_file.read_bytes()),
            "attempt_context_keys": sorted(context),
            "exercised_without_target_or_store": True,
            "files_written_by_allocation": 0,
            "audited_target_store_or_process_events": audited,
        },
    )
elif phase == "execute":
    from inferrsi.contracts._harness_errors import PublicError
    from inferrsi.harness.executor import LocalCpuTarget
    from inferrsi.harness.records import RunStore, RunStoreReader

    assert set(snapshot(run)) == {"attempt-context.json"}
    context_bytes = context_file.read_bytes()
    context = json.loads(context_bytes)
    controller = run / "controller"
    controller.mkdir()
    starts = run / "child-pids.txt"
    store = RunStore(run / "store", namespace)
    target = LocalCpuTarget("cpu-rfc766", "1", work_root=run / "work", controller_root=controller)
    harness = Harness(store, target)
    child_code = textwrap.dedent(f"""
        import json
        import os
        from pathlib import Path

        pid = os.getpid()
        with Path({str(starts)!r}).open("a", encoding="utf-8") as marker:
            marker.write(str(pid) + "\\n")
        result = sum(i * i for i in range(1, 10001))
        report = json.dumps({{"pid": pid, "sum_of_squares": result}})
        Path("report.json").write_text(report, encoding="utf-8")
    """).strip()
    spec = {
        **context,
        "schema_version": 1,
        "generation_record_ref": None,
        "prepared_ref": None,
        "protocol_digest": None,
        "operation": None,
        "validation_scope": None,
        "inputs": [],
        "candidate": None,
        "steps": [
            {
                "step_id": "main",
                "runtime_role": "local-python",
                "entrypoint_kind": "executable",
                "entrypoint": sys.executable,
                "entrypoint_revision": "1",
                "expected_code_sha256": None,
                "args": ["-c", child_code],
                "cwd": ".",
                "outputs": [
                    {
                        "role": "report",
                        "path": "report.json",
                        "required": True,
                        "media_type": "application/json",
                        "format_schema": {"name": "json", "revision": "1"},
                    }
                ],
                "timeout_seconds": None,
            }
        ],
        "output_root": f"attempts/{context['attempt_id']}",
        "required_capabilities": capabilities,
    }
    save_json(receipts / "run-spec.json", spec)
    record = harness.execute(spec)
    save_json(receipts / "execution-record.json", record)
    assert record["attempt_id"] == context["attempt_id"]
    assert record["phase"] == "finished", record
    assert record["process_outcome"] == "exited" and record["exit_code"] == 0, record
    assert record["cleanup"]["status"] == "confirmed"
    ref = record["record_ref"]
    assert ref["record_version"] == 1
    reader = RunStoreReader(store.root, namespace)
    report_ref = next(
        entry["artifact"] for entry in record["artifacts"] if entry["role"] == "report"
    )
    report_bytes = reader.open(report_ref).read()
    assert digest(report_bytes) == report_ref["sha256"]
    report = json.loads(report_bytes)
    assert report["sum_of_squares"] == 333383335000
    assert report["pid"] != os.getpid()
    assert starts.read_text().splitlines() == [str(report["pid"])]
    stored = reader.open(ref["artifact"]).read()
    assert digest(stored) == ref["artifact"]["sha256"]
    pinned = harness.read(context["attempt_id"], record_version=ref["record_version"])
    latest = harness.read(context["attempt_id"])
    repeat = harness.execute(spec)
    assert pinned["record_ref"] == latest["record_ref"] == repeat["record_ref"] == ref
    try:
        harness.execute({**spec, "output_root": f"changed/{context['attempt_id']}"})
    except PublicError as error:
        assert error.code == "RequestConflict"
        conflict = error.code
    else:
        raise AssertionError("changed RunSpec under same attempt_id must raise RequestConflict")
    assert starts.read_text().splitlines() == [str(report["pid"])]
    assert reader.open(ref["artifact"]).read() == stored
    assert context_file.read_bytes() == context_bytes
    save_json(
        receipts / "execute.json",
        {
            **common,
            "entrypoint": "inferrsi.harness.api.Harness.execute",
            "attempt_id": context["attempt_id"],
            "context_sha256": digest(context_bytes),
            "child_pid": report["pid"],
            "cpu_result": report["sum_of_squares"],
            "process_outcome": record["process_outcome"],
            "exit_code": record["exit_code"],
            "cleanup": record["cleanup"]["status"],
            "actual_child_starts": len(starts.read_text().splitlines()),
            "record_version": ref["record_version"],
            "record_sha256": digest(stored),
            "report_sha256": digest(report_bytes),
            "latest_pinned_and_replay_match": True,
            "changed_spec": conflict,
        },
    )
else:
    raise ValueError(phase)
