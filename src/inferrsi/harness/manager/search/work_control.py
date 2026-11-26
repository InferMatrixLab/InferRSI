"""Campaign accounting and CAS in the shared RunStore database.

This is a controller for trusted host operations, not an executor or sandbox.
All cooperating controllers must share the same RunStore for resource domains
and holdout scopes to be exclusive. Unknown work retains at least its entire
reservation and any larger known usage lower bound.
"""

import json
import math
import time
from contextlib import contextmanager

from inferrsi.harness.records.artifact_primitives import digest, file_lock


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _positive(value):
    if type(value) is not int or value <= 0:
        raise ValueError("Work limits must be positive integer milliseconds")


class WorkControl:
    # Included in the binding so an older finalizer cannot join a guarded claim.
    FINAL_OWNER_PROTOCOL = "campaign-file-lock-v1"

    def __init__(self, store):
        self.store = store
        if store.read_only:
            return
        with store.work_control_connection(write=True) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS work_campaigns "
                "(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS work_domains "
                "(id TEXT PRIMARY KEY, campaign TEXT NOT NULL, operation TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS work_holdouts "
                "(scope TEXT PRIMARY KEY, campaign TEXT NOT NULL, binding TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS work_holdout_aliases "
                "(previous_scope TEXT PRIMARY KEY, scope TEXT NOT NULL)"
            )

    @contextmanager
    def _transaction(self, campaign, revision=None):
        with self.store.work_control_connection(write=True) as db:
            row = db.execute(
                "SELECT revision, body FROM work_campaigns WHERE id=?", (campaign,)
            ).fetchone()
            if row is None:
                raise ValueError("Unknown campaign")
            if revision is not None and row[0] != revision:
                raise ValueError("Stale campaign revision")
            body = json.loads(row[1])
            yield db, body
            db.execute(
                "UPDATE work_campaigns SET revision=?, body=? WHERE id=?",
                (row[0] + 1, _json(body), campaign),
            )

    def create(self, campaign, contract, state, *, cap_ms, final_reserve_ms, deadline):
        _positive(cap_ms)
        _positive(final_reserve_ms)
        if (
            not campaign
            or final_reserve_ms >= cap_ms
            or not math.isfinite(deadline)
            or deadline <= time.time()
        ):
            raise ValueError("Invalid campaign budget or deadline")
        body = {
            "contract": contract,
            "contract_digest": digest(contract),
            "state": state,
            "cap_ms": cap_ms,
            "final_reserve_ms": final_reserve_ms,
            "deadline": deadline,
            "spent_ms": 0,
            "operations": {},
            "events": [],
            "final_claim": None,
            "final_result": None,
            "blocked": False,
        }
        with self.store.work_control_connection(write=True) as db:
            db.execute("INSERT INTO work_campaigns VALUES (?, 0, ?)", (campaign, _json(body)))
        return self.read(campaign)

    def read(self, campaign):
        with self.store.work_control_connection() as db:
            row = db.execute(
                "SELECT revision, body FROM work_campaigns WHERE id=?", (campaign,)
            ).fetchone()
        if row is None:
            raise ValueError("Unknown campaign")
        body = json.loads(row[1])
        if digest(body["contract"]) != body["contract_digest"]:
            raise ValueError("Frozen campaign contract changed")
        return {"revision": row[0], **body}

    @contextmanager
    def final_owner(self, campaign):
        """Exclude live finalizers across processes using the same campaign database."""
        if self.store.read_only:
            raise ValueError("Recovering a pending final requires a writable RunStore")
        # SQLite's TEXT key can identify the same row for e.g. 1 and "1".
        # Derive both the lock and new operation IDs from the stored identity.
        with self.store.work_control_connection() as db:
            row = db.execute("SELECT id FROM work_campaigns WHERE id=?", (campaign,)).fetchone()
        if row is None:
            raise ValueError("Unknown campaign")
        with file_lock(self.store.root / (".final-" + digest(row[0]) + ".lock")):
            yield row[0]

    @staticmethod
    def available(body, *, final=False):
        held = sum(
            max(op["cap_ms"], op.get("known_ms", 0))
            for op in body["operations"].values()
            if op["status"] != "settled"
        )
        return body["cap_ms"] - body["spent_ms"] - held - (0 if final else body["final_reserve_ms"])

    def update(self, campaign, revision, transition):
        """Persist a pure state transition and incumbent recomputation in one CAS."""
        with self._transaction(campaign, revision) as (_, body):
            if body["blocked"] or body["final_claim"] is not None:
                raise ValueError("Campaign transitions are blocked or final selection is frozen")
            body["state"] = transition(body["state"])
        return self.read(campaign)

    def claim(
        self,
        campaign,
        revision,
        operation,
        *,
        category,
        cap_ms,
        domains=(),
        binding,
        final=False,
        transition=None,
    ):
        _positive(cap_ms)
        domains = tuple(sorted(set(domains)))
        if not operation or not category or any(not item for item in domains):
            raise ValueError("Missing operation or resource identity")
        if final != (category == "final"):
            raise ValueError("Final reservations require the final work category")
        with self._transaction(campaign, revision) as (db, body):
            if operation in body["operations"]:
                raise ValueError("Operation already claimed; recover without relaunch")
            if body["final_result"] is not None:
                raise ValueError("Campaign final result is immutable")
            if body["blocked"] or (body["final_claim"] is not None and not final):
                raise ValueError("Campaign is blocked or final selection is frozen")
            if final and body["final_claim"] is None:
                raise ValueError("Final work requires a durable one-time claim")
            if time.time() >= body["deadline"] or cap_ms > self.available(body, final=final):
                raise ValueError("Work exceeds remaining budget or deadline")
            for domain in domains:
                if db.execute("SELECT 1 FROM work_domains WHERE id=?", (domain,)).fetchone():
                    raise ValueError("Measurement domain is already leased")
                db.execute(
                    "INSERT INTO work_domains VALUES (?, ?, ?)", (domain, campaign, operation)
                )
            body["operations"][operation] = {
                "category": category,
                "binding": binding,
                "cap_ms": cap_ms,
                "domains": domains,
                "status": "claimed",
                "receipt": None,
                "deadline": min(body["deadline"], time.time() + cap_ms / 1000),
                "execution_key": operation,
            }
            body["events"].append({"kind": "claimed", "operation": operation, "at": time.time()})
            if transition is not None:
                body["state"] = transition(body["state"])
        return self.read(campaign)

    def reconcile_blocked(self, campaign, revision, operation, transition):
        """Archive settled work in consumer state without reopening the campaign.

        The transition must not adopt the operation's output as usable evidence.
        Accounting, receipts and the dispatch block remain unchanged.
        """
        with self._transaction(campaign, revision) as (_, body):
            if not body["blocked"] or body["operations"][operation]["status"] != "settled":
                raise ValueError("Blocked recovery requires conclusively settled work")
            body["state"] = transition(body["state"])
        return self.read(campaign)

    @staticmethod
    def _stop_reason(body, op, now):
        if body["final_result"] is not None:
            return "finalized"
        if body["blocked"]:
            return "blocked"
        if now >= op["deadline"]:
            return "deadline"
        return None

    @staticmethod
    def _release_unstarted(db, campaign, body, operation, reason, now):
        body["operations"][operation].update(
            status="settled", actual_ms=0, receipt={"not_started": reason}
        )
        db.execute(
            "DELETE FROM work_domains WHERE campaign=? AND operation=?", (campaign, operation)
        )
        body["events"].append({"kind": "not_started", "operation": operation, "at": now})

    def recover_unstarted(self, campaign):
        """Release stopped reservations only while their launch intent is still absent."""
        doc = self.read(campaign)
        now = time.time()
        if not any(
            op["status"] == "claimed" and self._stop_reason(doc, op, now)
            for op in doc["operations"].values()
        ):
            return doc
        with self._transaction(campaign) as (db, body):
            now = time.time()
            for name, op in body["operations"].items():
                if op["status"] == "claimed" and (reason := self._stop_reason(body, op, now)):
                    self._release_unstarted(db, campaign, body, name, reason, now)
        return self.read(campaign)

    def launch(self, campaign, operation):
        """Persist intent before external launch. A crash here must never relaunch."""
        with self._transaction(campaign) as (db, body):
            op = body["operations"][operation]
            if op["status"] != "claimed":
                raise ValueError("Operation is no longer awaiting launch")
            now = time.time()
            reason = self._stop_reason(body, op, now)
            if reason:
                self._release_unstarted(db, campaign, body, operation, reason, now)
            else:
                op.update(status="launched", started_at=now)
                body["events"].append({"kind": "launch_intent", "operation": operation, "at": now})
        # Signal refusal after the transaction has committed the release.
        if reason == "finalized":
            raise ValueError("Campaign finalized before launch")
        if reason == "blocked":
            raise ValueError("Campaign blocked before launch")
        if reason == "deadline":
            raise ValueError("Deadline expired before launch")
        return op

    def settle(self, campaign, operation, receipt, *, actual_ms, cleanup_verified, transition=None):
        """Only authenticated, owner-scoped receipts may be passed by the adapter.

        Receipt replay is idempotent. Evidence and accounting commit together.
        Unknown usage/cleanup does not release the domain or budget reservation.
        """
        if actual_ms is not None and (type(actual_ms) is not int or actual_ms < 0):
            raise ValueError("Usage must be nonnegative integer milliseconds or unknown")
        with self._transaction(campaign) as (db, body):
            op = body["operations"][operation]
            settlement = {
                "receipt": receipt,
                "actual_ms": actual_ms,
                "cleanup_verified": cleanup_verified,
            }
            if op["status"] == "settled":
                if _json(op.get("settlement")) != _json(settlement):
                    raise ValueError("Conflicting duplicate settlement")
                return
            if op["status"] not in ("launched", "unknown"):
                raise ValueError("Cannot settle an unlaunched operation")
            known_ms = max(op.get("known_ms", 0), actual_ms or 0)
            if cleanup_verified is True and actual_ms is not None and actual_ms < known_ms:
                raise ValueError("Final usage cannot be below previously known usage")
            op["known_ms"] = known_ms
            executable_ms = min(op["cap_ms"], (op["deadline"] - op["started_at"]) * 1000)
            # Cleanup uncertainty cannot erase an observed overrun. Keep the
            # domain and conservative hold until reconciliation, blocking any
            # further work immediately, including work on other domains.
            if known_ms > executable_ms:
                body["blocked"] = True
            op["settlement"] = settlement
            if actual_ms is None or cleanup_verified is not True:
                op["status"] = "unknown"
                body["events"].append(
                    {"kind": "unknown", "operation": operation, "at": time.time()}
                )
            else:
                op.update(status="settled", actual_ms=actual_ms, receipt=receipt)
                body["spent_ms"] += actual_ms
                if body["spent_ms"] > body["cap_ms"]:
                    body["blocked"] = True
                if transition is not None and not body["blocked"]:
                    body["state"] = transition(body["state"])
                db.execute(
                    "DELETE FROM work_domains WHERE campaign=? AND operation=?",
                    (campaign, operation),
                )
                body["events"].extend(
                    [
                        {"kind": "cleanup_confirmed", "operation": operation, "at": time.time()},
                        {"kind": "released", "operation": operation, "at": time.time()},
                    ]
                )
        return self.read(campaign)

    def bind_consumed_holdout(self, previous_scope, resolve_scope):
        """Resolve a consumed claim from archived inputs without reopening a final."""
        with self.store.work_control_connection(write=True) as db:
            if not db.execute(
                "SELECT 1 FROM work_holdouts WHERE scope=?", (previous_scope,)
            ).fetchone():
                raise ValueError("Previous holdout scope has not been consumed")
            scope = resolve_scope()
            alias = db.execute(
                "SELECT scope FROM work_holdout_aliases WHERE previous_scope=?", (previous_scope,)
            ).fetchone()
            if alias is None:
                db.execute(
                    "INSERT INTO work_holdout_aliases VALUES (?, ?)", (previous_scope, scope)
                )
            elif alias[0] != scope:
                raise ValueError("Consumed holdout scope already maps to another identity")
        return scope

    def claim_final(self, campaign, revision, scope, binding, *, previous_scope_prefix=None):
        """Consume a shared holdout scope before any access, including interrupted access."""
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError("Holdout scope must have a nonempty identity")
        with self._transaction(campaign, revision) as (db, body):
            if (
                body["final_claim"] is not None
                or body["blocked"]
                or any(op["status"] != "settled" for op in body["operations"].values())
            ):
                raise ValueError("Final is already claimed or work remains unresolved")
            if time.time() >= body["deadline"]:
                raise ValueError("Final deadline exhausted")
            if previous_scope_prefix is not None:
                unmapped = db.execute(
                    "SELECT h.scope FROM work_holdouts h LEFT JOIN work_holdout_aliases a "
                    "ON h.scope=a.previous_scope WHERE a.previous_scope IS NULL "
                    "AND substr(h.scope, 1, length(?))=? LIMIT 1",
                    (previous_scope_prefix, previous_scope_prefix),
                ).fetchone()
                if unmapped is not None:
                    raise ValueError(
                        f"Unmapped legacy holdout {unmapped[0]}. "
                        "Bind its verified archived input before claiming a new scope."
                    )
            if db.execute(
                "SELECT 1 FROM work_holdouts WHERE scope=? UNION ALL "
                "SELECT 1 FROM work_holdout_aliases WHERE scope=? LIMIT 1", (scope, scope)
            ).fetchone():
                raise ValueError("Holdout scope already consumed in this RunStore")
            db.execute(
                "INSERT INTO work_holdouts VALUES (?, ?, ?)", (scope, campaign, _json(binding))
            )
            body["final_claim"] = {"scope": scope, "binding": binding}
        return self.read(campaign)

    def finish_final(self, campaign, binding, result, *, transition=None, unreserved=()):
        with self._transaction(campaign) as (_, body):
            if body["final_claim"] is None or _json(body["final_claim"]["binding"]) != _json(
                binding
            ):
                raise ValueError("Final result does not match the frozen selection")
            if body["final_result"] is not None:
                if _json(body["final_result"]) != _json(result):
                    raise ValueError("Final result is immutable; export the existing result")
                return
            if any(op["status"] != "settled" for op in body["operations"].values()):
                raise ValueError("Unknown final usage or cleanup; recover the existing receipt")
            if unreserved:
                # Check absence again under the write transaction. A legacy owner did
                # not take the OS lock and can still register work until dispatch stops.
                if any(op["category"] == "final" and op["binding"].get("check") in unreserved
                       for op in body["operations"].values()):
                    raise ValueError("Final reservations changed; recover the registered checks")
                if (binding.get("final_owner") != self.FINAL_OWNER_PROTOCOL
                        and not body["blocked"] and time.time() < body["deadline"]):
                    raise ValueError("Legacy final owner may still reserve checks before deadline")
                if result.get("verdict") != "INCONCLUSIVE" or transition is not None:
                    raise ValueError("Unreserved final checks require an INCONCLUSIVE result")
            if transition is not None and (body["blocked"] or result.get("verdict") != "PASS"):
                raise ValueError("Unresolved or over-budget work cannot promote a candidate")
            body["final_result"] = result
            if transition is not None:
                body["state"] = transition(body["state"])
        return self.read(campaign)
