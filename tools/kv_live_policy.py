"""Fixed public freeze/current-main validation. No secrets, writes or fallback policy."""

import hashlib
import io
import json
import os
import re
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from inferrsi.harness import kv_reclamation as kv
from inferrsi.model import anthropic_agent as provider
from tools import kv_edit_inputs as inputs
from tools import kv_edit_pilot as scripted
from tools import kv_pilot_admission as admission
from tools import skill_eval_budget as budget
from tools.skill_eval_budget_git import DailyLedgerAnchor, LedgerAnchor

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "InferMatrixLab/InferRSI"
REPOSITORY_ID = 1409534281
OPERATOR = "Dong1017"
WORKFLOW = ".github/workflows/kv-edit-pilot.yml"
LOCATOR = ROOT / "tools/kv_live_authorization.json"
PREFIX = "<!-- inferrsi-kv-edit-authorization:v1 -->\n```json\n"
SUFFIX = "\n```"
MAX_JSON = 1024 * 1024
PLAN_FIELDS = {
    "schema", "repository_id", "issue", "campaign_id", "execution_id", "charge_pr",
    "charge_head", "expires_at", "provider", "actors", "dependencies", "ledger",
    "daily_ledger", "qualification", "suite", "final_suite", "hidden_traces",
    "arm_order", "scope", "price_evidence", "prior_owner_group_statement",
    "final_seconds", "final_repetitions",
}
DEPENDENCIES = (
    "tools/kv_edit_inputs.py", "tools/kv_live_policy.py", "tools/kv_live_job.py",
    "tools/kv_live_worker.py",
    "tools/kv_pilot_admission.py", "tools/kv_edit_pilot.py",
    "src/inferrsi/model/anthropic_agent.py", "src/inferrsi/model/anthropic_edit_agent.py",
    "src/inferrsi/model/request_guard.py", "tools/skill_eval_budget.py",
    "tools/skill_eval_budget_git.py", "tools/skill_eval_pr.py",
    "tools/qualify_kv_actor_cleanup.py", "src/inferrsi/infra/targets/__init__.py",
    "src/inferrsi/infra/targets/git.py",
    ".github/workflows/kv-edit-pilot.yml", "pyproject.toml",
)

QUALIFICATION_DEPENDENCIES = {
    "tools/kv_edit_inputs.py",
    "tools/qualify_kv_edit_actor.py", "tools/qualify_kv_actor_cleanup.py",
    "tools/kv_runtime_qualification.py", "tools/qualify_kv_reclamation.py",
    "tools/kv_pilot_admission.py", "src/inferrsi/model/anthropic_edit_agent.py",
    "src/inferrsi/model/anthropic_agent.py", "src/inferrsi/model/request_guard.py",
}


def read_json(path, limit=MAX_JSON):
    return json.loads(kv.read_regular(Path(path), limit), object_pairs_hook=provider.unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(value):
    return sha(provider.canonical(value).encode())


def relative(name):
    if (type(name) is not str or not name or "\\" in name
            or PurePosixPath(name).is_absolute()
            or any(p in {"", ".", ".."} for p in name.split("/"))):
        raise ValueError("Invalid frozen relative path")
    return name


def _hex(value, size=64):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(size) + "}", value) is not None


def _positive(value):
    return type(value) is int and value > 0


def artifact(record, *, limit=MAX_JSON):
    if (type(record) is not dict or set(record) != {"path", "bytes", "sha256"}
            or not _positive(record["bytes"]) or record["bytes"] > limit
            or not _hex(record["sha256"])):
        raise ValueError("Invalid frozen artifact record")
    path = ROOT / relative(record["path"])
    data = kv.read_regular(path, limit)
    if len(data) != record["bytes"] or sha(data) != record["sha256"]:
        raise ValueError("Frozen artifact changed")
    return data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Authorization redirect forbidden")


def fetch_comment(number):
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPOSITORY}/issues/comments/{number}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "InferRSI-KV-controller"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(
            request, timeout=20) as response:
        raw = response.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise ValueError("Authorization response too large")
    return json.loads(raw, object_pairs_hook=provider.unique_object)


def frozen_authorization(*, fetch=fetch_comment, now=None):
    locator = read_json(LOCATOR, 16384)
    fields = {"schema", "enabled", "repository_id", "issue", "comment_id", "author_login",
              "body_sha256"}
    if (type(locator) is not dict or set(locator) != fields or locator.get("enabled") is not True
            or locator["schema"] != "kv-live-authorization-locator-v1"
            or locator["repository_id"] != REPOSITORY_ID or locator["author_login"] != OPERATOR
            or not all(_positive(locator[k]) for k in ("issue", "comment_id"))
            or not _hex(locator["body_sha256"])):
        raise ValueError("Live KV authorization is disabled or incomplete")
    comment = fetch(locator["comment_id"])
    body = comment.get("body")
    if (comment.get("id") != locator["comment_id"]
            or comment.get("issue_url") !=
            f"https://api.github.com/repos/{REPOSITORY}/issues/{locator['issue']}"
            or comment.get("user", {}).get("login") != OPERATOR
            or comment.get("user", {}).get("type") != "User"
            or type(body) is not str or sha(body.encode()) != locator["body_sha256"]
            or not body.startswith(PREFIX) or not body.endswith(SUFFIX)):
        raise ValueError("Fixed authorization identity or exact bytes changed")
    value = json.loads(body[len(PREFIX):-len(SUFFIX)], object_pairs_hook=provider.unique_object)
    if (type(value) is not dict or set(value) != {"schema", "plan_sha256", "plan"}
            or value["schema"] != "kv-live-authorization-v1"
            or value["plan_sha256"] != fingerprint(value["plan"])):
        raise ValueError("Authorization does not bind the exact plan")
    validate_plan(value["plan"], now=time.time() if now is None else now)
    if value["plan"]["issue"] != locator["issue"]:
        raise ValueError("Authorization Issue changed")
    return value, locator


def validate_plan(plan, *, now):
    fields = PLAN_FIELDS | ({"budget_exception"} if type(plan) is dict
                            and plan.get("schema") == "kv-live-plan-v2" else set())
    if (type(plan) is not dict or set(plan) != fields
            or plan["schema"] not in {"kv-live-plan-v1", "kv-live-plan-v2"}
            or plan["repository_id"] != REPOSITORY_ID
            or not all(_positive(plan[k]) for k in ("issue", "charge_pr", "expires_at"))
            or not _hex(plan["charge_head"], 40) or plan["expires_at"] <= now
            or plan["arm_order"] not in (["A2", "A3"], ["A3", "A2"])
            or plan["final_seconds"] != 180 or plan["final_repetitions"] != 8
            or type(plan["actors"]) is not dict or set(plan["actors"]) != {"A2", "A3"}
            or any(type(plan[k]) is not str or not plan[k].strip()
                   for k in ("scope", "price_evidence", "prior_owner_group_statement"))):
        raise ValueError("Wrong, expired or incomplete fixed KV scope")
    for actor in plan["actors"].values():
        if (type(actor) is not dict or set(actor) != {"config", "workspace"}
                or type(actor["workspace"]) is not list or not actor["workspace"]):
            raise ValueError("Wrong frozen actor inputs")
        artifact(actor["config"])
    key = budget.PRKey(REPOSITORY_ID, plan["charge_pr"])
    LedgerAnchor(key=key, **plan["ledger"])
    DailyLedgerAnchor(key=budget.DailyKey(REPOSITORY_ID), **plan["daily_ledger"])
    additional_attempt(plan)
    sources = plan["dependencies"]
    required = set(DEPENDENCIES) | set(scripted.dependencies())
    if (type(sources) is not dict or not required <= set(sources)
            or any(not _hex(value) or sha(kv.read_regular(ROOT / relative(name), MAX_JSON)) != value
                   for name, value in sources.items())):
        raise ValueError("Frozen executable dependencies changed")
    for name in ("suite", "final_suite", "hidden_traces"):
        artifact(plan[name], limit=16 * MAX_JSON)
    validate_qualification(plan)
    # Reuse strict cost identity validation; no new rates or token arithmetic here.
    policy(plan, "0" * 40).reservation(now=now)


def qualification_dependencies():
    # Canonical closure belongs to the actor qualifier, including package
    # initializers and transitive runtime/metric/scenario helpers. A checkout
    # without that reviewed prerequisite cannot activate this launcher.
    from tools import qualify_kv_edit_actor
    return qualify_kv_edit_actor.dependencies()


def validate_qualification(plan):
    q = plan["qualification"]
    fields = {"run_id", "run_attempt", "head", "revision", "artifact_id", "archive", "receipt",
              "dependencies_sha256"}
    if (type(q) is not dict or set(q) != fields
            or not all(_positive(q[k]) for k in ("run_id", "run_attempt", "artifact_id"))
            or not _hex(q["head"], 40) or not _hex(q["revision"], 40)):
        raise ValueError("Exact hosted actor qualification provenance required")
    raw = artifact(q["receipt"])
    receipt = json.loads(raw, object_pairs_hook=provider.unique_object)
    sources = receipt.get("dependencies", {})
    required = QUALIFICATION_DEPENDENCIES | set(scripted.dependencies())
    if (not required <= set(sources) or sources != qualification_dependencies()
            or q["dependencies_sha256"] != fingerprint(sources)
            or receipt.get("dependencies_sha256") != fingerprint(sources)
            or any(not _hex(digest)
                   or sha(kv.read_regular(ROOT / relative(name), MAX_JSON)) != digest
                   for name, digest in sources.items())):
        raise ValueError("Actor qualification dependency closure changed")
    archive = artifact(q["archive"], limit=64 * MAX_JSON)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        entries = bundle.infolist()
        if (len(entries) != 2 or {e.filename for e in entries}
                != {"qualification.json", "raw-evidence.zip"}
                or any(e.flag_bits & 1 or e.file_size > 64 * MAX_JSON for e in entries)
                or bundle.getinfo("qualification.json").file_size > MAX_JSON
                or bundle.read("qualification.json") != raw):
            raise ValueError("Hosted artifact does not contain the exact qualification receipt")
        evidence = bundle.read("raw-evidence.zip")
    if (receipt.get("schema") != "kv-scripted-actor-qualification-v1"
            or receipt.get("revision") != q["revision"] or receipt.get("verdict") != "PASS"
            or receipt.get("software_checks_passed") is not True
            or receipt.get("source_unchanged") is not True
            or receipt.get("model_calls") != 0 or receipt.get("provider_charges_usd") != 0
            or receipt.get("cleanup", {}).get("verdict") != "PASS"
            or receipt.get("runtime_isolation", {}).get("verdict") != "PASS"
            or not _hex(receipt.get("runtime_isolation", {}).get("inventory_sha256"))
            or not _positive(receipt.get("runtime_isolation", {}).get("mount_count"))
            or receipt.get("raw_evidence", {}).get("sha256") != sha(evidence)
            or set(receipt.get("arms", {})) != {"A2", "A3"}):
        raise ValueError("Exact model-free actor qualification required")
    for arm in ("A2", "A3"):
        result = receipt["arms"][arm]
        config = read_json(ROOT / plan["actors"][arm]["config"]["path"])
        if (result.get("executor_status") != "completed"
                or result.get("worker_status") != "completed"
                or result.get("request_completion_known") is not True
                or result.get("simulated_slots_consumed") != 4
                or result.get("visible_workbench_verified") is not True
                or result.get("two_revision_receipts_retained") is not True
                or result.get("hidden_correctness", {}).get("verdict") != "PASS"
                or result.get("common_actor_contract_sha256")
                != inputs.common_actor_contract_sha256(config)
                or result.get("exposure") != config["edit_plan"]["files"]
                or result.get("prompt_sha256") != sha(config["prompt"].encode())):
            raise ValueError("Hosted actor exposure/tool evidence differs from frozen live arm")
    return receipt


def additional_attempt(plan):
    """Resolve only exact frozen v2 data; no ledger/worker/CLI cap authority."""
    if plan.get("schema", "kv-live-plan-v1") == "kv-live-plan-v1":
        if "budget_exception" in plan:
            raise ValueError("Legacy plan cannot carry a budget exception")
        return None
    value = plan.get("budget_exception")
    fields = {"schema", "key", "pr_lifetime_cap_microusd", "pilot_lifetime_cap_microusd",
              "additional_attempts", "prior_binding", "pr_checkpoint", "daily_checkpoint",
              "campaign_id", "execution_id"}
    if (plan.get("schema") != "kv-live-plan-v2" or type(value) is not dict
            or set(value) != fields or value["schema"] != "kv-one-additional-attempt-v1"
            or type(value["additional_attempts"]) is not int or value["additional_attempts"] != 1
            or type(value["pilot_lifetime_cap_microusd"]) is not int
            or value["pilot_lifetime_cap_microusd"] != admission.PILOT_LIMIT_MICROUSD
            or type(value["key"]) is not dict
            or value["key"] != {"repository_id": REPOSITORY_ID, "pr_number": plan["charge_pr"]}
            or type(value["prior_binding"]) is not dict
            or set(value["prior_binding"]) != {"plan_digest", "run_id", "worst_case"}
            or value["campaign_id"] != plan["campaign_id"]
            or value["execution_id"] != plan["execution_id"]
            or value["pr_checkpoint"] != plan["ledger"]["checkpoint_commit"]
            or value["daily_checkpoint"] != plan["daily_ledger"]["checkpoint_commit"]):
        raise ValueError("Invalid exact one-additional-attempt scope")
    return admission.AdditionalAttempt(
        budget.TrustedPRLimit(budget.PRKey(**value["key"]), value["pr_lifetime_cap_microusd"]),
        budget.Binding(**value["prior_binding"]), value["campaign_id"], value["execution_id"],
        value["pr_checkpoint"], value["daily_checkpoint"])


def policy(plan, revision):
    actors = [read_json(ROOT / plan["actors"][arm]["config"]["path"]) for arm in ("A2", "A3")]
    return admission.PilotPolicy(
        plan["campaign_id"], budget.PRKey(REPOSITORY_ID, plan["charge_pr"]),
        plan["execution_id"], fingerprint(plan), plan["charge_head"], revision,
        tuple(a["actor_sha256"] for a in actors), provider.canonical(plan["provider"]),
        plan["expires_at"], additional_attempt(plan))


def runtime(environment=None):
    env = os.environ if environment is None else environment
    expected = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
                "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_RUN_ATTEMPT": "1",
                "GITHUB_ACTOR": OPERATOR, "GITHUB_TRIGGERING_ACTOR": OPERATOR}
    if any(env.get(k) != v for k, v in expected.items()):
        raise ValueError("Only fixed first-attempt owner main dispatch is supported")
    revision, run_id = env.get("GITHUB_SHA", ""), env.get("GITHUB_RUN_ID", "")
    if not _hex(revision, 40) or not re.fullmatch(r"[1-9][0-9]*", run_id):
        raise ValueError("Invalid runtime identity")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if head != revision or dirty:
        raise ValueError("Execution checkout differs or is dirty")
    return revision, run_id


def verify_live(api, plan, revision, run_id):
    if api.request("GET", "").get("id") != REPOSITORY_ID:
        raise ValueError("Live repository changed")
    main = api.request("GET", "/git/ref/heads/main")
    if (main.get("ref") != "refs/heads/main" or main.get("object", {}).get("type") != "commit"
            or main["object"].get("sha") != revision):
        raise ValueError("Only exact current main may execute")
    current = api.request("GET", f"/pulls/{plan['charge_pr']}")
    if (current.get("number") != plan["charge_pr"] or current.get("head", {}).get("sha")
            != plan["charge_head"] or current.get("draft") is not False
            or current.get("base", {}).get("ref") != "main"
            or current.get("base", {}).get("repo", {}).get("id") != REPOSITORY_ID
            or current.get("merged") is not True):
        raise ValueError("Final reviewed implementation charge PR changed or is not merged")
    run = api.request("GET", f"/actions/runs/{run_id}")
    if (run.get("event") != "workflow_dispatch" or run.get("head_branch") != "main"
            or run.get("head_sha") != revision or run.get("run_attempt") != 1
            or run.get("status") != "in_progress" or run.get("path") != WORKFLOW
            or run.get("repository", {}).get("id") != REPOSITORY_ID
            or any(run.get(k, {}).get("login") != OPERATOR for k in ("actor", "triggering_actor"))):
        raise ValueError("Live workflow identity changed")
    qualified = api.request("GET", f"/actions/runs/{plan['qualification']['run_id']}")
    if (qualified.get("head_sha") != plan["qualification"]["head"]
            or qualified.get("path") != ".github/workflows/ci-ready.yml"
            or qualified.get("status") != "completed" or qualified.get("conclusion") != "success"
            or qualified.get("repository", {}).get("id") != REPOSITORY_ID
            or qualified.get("run_attempt") != plan["qualification"]["run_attempt"]):
        raise ValueError("Actor qualification run is not successful for the pinned source")

    q = plan["qualification"]
    artifact_record = api.request("GET", f"/actions/artifacts/{q['artifact_id']}")
    expected_name = f"kv-actor-qualification-{q['run_id']}-{q['run_attempt']}"
    if (artifact_record.get("id") != q["artifact_id"]
            or artifact_record.get("name") != expected_name
            or artifact_record.get("expired") is not False
            or artifact_record.get("digest") != "sha256:" + q["archive"]["sha256"]
            or artifact_record.get("workflow_run", {}).get("id") != q["run_id"]
            or artifact_record.get("workflow_run", {}).get("head_sha") != q["head"]
            or artifact_record.get("workflow_run", {}).get("head_repository_id") != REPOSITORY_ID):
        raise ValueError("Qualification archive is not the exact successful hosted run artifact")
