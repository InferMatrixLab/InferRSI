"""Offline-capable admission seam for ONE paired KV editing feasibility pilot.

No CLI, ledger bootstrap, credential discovery, transport, workflow dispatch or
new storage schema. Only trusted controller code may supply policy/stores/checks
or call these methods; candidate/author artifacts are never spending authority.
The existing ledgers retain the entire bound even after errors and completion.
"""

import hashlib
import json
import math
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal

from inferrsi.model import anthropic_agent as provider
from tools import skill_eval_budget as budget

ARMS = ("A2", "A3")
CAMPAIGN_NAMESPACE = "kv-reclamation-one-pair-v1:"
MAX_ATTEMPTS_PER_ARM = 8
PER_REQUEST_MICROUSD = 10_170_000
FULL_RESERVATION_MICROUSD = 162_720_000
MAX_ARM_SECONDS = 600


def _identifier(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", value) is not None


def _sha(value, size=64):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(size) + "}", value) is not None


def _fingerprint(value):
    return hashlib.sha256(provider.canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class PilotPolicy:
    """Reviewed root configuration, NOT data accepted from a worker or PR.

    The plan digest binds visible task/K, verifier, schedule, artifact/isolation
    qualification and all source revisions. Per-arm actor digests bind the exact
    edit protocol/manifests. ``check_current`` independently revalidates this
    policy, authorized PR/head, source revision and qualification before spending.
    ``provider_json`` is canonical immutable JSON; mutable dicts are not retained.
    """

    campaign_id: str
    key: budget.PRKey
    execution_id: str
    plan_sha256: str
    pr_head: str
    source_revision: str
    actor_sha256: tuple[str, str]
    provider_json: str
    expires_at: int

    def __post_init__(self):
        if (not _identifier(self.campaign_id) or not _identifier(self.execution_id)
                or type(self.key) is not budget.PRKey or not _sha(self.plan_sha256)
                or not _sha(self.pr_head, 40) or not _sha(self.source_revision, 40)
                or type(self.actor_sha256) is not tuple or len(self.actor_sha256) != 2
                or any(not _sha(value) for value in self.actor_sha256)
                or type(self.expires_at) is not int or self.expires_at <= 0):
            raise budget.BudgetError("Invalid trusted pilot binding")
        self.reservation(now=0)

    def reservation(self, *, now):
        try:
            config = json.loads(self.provider_json)
            if (provider.canonical(config) != self.provider_json
                    or set(config) != {"model", "client", "pricing", "spend_limit"}
                    or config["model"] != {"name": "claude-opus-5-5",
                                           "effort": "not_applicable"}
                    or config["client"]["kind"] != provider.EDIT_KIND
                    or config["client"]["max_requests"] != MAX_ATTEMPTS_PER_ARM
                    or config["client"]["max_output_tokens"] != 4096
                    or config["pricing"]["currency"] != "USD"
                    or config["pricing"]["max_input_tokens"] != 1_000_000
                    or self.expires_at > config["pricing"]["expires_at"]
                    or self.expires_at <= now):
                raise ValueError("Unqualified pilot envelope")
            result = provider.reservation(config["model"]["name"], config["client"],
                                          config["pricing"], config["spend_limit"], 2, now=now)
            if (result["requests"] != 16
                    or Decimal(result["per_request"]) * 1_000_000 != PER_REQUEST_MICROUSD
                    or Decimal(result["amount"]) * 1_000_000 != FULL_RESERVATION_MICROUSD
                    or Decimal(result["limit"]) * 1_000_000 > budget.PR_LIMIT_MICROUSD):
                raise ValueError("Changed pilot reservation")
            return result
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise budget.BudgetError("Missing, changed or expired pilot pricing/bounds") from exc

    @property
    def binding(self):
        # Global run uniqueness plus the fixed namespace below prevents a new
        # digest, PR, date, workflow run/attempt or campaign ID from resetting it.
        return budget.Binding(_fingerprint(asdict(self)),
                              CAMPAIGN_NAMESPACE + self.campaign_id,
                              FULL_RESERVATION_MICROUSD)


def _now(clock):
    now = clock()
    budget.shanghai_day(now)  # Reject naive or malformed clocks before timestamp().
    return now


def _read_pair(policy, daily_store, pr_store):
    daily_key = budget.DailyKey(policy.key.repository_id)
    daily = daily_store.read_verified(daily_key)
    pr = pr_store.read_verified(policy.key)
    if (type(daily) is not budget.DailySnapshot or daily.ledger.key != daily_key
            or type(pr) is not budget.Snapshot or pr.ledger.key != policy.key):
        raise budget.BudgetError("Wrong verified ledger identity")
    daily.ledger.require_active()
    # An audited PR genesis is not enough if global historical obligations
    # disagree. In particular, an old PR tip subtotal cannot erase daily imports.
    retained_pr = sum(e.binding.worst_case for e in daily.ledger.entries if e.key == policy.key)
    if retained_pr != pr.ledger.charged:
        raise budget.BudgetError("Inconsistent historical daily/PR charges")
    return daily, pr


def _current(policy, check_current, wall_clock, admitted_day=None):
    now = _now(wall_clock)
    policy.reservation(now=now.timestamp())
    if check_current(policy) is not True:
        raise budget.BudgetError("Trusted pilot authorization or qualification changed")
    # The trusted live check can take time. Do not issue a stale boundary grant.
    now = _now(wall_clock)
    policy.reservation(now=now.timestamp())
    day = budget.shanghai_day(now)
    if admitted_day is not None and day != admitted_day:
        raise budget.BudgetError("Shanghai admission day ended")
    return day


def admit(policy, daily_store, pr_store, *, check_current,
          wall_clock=lambda: datetime.now(timezone.utc), monotonic_clock=time.monotonic):
    """Reserve/claim once, daily first, then return a process-local controller.

    Stores implement the EXISTING verified-read/CAS contracts and must already
    have audited genesis/checkpoints. No retries, missing-ledger initialization,
    takeover or reconciliation-to-grant is performed. Persisted partial writes
    burn capacity. A caller receiving an uncertain first write must stop, not
    blindly retry: an absent observation does not prove a write cannot arrive.
    """
    if (type(policy) is not PilotPolicy or not callable(check_current)
            or not callable(wall_clock) or not callable(monotonic_clock)):
        raise budget.BudgetError("Explicit trusted admission dependencies required")
    admitted_day = _current(policy, check_current, wall_clock)
    daily, pr = _read_pair(policy, daily_store, pr_store)
    if any(e.binding.run_id.startswith(CAMPAIGN_NAMESPACE) for e in daily.ledger.entries):
        raise budget.BudgetError("Pilot campaign already bound; no relaunch or replan")
    # One immutable campaign on one lifetime-capped PR is strictly below the
    # $1,000 task ceiling. Unrelated past campaigns are NOT new pilot spending;
    # daily_reserve still includes all relevant global charges and carryover.
    binding = policy.binding
    day_next = budget.daily_reserve(daily.ledger, policy.key, binding, admitted_day)
    pr_next = budget.reserve(pr.ledger, binding)  # Check BOTH caps before any write.
    _current(policy, check_current, wall_clock, admitted_day)
    for store, before, after in ((daily_store, daily, day_next), (pr_store, pr, pr_next)):
        if (after == before.ledger
                or store.compare_and_swap(before, after) is not budget.WriteResult.COMMITTED):
            raise budget.BudgetError("Duplicate, conflicted or uncertain pilot reservation")
    _current(policy, check_current, wall_clock, admitted_day)
    budget.daily_claim_once(daily_store, policy.key, binding,
                            budget.shanghai_day(_now(wall_clock)))
    budget.claim_once(pr_store, policy.key, binding)
    session = _Admission(policy, daily_store, pr_store, admitted_day,
                         check_current, wall_clock, monotonic_clock)
    session._check()  # Both durable claims, price and day checked AFTER all writes.
    return session


class _Admission:
    """Trusted supervisor state; never serialize or pass this object to workers.

    Call start_arm BEFORE disclosure/launch. authorize matches the edit protocol's
    exact grant and returns True, not a transferable token. complete requires the
    SAME grant plus RAW four-class usage from trusted transport/worker observation,
    never candidate-authored JSON or an unverified trace. Only one request may be
    pending; missing/unknown usage in either arm stops both. No method refunds or
    closes durable ledger charges. A process crash burns both durable claims.
    """

    def __init__(self, policy, daily_store, pr_store, day, check, wall, monotonic):
        self.policy, self._daily_store, self._pr_store = policy, daily_store, pr_store
        self._day, self._check_current = day, check
        self._wall, self._monotonic = wall, monotonic
        self._used = dict.fromkeys(ARMS, 0)
        self._deadlines = {}
        self._finished = set()
        self._pending = None
        self._stopped = False
        self._lock = threading.Lock()

    def __reduce__(self):
        raise TypeError("Pilot admission is process-local and nontransferable")

    def _check(self):
        if self._stopped:
            raise budget.BudgetError("Pilot admission stopped")
        daily, pr = _read_pair(self.policy, self._daily_store, self._pr_store)
        binding = self.policy.binding
        if (not any(e.binding == binding and e.phase == "claimed" for e in pr.ledger.entries)
                or not any(e.key == self.policy.key and e.binding == binding
                           and e.phase == "claimed" and e.admitted_day == self._day
                           for e in daily.ledger.entries)):
            raise budget.BudgetError("Both exact durable pilot claims are required")
        _current(self.policy, self._check_current, self._wall, self._day)

    def context(self, arm):
        if arm not in ARMS:
            raise budget.BudgetError("Unknown pilot arm")
        return f"{self.policy.binding.plan_digest}:{self.policy.binding.run_id}:{arm}"

    def start_arm(self, arm, absolute_deadline):
        """Trusted supervisor only, immediately BEFORE task disclosure."""
        with self._lock:
            try:
                self._check()
                remaining = absolute_deadline - self._monotonic()
                if (arm not in ARMS or arm in self._deadlines or self._pending is not None
                        or set(self._deadlines) - self._finished
                        or type(absolute_deadline) not in (int, float)
                        or not math.isfinite(absolute_deadline)
                        or not 0 < remaining <= MAX_ARM_SECONDS):
                    raise budget.BudgetError("Invalid, repeated or overlapping arm launch")
                self._deadlines[arm] = absolute_deadline
            except BaseException:
                self._stopped = True
                raise

    def authorize(self, grant, absolute_deadline):
        """Burn one per-arm/global attempt before live checks, then permit ONE send."""
        with self._lock:
            try:
                arm = grant.get("arm") if type(grant) is dict else None
                if (self._stopped or self._pending is not None or arm not in self._deadlines
                        or arm in self._finished or self._used[arm] >= MAX_ATTEMPTS_PER_ARM):
                    raise budget.BudgetError("Pilot request allocation unavailable")
                self._used[arm] += 1  # No failure after this point restores a slot.
                expected = {"plan_sha256": self.policy.plan_sha256,
                            "execution_id": self.policy.execution_id, "arm": arm,
                            "slot": self._used[arm],
                            "request_sha256": grant.get("request_sha256"),
                            "actor_sha256": self.policy.actor_sha256[ARMS.index(arm)],
                            "reserved_microusd": PER_REQUEST_MICROUSD}
                if (grant != expected or type(grant.get("slot")) is not int
                        or type(grant.get("reserved_microusd")) is not int
                        or not _sha(grant.get("request_sha256"))
                        or absolute_deadline != self._deadlines[arm]):
                    raise budget.BudgetError("Request differs from frozen pilot binding")
                self._pending = dict(expected)  # Lost/ambiguous grant stays unresolved.
                self._check()
                if self._monotonic() >= absolute_deadline:
                    raise budget.BudgetError("Frozen arm deadline ended")
                return True
            except BaseException:
                self._stopped = True
                raise

    def complete(self, grant, raw_usage):
        """Record trusted observed usage only; never a refund or restart permit."""
        with self._lock:
            try:
                if (self._stopped or self._pending is None or type(grant) is not dict
                        or provider.canonical(grant) != provider.canonical(self._pending)):
                    raise budget.BudgetError("Missing or inconsistent request completion")
                usage = provider.token_usage(raw_usage)
                if usage["input_tokens"] > 1_000_000 or usage["output_tokens"] > 4096:
                    raise budget.BudgetError("Observed usage exceeds reserved request bound")
                self._pending = None
            except BaseException:
                self._stopped = True
                raise

    def finish_arm(self, arm):
        """Keep failure/missing artifacts externally; unknown usage cannot finish."""
        with self._lock:
            if (self._stopped or self._pending is not None or arm not in self._deadlines
                    or arm in self._finished):
                self._stopped = True
                raise budget.BudgetError("Unresolved, unknown or repeated arm completion")
            self._finished.add(arm)

    def attempts(self):
        with self._lock:
            return dict(self._used)

    def close(self):
        with self._lock:
            self._stopped = True


def run_admitted(policy, daily_store, pr_store, *, launch, **dependencies):
    """Invoke the injected TRUSTED launch callback once after both durable claims.

    Intended for fake/offline integration until independently reviewed real launch
    wiring is supplied. This module itself performs no provider or process call.
    """
    if not callable(launch):
        raise budget.BudgetError("A trusted launch callback is required")
    session = admit(policy, daily_store, pr_store, **dependencies)
    try:
        return launch(session)
    finally:
        session.close()
