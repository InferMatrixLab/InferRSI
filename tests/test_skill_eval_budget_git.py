"""Credential-free Git-data API model; no remote writes/provider requests."""

import base64
import copy
import hashlib
import json
from dataclasses import replace

import pytest

from tools import skill_eval_budget as budget
from tools.skill_eval_budget_git import GitHubGitStore, LedgerAnchor

KEY = budget.PRKey(123, 7)
REF = "refs/heads/skill-eval-budget/123/7"


def binding(number=1, amount=50_000_000):
    return budget.Binding(f"{number:064x}", f"run-{number}:attempt-1", amount)


class GitAPI:
    """Immutable objects plus non-force fast-forward reference updates."""

    def __init__(self):
        self.objects, self.calls = {}, []
        self.tip = None
        self.before_patch = None
        self.lose_response = False
        self.reject_write = False
        self.repository_id = KEY.repository_id
        ledger = budget.Ledger(KEY, budget.Genesis("audited legacy fixture", 0))
        self.genesis = self.append(ledger, parents=[])
        self.anchor = LedgerAnchor(KEY, REF, self.genesis, self.genesis)

    def put(self, value):
        sha = hashlib.sha1(json.dumps(value, sort_keys=True).encode()).hexdigest()
        self.objects[sha] = {**value, "sha": sha}
        return sha

    def tree(self, content):
        raw = content.encode()
        blob = self.put({"encoding": "base64", "size": len(raw),
                         "content": base64.b64encode(raw).decode()})
        return self.put({"truncated": False, "tree": [{"path": "ledger.json",
                         "mode": "100644", "type": "blob", "sha": blob}]})

    def append(self, ledger, parents=None):
        tree = self.tree(budget.encode(ledger))
        parents = [self.tip] if parents is None else parents
        self.tip = self.put({"tree": {"sha": tree},
                             "parents": [{"sha": p} for p in parents]})
        return self.tip

    def ref(self):
        if self.tip is None:
            raise OSError("404")
        return {"ref": REF, "object": {"type": "commit", "sha": self.tip}}

    def request(self, method, path, data=None):
        self.calls.append((method, path, copy.deepcopy(data)))
        if method == "GET":
            if path == "":
                return {"id": self.repository_id}
            if path.startswith("/git/ref/"):
                return self.ref()
            return copy.deepcopy(self.objects[path.rsplit("/", 1)[1]])
        if self.reject_write:
            raise OSError("rules reject writes")
        if path == "/git/trees":
            assert set(data) == {"tree"}
            return {"sha": self.tree(data["tree"][0]["content"])}
        if path == "/git/commits":
            return {"sha": self.put({"tree": {"sha": data["tree"]},
                    "parents": [{"sha": p} for p in data["parents"]],
                    "message": data["message"]})}
        assert method == "PATCH" and path == "/git/refs/heads/skill-eval-budget/123/7"
        assert data["force"] is False
        if self.before_patch:
            callback, self.before_patch = self.before_patch, None
            callback()
        if self.tip is None:
            raise OSError("404")
        parents = self.objects[data["sha"]]["parents"]
        if self.tip != data["sha"] and parents != [{"sha": self.tip}]:
            raise OSError("422 non fast-forward")
        self.tip = data["sha"]
        if self.lose_response:
            raise TimeoutError("lost response after commit")
        return self.ref()


def test_real_adapter_read_reserve_claim_and_permanent_charge():
    api = GitAPI()
    store = GitHubGitStore(api, api.anchor)
    snap = store.read_verified(KEY)
    reserved = budget.reserve(snap.ledger, binding())
    assert store.compare_and_swap(snap, reserved) is budget.WriteResult.COMMITTED
    claimed = budget.claim_once(store, KEY, binding())
    assert claimed.charged == 50_000_000
    with pytest.raises(budget.BudgetError):
        budget.claim_once(store, KEY, binding())
    snap = store.read_verified(KEY)
    done = budget.advance(snap.ledger, binding(), "finished", actual_cost=1)
    assert store.compare_and_swap(snap, done) is budget.WriteResult.COMMITTED
    assert store.read_verified(KEY).ledger.remaining == 150_000_000


def test_racing_identical_claim_has_only_one_grant_and_unique_commit():
    api = GitAPI()
    a, b = GitHubGitStore(api, api.anchor), GitHubGitStore(api, api.anchor)
    snap = a.read_verified(KEY)
    a.compare_and_swap(snap, budget.reserve(snap.ledger, binding()))
    grants = []
    api.before_patch = lambda: grants.append(budget.claim_once(b, KEY, binding()))
    with pytest.raises(budget.BudgetError):
        budget.claim_once(a, KEY, binding())
    assert len(grants) == 1
    messages = [data["message"] for method, path, data in api.calls
                if path == "/git/commits"]
    assert len(messages) == len(set(messages))


def test_racing_reservations_cannot_overwrite_or_exceed_cap():
    api = GitAPI()
    a, b = GitHubGitStore(api, api.anchor), GitHubGitStore(api, api.anchor)
    snap = a.read_verified(KEY)
    one = budget.reserve(snap.ledger, binding(1, 150_000_000))
    two = budget.reserve(snap.ledger, binding(2, 150_000_000))
    api.before_patch = lambda: b.compare_and_swap(snap, two)
    assert a.compare_and_swap(snap, one) is budget.WriteResult.UNKNOWN
    latest = a.read_verified(KEY)
    assert latest.ledger == two
    assert a.compare_and_swap(snap, one) is budget.WriteResult.CONFLICT
    with pytest.raises(budget.BudgetError):
        budget.reserve(latest.ledger, binding(1, 150_000_000))


@pytest.mark.parametrize("phase", ["reserved", "claimed"])
def test_unknown_write_is_never_execution_permission(phase):
    api = GitAPI()
    store = GitHubGitStore(api, api.anchor)
    snap = store.read_verified(KEY)
    reserved = budget.reserve(snap.ledger, binding())
    if phase == "claimed":
        store.compare_and_swap(snap, reserved)
        api.lose_response = True
        with pytest.raises(budget.BudgetError):
            budget.claim_once(store, KEY, binding())
        api.lose_response = False
        with pytest.raises(budget.BudgetError):
            budget.claim_once(GitHubGitStore(api, api.anchor), KEY, binding())
    else:
        api.lose_response = True
        assert store.compare_and_swap(snap, reserved) is budget.WriteResult.UNKNOWN
    assert store.read_verified(KEY).ledger.charged == 50_000_000


def test_missing_ledger_never_recreated_and_rule_rejection_blocks():
    api = GitAPI()
    store = GitHubGitStore(api, api.anchor)
    snap = store.read_verified(KEY)
    api.reject_write = True
    assert store.compare_and_swap(snap, budget.reserve(snap.ledger, binding())) is (
        budget.WriteResult.UNKNOWN)
    api.tip = None
    with pytest.raises(budget.BudgetError):
        store.read_verified(KEY)
    assert not any(path == "/git/refs" for _, path, _ in api.calls)


@pytest.mark.parametrize("damage", ["reset", "merge", "key", "tree", "blob", "missing",
                                    "repository", "truncated", "genesis"])
def test_corruption_and_discontinuous_history_fail_closed(damage):
    api = GitAPI()
    store = GitHubGitStore(api, api.anchor)
    initial = store.read_verified(KEY).ledger
    api.append(budget.reserve(initial, binding()))
    if damage == "reset":
        api.append(initial)
    elif damage == "merge":
        api.objects[api.tip]["parents"].append({"sha": api.genesis})
    elif damage == "key":
        api.append(replace(initial, key=budget.PRKey(124, 7)))
    elif damage == "repository":
        api.repository_id = 124
    elif damage == "genesis":
        api.anchor = replace(api.anchor, genesis_commit="f" * 40)
        store = GitHubGitStore(api, api.anchor)
    else:
        tree = api.objects[api.objects[api.tip]["tree"]["sha"]]
        if damage == "tree":
            tree["tree"].append(dict(tree["tree"][0]))
        elif damage == "truncated":
            tree["truncated"] = True
        elif damage == "blob":
            api.objects[tree["tree"][0]["sha"]]["content"] = "invalid%"
        else:
            del api.objects[api.genesis]
    with pytest.raises(budget.BudgetError):
        store.read_verified(KEY)


def test_checkpoint_and_observed_tip_detect_rollback():
    api = GitAPI()
    store = GitHubGitStore(api, api.anchor)
    snap = store.read_verified(KEY)
    store.compare_and_swap(snap, budget.reserve(snap.ledger, binding()))
    anchor = replace(api.anchor, checkpoint_commit=api.tip)
    api.tip = api.genesis
    for reader in (store, GitHubGitStore(api, anchor)):
        with pytest.raises(budget.BudgetError, match="rollback"):
            reader.read_verified(KEY)
    # Explicit limit: a new reader pinned ONLY to genesis cannot detect an
    # administrator's rollback after genesis. Do not claim otherwise.
    assert GitHubGitStore(api, api.anchor).read_verified(KEY).ledger.revision == 0


def test_history_bound_and_anchor_validation():
    api = GitAPI()
    initial = GitHubGitStore(api, api.anchor).read_verified(KEY).ledger
    api.append(budget.reserve(initial, binding()))
    with pytest.raises(budget.BudgetError, match="bound"):
        GitHubGitStore(api, api.anchor, max_history=1).read_verified(KEY)
    with pytest.raises(budget.BudgetError):
        replace(api.anchor, ref="refs/heads/main")
    with pytest.raises(budget.BudgetError):
        replace(api.anchor, genesis_commit="not-a-sha")


@pytest.mark.parametrize("failure", ["before_commit", "before_patch", "deleted", "bad_response"])
def test_crashes_and_uncertain_responses_cannot_grant_claim(failure):
    api = GitAPI()
    store = GitHubGitStore(api, api.anchor)
    snap = store.read_verified(KEY)
    store.compare_and_swap(snap, budget.reserve(snap.ledger, binding()))
    request = api.request

    def fail(method, path, data=None):
        if failure == "before_commit" and method == "POST" and path == "/git/commits":
            raise TimeoutError("commit creation unknown")
        if failure == "before_patch" and method == "PATCH":
            raise TimeoutError("patch not sent")
        if failure == "deleted" and method == "PATCH":
            api.tip = None
        result = request(method, path, data)
        if failure == "bad_response" and method == "PATCH":
            return {}
        return result

    api.request = fail
    with pytest.raises(budget.BudgetError):
        budget.claim_once(store, KEY, binding())
    api.request = request
    if failure == "deleted":
        with pytest.raises(budget.BudgetError):
            GitHubGitStore(api, api.anchor).read_verified(KEY)
    else:
        latest = GitHubGitStore(api, api.anchor).read_verified(KEY).ledger
        assert latest.charged == 50_000_000
        if failure == "bad_response":
            with pytest.raises(budget.BudgetError):
                budget.claim_once(store, KEY, binding())
        else:
            # Only an independently successful new claim can permit execution;
            # no caller received a grant for the failed attempt.
            assert latest.entries[0].phase == "reserved"


def test_caller_forged_snapshot_and_identity_do_not_write():
    api = GitAPI()
    store = GitHubGitStore(api, api.anchor)
    snap = store.read_verified(KEY)
    fake = budget.Snapshot("f" * 40, snap.ledger)
    assert store.compare_and_swap(fake, budget.reserve(fake.ledger, binding())) is (
        budget.WriteResult.CONFLICT)
    with pytest.raises(budget.BudgetError):
        store.read_verified(budget.PRKey(123, 8))
    assert all(method == "GET" for method, _, _ in api.calls)


@pytest.mark.parametrize("parent_count", [1, 2])
def test_audited_genesis_can_have_one_main_parent_but_not_merge(parent_count):
    api = GitAPI()
    # Deliberately absent from the ledger object model: main ancestry is not
    # ledger history and must not be read or interpreted as budget transitions.
    main_parents = [f"{i + 1:040x}" for i in range(parent_count)]
    genesis = budget.Ledger(KEY, budget.Genesis("audited main-parent migration", 10))
    api.genesis = api.append(genesis, parents=main_parents)
    api.anchor = replace(api.anchor, genesis_commit=api.genesis,
                         checkpoint_commit=api.genesis)
    store = GitHubGitStore(api, api.anchor)
    if parent_count > 1:
        with pytest.raises(budget.BudgetError, match="genesis"):
            store.read_verified(KEY)
        return
    snap = store.read_verified(KEY)
    assert snap.ledger == genesis
    reserved = budget.reserve(snap.ledger, binding())
    assert store.compare_and_swap(snap, reserved) is budget.WriteResult.COMMITTED
    assert store.read_verified(KEY).ledger.charged == 50_000_010
    assert not any(path == "/git/commits/" + main_parents[0] for _, path, _ in api.calls)
