"""Fail-closed GitHub Git-data ledger adapter; never initializes a ledger.

The caller supplies the existing authenticated GitHub API client and trusted
root configuration, never values from a PR checkout/artifact. See the budget
contract for the administrator/rollback trust boundary.
"""

import base64
import binascii
import re
import uuid
from dataclasses import dataclass

from tools.skill_eval_budget import (
    BudgetError,
    DailyKey,
    DailySnapshot,
    Ledger,
    PRKey,
    Snapshot,
    WriteResult,
    decode,
    decode_daily,
    encode,
    encode_daily,
    validate_daily_successor,
    validate_successor,
)


def _sha(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise BudgetError("Invalid Git object identity")
    return value


@dataclass(frozen=True)
class LedgerAnchor:
    """Reviewed root configuration, pinned independently of the mutable ref.

    Genesis is audited and contains only ledger.json. It may have no parent or
    one audited existing-main parent; that ancestry is outside ledger history.
    Checkpoint is an independently retained known tip (genesis at first setup).
    Refreshing checkpoints strengthens rollback detection, never refunds spend.
    """

    key: PRKey
    ref: str
    genesis_commit: str
    checkpoint_commit: str

    def __post_init__(self):
        if type(self.key) is not PRKey:
            raise BudgetError("Invalid immutable PR identity")
        expected_ref = f"refs/heads/skill-eval-budget/{self.key.repository_id}/{self.key.pr_number}"
        if self.ref != expected_ref:
            raise BudgetError("Ledger must use its dedicated immutable PR ref")
        _sha(self.genesis_commit)
        _sha(self.checkpoint_commit)


class GitHubGitStore:
    """Single-parent, unique-commit, non-force fast-forward CAS.

    A failed/uncertain PATCH is UNKNOWN, never an execution grant. Each commit
    has a random operation nonce so simultaneous identical claims cannot share
    a commit SHA and both receive successful idempotent ref-update responses.
    No ref creation, deletion, force update, or settings endpoint is used.
    """

    anchor_type = LedgerAnchor
    snapshot_type = Snapshot
    decode_state = staticmethod(decode)
    encode_state = staticmethod(encode)
    validate_transition = staticmethod(validate_successor)

    def valid_genesis(self, ledger):
        return ledger.revision == 0 and not ledger.entries

    def __init__(self, api, anchor: LedgerAnchor, *, max_history=10000):
        if type(anchor) is not self.anchor_type or type(max_history) is not int or max_history < 1:
            raise BudgetError("Trusted anchor and bounded history are required")
        self.api, self.anchor, self.max_history = api, anchor, max_history
        self._observed = anchor.checkpoint_commit

    def _get(self, path):
        try:
            value = self.api.request("GET", path)
            if type(value) is not dict:
                raise ValueError("Not an object")
            return value
        except Exception:
            raise BudgetError("Ledger read failed; uncertain history blocks work") from None

    def _tip(self):
        value = self._get("/git/ref/" + self.anchor.ref.removeprefix("refs/"))
        try:
            if value["ref"] != self.anchor.ref or value["object"]["type"] != "commit":
                raise ValueError("Invalid ref")
            return _sha(value["object"]["sha"])
        except (KeyError, TypeError, ValueError):
            raise BudgetError("Invalid ledger ref") from None

    def _state(self, commit_sha):
        try:
            commit = self._get("/git/commits/" + commit_sha)
            if commit["sha"] != commit_sha or type(commit["parents"]) is not list:
                raise ValueError("Invalid commit")
            parents = [_sha(p["sha"]) for p in commit["parents"]]
            tree_sha = _sha(commit["tree"]["sha"])
            tree = self._get("/git/trees/" + tree_sha)
            if tree["sha"] != tree_sha or tree.get("truncated") is not False:
                raise ValueError("Incomplete tree")
            entries = tree["tree"]
            if (type(entries) is not list or len(entries) != 1
                    or entries[0]["path"] != "ledger.json"
                    or entries[0]["mode"] != "100644" or entries[0]["type"] != "blob"):
                raise ValueError("Invalid ledger tree")
            blob_sha = _sha(entries[0]["sha"])
            blob = self._get("/git/blobs/" + blob_sha)
            if blob["sha"] != blob_sha or blob["encoding"] != "base64":
                raise ValueError("Invalid ledger blob")
            raw = base64.b64decode("".join(blob["content"].split()), validate=True)
            if len(raw) > 4_000_000 or blob["size"] != len(raw):
                raise ValueError("Invalid ledger size")
            ledger = self.decode_state(raw.decode("utf-8"))
            if ledger.key != self.anchor.key:
                raise ValueError("Wrong PR identity")
            return parents, ledger
        except (KeyError, TypeError, ValueError, UnicodeError, binascii.Error):
            raise BudgetError("Corrupt or incomplete ledger history") from None

    def read_verified(self, key: PRKey) -> Snapshot:
        if key != self.anchor.key:
            raise BudgetError("Wrong PR key for trusted anchor")
        repository_id = self._get("").get("id")
        if type(repository_id) is not int or repository_id != key.repository_id:
            raise BudgetError("Repository identity changed")
        tip = current = self._tip()
        seen, states = set(), []
        for _ in range(self.max_history):
            if current in seen:
                raise BudgetError("Cyclic ledger history")
            seen.add(current)
            parents, ledger = self._state(current)
            states.append(ledger)
            if current == self.anchor.genesis_commit:
                if len(parents) > 1 or not self.valid_genesis(ledger):
                    raise BudgetError("Invalid audited genesis")
                break
            if len(parents) != 1:
                raise BudgetError("Ledger must be a complete single-parent history")
            current = parents[0]
        else:
            raise BudgetError("Ledger history exceeds verification bound")
        if self.anchor.checkpoint_commit not in seen or self._observed not in seen:
            raise BudgetError("Ledger rollback or divergent history detected")
        for before, after in zip(reversed(states[1:]), reversed(states[:-1])):
            self.validate_transition(before, after)
        # A racing writer is harmless, but do not label an already stale read current.
        if self._tip() != tip:
            raise BudgetError("Ledger changed during verification; retry a fresh read")
        self._observed = tip
        return self.snapshot_type(tip, states[0])

    def compare_and_swap(self, expected: Snapshot, successor: Ledger) -> WriteResult:
        self.validate_transition(expected.ledger, successor)
        verified = self.read_verified(self.anchor.key)
        if verified != expected:
            return WriteResult.CONFLICT
        try:
            tree = self.api.request("POST", "/git/trees", {"tree": [{
                "path": "ledger.json", "mode": "100644", "type": "blob",
                "content": self.encode_state(successor),
            }]})
            tree_sha = _sha(tree["sha"])
            commit = self.api.request("POST", "/git/commits", {
                "message": "budget append " + uuid.uuid4().hex,
                "tree": tree_sha, "parents": [expected.token],
            })
            commit_sha = _sha(commit["sha"])
            updated = self.api.request(
                "PATCH", "/git/refs/" + self.anchor.ref.removeprefix("refs/"),
                {"sha": commit_sha, "force": False})
            if (updated["ref"] != self.anchor.ref or updated["object"]["type"] != "commit"
                    or updated["object"]["sha"] != commit_sha):
                return WriteResult.UNKNOWN
        except Exception:
            # Includes rule/permission rejection and uncertain or lost responses.
            # Never reconcile a claim by treating an observed commit as our grant.
            return WriteResult.UNKNOWN
        self._observed = commit_sha
        return WriteResult.COMMITTED


@dataclass(frozen=True)
class DailyLedgerAnchor:
    """One independently pinned repository-wide ledger; never a per-day ref."""

    key: DailyKey
    ref: str
    genesis_commit: str
    checkpoint_commit: str

    def __post_init__(self):
        if type(self.key) is not DailyKey:
            raise BudgetError("Invalid global ledger identity")
        if self.ref != f"refs/heads/skill-eval-budget/{self.key.repository_id}/daily":
            raise BudgetError("Global budget requires its single repository-wide ref")
        _sha(self.genesis_commit)
        _sha(self.checkpoint_commit)


class GitHubDailyStore(GitHubGitStore):
    """Reuse the same nonce-bearing Git CAS and full lineage verification.

    Genesis is separately audited, including imported historical and outstanding
    entries. This adapter never creates or resets it. Existing PR ledgers remain
    independently mandatory; commit daily admission first, then PR admission,
    then both one-shot claims before launching. Partial failures burn capacity.
    """

    anchor_type = DailyLedgerAnchor
    snapshot_type = DailySnapshot
    decode_state = staticmethod(decode_daily)
    encode_state = staticmethod(encode_daily)
    validate_transition = staticmethod(validate_daily_successor)

    def valid_genesis(self, ledger):
        return ledger.revision == 0
