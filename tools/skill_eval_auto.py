"""Trusted label controller. Configuration and ledger genesis are deployment prerequisites."""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from urllib.parse import quote

from inferrsi.infra.artifacts import write_json
from tools import skill_eval_pr as pr
from tools.skill_eval_budget import Binding, BudgetError, PRKey, WriteResult, claim_once, reserve
from tools.skill_eval_budget_git import GitHubGitStore, LedgerAnchor

CONFIG = pr.ROOT / "tools/skill_eval_auto_config.json"


def configuration(path=CONFIG, *, now=None):
    """Never accept provider or ledger identity from dispatch inputs or PR files."""
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(value) != {"schema_version", "repository_id", "label", "operators", "expires_at",
                      "provider", "provider_sha256", "anchors", "review_evidence"}:
        raise ValueError("Incomplete trusted automatic-execution configuration")
    if (value["schema_version"] != 1 or type(value["repository_id"]) is not int
            or value["repository_id"] <= 0 or not isinstance(value["label"], str)
            or not value["label"] or not value["operators"]
            or not all(re.fullmatch(r"[A-Za-z0-9_-]+", a) for a in value["operators"])
            or type(value["expires_at"]) is not int
            or value["expires_at"] <= (time.time() if now is None else now)
            or not value["review_evidence"]):
        raise ValueError("Invalid or expired trusted automatic-execution configuration")
    provider = value["provider"]
    if pr.fingerprint(provider) != value["provider_sha256"]:
        raise ValueError("Provider configuration identity mismatch")
    pricing = provider["pricing"]
    # Only the owner-reviewed provider/model and known rates; no fallback, cache-write
    # rate or context/fee assumption is supplied by this controller.
    if (provider["model"]["name"] != "claude-opus-5-5"
            or provider["client"]["provider"] != "yibuapi"
            or pricing["currency"] != "USD"
            or any(Decimal(pricing["rates"][k]) != Decimal(v)
                   for k, v in {"input": "8", "output": "40", "cache_read": "0.4"}.items())):
        raise ValueError("Provider is outside the reviewed owner configuration")
    pr.reservation(provider["model"]["name"], provider["client"], pricing,
                   provider["spend_limit"], 1, now=now)
    return value


def ledger_store(api, config, number):
    key = PRKey(config["repository_id"], number)
    anchor = config["anchors"].get(str(number))
    if (not isinstance(anchor, dict)
            or set(anchor) != {"ref", "genesis_commit", "checkpoint_commit"}):
        raise BudgetError("Audited historical-spend genesis and trusted anchor required")
    return GitHubGitStore(api, LedgerAnchor(key=key, **anchor)), key


def live_label(api, plan, config):
    """Verify current state and latest applicable label action, not event sender/PR author."""
    if api.request("GET", "")["id"] != config["repository_id"]:
        raise ValueError("Repository identity changed")
    current = api.request("GET", f"/pulls/{plan['pr']}")
    if (current["base"].get("ref") != "main"
            or current["base"].get("repo", {}).get("id") != config["repository_id"]):
        raise ValueError("PR must target trusted repository main")
    if (current["state"] != "open" or current.get("draft", False)
            or current["base"]["sha"] != plan["base"]
            or current["head"]["sha"] != plan["head"]):
        raise ValueError("PR is closed, draft or revision changed")
    if config["label"] not in {label["name"] for label in current["labels"]}:
        raise ValueError("Execution label is absent")
    # Bounded complete pagination: full final short page required, no partial acceptance.
    events, last_id = [], 0
    for page in range(1, 101):
        batch = api.request("GET", f"/issues/{plan['pr']}/events?per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("Incomplete label history")
        for event in batch:
            if type(event.get("id")) is not int or event["id"] <= last_id:
                raise ValueError("Ambiguous label history")
            last_id = event["id"]
            if (event.get("event") in {"labeled", "unlabeled"}
                    and event.get("label", {}).get("name") == config["label"]):
                events.append(event)
        if len(batch) < 100:
            break
    else:
        raise ValueError("Label history exceeds safe pagination bound")
    if not events or events[-1]["event"] != "labeled":
        raise ValueError("No current label-add authorization")
    event = events[-1]
    actor = event["actor"]["login"]
    if actor not in config["operators"]:
        raise ValueError("Latest label-add actor is not an owner-authorized operator")
    path = f"/collaborators/{quote(actor, safe='')}/permission"
    permission = api.request("GET", path)["permission"]
    if permission not in {"admin", "maintain", "write"}:
        raise ValueError("Label operator no longer has trusted repository permission")
    # Require parseable action time; authorization TTL is the trusted configuration TTL.
    datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
    return {"actor": actor, "label_event_id": event["id"]}


def eligible(plan, config):
    if plan.get("version") != plan["base"]:
        raise ValueError("Automatic execution requires the current trusted main implementation")
    if not plan["estimated_calls"] or not plan["comparisons"]:
        raise ValueError("No meaningful mapped comparisons")
    if any(c.get("coverage") == "unsupported" for c in plan["coverage"]):
        raise ValueError("Unsupported changed scope")
    if any("plan_sha256" not in c for c in plan["comparisons"]):
        raise ValueError("Unsupported comparison")
    if plan.get("provider_config") != config["provider"]:
        raise ValueError("Plan does not bind the trusted provider configuration")
    if pr.provider_reservation(plan) != plan["reservation"]:
        raise ValueError("Expired or changed plan reservation")


def status(api, plan, config):
    store, key = ledger_store(api, config, plan["pr"])
    ledger = store.read_verified(key).ledger
    actual = ledger.genesis.legacy_charge + sum(e.actual_cost or 0 for e in ledger.entries)
    return {"label": config["label"], "spent_or_legacy_usd": str(Decimal(actual) / 1000000),
            "reserved_or_unresolved_usd": str(Decimal(ledger.charged - actual) / 1000000),
            "remaining_usd": str(Decimal(ledger.remaining) / 1000000)}


def controlled_execute(api, output, *, config_path=CONFIG, run_id, attempt, launch=None):
    from inferrsi.model.request_guard import authorization_broker

    plan = pr.compare.read_json(output / "pr-plan.json")
    config = configuration(config_path)
    eligible(plan, config)
    authorization = live_label(api, plan, config)
    if attempt != 1:
        raise ValueError("Execution reruns are blocked; publish retained evidence only")
    if not os.environ.get("SKILL_EVAL_YIBUAPI_KEY"):
        raise ValueError("Provider credential is unavailable; no reservation created")
    store, key = ledger_store(api, config, plan["pr"])
    amount = Decimal(plan["reservation"]["amount"]) * 1000000
    binding = Binding(pr.fingerprint(plan), f"{run_id}.{attempt}",
                      int(amount.to_integral_value(rounding=ROUND_CEILING)))
    snapshot = store.read_verified(key)
    successor = reserve(snapshot.ledger, binding)
    if (successor == snapshot.ledger
            or store.compare_and_swap(snapshot, successor) is not WriteResult.COMMITTED):
        raise BudgetError("Duplicate, conflicted or uncertain reservation; no paid execution")
    claim_once(store, key, binding)  # Not transferable: launch once in this process only.

    def check():
        fresh = configuration(config_path)
        if fresh != config:
            raise ValueError("Trusted configuration changed")
        eligible(plan, fresh)
        if live_label(api, plan, fresh) != authorization:
            raise ValueError("Label authorization changed")
        ledger = store.read_verified(key).ledger
        if not any(e.binding == binding and e.phase == "claimed" for e in ledger.entries):
            raise ValueError("Live ledger claim missing")

    write_json(output / "approval.json", {"execution_id": pr.execution_id(plan), **authorization})
    context = f"{binding.plan_digest}:{binding.run_id}"
    with authorization_broker(check, plan["reservation"]["requests"],
                              context=context) as guard_environment:
        # Allowlist: neither GitHub token nor Actions runtime/artifact write credentials
        # enter model execution. The provider subprocess applies its own tighter allowlist.
        environment = {k: os.environ[k] for k in ("PATH", "LANG", "SYSTEMROOT", "TEMP", "TMP",
                       "SKILL_EVAL_YIBUAPI_KEY") if k in os.environ}
        environment.update(guard_environment)
        environment["PYTHONPATH"] = str(pr.ROOT / "src")
        command = [sys.executable, "-c",
                   "from pathlib import Path; from tools.skill_eval_pr import "
                   "execute; import json,sys; p=Path(sys.argv[1]); "
                   "execute(p,json.loads((p/'approval.json').read_text()))", str(output)]
        (launch or subprocess.run)(command, cwd=pr.ROOT, env=environment, check=True)
    # No refund: missing/partial usage and cancellations retain the full reservation.


def report_control(api, plan):
    """Read-only publisher derivation; never trust an artifact's claimed budget state."""
    result = {"state": "blocked", "reason": "Trusted config / audited ledger unavailable",
              "spent_or_legacy_usd": "unknown", "reserved_or_unresolved_usd": "unknown",
              "remaining_usd": "unknown"}
    try:
        config = configuration()
        result["reason"] = "Audited PR ledger missing, unavailable or unsafe"
        result.update(status(api, plan, config))
        result["reason"] = "Plan has no supported pairs or provider/bounds are stale"
        eligible(plan, config)
        result["reason"] = "Current label, trusted operator permission or PR revision is invalid"
        live_label(api, plan, config)
        result.update(state="enabled", reason="Only an unconsumed reserved plan may execute")
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return result
