"""Fixed, secret-free actor-host qualification. Scripted data, never model calls."""

import argparse
import hashlib
import json
import re
import tempfile
import time
import zipfile
from pathlib import Path

from inferrsi.harness import kv_edit_workbench as workbench
from inferrsi.harness import kv_reclamation as kv
from inferrsi.infra.artifacts import atomic_write_json
from inferrsi.infra.targets import repository_identity
from inferrsi.model import anthropic_edit_agent as edit
from tools import kv_edit_inputs as shared_inputs
from tools import kv_edit_pilot as pilot
from tools import kv_runtime_qualification as runtime
from tools import qualify_kv_actor_cleanup as cleanup
from tools import qualify_kv_reclamation as task

ROOT = Path(__file__).resolve().parents[1]
TASK_PLAN = task.EVIDENCE / "plan/qualification-plan.json"


def checked_plan(path):
    value = pilot._read_json(path)
    if (
        value.get("schema") != "kv-actor-model-free-qualification-v1"
        or task.file_hash(TASK_PLAN) != value["task_plan_sha256"]
        or type(value["qualification_max_seconds"]) is not int
        or not 0 < value["qualification_max_seconds"] <= 600
        or type(value["visible_workload_count"]) is not int
        or not 0 < value["visible_workload_count"] <= 10000
    ):
        raise ValueError("Unsupported actor qualification plan")
    task.checked_plan(TASK_PLAN)  # Includes independent original + supplemental verifier hashes.
    expected = {"SKILL.md", "metadata.json", "references/source-notes.md"}
    if (
        value["knowledge_root"]
        != "src/inferrsi/data/skill_library/repositories/vllm/audit-vllm-kv-lifetimes"
        or set(value["knowledge_files_sha256"]) != expected
    ):
        raise ValueError("Only the explicit complete pinned K owner is supported")
    owner = ROOT / value["knowledge_root"]
    actual_files = {p.relative_to(owner).as_posix() for p in owner.rglob("*") if p.is_file()}
    if actual_files != expected or any(p.is_symlink() for p in owner.rglob("*")):
        raise ValueError("Pinned K owner is not the complete declared regular-file set")
    for name, digest in value["knowledge_files_sha256"].items():
        if task.file_hash(ROOT / value["knowledge_root"] / name) != digest:
            raise ValueError("Pinned K bytes changed")
    return value


def _message(calls):
    return {
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "stop_reason": "tool_use",
        "content": [
            {"type": "tool_use", "id": ident, "name": name, "input": inputs}
            for ident, name, inputs in calls
        ],
        "usage": {
            "input_tokens": 1,
            "output_tokens": 1,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
        "fixture_origin": "scripted software control, not a provider response",
    }


def _scripts(paths, baseline):
    messages = [
        _message([(f"read-{i}", "read_file", {"path": path}) for i, path in enumerate(paths)])
    ]
    for revision in (1, 2):
        messages.append(
            _message(
                [
                    (
                        f"write-{revision}",
                        "write_candidate",
                        {
                            "source": baseline.decode()
                            + f"\n# Scripted revision {revision}; unchanged algorithm.\n"
                        },
                    ),
                    (f"check-{revision}", "run_visible_checks", {}),
                    (f"benchmark-{revision}", "run_visible_benchmark", {}),
                ]
            )
        )
    messages.append(_message([("submit", "submit_candidate", {})]))
    return messages


def _archive(private, output):
    """Public generated controls/K only; never captures environment or gate tokens."""
    archive = output / "raw-evidence.zip"
    names = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(private.rglob("*")):
            if not path.is_file() or path.suffix not in {
                ".json",
                ".log",
                ".py",
                ".md",
                ".html",
                ".svg",
            }:
                continue
            content = kv.read_regular(path, 32 * 1024 * 1024).decode("utf-8", errors="replace")
            content = content.replace(str(ROOT), "<CHECKOUT>")
            content = content.replace(str(private), "<QUALIFICATION_WORK>")
            content = content.replace(str(output), "<PUBLISHED_OUTPUT>")
            content = re.sub(r"/tmp/kv-replay-[A-Za-z0-9_-]+", "<REPLAY_WORK>", content)
            content = re.sub(r"/tmp/kv-tree-probe-[A-Za-z0-9_-]+", "<TREE_PROBE_WORK>", content)
            name = path.relative_to(private).as_posix()
            names.append(name)
            bundle.writestr(name, content)
        bundle.writestr(
            "REDACTIONS.txt",
            "Paths replaced by <CHECKOUT>, <QUALIFICATION_WORK>, "
            "<PUBLISHED_OUTPUT>, <REPLAY_WORK>, <TREE_PROBE_WORK>. No provider transport, "
            "provider key, GitHub token or gate-token capture. All message/usage fixtures "
            "are scripted and establish no real API usage or K efficacy.\n",
        )
    return {"path": archive.name, "sha256": task.file_hash(archive), "files": names}


def visible_receipts(path, artifact, actor_sha256, repetitions, revisions):
    """Independently read back exact current receipts and all expected control checks."""
    events = [
        json.loads(line) for line in kv.read_regular(path, 16 * 1024 * 1024).decode().splitlines()
    ]
    receipts = [
        event["receipt"]
        for event in events
        if event.get("type") == "agent.tool" and "receipt" in event
    ]
    if [(r["revision"], r["kind"]) for r in receipts] != [
        (1, "checks"), (1, "benchmark"), (2, "checks"), (2, "benchmark")
    ] or artifact["revision"] != 2:
        return False
    retained = {
        revision: edit.digest(kv.source_bytes(revisions / f"revision-{revision:04d}/candidate.py"))
        for revision in (0, 1, 2)
    }
    artifact_events = [e for e in events if e.get("type") == "edit.artifact"]
    if [e["revision"] for e in artifact_events] != [0, 1, 2]:
        return False
    for event in artifact_events:
        directory = revisions / f"revision-{event['revision']:04d}"
        metadata = {k: v for k, v in event.items() if k not in {"type", "bytes"}}
        if (
            metadata != pilot._read_json(directory / "receipt.json")
            or event["sha256"] != retained[event["revision"]]
            or event["bytes"] != len(kv.source_bytes(directory / "candidate.py"))
            or event["actor_sha256"] != actor_sha256
            or event["artifact"] != "candidate.py"
            or any(event[k] != artifact[k] for k in ("plan_sha256", "execution_id", "arm"))
        ):
            return False
    for receipt in receipts:
        if (
            receipt["artifact_sha256"] != retained[receipt["revision"]]
            or any(receipt[k] != artifact[k] for k in ("plan_sha256", "execution_id", "arm"))
        ):
            return False
        body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
        if receipt["receipt_sha256"] != edit.fingerprint({**body, "actor_sha256": actor_sha256}):
            return False
        feedback = receipt["feedback"]
        if receipt["kind"] == "checks":
            if feedback["verdict"] != "PASS":
                return False
        elif receipt["kind"] == "benchmark":
            if (
                feedback["verdict"] == "INCONCLUSIVE"
                or feedback["quality_verdict"] != "PASS"
                or len(feedback["baseline_values"]) != repetitions
                or len(feedback["candidate_values"]) != repetitions
            ):
                return False
        else:
            return False
    final = {r["kind"]: r for r in receipts if r["revision"] == artifact["revision"]}
    if set(final) != {"checks", "benchmark"}:
        return False
    return all(
        r["artifact_sha256"] == artifact["sha256"]
        and r["plan_sha256"] == artifact["plan_sha256"]
        and r["execution_id"] == artifact["execution_id"]
        and r["arm"] == artifact["arm"]
        and r["receipt_sha256"] == artifact[field]
        for kind, field in (("checks", "check_receipt"), ("benchmark", "benchmark_receipt"))
        for r in [final[kind]]
    )


def dependencies():
    names = set(pilot.FILES) | {
        "src/inferrsi/model/anthropic_edit_agent.py",
        "src/inferrsi/model/anthropic_agent.py",
        "src/inferrsi/model/request_guard.py",
        "src/inferrsi/model/protocols/metrics.py",
        "src/inferrsi/harness/scenarios/external.py",
        "src/inferrsi/infra/targets/git.py",
        "tools/qualify_kv_edit_actor.py",
        "tools/qualify_kv_actor_cleanup.py",
        "tools/kv_runtime_qualification.py",
        "tools/kv_pilot_admission.py",
        "tools/skill_eval_budget.py",
        "tools/kv_edit_inputs.py",
        "tools/qualify_kv_reclamation.py",
    }
    # Imported package initializers are executable dependencies too, including
    # target identity and transitive runner metric/scenario imports.
    for name in tuple(names):
        for parent in Path(name).parents:
            initializer = parent / "__init__.py"
            if (ROOT / initializer).is_file():
                names.add(initializer.as_posix())
    return {name: task.file_hash(ROOT / name) for name in sorted(names)}


def qualify(plan_path, revision, output):
    plan = checked_plan(plan_path)
    identity = repository_identity(ROOT)
    if (
        not re.fullmatch(r"[0-9a-f]{40}", revision)
        or not identity.get("available")
        or identity["head"] != revision
        or identity["dirty"]
    ):
        raise ValueError("Actor qualification requires the exact clean Git revision")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic() + plan["qualification_max_seconds"]
    result = {
        "schema": "kv-scripted-actor-qualification-v1",
        "revision": revision,
        "snapshot_hash": identity["snapshot_hash"],
        "plan_sha256": task.file_hash(plan_path),
        "qualifier_sha256": task.file_hash(Path(__file__)),
        "dependencies": dependencies(),
        "dependencies_sha256": edit.fingerprint(dependencies()),
        "model_calls": 0,
        "provider_charges_usd": 0,
        "verdict": "INCONCLUSIVE",
        "software_checks_passed": False,
        "scope": "scripted actual-host actor mechanics; NOT a paid A2/A3 or efficacy result",
        "arms": {},
    }
    with tempfile.TemporaryDirectory(prefix="kv-actor-qualification-") as temporary:
        private = Path(temporary)
        try:
            result["cleanup"] = cleanup.qualify(
                private / "cleanup", deadline, plan["descendant_probe_seconds"]
            )
            result["runtime_isolation"] = runtime.qualify(
                private / "runtime",
                deadline,
                root=ROOT,
                independent=task.INDEPENDENT,
                fixtures=task.FIXTURES,
                knowledge_root=ROOT / plan["knowledge_root"],
            )
            traces = task.load_module(
                "fixed_verifier", task.INDEPENDENT / "verifier.py"
            ).load_traces()

            def selected(split):
                return [
                    {k: t[k] for k in ("id", "split", "events", "expected")}
                    for t in traces
                    if t["split"] == split
                ]

            development, hidden = selected("development"), selected("grader")
            workload = task.load_module("fixed_workload", task.FIXTURES / "workload.py")
            oracle = task.load_module("fixed_benchmark", task.EVIDENCE / "validator/benchmark.py")
            baseline = kv.source_bytes(task.FIXTURES / "candidate.py")
            common, prompt, suite = shared_inputs.build_inputs(
                baseline, (task.INDEPENDENT / "CONTRACT.md").read_bytes(), development,
                workload.workload(plan["visible_workload_count"]),
                oracle.benchmark_expected(plan["visible_workload_count"]),
                plan["visible_min_improvement_pct"],
            )
            for arm in ("A2", "A3"):
                root = private / arm
                workspace = root / "workspace"
                workspace.mkdir(parents=True)
                for name, data in common.items():
                    (workspace / name).write_bytes(data)
                if arm == "A3":
                    for name in plan["knowledge_files_sha256"]:
                        target = workspace / "knowledge" / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes((ROOT / plan["knowledge_root"] / name).read_bytes())
                paths = [
                    "task.json",  # First read is identical in both scripted arms.
                    *sorted(shared_inputs.COMMON - {"task.json"}),
                    *(
                        sorted("knowledge/" + n for n in plan["knowledge_files_sha256"])
                        if arm == "A3"
                        else []
                    ),
                ]
                actor = edit.EditPlan(
                    edit.freeze_files(workspace, paths),
                    edit.EditLimits(**plan["actor_limits"]),
                    tuple(t["id"] for t in development),
                    "elapsed_seconds",
                    "seconds",
                    "minimize",
                    "0" * 64,
                )
                config = pilot.prepare_scripted(
                    root / "inputs",
                    workspace,
                    actor,
                    suite,
                    baseline,
                    _scripts(paths, baseline),
                    plan_sha256=result["plan_sha256"],
                    execution_id="scripted-host-qualification",
                    arm=arm,
                    model=plan["model"],
                    spec=plan["client"],
                    prompt=prompt,
                    input_token_ceiling=plan["input_token_ceiling"],
                )
                run = pilot.run_supervised(
                    root / "inputs",
                    workspace,
                    root / "run",
                    min(deadline, time.monotonic() + actor.limits.max_seconds),
                )
                item = {
                    "executor_status": run["execution"]["status"],
                    "worker_status": run["worker"]["status"],
                    "request_completion_known": run["request_completion_known"],
                    "simulated_slots_consumed": run["simulated_slots_consumed"],
                    "actor_sha256": config["actor_sha256"],
                    "common_actor_contract_sha256": shared_inputs.common_actor_contract_sha256(
                        config
                    ),
                    "exposure": config["edit_plan"]["files"],
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                }
                result["arms"][arm] = item
                if run["worker"]["status"] != "completed":
                    item["reason"] = run["worker"].get("reason", "worker_incomplete")
                    continue
                receipt = run["worker"]["artifact"]
                item["visible_workbench_verified"] = visible_receipts(
                    root / "run/executor/stdout.log",
                    receipt,
                    config["actor_sha256"],
                    actor.limits.benchmark_repetitions,
                    root / "run/worker/workbench/revisions",
                )
                source = kv.source_bytes(root / "run/worker/final/candidate.py")
                item["final_artifact_sha256"] = receipt["sha256"]
                item["hidden_correctness"] = workbench.grade_final(
                    source, receipt["sha256"], hidden, root / "post-submission-grading", deadline
                )
                item["two_revision_receipts_retained"] = all(
                    (
                        root / f"run/worker/workbench/revisions/revision-{i:04d}/candidate.py"
                    ).is_file()
                    for i in (0, 1, 2)
                )
            complete = (
                all(
                    a["executor_status"] == "completed"
                    and a["worker_status"] == "completed"
                    and a["request_completion_known"]
                    and a["simulated_slots_consumed"] == 4
                    and a.get("two_revision_receipts_retained")
                    and a.get("visible_workbench_verified")
                    and a.get("hidden_correctness", {}).get("verdict") == "PASS"
                    for a in result["arms"].values()
                )
                and len(result["arms"]) == 2
            )
            result["software_checks_passed"] = (
                complete
                and result["cleanup"]["verdict"] == "PASS"
                and result["runtime_isolation"]["verdict"] == "PASS"
            )
            if result["software_checks_passed"]:
                result["verdict"] = "PASS"
            elif (
                result["cleanup"]["verdict"] == "FAIL"
                or result["runtime_isolation"]["verdict"] == "FAIL"
            ) or any(
                a.get("hidden_correctness", {}).get("verdict") == "FAIL"
                for a in result["arms"].values()
            ):
                result["verdict"] = "FAIL"
        finally:
            try:
                result["raw_evidence"] = _archive(private, output)
            except Exception:
                result.update(
                    verdict="INCONCLUSIVE",
                    software_checks_passed=False,
                    retention_error="raw_evidence_retention_failed",
                )
            after = repository_identity(ROOT)
            result["source_unchanged"] = after.get("available") and identity[
                "snapshot_hash"
            ] == after.get("snapshot_hash")
            if not result["source_unchanged"]:
                result.update(verdict="INCONCLUSIVE", software_checks_passed=False)
            atomic_write_json(output / "qualification.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.plan, args.revision, args.output)
    print(
        json.dumps(
            {
                "verdict": result["verdict"],
                "model_calls": 0,
                "software_checks_passed": result["software_checks_passed"],
            }
        )
    )
    return 0 if result["software_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
