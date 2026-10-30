"""Explicit owner-approved historical experiment admission, not a PR-label bypass.

The trusted operator supplies an independently approved receipt hash, never a value
from a PR, model output or dispatch payload. The charge PR identifies accounting
only; the frozen arms identify the compared skill revisions. No genesis creation,
refund, retry, or normal PR-controller policy changes are performed here.
"""

import json
import os
import re
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

from inferrsi.model.request_guard import authorization_broker
from tools import skill_eval_auto as auto
from tools import skill_eval_compare as compare
from tools import skill_eval_pr as pr
from tools.skill_eval_budget import (
    Binding,
    BudgetError,
    WriteResult,
    claim_once,
    daily_claim_once,
    daily_reserve,
    reserve,
    shanghai_day,
)


def receipt(path, expected_sha256):
    """Hash must come from the owner's trusted execution control plane."""
    if (not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
            or compare.sha256(Path(path)) != expected_sha256):
        raise ValueError("Historical approval receipt changed")
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    fields = {"schema_version", "experiment_id", "repository_id", "issue", "charge_pr",
              "charge_head", "implementation_sha", "plan_sha256", "protocol_sha256",
              "baseline", "candidate",
              "expires_at", "max_requests", "currency", "amount", "approval_evidence"}
    if (not isinstance(value, dict) or set(value) != fields or value["schema_version"] != 1
            or not isinstance(value["experiment_id"], str)
            or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", value["experiment_id"])
            or any(type(value[k]) is not int or value[k] <= 0
                   for k in ("repository_id", "issue", "charge_pr", "expires_at"))
            or value["expires_at"] <= time.time()
            or type(value["max_requests"]) is not int or value["max_requests"] != 2
            or value["currency"] != "USD" or value["amount"] != "20.34"
            or not isinstance(value["approval_evidence"], str)
            or not value["approval_evidence"].strip()
            or any(not isinstance(value[k], str) or not re.fullmatch(r"[0-9a-f]{40}", value[k])
                   for k in ("charge_head", "implementation_sha", "baseline", "candidate"))
            or not isinstance(value["plan_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["plan_sha256"])
            or not isinstance(value["protocol_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["protocol_sha256"])):
        raise ValueError("Incomplete, expired or unbounded historical approval")
    return value


def validate(api, output, approval, config, protocol_path):
    """Reconcile exact frozen experiment, provider, main and accounting identity."""
    if compare.sha256(Path(protocol_path)) != approval["protocol_sha256"]:
        raise ValueError("Prospective protocol changed")
    if approval["repository_id"] != config["repository_id"]:
        raise ValueError("Historical repository mismatch")
    if compare.sha256(output / "plan/freeze.json") != approval["plan_sha256"]:
        raise ValueError("Historical plan differs from owner-approved freeze")
    plan = compare.load_plan(output)
    if (plan.get("execution_mode") != "provider-generation-only-v1"
            or plan.get("retry_policy") != "none" or len(plan["schedule"]) != 2
            or {entry["condition"] for entry in plan["schedule"]} != {"baseline", "candidate"}
            or plan["arms"]["baseline"]["git_revision"] != approval["baseline"]
            or plan["arms"]["candidate"]["git_revision"] != approval["candidate"]):
        raise ValueError("Historical experiment scope changed")
    provider = config["provider"]
    if (plan["model"] != provider["model"]
            or plan["client"]["settings"] != provider["client"]
            or plan["client"]["pricing"] != provider["pricing"]
            or plan["client"]["spend_limit"] != provider["spend_limit"]
            or provider["client"]["max_requests"] != 1):
        raise ValueError("Historical provider differs from trusted configuration")
    bound = compare.provider_client(plan).require_live_readiness(2)
    if (bound != plan.get("reservation") or bound["requests"] != 2
            or bound["currency"] != "USD" or Decimal(bound["amount"]) > Decimal("20.34")):
        raise ValueError("Historical request reservation changed or exceeds approval")
    auto.daily_anchor(config)
    if api.request("GET", "")["id"] != approval["repository_id"]:
        raise ValueError("Live repository identity changed")
    main = api.request("GET", "/git/ref/heads/main")
    if (main.get("ref") != "refs/heads/main" or main.get("object", {}).get("type") != "commit"
            or main["object"]["sha"] != approval["implementation_sha"]):
        raise ValueError("Historical execution requires the approved current main")
    current = api.request("GET", f"/pulls/{approval['charge_pr']}")
    if (current["number"] != approval["charge_pr"]
            or current["base"].get("ref") != "main"
            or current["base"].get("repo", {}).get("id") != approval["repository_id"]
            or current["head"]["sha"] != approval["charge_head"]
            or current.get("draft", False)
            or not (current["state"] == "open" or current.get("merged") is True)):
        raise ValueError("Accounting PR changed or unavailable; historical arms are separate")
    return plan


def controlled_execute(api, output, *, config_path, approval_path, approval_sha256,
                       protocol_path, run_id, attempt, launch=None, live_authorization_check=None):
    """Trusted orchestration only. No paid operation is reachable without two ledgers."""
    output = Path(output)
    if attempt != 1:
        raise ValueError("Historical execution retries are forbidden")
    config = auto.configuration(config_path)
    approval = receipt(approval_path, approval_sha256)
    validate(api, output, approval, config, protocol_path)
    if any((output / "results").iterdir()):
        raise ValueError("Historical execution requires fresh results")
    if not os.environ.get("SKILL_EVAL_YIBUAPI_KEY"):
        raise ValueError("Provider credential unavailable; no reservation created")
    if live_authorization_check is not None:
        live_authorization_check()
    store, key = auto.ledger_store(api, config, approval["charge_pr"])
    global_store, global_key = auto.daily_store(api, config)
    # The digest binds every approved byte, including the exact frozen plan. The
    # stable logical run prevents a replacement receipt/physical run replenishing
    # this experiment; both plan and run identities are unique in each ledger.
    binding = Binding(approval_sha256,
                      f"historical:{approval['experiment_id']}:attempt-1", 20_340_000)
    snapshot = store.read_verified(key)
    global_snapshot = global_store.read_verified(global_key)
    admitted_day = shanghai_day()
    successor = daily_reserve(global_snapshot.ledger, key, binding, admitted_day)
    if (successor == global_snapshot.ledger or global_store.compare_and_swap(
            global_snapshot, successor) is not WriteResult.COMMITTED):
        raise BudgetError("Duplicate, conflicted or uncertain global reservation")
    successor = reserve(snapshot.ledger, binding)
    if (successor == snapshot.ledger
            or store.compare_and_swap(snapshot, successor) is not WriteResult.COMMITTED):
        raise BudgetError("Duplicate, conflicted or uncertain PR reservation")
    daily_claim_once(global_store, key, binding, shanghai_day())
    claim_once(store, key, binding)

    def check():
        if live_authorization_check is not None:
            live_authorization_check()
        fresh = auto.configuration(config_path)
        if fresh != config or receipt(approval_path, approval_sha256) != approval:
            raise ValueError("Historical authorization changed")
        validate(api, output, approval, fresh, protocol_path)
        ledger = store.read_verified(key).ledger
        daily = global_store.read_verified(global_key).ledger
        daily.require_active()
        if (not any(e.binding == binding and e.phase == "claimed" for e in ledger.entries)
                or not any(e.key == key and e.binding == binding and e.phase == "claimed"
                           and e.admitted_day == admitted_day for e in daily.entries)):
            raise BudgetError("Historical durable claims missing")
        if shanghai_day() != admitted_day:
            raise BudgetError("Shanghai admission day ended")

    check()
    # Pre-request provenance only; never copy private approval text or credentials.
    retained = {k: approval[k] for k in ("experiment_id", "repository_id", "issue",
                "charge_pr", "charge_head", "baseline", "candidate", "plan_sha256",
                "protocol_sha256", "implementation_sha", "max_requests", "currency", "amount")}
    retained.update(approval_sha256=approval_sha256, recorded_at=time.time(),
                    admitted_day=admitted_day, binding_plan_digest=binding.plan_digest,
                    binding_run_id=binding.run_id, physical_run_id=run_id)
    with (output / "historical-execution-approval.json").open("x", encoding="utf-8") as handle:
        json.dump(retained, handle, sort_keys=True, indent=2)
    with authorization_broker(check, 2, context=f"{approval_sha256}:{binding.run_id}") as gate:
        environment = {k: os.environ[k] for k in ("PATH", "LANG", "SYSTEMROOT", "TEMP", "TMP",
                       "SKILL_EVAL_YIBUAPI_KEY") if k in os.environ}
        environment.update(gate)
        environment["PYTHONPATH"] = str(pr.ROOT / "src")
        command = [sys.executable, "-c", "from pathlib import Path; import sys; "
                   "from tools.skill_eval_compare import execute; "
                   "execute(Path(sys.argv[1]),sys.argv[2],require_request_authorization=True)",
                   str(output), approval["plan_sha256"]]
        (launch or subprocess.run)(command, cwd=pr.ROOT, env=environment, check=True)
    # No automatic refunds or retries, including partial/uncertain execution.
