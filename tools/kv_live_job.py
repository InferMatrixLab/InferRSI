"""Fixed main-only KV launcher; disabled until a reviewed authorization is installed.

No dispatch inputs, PR-code checkout, ledger initializer, refund or retry. Ordinary
CI tests use fake transports/stores only. Candidate source never executes on host.
"""

import argparse
import json
import os
import re
import shutil
import time
import urllib.request
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from inferrsi.harness import kv_edit_workbench as workbench
from inferrsi.harness import kv_reclamation as kv
from inferrsi.infra.artifacts import atomic_write_json
from inferrsi.model import anthropic_agent as provider
from tools import kv_edit_inputs as inputs
from tools import kv_live_policy as policy
from tools import kv_live_worker as worker
from tools import kv_pilot_admission as admission
from tools import qualify_kv_actor_cleanup as cleanup
from tools.skill_eval_budget_git import GitHubDailyStore, GitHubGitStore

ROOT = policy.ROOT
COMMON, KNOWLEDGE, KNOWLEDGE_ROOT = inputs.COMMON, inputs.KNOWLEDGE, inputs.KNOWLEDGE_ROOT


class DeadlineGitHub:
    """Existing Git ledger API with bounded single-attempt IO, no new storage protocol."""

    def __init__(self, token, deadline, *, opener=None):
        self.token, self.deadline = token, deadline
        self.opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), policy.NoRedirect())

    def request(self, method, path, data=None):
        allowed = ((method == "GET" and re.fullmatch(
            r"(?:|/git/ref/heads/[A-Za-z0-9/_-]+|/git/(?:commits|trees|blobs)/[0-9a-f]{40}"
            r"|/pulls/[1-9][0-9]*|/actions/(?:runs|artifacts)/[1-9][0-9]*"
            r"|/issues/comments/[1-9][0-9]*)", path))
            or (method == "POST" and path in {"/git/trees", "/git/commits"})
            or (method == "PATCH" and re.fullmatch(
                r"/git/refs/heads/skill-eval-budget/1409534281/(?:[1-9][0-9]*|daily)", path)))
        left = self.deadline - time.monotonic()
        if method == "PATCH" and (type(data) is not dict
                or set(data) != {"sha", "force"} or data["force"] is not False
                or not policy._hex(data["sha"], 40)):
            allowed = False
        if not allowed or left <= 0:
            raise ValueError("Controller API scope/deadline denied")
        request = urllib.request.Request(
            "https://api.github.com/repos/" + policy.REPOSITORY + path, method=method,
            headers={"Authorization": "Bearer " + self.token,
                     "Accept": "application/vnd.github+json", "Content-Type": "application/json",
                     "X-GitHub-Api-Version": "2022-11-28"},
            data=None if data is None else provider.canonical(data).encode())
        try:
            chunks, size = [], 0
            with self.opener.open(request, timeout=min(left, 10)) as response:
                while True:
                    if time.monotonic() >= self.deadline:
                        raise ValueError("deadline")
                    chunk = response.read1(min(65536, 4 * 1024 * 1024 + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > 4 * 1024 * 1024:
                        raise ValueError("size")
            if time.monotonic() >= self.deadline:
                raise ValueError("deadline")
            return json.loads(b"".join(chunks), object_pairs_hook=provider.unique_object)
        except Exception:
            # An uncertain write remains uncertain in the existing CAS adapter.
            # No response body, URL, credential or urllib error text is retained.
            raise ValueError("Controller API response unavailable") from None


def runway(expires_at, now=None):
    now = datetime.now(timezone.utc) if now is None else now
    local = now.astimezone(timezone(timedelta(hours=8)))
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    # Two 600s arms, plus bounded admission/launch margin. Not an extra model allowance.
    if min(expires_at - now.timestamp(), (midnight - local).total_seconds()) < 1320:
        raise ValueError("Insufficient expiry/Shanghai-day runway for the complete pair")


def _stage(plan, output):
    suite = policy.artifact(plan["suite"], limit=16 * policy.MAX_JSON)
    common_bytes, common_protocol = None, None
    for arm in ("A2", "A3"):
        value = plan["actors"][arm]
        config = policy.read_json(ROOT / value["config"]["path"])
        folder, workspace = output / arm / "inputs", output / arm / "workspace"
        folder.mkdir(parents=True)
        workspace.mkdir()
        names = [e["path"] for e in value["workspace"]]
        expected = COMMON | (KNOWLEDGE if arm == "A3" else set())
        if set(names) != expected or len(names) != len(expected):
            raise ValueError("Actor exposure differs from the fixed A2/A3 allowlist")
        staged = {}
        for entry in value["workspace"]:
            if type(entry) is not dict or set(entry) != {"path", "source"}:
                raise ValueError("Wrong exposure record")
            name = policy.relative(entry["path"])
            source = entry["source"]
            if name in KNOWLEDGE and source["path"] != KNOWLEDGE_ROOT + name[len("knowledge/"):]:
                raise ValueError("Knowledge export is not the complete nominated owner")
            if name == "candidate.py" and source["path"] != (
                    "tests/fixtures/kv_reclamation/candidate.py"):
                raise ValueError("Candidate starter differs from qualified task")
            if name == "CONTRACT.md" and source["path"] != (
                    "evidence/kv-reclamation-20261030/validator/independent/CONTRACT.md"):
                raise ValueError("Neutral contract changed")
            data = policy.artifact(source)
            path = workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            staged[name] = data
        common = {name: staged[name] for name in COMMON}
        if common_bytes is not None and common != common_bytes:
            raise ValueError("A2/A3 common workbench bytes differ")
        common_bytes = common
        suite_data = workbench.VisibleSuite(suite).read()
        expected_common, expected_prompt, _ = inputs.build_inputs(
            staged["candidate.py"], staged["CONTRACT.md"], suite_data["development"],
            suite_data["benchmark_events"], suite_data["benchmark_expected"],
            suite_data["min_improvement_pct"])
        if common != expected_common or config["prompt"] != expected_prompt:
            raise ValueError("Actor inputs differ from the shared qualified public workbench")
        protocol = {k: config[k] for k in ("model", "client", "prompt", "input_token_ceiling")}
        protocol["edit_plan"] = {k: v for k, v in config["edit_plan"].items()
                                 if k not in {"files", "callbacks_sha256"}}
        if common_protocol is not None and protocol != common_protocol:
            raise ValueError("A2/A3 tool/metric/prompt limits differ")
        common_protocol = protocol
        edit_plan = worker.scripted._plan(config["edit_plan"])
        expected_config = worker.configuration(workspace, edit_plan, workbench.VisibleSuite(suite),
            staged["candidate.py"], arm=arm, model=plan["provider"]["model"]["name"],
            spec=plan["provider"]["client"], prompt=config["prompt"])
        if provider.canonical(config) != provider.canonical(expected_config):
            raise ValueError("Frozen worker config differs from staged actor identity")
        atomic_write_json(folder / "worker.json", config)
        (folder / "suite.json").write_bytes(suite)
        (folder / "baseline.py").write_bytes(staged["candidate.py"])
        atomic_write_json(folder / "binding.json", {"plan_sha256": policy.fingerprint(plan),
                                                   "execution_id": plan["execution_id"]})
        worker.checked_inputs(folder)


def replay_preflight(output, deadline):
    """Same-host fixed tool replay, with response DATA and no provider transport.

    Rewrites the starter itself (not a hidden solution), checks/benchmarks that
    exact revision and submits it. A failed speed gate is valid feedback, not a
    reason to discard or rerun this mechanical qualification.
    """
    results = {}
    for arm in ("A2", "A3"):
        config, plan, suite, baseline = worker.checked_inputs(output / arm / "inputs")
        root = output / "preflight/replay" / arm
        root.mkdir(parents=True)
        workspace = root / "workspace"
        shutil.copytree(output / arm / "workspace", workspace)

        def call(name, inputs, number):
            return {"type": "tool_use", "id": f"replay-{number}", "name": name, "input": inputs}

        def response(content):
            return {"type": "message", "role": "assistant", "model": config["model"],
                    "stop_reason": "tool_use", "content": content,
                    "usage": {"input_tokens": 1, "output_tokens": 1,
                              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}

        scripts = [response([call("read_file", {"path": "task.json"}, 1)]),
            response([call("write_candidate", {"source": baseline.decode()}, 2),
                      call("run_visible_checks", {}, 3), call("run_visible_benchmark", {}, 4)]),
            response([call("submit_candidate", {}, 5)])]
        worker.scripted.prepare_scripted(root / "inputs", workspace, plan, suite, baseline,
            scripts, plan_sha256=config["plan_sha256"], execution_id=config["execution_id"],
            arm=arm, model=config["model"], spec=config["client"], prompt=config["prompt"],
            input_token_ceiling=config["input_token_ceiling"])
        result = worker.scripted.run_supervised(root / "inputs", workspace, root / "run", deadline)
        if (result["worker"].get("status") != "completed"
                or result["execution"].get("status") != "completed"
                or not result["request_completion_known"]
                or result["simulated_slots_consumed"] != 3
                or kv.source_bytes(root / "run/worker/final/candidate.py") != baseline):
            raise ValueError("Same-host scripted tool replay incomplete")
        results[arm] = {"verdict": "PASS", "model_calls": 0,
                        "artifact_sha256": policy.sha(baseline), "scripted_requests": 3}
    return results


def runtime_preflight(output, deadline, plan):
    """Recheck actual mounted runtime/K/oracle isolation; hosted evidence is not a bypass."""
    from tools import kv_runtime_qualification
    receipt = policy.validate_qualification(plan)
    result = kv_runtime_qualification.qualify(output, deadline, root=ROOT,
        independent=ROOT / "evidence/kv-reclamation-20261030/validator/independent",
        fixtures=ROOT / "tests/fixtures/kv_reclamation", knowledge_root=ROOT / KNOWLEDGE_ROOT)
    qualified = receipt["runtime_isolation"]
    profile_source = receipt["dependencies"]["src/inferrsi/harness/skill_eval_engineering.py"]
    if (result.get("verdict") != "PASS"
            or not policy._hex(result.get("inventory_sha256"))
            or not policy._hex(qualified.get("inventory_sha256"))
            or not policy._hex(profile_source)
            or result.get("mount_count") != qualified.get("mount_count")):
        raise ValueError("Same-host runtime/profile differs from hosted actor qualification")
    # Inventory hashing is sensitive-set dependent, not a portable host fingerprint.
    # The exact sandbox source/profile is bound by the canonical qualification
    # closure; independently require this host's full inventory/probe PASS.
    return {**result, "qualified_inventory_sha256": qualified["inventory_sha256"],
            "profile_source_sha256": profile_source}


def prepare(output):
    if os.environ.get(provider.KEY_ENV):
        raise ValueError("Preparation must precede provider-secret injection")
    captured = {}
    def capture(number):
        comment = policy.fetch_comment(number)
        captured.update({"id": comment["id"], "body": comment["body"],
                         "issue_url": comment["issue_url"],
                         "user": {k: comment["user"][k] for k in ("login", "type")}})
        return comment
    authorization, locator = policy.frozen_authorization(fetch=capture)
    plan = authorization["plan"]
    revision, run_id = policy.runtime()
    runway(plan["expires_at"])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    atomic_write_json(output / "authorization.json", captured)
    _stage(plan, output)
    deadline = time.monotonic() + 120
    isolation = kv.probe_isolation(output / "preflight/isolation", deadline,
        [str(ROOT), str(output / "A2/inputs"), str(output / "A3/workspace")])
    descendants = cleanup.qualify(output / "preflight/cleanup", deadline, 3)
    if descendants["verdict"] != "PASS":
        raise ValueError("Same-host actor cleanup qualification incomplete")
    runtime_profile = runtime_preflight(output / "preflight/runtime", deadline, plan)
    replay = replay_preflight(output, deadline)
    receipt = {"schema": "kv-live-prepared-v1", "implementation_sha": revision,
               "run_id": run_id, "plan_sha256": authorization["plan_sha256"],
               "locator_sha256": policy.fingerprint(locator),
               "isolation": isolation, "cleanup": descendants, "replay": replay,
               "runtime_profile": runtime_profile,
               "inputs": kv.workspace_hashes(output)}
    atomic_write_json(output / "prepared.json", receipt)
    return receipt


def execute(output, *, api=None, stores=None, launch=worker.run_supervised):
    output = Path(output)
    authorization, locator = policy.frozen_authorization()
    plan = authorization["plan"]
    revision, run_id = policy.runtime()
    prepared = policy.read_json(output / "prepared.json")
    if (prepared["schema"] != "kv-live-prepared-v1"
            or prepared["implementation_sha"] != revision or prepared["run_id"] != run_id
            or prepared["plan_sha256"] != authorization["plan_sha256"]
            or prepared["locator_sha256"] != policy.fingerprint(locator)
            or prepared["cleanup"]["verdict"] != "PASS"
            or prepared["runtime_profile"]["verdict"] != "PASS"
            or set(prepared["replay"]) != {"A2", "A3"}
            or any(v.get("verdict") != "PASS" or v.get("model_calls") != 0
                   for v in prepared["replay"].values())):
        raise ValueError("Prepared exact source/authorization/host identity changed")
    current = kv.workspace_hashes(output)
    current.pop("prepared.json", None)
    if current != prepared["inputs"]:
        raise ValueError("Prepared inputs changed before admission")
    runway(plan["expires_at"])
    # Only the existing named injected key is used. Never inspect secret files or env dumps.
    safe = provider.execution_environment({provider.KEY_ENV: os.environ.get(provider.KEY_ENV)})
    api = api or DeadlineGitHub(os.environ["GITHUB_TOKEN"], time.monotonic() + 120)
    root_policy = policy.policy(plan, revision)

    def check_current(value):
        if value != root_policy:
            return False
        fresh = policy.frozen_authorization(fetch=lambda n: api.request(
            "GET", f"/issues/comments/{n}"))
        if fresh != (authorization, locator):
            return False
        policy.verify_live(api, plan, revision, run_id)
        return True

    if stores is None:
        stores = (GitHubDailyStore(api, policy.DailyLedgerAnchor(
            key=policy.budget.DailyKey(policy.REPOSITORY_ID), **plan["daily_ledger"])),
            GitHubGitStore(api, policy.LedgerAnchor(key=root_policy.key, **plan["ledger"])))
    summary = {"schema": "kv-live-execution-v1", "implementation_sha": revision,
               "run_id": run_id, "plan_sha256": authorization["plan_sha256"],
               "execution_id": plan["execution_id"], "charge_pr": plan["charge_pr"],
               "charge_head": plan["charge_head"],
               "reservation_upper_bound_usd": "162.72", "reserved_usd": None,
               "admission_outcome": "pending_durable_state_unknown_no_retry",
               "actual_cost_usd": None,
               "arms": {arm: {"status": "not_started", "request_completion_known": False,
                              "slots_consumed": 0} for arm in plan["arm_order"]}}
    atomic_write_json(output / "execution.json", summary)
    try:
        session = admission.admit(root_policy, *stores, check_current=check_current)
    except BaseException:
        # Failed admission can have written a partial/uncertain durable claim.
        # Preserve identity for no-secret grading, but never assert zero spend.
        summary["admission_outcome"] = "not_granted_durable_state_unknown_no_retry"
        atomic_write_json(output / "execution.json", summary)
        raise
    summary.update(admission_outcome="granted", reserved_usd="162.72")
    atomic_write_json(output / "execution.json", summary)
    try:
        for arm in plan["arm_order"]:
            summary["arms"][arm] = {"status": "launching_or_interrupted",
                "request_completion_known": False, "slots_consumed": None}
            atomic_write_json(output / "execution.json", summary)
            deadline = time.monotonic() + 600
            api.deadline = deadline
            result = launch(output / arm / "inputs", output / arm / "workspace",
                output / arm / "run", deadline, admission=session, key=safe[provider.KEY_ENV])
            summary["arms"][arm] = {"status": result["worker"].get("status", "missing"),
                "request_completion_known": result["request_completion_known"],
                "slots_consumed": result["slots_consumed"]}
            atomic_write_json(output / "execution.json", summary)
            if not result["request_completion_known"]:
                break
    finally:
        session.close()
    return summary


def _validate_feedback(receipt, config, arm, execution):
    fields = {"plan_sha256", "execution_id", "arm", "artifact_sha256", "revision",
              "kind", "feedback", "receipt_sha256"}
    if (type(receipt) is not dict or set(receipt) != fields or receipt["arm"] != arm
            or receipt["plan_sha256"] != execution["plan_sha256"]
            or receipt["execution_id"] != execution["execution_id"]
            or receipt["kind"] not in {"checks", "benchmark"}
            or type(receipt["revision"]) is not int or not 0 <= receipt["revision"] <= 8
            or not policy._hex(receipt["artifact_sha256"])):
        raise ValueError("Wrong visible receipt identity")
    value = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    if receipt["receipt_sha256"] != policy.fingerprint({**value,
                                                       "actor_sha256": config["actor_sha256"]}):
        raise ValueError("Visible feedback digest changed")
    worker.edit._feedback(receipt["kind"], receipt["feedback"],
                          worker.scripted._plan(config["edit_plan"]))


def _validate_submission(root, receipt, source, config, arm, execution):
    fields = {"plan_sha256", "execution_id", "arm", "artifact", "revision", "sha256",
              "actor_sha256", "check_receipt", "benchmark_receipt"}
    if (type(receipt) is not dict or set(receipt) != fields or receipt["arm"] != arm
            or receipt["plan_sha256"] != execution["plan_sha256"]
            or receipt["execution_id"] != execution["execution_id"]
            or receipt["artifact"] != "candidate.py" or type(receipt["revision"]) is not int
            or not 0 <= receipt["revision"] <= 8
            or receipt["actor_sha256"] != config["actor_sha256"]
            or receipt["sha256"] != policy.sha(source)):
        raise ValueError("Wrong final submission identity")
    revision = root / "revisions" / f"revision-{receipt['revision']:04d}"
    expected = {k: v for k, v in receipt.items() if k not in {"check_receipt", "benchmark_receipt"}}
    if (policy.read_json(revision / "receipt.json", 16384) != expected
            or kv.source_bytes(revision / "candidate.py") != source):
        raise ValueError("Final source differs from retained revision")
    found = set()
    for number in range(1, 13):
        path = root / "feedback" / f"{number:04d}.json"
        if not path.exists():
            continue
        feedback = policy.read_json(path, 8192)
        _validate_feedback(feedback, config, arm, execution)
        field = "check_receipt" if feedback["kind"] == "checks" else "benchmark_receipt"
        if (feedback["revision"] == receipt["revision"]
                and feedback["artifact_sha256"] == receipt["sha256"]
                and feedback["receipt_sha256"] == receipt[field]):
            found.add(field)
    if found != {"check_receipt", "benchmark_receipt"}:
        raise ValueError("Missing exact current-revision visible receipts")


def _public_evidence(root, destination, arm, execution):
    """Bounded structured revision/feedback only; raw logs are never publication inputs."""
    result = {"revisions": [], "feedback": [], "status": "incomplete"}
    try:
        config = policy.read_json(root.parents[1] / "inputs/worker.json")
    except (OSError, ValueError):
        return result
    for revision in range(9):
        source = root / "workbench/revisions" / f"revision-{revision:04d}"
        try:
            receipt = policy.read_json(source / "receipt.json", 16384)
            data = kv.source_bytes(source / "candidate.py")
            fields = {"plan_sha256", "execution_id", "arm", "artifact", "revision",
                      "sha256", "actor_sha256"}
            if (set(receipt) != fields or receipt["arm"] != arm
                    or receipt["plan_sha256"] != execution["plan_sha256"]
                    or receipt["execution_id"] != execution["execution_id"]
                    or receipt["actor_sha256"] != config["actor_sha256"]
                    or receipt["artifact"] != "candidate.py" or receipt["revision"] != revision
                    or receipt["sha256"] != policy.sha(data)
                    or not policy._hex(receipt["actor_sha256"])):
                raise ValueError("Wrong revision identity")
            target = destination / "revisions" / f"revision-{revision:04d}"
            target.mkdir(parents=True)
            (target / "candidate.py").write_bytes(data)
            atomic_write_json(target / "receipt.json", receipt)
            result["revisions"].append({"revision": revision, "sha256": policy.sha(data)})
        except (OSError, ValueError, KeyError, TypeError, provider.AgentError):
            continue
    for number in range(1, 13):
        try:
            receipt = policy.read_json(root / "feedback" / f"{number:04d}.json", 8192)
            _validate_feedback(receipt, config, arm, execution)
            (destination / "feedback").mkdir(parents=True, exist_ok=True)
            atomic_write_json(destination / "feedback" / f"{number:04d}.json", receipt)
            result["feedback"].append({"number": number, "sha256": policy.fingerprint(receipt)})
        except (OSError, ValueError, KeyError, TypeError, provider.AgentError):
            continue
    if result["revisions"] and result["feedback"]:
        result["status"] = "retained"
    return result


def package(output):
    """Fixed bounded public projection. Never copy raw worker/provider logs or private paths."""
    output = Path(output)
    public = output / "public"
    public.mkdir(parents=True, exist_ok=False)
    try:
        # Public bytes already verified before preparation; never credentials.
        captured = policy.read_json(output / "authorization.json")
        policy.frozen_authorization(fetch=lambda _: captured, now=0)
        atomic_write_json(public / "authorization.json", captured)
    except (OSError, ValueError, KeyError, TypeError):
        pass  # Missing authorization is explicit INCONCLUSIVE in the no-spend grader.
    execution = (policy.read_json(output / "execution.json")
                 if (output / "execution.json").is_file() else {})
    summary = {"schema": "kv-live-bundle-v1", "execution": execution, "artifacts": {},
               "requests": {}, "evidence": {}}
    for arm in ("A2", "A3"):
        try:
            supervision = policy.read_json(output / arm / "run/supervision.json")
            requests = supervision["completions"]
            if type(requests) is not list or len(requests) > 8:
                raise ValueError("Wrong request count")
            safe = []
            for entry in requests:
                raw = entry["usage"]
                if raw is not None:
                    provider.token_usage(raw)
                grant = entry["grant"]
                if (grant["arm"] != arm or grant["plan_sha256"] != execution["plan_sha256"]
                        or not policy._hex(grant["request_sha256"])):
                    raise ValueError("Wrong completion identity")
                safe.append({"slot": grant["slot"], "request_sha256": grant["request_sha256"],
                    "status": "known" if raw is not None else "unresolved",
                    "usage": None if raw is None else {k: raw[k] for k in ("input_tokens",
                              "output_tokens", "cache_read_input_tokens",
                              "cache_creation_input_tokens")}})
            summary["requests"][arm] = safe
        except (OSError, ValueError, KeyError, TypeError, provider.AgentError):
            summary["requests"][arm] = []
    for arm in ("A2", "A3"):
        root = output / arm / "run/worker"
        summary["evidence"][arm] = _public_evidence(root, public / arm, arm, execution)
        try:
            result = policy.read_json(root / "result.json")
            if result.get("status") != "completed":
                raise ValueError("not submitted")
            receipt = policy.read_json(root / "final/receipt.json", 16384)
            data = kv.source_bytes(root / "final/candidate.py")
            if (receipt["sha256"] != policy.sha(data) or receipt["arm"] != arm
                    or receipt["plan_sha256"] != execution["plan_sha256"]):
                raise ValueError("wrong final artifact")
            config = policy.read_json(output / arm / "inputs/worker.json")
            _validate_submission(public / arm, receipt, data, config, arm, execution)
            (public / arm).mkdir(exist_ok=True)
            (public / arm / "candidate.py").write_bytes(data)
            atomic_write_json(public / arm / "receipt.json", receipt)
            summary["artifacts"][arm] = {"status": "submitted", "sha256": policy.sha(data),
                                         "receipt_sha256": policy.fingerprint(receipt)}
        except (OSError, ValueError, KeyError, TypeError, provider.AgentError):
            summary["artifacts"][arm] = {"status": "missing_or_invalid"}
    atomic_write_json(public / "bundle.json", summary)
    return summary


def _grade_rejected(output, reason, plan_sha256=None):
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema": "kv-live-final-grade-v1", "plan_sha256": plan_sha256,
              "scope": "final input identity unavailable; no candidate evaluation or spending",
              "arms": {arm: {"verdict": "INCONCLUSIVE", "reason": reason}
                       for arm in ("A2", "A3")}}
    atomic_write_json(output / "grade.json", result)
    return result


def grade(bundle, output):
    """Separate no-secret hidden grade of immutable final bytes; never model feedback."""
    if os.environ.get(provider.KEY_ENV) or os.environ.get("GITHUB_TOKEN"):
        raise ValueError("Final grading must run without injected provider/GitHub credentials")
    # Revocation/expiry stops spending, not offline grading of already captured
    # public bytes. The checked-in immutable locator still verifies exact identity.
    bundle, output = Path(bundle), Path(output)
    try:
        captured = policy.read_json(bundle / "authorization.json")
        authorization, _ = policy.frozen_authorization(fetch=lambda _: captured, now=0)
    except (OSError, ValueError, KeyError, TypeError):
        return _grade_rejected(output, "missing_or_invalid_authorization")
    plan = authorization["plan"]
    try:
        metadata = policy.read_json(bundle / "bundle.json")
    except (OSError, ValueError):
        return _grade_rejected(output, "missing_or_invalid_bundle", authorization["plan_sha256"])
    if (type(metadata) is not dict or metadata.get("schema") != "kv-live-bundle-v1"
            or type(metadata.get("execution")) is not dict
            or metadata.get("execution", {}).get("plan_sha256") != authorization["plan_sha256"]
            or metadata["execution"].get("run_id") != os.environ.get("GITHUB_RUN_ID")
            or metadata["execution"].get("implementation_sha") != os.environ.get("GITHUB_SHA")
            or metadata["execution"].get("execution_id") != plan["execution_id"]
            or metadata["execution"].get("charge_pr") != plan["charge_pr"]
            or metadata["execution"].get("charge_head") != plan["charge_head"]):
        return _grade_rejected(output, "invalid_execution_identity", authorization["plan_sha256"])
    output.mkdir(parents=True, exist_ok=False)
    hidden = json.loads(policy.artifact(plan["hidden_traces"], limit=16 * policy.MAX_JSON))
    suite = workbench.VisibleSuite(policy.artifact(plan["final_suite"], limit=16 * policy.MAX_JSON))
    result = {"schema": "kv-live-final-grade-v1", "plan_sha256": authorization["plan_sha256"],
              "scope": "one synthetic pair; hidden semantics and nonheldout task timing",
              "arms": {}}
    for arm in plan["arm_order"]:
        try:
            entry = metadata["artifacts"][arm]
            source = kv.source_bytes(bundle / arm / "candidate.py")
            receipt = policy.read_json(bundle / arm / "receipt.json", 16384)
            config = policy.read_json(ROOT / plan["actors"][arm]["config"]["path"])
            if (entry["status"] != "submitted" or entry["sha256"] != policy.sha(source)
                    or entry["receipt_sha256"] != policy.fingerprint(receipt)
                    or receipt["sha256"] != policy.sha(source) or receipt["arm"] != arm
                    or receipt["actor_sha256"] != config["actor_sha256"]
                    or receipt["plan_sha256"] != authorization["plan_sha256"]):
                raise ValueError("Final source/receipt identity changed")
            _validate_submission(bundle / arm, receipt, source, config, arm, metadata["execution"])
            deadline = time.monotonic() + plan["final_seconds"]
            semantic = workbench.grade_final(source, policy.sha(source), hidden,
                                             output / arm / "semantics", deadline)
            ep = worker.scripted._plan(config["edit_plan"])
            ep = replace(ep, limits=replace(ep.limits,
                         benchmark_repetitions=plan["final_repetitions"]))
            baseline = policy.artifact(next(e["source"] for e in plan["actors"][arm]["workspace"]
                                            if e["path"] == "candidate.py"))
            bench = workbench.VisibleWorkbench(ep, suite, baseline, output / arm / "benchmark")
            result["arms"][arm] = {"semantic": semantic,
                                    "performance": bench.visible_benchmark(source, deadline)}
        except (OSError, ValueError, KeyError, TypeError, provider.AgentError):
            result["arms"][arm] = {"verdict": "INCONCLUSIVE",
                                    "reason": "missing_or_invalid_artifact"}
    atomic_write_json(output / "grade.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "execute", "package", "grade"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    if args.action == "grade":
        if args.bundle is None:
            parser.error("grade requires the fixed current-run bundle")
        grade(args.bundle, args.output)
    elif args.bundle is not None:
        parser.error("bundle input is only for final grading")
    else:
        {"prepare": prepare, "execute": execute, "package": package}[args.action](args.output)


if __name__ == "__main__":
    main()
