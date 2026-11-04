"""Explicit trusted incident stop; never admission, billing ingestion or unquarantine."""

import argparse
import json
import os
import re

from tools.skill_eval_auto import CONFIG, daily_store
from tools.skill_eval_budget import BudgetError, DailySnapshot, daily_quarantine
from tools.skill_eval_pr import GitHub


def evidence_reference(value):
    # Public incident references only; never accept arbitrary raw billing/error text,
    # credential URLs, query strings or fragments containing private payloads.
    if (not isinstance(value, str) or len(value) > 512 or not re.fullmatch(
            r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/"
            r"(?:issues|pull)/[1-9][0-9]*"
            r"(?:#(?:issuecomment|discussion_r|pullrequestreview)-[1-9][0-9]*)?",
            value)):
        raise BudgetError("A public GitHub incident evidence reference is required")
    return value


def persist_quarantine(store, key, evidence, *, attempts=3):
    """Only verified durable stop is success, including after a lost CAS receipt.

    Reread/retry is safe for this monotonic stop, NEVER for an execution grant.
    Any existing quarantine satisfies the stop; preserve its original evidence.
    A bounded failure is NOT success: caller must keep paid work stopped and
    escalate reconciliation, then retry this operation when storage is usable.
    Already issued/in-flight provider calls cannot be recalled by this operation.
    """
    evidence_reference(evidence)
    if type(attempts) is not int or not 1 <= attempts <= 10:
        raise BudgetError("Invalid bounded quarantine retry count")
    for _ in range(attempts):
        try:
            snapshot = store.read_verified(key)
            if type(snapshot) is not DailySnapshot or snapshot.ledger.key != key:
                raise BudgetError("Wrong global quarantine history")
            if snapshot.ledger.quarantine is not None:
                return snapshot
            successor = daily_quarantine(snapshot.ledger, evidence)
            # All receipts (including explicit COMMITTED) require fresh verified
            # readback. A competing admission can win; recompute against its tip.
            store.compare_and_swap(snapshot, successor)
        except (OSError, ValueError, KeyError, TypeError):
            # Never expose provider material, tokens, or backend exception text.
            continue
    # Last write may have committed despite lost response; final read is read-only.
    try:
        snapshot = store.read_verified(key)
        if (type(snapshot) is DailySnapshot and snapshot.ledger.key == key
                and snapshot.ledger.quarantine is not None):
            return snapshot
    except (OSError, ValueError, KeyError, TypeError):
        pass
    raise BudgetError("Global quarantine NOT verified; keep paid work stopped and reconcile")


def quarantine(api, evidence, *, config_path=CONFIG):
    """Trusted root anchor only; expired provider pricing must not prevent a stop."""
    evidence_reference(evidence)
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    store, key = daily_store(api, config)
    return persist_quarantine(store, key, evidence)


def main():
    parser = argparse.ArgumentParser(description="Persist global skill-eval incident quarantine")
    parser.add_argument("--repository", required=True, help="Trusted owner/repository")
    parser.add_argument("--evidence", required=True, help="Public GitHub incident reference")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("Invalid repository identity")
    try:
        evidence_reference(args.evidence)
        # Reuse the existing authenticated client; no provider key or model call.
        api = GitHub(args.repository, os.environ["GITHUB_TOKEN"])
        snapshot = quarantine(api, args.evidence)
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "Global quarantine NOT verified; keep paid work stopped and reconcile.\n")
    print(json.dumps({"state": "quarantine_verified", "revision": snapshot.ledger.revision}))


if __name__ == "__main__":
    main()
