"""Fixed main-only KV launcher; disabled until a reviewed authorization is installed.

No dispatch inputs, PR-code checkout, ledger initializer, refund or retry. Ordinary
CI tests use fake transports/stores only. Candidate source never executes on host.
"""

import argparse
import json
import math
import os
import re
import shutil
import stat
import time
import urllib.request
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import islice
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
        atomic_write_json(root / "receipt.json", results[arm])
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
    result = {**result, "qualified_inventory_sha256": qualified["inventory_sha256"],
              "profile_source_sha256": profile_source}
    atomic_write_json(output / "receipt.json", result)
    if (result.get("verdict") != "PASS"
            or not policy._hex(result.get("inventory_sha256"))
            or not policy._hex(qualified.get("inventory_sha256"))
            or not policy._hex(profile_source)
            or result.get("mount_count") != qualified.get("mount_count")):
        raise ValueError("Same-host runtime/profile differs from hosted actor qualification")
    # Inventory hashing is sensitive-set dependent, not a portable host fingerprint.
    # The exact sandbox source/profile is bound by the canonical qualification
    # closure; independently require this host's full inventory/probe PASS.
    return result


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
    progress = {"schema": "kv-live-preflight-progress-v1", "implementation_sha": revision,
                "run_id": run_id, "plan_sha256": authorization["plan_sha256"],
                "stages": dict.fromkeys(("stage", "isolation", "cleanup", "runtime", "replay"),
                                       "not_started")}
    def step(name, callback):
        progress["stages"][name] = "started_outcome_unknown"
        atomic_write_json(output / "preflight.json", progress)
        try:
            result = callback()
        except BaseException:
            progress["stages"][name] = "failed_or_interrupted"
            atomic_write_json(output / "preflight.json", progress)
            raise
        progress["stages"][name] = "completed"
        atomic_write_json(output / "preflight.json", progress)
        return result
    step("stage", lambda: _stage(plan, output))
    deadline = time.monotonic() + 120
    isolation = step("isolation", lambda: kv.probe_isolation(
        output / "preflight/isolation", deadline,
        [str(ROOT), str(output / "A2/inputs"), str(output / "A3/workspace")]))
    descendants = step("cleanup", lambda: cleanup.qualify(
        output / "preflight/cleanup", deadline, 3))
    if descendants["verdict"] != "PASS":
        raise ValueError("Same-host actor cleanup qualification incomplete")
    runtime_profile = step("runtime", lambda: runtime_preflight(
        output / "preflight/runtime", deadline, plan))
    replay = step("replay", lambda: replay_preflight(output, deadline))
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


def _proof_projection(value):
    """Exact public probe fields only: never scope/error/path/log/environment text."""
    if type(value) is not dict:
        return {}
    result = {}
    for key in ("verdict", "executor_status", "worker_status"):
        if value.get(key) in {"PASS", "FAIL", "INCONCLUSIVE", "completed", "failed",
                             "timeout", "cancelled", "error"}:
            result[key] = value[key]
    for key in ("readonly", "clean_env", "network_blocked", "fork_denied",
                "normal_exit_process_group_gone", "detached_session_observed",
                "visibility_complete", "explicit_cancel_sent", "candidate_profile_unchanged",
                "outer_worker_supervised", "source_unchanged", "dirty",
                "recovery_visibility_complete"):
        if type(value.get(key)) is bool:
            result[key] = value[key]
    for key in ("model_calls", "observed_descendants", "surviving_descendants", "recovery_kills",
                "recovery_survivors", "nodes", "mount_count", "escaped_symlinks",
                "sensitive_files", "scripted_requests"):
        if type(value.get(key)) is int and 0 <= value[key] <= 200000:
            result[key] = value[key]
    for key in ("probe_sha256", "qualifier_sha256", "snapshot_hash", "inventory_sha256",
                "qualified_inventory_sha256", "profile_source_sha256", "artifact_sha256"):
        if policy._hex(value.get(key)):
            result[key] = value[key]
    if policy._hex(value.get("revision"), 40):
        result["revision"] = value["revision"]
    denied = value.get("inaccessible")
    if type(denied) is list and len(denied) <= 30000 and all(type(v) is bool for v in denied):
        result["inaccessible"] = denied
    limits = value.get("limits")
    if (type(limits) is dict
            and set(limits) == {"memory", "processes", "cpu", "output", "files", "core"}):
        if all(type(v) is list and len(v) == 2 and all(type(n) is int and -1 <= n <= 2**40
                                                    for n in v) for v in limits.values()):
            result["limits"] = limits
    for key in ("probe",):
        if key in value:
            result[key] = _proof_projection(value[key])
    if type(value.get("cases")) is dict:
        result["cases"] = {mode: _proof_projection(value["cases"].get(mode))
                           for mode in ("normal", "timeout", "cancel")}
    chain = value.get("bound_chain")
    if (type(chain) is dict and type(chain.get("chain_length")) is int
            and 3 <= chain["chain_length"] <= 128):
        result["bound_chain"] = {"chain_length": chain["chain_length"]}
        for role in ("worker", "detached"):
            identity = chain.get(role)
            if (type(identity) is dict and set(identity) == {"pid", "start"}
                    and all(type(v) is int and 0 < v < 2**63 for v in identity.values())):
                result["bound_chain"][role] = identity
    return result


def _public_preflight(output, authorization, locator):
    """Project fixed receipts, including partial preparation; no directory walk."""
    result = {"schema": "kv-live-public-preflight-v1", "status": "missing_or_invalid",
              "plan_sha256": authorization["plan_sha256"], "stages": {}, "proofs": {}}
    binding = None
    try:
        execution = policy.read_json(output / "execution.json")
        binding = tuple(execution[k] for k in ("implementation_sha", "run_id", "plan_sha256"))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    for filename in ("preflight.json", "prepared.json"):
        try:
            value = policy.read_json(output / filename)
            schema = ("kv-live-preflight-progress-v1" if filename == "preflight.json"
                      else "kv-live-prepared-v1")
            if (value["schema"] != schema or value["plan_sha256"] != authorization["plan_sha256"]
                    or not policy._hex(value["implementation_sha"], 40)
                    or not re.fullmatch(r"[1-9][0-9]*", value["run_id"])):
                raise ValueError("Unbound preparation")
            identity = tuple(value[k] for k in ("implementation_sha", "run_id", "plan_sha256"))
            if binding is not None and identity != binding:
                raise ValueError("Preparation execution identity changed")
            binding = identity
            result.update(implementation_sha=value["implementation_sha"], run_id=value["run_id"])
            if filename == "preflight.json":
                result["stages"] = {name: state if state in {
                    "not_started", "started_outcome_unknown",
                    "failed_or_interrupted", "completed"} else "missing_or_invalid"
                    for name in ("stage", "isolation", "cleanup", "runtime", "replay")
                    for state in [value.get("stages", {}).get(name)]}
                result["status"] = "partial"
            else:
                if value.get("locator_sha256") != policy.fingerprint(locator):
                    raise ValueError("Unbound prepared locator")
                result["locator_sha256"] = value["locator_sha256"]
                for name in ("isolation", "cleanup", "runtime_profile"):
                    result["proofs"][name] = _proof_projection(value.get(name))
                result["proofs"]["replay"] = {a: _proof_projection(value.get("replay", {}).get(a))
                                              for a in ("A2", "A3")}
                workspace = {arm: {entry["path"]: {
                    "expected_sha256": entry["source"]["sha256"],
                    "observed_sha256": value.get("inputs", {}).get(
                        f"{arm}/workspace/{entry['path']}")}
                    for entry in authorization["plan"]["actors"][arm]["workspace"]
                    if entry["path"] in COMMON | (KNOWLEDGE if arm == "A3" else set())}
                    for arm in ("A2", "A3")}
                if any(not policy._hex(entry["observed_sha256"])
                       or entry["observed_sha256"] != entry["expected_sha256"]
                       for paths in workspace.values() for entry in paths.values()):
                    raise ValueError("Missing staged workspace hashes")
                result["workspace"] = workspace
                result["status"] = "prepared"
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            continue
    for name, path in (("isolation", "preflight/isolation/stdout.log"),
                       ("cleanup", "preflight/cleanup/qualification.json"),
                       ("runtime_profile", "preflight/runtime/receipt.json")):
        if not result["proofs"].get(name):
            try:
                result["proofs"][name] = _proof_projection(policy.read_json(output / path))
            except (OSError, ValueError, TypeError, RecursionError):
                result["proofs"][name] = {"verdict": "INCONCLUSIVE"}
    for kind, names, pattern in (("replay", ("A2", "A3"), "preflight/replay/{}/receipt.json"),
            ("cleanup", ("normal", "timeout", "cancel"), "preflight/cleanup/{}/result.json")):
        target = result["proofs"].setdefault(kind, {})
        if kind == "cleanup":
            target = target.setdefault("cases", {})
        for name in names:
            if not target.get(name):
                try:
                    target[name] = _proof_projection(policy.read_json(
                        output / pattern.format(name)))
                except (OSError, ValueError, TypeError, RecursionError):
                    target[name] = {"verdict": "INCONCLUSIVE"}
    return result


def _raw_kv_output(path, destination, events, *, verify, remaining):
    """Retain exact raw JSON only after a closed KV-data schema/privacy check.

    Malformed candidate-only output is withheld, with bounded byte/hash diagnostics;
    this is not a sanitizer for provider logs or private inputs. Frozen task inputs
    identify allowed strings. Oversize/unsafe files are not opened or fully hashed.
    """
    result = {"status": "missing_or_unreadable", "reason": "unavailable",
              "bytes": None, "sha256": None, "truncated": None}
    try:
        if any(p.is_symlink() for p in (path, *path.parents)):
            return {**result, "reason": "unsafe_path"}
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            return {**result, "reason": "nonregular_file"}
        if info.st_size > 4 * policy.MAX_JSON:
            return {**result, "reason": "file_byte_limit", "bytes": info.st_size,
                    "truncated": True}
        raw = kv.read_regular(path, 4 * policy.MAX_JSON)
        result = {"status": "redacted_invalid_output", "reason": "json_parse_failed",
                  "bytes": len(raw), "sha256": policy.sha(raw), "truncated": False}
        value = json.loads(raw, object_pairs_hook=provider.unique_object)
        result["reason"] = "not_allowlisted_kv_data"
        ids = {e["request_id"] for e in events if type(e) is dict
               and type(e.get("request_id")) is str}
        def integers(items):
            return type(items) is list and len(items) <= 20000 and all(
                type(n) is int for n in items)
        def pending(items):
            return type(items) is list and len(items) <= 10000 and all(
                type(v) is list and len(v) == 3 and v[0] in ids
                and type(v[1]) is int
                and integers(v[2]) for v in items)
        if (type(value) is not dict or set(value) != {"observations", "pending"}
                or not pending(value["pending"]) or type(value["observations"]) is not list
                or len(value["observations"]) > 10000):
            raise ValueError("Not public KV output")
        for observation in value["observations"]:
            fields = {"pending"} if verify else set()
            if (type(observation) is not dict
                    or set(observation) not in (fields | {"error"}, fields | {"reclaimed"})
                    or (verify and not pending(observation["pending"]))
                    or ("error" in observation and observation["error"] != "ValueError")
                    or ("reclaimed" in observation and not integers(observation["reclaimed"]))):
                raise ValueError("Not public observation")
        if len(raw) > remaining[0]:
            return {**result, "status": "total_evidence_limit",
                    "reason": "whole_evidence_budget_exhausted"}
        result.update(status="projection_write_failed", reason="projection_write_failed")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        remaining[0] -= len(raw)
        result = {"status": "retained", "bytes": len(raw), "sha256": policy.sha(raw),
                  "data_sha256": policy.fingerprint(value), "truncated": False}
    except OSError:
        return result
    except (ValueError, TypeError, RecursionError):
        pass
    return result


def _execution_projection(value):
    result = {"status": "unavailable"}
    if type(value) is dict:
        if value.get("status") in {"completed", "failed", "timeout", "cancelled", "error"}:
            result["status"] = value["status"]
        for name in ("elapsed_seconds", "metric"):
            number = value.get(name)
            if type(number) in (int, float) and math.isfinite(number) and 0 <= number <= 3600:
                result[name] = number
            elif name in value and number is None:
                result[name] = None
        code = value.get("returncode")
        if type(code) is int and -255 <= code <= 255:
            result["returncode"] = code
        elif "returncode" in value and code is None:
            result["returncode"] = None
    return result


def _grade_evidence(bundle, output, result, plan=None):
    """Only known grader paths; all assigned cases/trials survive as explicit rows."""
    public = output / "public"
    public.mkdir(exist_ok=True)
    state = {"schema": "kv-live-grade-projection-v1", "status": "started_outcome_unknown"}
    atomic_write_json(public / "projection.json", state)
    try:
        remaining = [32 * policy.MAX_JSON]  # Whole two-arm raw evidence ceiling, not per file.
        manifest = {"schema": "kv-live-grade-evidence-v1", "plan_sha256": result["plan_sha256"],
                    "arms": {a: {"status": "not_evaluated"} for a in ("A2", "A3")}}
        if plan is not None:
            captured = policy.read_json(bundle / "authorization.json")
            atomic_write_json(public / "authorization.json", captured)
            metadata = policy.read_json(bundle / "bundle.json")
            manifest["execution"] = {k: metadata["execution"][k] for k in
                ("implementation_sha", "run_id", "execution_id", "charge_pr", "charge_head")}
            hidden = json.loads(policy.artifact(plan["hidden_traces"], limit=16 * policy.MAX_JSON))
            if type(hidden) is not list or not 0 < len(hidden) <= 256:
                raise ValueError("Frozen grader trace-count evidence bound exceeded")
            suite = workbench.VisibleSuite(policy.artifact(
                plan["final_suite"], limit=16 * policy.MAX_JSON)).read()
            for arm in ("A2", "A3"):
                records = {"status": "recorded", "semantics": [], "performance": []}
                manifest["arms"][arm] = records
                arm_result = result["arms"].get(arm, {})
                source = arm_result.get("artifact_sha256",
                                       arm_result.get("semantic", {}).get("artifact_sha256"))
                records["artifact_sha256"] = source if policy._hex(source) else None
                baseline_hash = next(e["source"]["sha256"] for e in plan["actors"][arm]["workspace"]
                                     if e["path"] == "candidate.py")
                checks = arm_result.get("semantic", {}).get("checks", {})
                for index, trace in enumerate(hidden):
                    name = f"{arm}/semantics/trace-{index:03d}.json"
                    trace_root = output / arm / "semantics" / f"trace-{index:03d}"
                    raw = _raw_kv_output(
                        trace_root / "stdout.log",
                        public / name, trace["events"], verify=True, remaining=remaining)
                    execution = {"status": "unavailable"}
                    try:
                        record = policy.read_json(trace_root / "execution.json", 16384)
                        if (type(record) is not dict or set(record) != {
                                "status", "returncode", "elapsed_seconds"}):
                            raise ValueError("Wrong trusted executor receipt")
                        execution = _execution_projection(record)
                    except (OSError, ValueError, TypeError):
                        pass
                    records["semantics"].append({"trace_id": trace["id"],
                        "trace_sha256": policy.fingerprint(trace), "output": {"path": name, **raw},
                        "check": checks.get(trace["id"]),
                        "execution": execution})
                runs = output / arm / "benchmark/benchmark-001/runs"
                run = None
                try:
                    entries = list(islice(runs.iterdir(), 2))
                    if (len(entries) == 1
                            and re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{10}", entries[0].name)
                            and entries[0].is_dir() and not entries[0].is_symlink()):
                        run = entries[0]
                except OSError:
                    pass
                schedule = [(side, index + 1, f"{side}/trial-{index + 1:03d}")
                    for index in range(plan["final_repetitions"])
                    for side in (("baseline", "candidate") if index % 2 == 0
                                 else ("candidate", "baseline"))]
                schedule.append(("candidate", None, "validation"))
                for side, trial, relative in schedule:
                    name = f"{arm}/performance/{relative}/output.json"
                    row = {"side": side, "trial": trial,
                           "phase": "quality" if trial is None else "measurement",
                           "source_sha256": baseline_hash if side == "baseline" else source,
                           "input_sha256": policy.fingerprint(suite["benchmark_events"]),
                           "expected_sha256": policy.fingerprint(suite["benchmark_expected"]),
                           "execution": {"status": "unavailable"},
                           "source_verified": False, "output": {"status": "not_observed"}}
                    if run is not None:
                        row["output"] = {"path": name, **_raw_kv_output(
                            run / relative / "stdout.log",
                            public / name, suite["benchmark_events"], verify=False,
                            remaining=remaining)}
                        try:
                            row["execution"] = _execution_projection(policy.read_json(
                                run / relative / "execution.json"))
                            identity = policy.read_json(run / relative / "source.json")
                            row["source_snapshots"] = {k: identity.get(k, {}).get("snapshot_hash")
                                if policy._hex(identity.get(k, {}).get("snapshot_hash")) else None
                                for k in ("before", "after")}
                            row["source_verified"] = all(
                                identity.get(k, {}).get("available") is True
                                and identity[k].get("snapshot_hash") == row["source_sha256"]
                                for k in ("before", "after"))
                        except (OSError, ValueError, TypeError):
                            pass
                    records["performance"].append(row)
                records["raw_outputs_complete"] = all(row["output"]["status"] == "retained"
                    for name in ("semantics", "performance") for row in records[name])
        atomic_write_json(public / "grade.json", result)
        atomic_write_json(public / "evidence.json", manifest)  # Completion marker written last.
    except BaseException:
        state["status"] = "failed_or_interrupted"
        atomic_write_json(public / "projection.json", state)
        raise
    state.update(status="completed", evidence_sha256=policy.fingerprint(manifest),
                 grade_sha256=policy.fingerprint(result))
    atomic_write_json(public / "projection.json", state)
    return manifest


def package(output):
    """Fixed bounded public projection. Never copy raw worker/provider logs or private paths."""
    output = Path(output)
    public = output / "public"
    public.mkdir(parents=True, exist_ok=False)
    preflight_status = "missing_or_invalid_authorization"
    try:
        # Public bytes already verified before preparation; never credentials.
        captured = policy.read_json(output / "authorization.json")
        authorization, locator = policy.frozen_authorization(fetch=lambda _: captured, now=0)
        atomic_write_json(public / "authorization.json", captured)
        proof = _public_preflight(output, authorization, locator)
        atomic_write_json(public / "preflight.json", proof)
        preflight_status = proof["status"]
    except (OSError, ValueError, KeyError, TypeError):
        pass  # Missing authorization is explicit INCONCLUSIVE in the no-spend grader.
    execution = (policy.read_json(output / "execution.json")
                 if (output / "execution.json").is_file() else {})
    summary = {"schema": "kv-live-bundle-v1", "execution": execution, "artifacts": {},
               "requests": {}, "evidence": {}, "preflight_status": preflight_status}
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
    output.mkdir(parents=True, exist_ok=True)
    result = {"schema": "kv-live-final-grade-v1", "plan_sha256": plan_sha256,
              "scope": "final input identity unavailable; no candidate evaluation or spending",
              "arms": {arm: {"verdict": "INCONCLUSIVE", "reason": reason}
                       for arm in ("A2", "A3")}}
    atomic_write_json(output / "grade.json", result)
    _grade_evidence(None, output, result)
    return result


def _grade_context(bundle):
    """Shared no-network identity check for grading and interruption-only packaging."""
    try:
        captured = policy.read_json(bundle / "authorization.json")
        authorization, _ = policy.frozen_authorization(fetch=lambda _: captured, now=0)
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("missing_or_invalid_authorization") from None
    plan = authorization["plan"]
    try:
        metadata = policy.read_json(bundle / "bundle.json")
    except (OSError, ValueError):
        raise ValueError("missing_or_invalid_bundle") from None
    if (type(metadata) is not dict or metadata.get("schema") != "kv-live-bundle-v1"
            or type(metadata.get("execution")) is not dict
            or metadata.get("execution", {}).get("plan_sha256") != authorization["plan_sha256"]
            or metadata["execution"].get("run_id") != os.environ.get("GITHUB_RUN_ID")
            or metadata["execution"].get("implementation_sha") != os.environ.get("GITHUB_SHA")
            or metadata["execution"].get("execution_id") != plan["execution_id"]
            or metadata["execution"].get("charge_pr") != plan["charge_pr"]
            or metadata["execution"].get("charge_head") != plan["charge_head"]):
        raise ValueError("invalid_execution_identity")
    return authorization, metadata


def package_grade(bundle, output):
    """Always-step recovery of already generated evidence; never invoke a candidate."""
    if os.environ.get(provider.KEY_ENV) or os.environ.get("GITHUB_TOKEN"):
        raise ValueError("Final packaging must run without injected credentials")
    bundle, output = Path(bundle), Path(output)
    try:
        authorization, _ = _grade_context(bundle)
    except ValueError as exc:
        return _grade_rejected(output, str(exc))
    plan = authorization["plan"]
    try:
        result = policy.read_json(output / "grade.json")
        if (result.get("schema") != "kv-live-final-grade-v1"
                or result.get("plan_sha256") != authorization["plan_sha256"]
                or set(result.get("arms", {})) != {"A2", "A3"}):
            raise ValueError("Unbound grade")
        # Reuse the existing closed feedback contract; never publish arbitrary fields.
        safe = {"schema": result["schema"], "plan_sha256": result["plan_sha256"],
                "scope": "one synthetic pair; hidden semantics and nonheldout task timing",
                "arms": {}}
        hidden = json.loads(policy.artifact(plan["hidden_traces"], limit=16 * policy.MAX_JSON))
        ids = {t["id"] for t in hidden}
        for arm, value in result["arms"].items():
            entry = {"verdict": "INCONCLUSIVE", "reason": "grading_interrupted"}
            if value.get("reason") in {"not_evaluated", "grading_interrupted",
                                       "missing_or_invalid_artifact"}:
                entry["reason"] = value["reason"]
            if policy._hex(value.get("artifact_sha256")):
                entry["artifact_sha256"] = value["artifact_sha256"]
            semantic = value.get("semantic", {})
            if (semantic.get("verdict") in {"PASS", "FAIL", "INCONCLUSIVE"}
                    and type(semantic.get("checks")) is dict and set(semantic["checks"]) <= ids
                    and all(type(v) is bool for v in semantic["checks"].values())
                    and (semantic["verdict"] == "INCONCLUSIVE" or (
                        set(semantic["checks"]) == ids
                        and (semantic["verdict"] == "PASS") == all(semantic["checks"].values())))
                    and policy._hex(semantic.get("artifact_sha256"))):
                entry["semantic"] = {k: semantic[k] for k in
                    ("verdict", "checks", "artifact_sha256")}
                if semantic.get("reason") in {"deadline", "error", "timeout", "cancelled",
                                              "sandbox_unavailable"}:
                    entry["semantic"]["reason"] = semantic["reason"]
            feedback = value.get("performance")
            if feedback is not None:
                config = policy.read_json(ROOT / plan["actors"][arm]["config"]["path"])
                ep = worker.scripted._plan(config["edit_plan"])
                ep = replace(ep, limits=replace(ep.limits,
                    benchmark_repetitions=plan["final_repetitions"]))
                try:
                    worker.edit._feedback("benchmark", feedback, ep)
                    entry["performance"] = feedback
                except provider.AgentError:
                    pass
            if "verdict" not in value and {"semantic", "performance"} <= set(entry):
                entry.pop("verdict")
                entry.pop("reason")
            safe["arms"][arm] = entry
        result = safe
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        result = {"schema": "kv-live-final-grade-v1", "plan_sha256": authorization["plan_sha256"],
                  "scope": "grade process incomplete; first outputs only, no re-execution",
                  "arms": {a: {"verdict": "INCONCLUSIVE", "reason": "grading_interrupted"}
                           for a in ("A2", "A3")}}
    output.mkdir(parents=True, exist_ok=True)
    return _grade_evidence(bundle, output, result, plan)


def grade(bundle, output):
    """Separate no-secret hidden grade of immutable final bytes; never model feedback."""
    if os.environ.get(provider.KEY_ENV) or os.environ.get("GITHUB_TOKEN"):
        raise ValueError("Final grading must run without injected provider/GitHub credentials")
    # Revocation/expiry stops spending, not offline grading of already captured public bytes.
    bundle, output = Path(bundle), Path(output)
    try:
        authorization, metadata = _grade_context(bundle)
    except ValueError as exc:
        return _grade_rejected(output, str(exc))
    plan = authorization["plan"]
    output.mkdir(parents=True, exist_ok=False)
    hidden = json.loads(policy.artifact(plan["hidden_traces"], limit=16 * policy.MAX_JSON))
    suite = workbench.VisibleSuite(policy.artifact(plan["final_suite"], limit=16 * policy.MAX_JSON))
    result = {"schema": "kv-live-final-grade-v1", "plan_sha256": authorization["plan_sha256"],
              "scope": "one synthetic pair; hidden semantics and nonheldout task timing",
              "arms": {arm: {"verdict": "INCONCLUSIVE", "reason": "not_evaluated"}
                       for arm in ("A2", "A3")}}
    atomic_write_json(output / "grade.json", result)
    try:
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
                _validate_submission(bundle / arm, receipt, source, config, arm,
                                     metadata["execution"])
                deadline = time.monotonic() + plan["final_seconds"]
                result["arms"][arm] = {"verdict": "INCONCLUSIVE", "reason": "grading_interrupted",
                                       "artifact_sha256": policy.sha(source)}
                atomic_write_json(output / "grade.json", result)
                semantic = workbench.grade_final(source, policy.sha(source), hidden,
                                                 output / arm / "semantics", deadline)
                ep = worker.scripted._plan(config["edit_plan"])
                ep = replace(ep, limits=replace(ep.limits,
                             benchmark_repetitions=plan["final_repetitions"]))
                baseline = policy.artifact(next(e["source"]
                    for e in plan["actors"][arm]["workspace"] if e["path"] == "candidate.py"))
                bench = workbench.VisibleWorkbench(ep, suite, baseline, output / arm / "benchmark")
                result["arms"][arm] = {"semantic": semantic, "performance": {
                    "verdict": "INCONCLUSIVE", "reason": "grading_interrupted"}}
                atomic_write_json(output / "grade.json", result)
                result["arms"][arm]["performance"] = bench.visible_benchmark(source, deadline)
                atomic_write_json(output / "grade.json", result)
            except (OSError, ValueError, KeyError, TypeError, provider.AgentError):
                result["arms"][arm].update(verdict="INCONCLUSIVE",
                                          reason="missing_or_invalid_artifact")
    finally:
        atomic_write_json(output / "grade.json", result)
        _grade_evidence(bundle, output, result, plan)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "execute", "package", "grade",
                                           "package-grade"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    if args.action in {"grade", "package-grade"}:
        if args.bundle is None:
            parser.error("grade requires the fixed current-run bundle")
        {"grade": grade, "package-grade": package_grade}[args.action](args.bundle, args.output)
    elif args.bundle is not None:
        parser.error("bundle input is only for final grading")
    else:
        {"prepare": prepare, "execute": execute, "package": package}[args.action](args.output)


if __name__ == "__main__":
    main()
