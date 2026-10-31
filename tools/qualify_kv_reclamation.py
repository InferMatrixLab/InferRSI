"""Model-free synthetic task qualification through existing execution primitives.

No provider, submitted artifact, arbitrary command or custom grader is accepted.
The numeric plan is explicit evidence, never a workflow/runtime default.
"""

import argparse
import hashlib
import importlib.util
import json
import platform
import re
import tempfile
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path

from inferrsi.harness import kv_reclamation as kv
from inferrsi.harness.runner import run_experiment
from inferrsi.infra.artifacts import digest, write_json
from inferrsi.infra.targets import repository_identity
from inferrsi.runspec import RunSpec

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/kv_reclamation"
EVIDENCE = ROOT / "evidence/kv-reclamation-20261030"
INDEPENDENT = EVIDENCE / "validator/independent"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retain_raw_evidence(private, output):
    """Retain actual outputs with labelled path redactions, never host environment."""
    archive = output / "raw-evidence.zip"
    files = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(private.rglob("*")):
            if path.suffix not in {".json", ".log", ".html", ".svg"}:
                continue
            data = kv.read_regular(path, 16 * 1024 * 1024).decode("utf-8", errors="replace")
            data = data.replace(str(ROOT), "<CHECKOUT>").replace(str(private), "<RUN_OUTPUT>")
            data = data.replace(str(output), "<PUBLISHED_OUTPUT>")
            data = re.sub(r"/tmp/kv-replay-[A-Za-z0-9_-]+", "<REPLAY_WORK>", data)
            name = path.relative_to(private).as_posix()
            files.append(name)
            bundle.writestr(name, data)
        bundle.writestr("REDACTIONS.txt", "Labelled path redactions: <CHECKOUT>, <RUN_OUTPUT>, "
                        "<PUBLISHED_OUTPUT>, <REPLAY_WORK>. Original paths are omitted. "
                        "No environment dump or provider credentials were captured.\n")
    return {"path": archive.name, "sha256": file_hash(archive), "files": files,
            "scope": "Actual control outputs and runner evidence; labelled path redactions"}


@contextmanager
def retained_workspace(output, result):
    with tempfile.TemporaryDirectory(prefix="kv-qualification-") as temporary:
        private = Path(temporary)
        try:
            yield private
        finally:
            try:
                result["raw_evidence"] = retain_raw_evidence(private, output)
            except (OSError, ValueError):
                result["verdict"] = "INCONCLUSIVE"
                result["software_checks_passed"] = False
                result["retention_error"] = "Raw evidence retention failed"
                raise


def checked_plan(path):
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("schema") != "kv-reclamation-model-free-plan-v1":
        raise ValueError("Unsupported qualification plan")
    for name, actual in (("verifier_freeze_sha256", file_hash(INDEPENDENT / "FREEZE.json")),
                         ("starter_sha256", file_hash(FIXTURES / "candidate.py")),
                         ("workload_sha256", file_hash(FIXTURES / "workload.py"))):
        if actual != plan[name]:
            raise ValueError("Frozen qualification input changed: " + name)
    frozen = json.loads((INDEPENDENT / "FREEZE.json").read_text())
    for name, expected in frozen["files_sha256"].items():
        if file_hash(INDEPENDENT / name) != expected:
            raise ValueError("Independent frozen verifier bytes changed")
    supplement = json.loads((EVIDENCE / "validator/supplemental-freeze.json").read_text())
    if supplement["parent_freeze_sha256"] != plan["verifier_freeze_sha256"]:
        raise ValueError("Benchmark supplement belongs to a different verifier freeze")
    for name, expected in supplement["files_sha256"].items():
        if file_hash(EVIDENCE / "validator" / name) != expected:
            raise ValueError("Independent benchmark supplement bytes changed")
    return plan


def control_sources():
    starter = kv.source_bytes(FIXTURES / "candidate.py").decode("utf-8")

    def replace(old, new):
        if starter.count(old) != 1:
            raise ValueError("Fault injection no longer matches frozen starter")
        return starter.replace(old, new).encode("utf-8")

    return {
        "starter": starter.encode("utf-8"),
        "reference": kv.source_bytes(FIXTURES / "reference.py"),
        "ignore_save": replace('(not lease["save_required"] or lease["saved"])', "True"),
        "ignore_fence": replace('and lease["write_step"] <= self._frontier', "and True"),
        "ignore_generation": replace(
            '(lease["request_id"], lease["generation"]) == (\n'
            '                        event["request_id"], event["generation"])',
            'lease["request_id"] == event["request_id"]'),
        "empty_answers": replace("return reclaimed", "return []"),
        "skip_events": replace("    def apply(self, event):\n",
                               "    def apply(self, event):\n"
                               "        if event.get('op') == 'save_complete':\n"
                               "            return []\n"),
        "missing_output": b"raise SystemExit(0)\n",
        "spoof_output": (b"import json\nprint(json.dumps({'observations': [], 'pending': []}))\n"
                         b"raise SystemExit(0)\n"),
    }


def protected_path_control(output):
    output.mkdir()
    (output / "candidate.py").write_bytes(b"# starter\n")
    (output / "contract.md").write_bytes(b"frozen contract\n")
    frozen = kv.workspace_hashes(output)
    (output / "contract.md").write_bytes(b"tampered\n")
    try:
        kv.capture_artifact(output, frozen)
    except ValueError:
        return True
    return False


def measure(name, before, after, events, expected, plan, output, deadline):
    """Adapter only: the shared runner owns AB/BA, snapshots and adjudication."""
    sources = {"baseline": before, "candidate": after}
    public_records = []

    def execute(command, cwd, trial_dir, runner_deadline, metric_key):
        label = command[1]
        record, actual = kv.invoke(sources[label], {"mode": "benchmark", "events": events},
                                   trial_dir, min(deadline, runner_deadline))
        complete = digest(actual) == digest(expected)
        record["metric"] = record["elapsed_seconds"] if complete else None
        record["metric_error"] = None if complete else "complete trace output mismatch"
        if record["status"] == "completed" and not complete:
            record["status"] = "failed"
        public_records.append({"side": label, "quality_check": metric_key is None,
                               "status": record["status"], "complete_trace": complete,
                               "elapsed_seconds": record["elapsed_seconds"],
                               "source_sha256": hashlib.sha256(sources[label]).hexdigest()})
        write_json(trial_dir / "execution.json", record)
        return record

    timing = plan["timing"]
    spec = RunSpec(
        repo=str(ROOT), repo_type="synthetic-cpu-kv", backend="cpu", mode="code",
        scenario="kv-reclamation-qualification", metric_key="elapsed_seconds", metric_unit="s",
        comparison_scope="whole CPU task command including sandbox and interpreter startup",
        baseline_command=("trusted-kv-control", "baseline"),
        candidate_command=("trusted-kv-control", "candidate"),
        validation_command=("trusted-kv-control", "candidate"),
        repetitions=timing["paired_repetitions"],
        min_improvement_pct=timing["min_improvement_pct"],
        max_minutes=min(timing["comparison_max_seconds"], max(0.001, deadline - time.monotonic()))
        / 60,
        output_dir=str(output / name), agent="scripted-software-control",
    )
    run = run_experiment(spec, {"platform": platform.system(),
                               "scope": "model-free trusted controls"}, execute=execute)
    return {"evaluation": json.loads((run / "evaluation.json").read_text()),
            "records": public_records}


def qualify(plan_path, revision, output):
    plan = checked_plan(plan_path)
    identity = repository_identity(ROOT)
    if (not re.fullmatch(r"[0-9a-f]{40}", revision) or not identity.get("available")
            or identity["head"] != revision):
        raise ValueError("Qualification revision must equal the exact checked-out Git head")
    started = time.monotonic()
    deadline = started + plan["qualification_max_seconds"]
    result = {
        "schema": "kv-reclamation-qualification-v1", "revision": revision,
        "snapshot_hash": identity["snapshot_hash"], "dirty": identity["dirty"],
        "plan_sha256": file_hash(plan_path), "verifier_freeze_sha256": plan[
            "verifier_freeze_sha256"], "controller_sha256": file_hash(Path(kv.__file__)),
        "qualifier_sha256": file_hash(Path(__file__)),
        "benchmark_supplement_sha256": file_hash(EVIDENCE / "validator/supplemental-freeze.json"),
        "python": platform.python_version(), "platform": platform.system(),
        "verdict": "INCONCLUSIVE", "software_checks_passed": False,
        "controls": {}, "measurements": {}, "model_calls": 0, "provider_charges_usd": 0,
        "scope": "Synthetic model-free artifact qualification; actor isolation NOT qualified",
        "chronology": "Independent and plan local freeze preceded reference; public plan posting "
                      "followed reference authorship and preceded all timing; independent "
                      "benchmark supplement frozen after reference authorship and before timing",
    }
    output.mkdir(parents=True, exist_ok=False)
    try:
        with retained_workspace(output, result) as private:
            sentinel = private / "not-mounted-oracle.txt"
            sentinel.write_text("synthetic isolation sentinel\n")
            result["isolation"] = kv.probe_isolation(private / "probe", deadline, [
                str(sentinel), str(INDEPENDENT / "fixtures.json"),
                str(ROOT / "src/inferrsi/data/skill_library/skill-index.json"),
            ])
            sources = control_sources()
            result["control_source_sha256"] = {
                name: hashlib.sha256(source).hexdigest() for name, source in sources.items()}
            verifier = load_module("kv_independent_verifier", INDEPENDENT / "verifier.py")
            traces = verifier.load_traces()
            result["trace_counts"] = {split: sum(t["split"] == split for t in traces)
                                      for split in ("development", "grader")}
            for name in plan["required_good"] + plan["required_bad"]:
                result["controls"][name] = kv.verify_source(
                    sources[name], traces, private / name, deadline, verifier.compare)
            result["protected_edit_rejected"] = protected_path_control(private / "protected")
            record, _ = kv.invoke(b"while True: pass\n", {"mode": "verify", "events": []},
                                  private / "deadline", min(deadline, time.monotonic()
                                                            + plan["deadline_probe_seconds"]))
            result["deadline"] = {"status": record["status"],
                                  "elapsed_seconds": record["elapsed_seconds"],
                                  "process_group_gone": kv.process_group_gone(record)}
            controls = result["controls"]
            good = all(controls[name]["verdict"] == "PASS" for name in plan["required_good"])
            bad = all(controls[name]["verdict"] == "FAIL" for name in plan["required_bad"])
            result["software_checks_passed"] = (good and bad and result["protected_edit_rejected"]
                                                and record["status"] == "timeout"
                                                and result["deadline"]["process_group_gone"])
            if not result["software_checks_passed"]:
                result["verdict"] = ("INCONCLUSIVE" if any(
                    item["verdict"] == "INCONCLUSIVE" for item in controls.values()) else "FAIL")
                return result
            workload = load_module("kv_workload", FIXTURES / "workload.py")
            benchmark = load_module("kv_benchmark_oracle", EVIDENCE / "validator/benchmark.py")
            result["benchmark_oracle_sha256"] = file_hash(EVIDENCE / "validator/benchmark.py")
            events = workload.workload(plan["timing"]["lease_count"])
            expected = benchmark.benchmark_expected(plan["timing"]["lease_count"])
            result["benchmark_input_sha256"] = digest(events)
            result["benchmark_expected_sha256"] = digest(expected)
            for name, after in (("reference", sources["reference"]),
                                ("unchanged", sources["starter"]),
                                ("no_op", sources["starter"])):
                result["measurements"][name] = measure(
                    name, sources["starter"], after, events, expected, plan, private, deadline)
            measured = result["measurements"]
            reference = measured["reference"]["evaluation"]
            negatives = [measured[name]["evaluation"]
                         for name in plan["required_negative_comparisons"]]
            complete = all(e["improvement_pct"] is not None
                           and e["verdict"] != "INCONCLUSIVE" for e in [reference, *negatives])
            passed = (reference["verdict"] == "PASS" and all(
                abs(e["improvement_pct"]) < plan["timing"]["negative_absolute_gain_limit_pct"]
                for e in negatives)) if complete else False
            result["verdict"] = "PASS" if passed else "FAIL" if complete else "INCONCLUSIVE"
    except kv.SandboxUnavailable as error:
        result["error"] = str(error)
        result["software_checks_passed"] = False
    finally:
        after = repository_identity(ROOT)
        result["source_unchanged"] = (after.get("available") and after.get("snapshot_hash")
                                      == identity["snapshot_hash"])
        if not result["source_unchanged"]:
            result["verdict"] = "INCONCLUSIVE"
            result["software_checks_passed"] = False
        result["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "qualification.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = qualify(args.plan, args.revision, args.output)
    print(json.dumps({"qualification_verdict": result["verdict"],
                      "software_checks_passed": result["software_checks_passed"]}))
    # CI checks software controls, not a campaign performance/efficacy threshold.
    # The full qualification verdict must be read separately from a green check.
    return 0 if result["software_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
