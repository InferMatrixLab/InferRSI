from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from tools import check_independent_approvals as gate

HEAD = "a" * 40
OLD = "b" * 40


def pr(number=10, head=HEAD, branch="main"):
    return {"number": number, "head": {"sha": head}, "state": "open", "draft": False,
            "base": {"ref": branch, "repo": {"full_name": "example/repo"}},
            "user": {"login": "author"}, "commits": 1}


def vote(login, state="APPROVED", body="", head=HEAD, can_push=True, actor_type="User"):
    return {"author": {"login": login, "__typename": actor_type}, "state": state, "body": body,
            "commit": {"oid": head}, "authorCanPushToRepository": can_push}


def test_only_current_eligible_approvals_count():
    reviews = [vote("A"), vote("a"), vote("B", body="PASS"),
               vote("dissent", state="CHANGES_REQUESTED"), vote("revoked", state="DISMISSED"),
               vote("old", head=OLD), vote("reader", can_push=False), vote("author"),
               vote("commit-author")]
    assert gate.review_candidates(reviews, HEAD, {"author", "commit-author"}) == {"a", "b"}


@pytest.mark.parametrize(("states", "bodies", "expected"), [
    (("APPROVED", "APPROVED"), ("", "Reviewed the tests."), 2),
    (("APPROVED", "COMMENTED"), ("PASS", "LGTM"), 1),
    (("COMMENTED", "COMMENTED"), ("LGTM", "PASS"), 0),
])
def test_only_formal_approvals_count_regardless_of_body(states, bodies, expected):
    reviews = [vote("first", states[0], bodies[0]), vote("second", states[1], bodies[1])]
    assert len(gate.review_candidates(reviews, HEAD, set())) == expected


@pytest.mark.parametrize(("login", "actor_type"), [
    ("integration[bot]", "Bot"), ("integration", "Bot"),
    ("integration[bot]", "User"), ("unresolved", "Mannequin"), ("unknown", None),
])
def test_apps_bots_and_unknown_actor_types_cannot_supply_an_approval(login, actor_type):
    reviews = [vote("independent"), vote(login, actor_type=actor_type)]
    assert gate.review_candidates(reviews, HEAD, set()) == {"independent"}


def test_rechecking_the_same_head_does_not_cache_a_revoked_permission(monkeypatch):
    item, api = pr(), Mock()
    api.pages.return_value = [{"sha": HEAD, "author": None, "committer": None}]
    permission = {"can_push": True}
    monkeypatch.setattr(gate, "read_reviews", lambda *args: [
        vote("first"), vote("second", can_push=permission["can_push"]),
    ])
    assert gate.evaluate(api, item) == 2
    permission["can_push"] = False
    assert gate.evaluate(api, item) == 1


@pytest.mark.parametrize(("second_vote", "expected"), [
    ("APPROVED", "success"), ("CHANGES_REQUESTED", "failure"), ("DISMISSED", "failure"),
])
def test_dissent_only_changes_its_own_vote(monkeypatch, second_vote, expected):
    item = pr()
    api = Mock()
    api.get.side_effect = [item, []]
    commit = {"sha": HEAD, "author": {"login": "coauthor"}, "committer": None}
    api.pages.side_effect = lambda route: [item] if route.startswith("pulls?") else [commit]
    monkeypatch.setattr(gate, "read_reviews", lambda *args: [
        vote("a"), vote("b", state=second_vote), vote("third", state="CHANGES_REQUESTED"),
        vote("author"), vote("coauthor"),
    ])
    assert gate.reconcile(api, [item], [item]) == 0
    route, status = api.request.call_args.args
    assert route == f"statuses/{HEAD}"
    assert status["context"] == gate.CONTEXT
    assert status["state"] == expected


def test_shared_head_is_never_approved():
    first, second = pr(), pr(number=11, branch="other")
    api = Mock()
    api.get.return_value = []
    assert gate.reconcile(api, [first, second], [first]) == 0
    assert api.request.call_args.args[1]["state"] == "failure"
    api.pages.assert_not_called()


@pytest.mark.parametrize("before", [HEAD, None, "not-a-sha"])
def test_synchronize_reconciles_a_peer_after_a_shared_head_splits(monkeypatch, before):
    first, second = pr(), pr(number=11)
    api, statuses = Mock(), {}
    monkeypatch.setattr(gate, "evaluate", lambda *_: 2)
    monkeypatch.setattr(gate, "publish",
                        lambda _api, head, state, _description: statuses.update({head: state}))
    assert gate.reconcile(api, [first, second], [first]) == 0
    assert statuses[HEAD] == "failure"

    # PR 11 advances; PR 10 is now the unique owner of the former shared SHA.
    moved = pr(number=11, head=OLD)
    current = [first, moved]
    api.get.side_effect = lambda route: first if route == "pulls/10" else moved
    api.pages.return_value = current
    event = {"action": "synchronize", "number": 11, "pull_request": moved}
    if before is not None:
        event["before"] = before
    selected = gate.targets(current, "pull_request_target", event)
    assert gate.reconcile(api, current, selected) == 0
    assert statuses == {HEAD: "success", OLD: "success"}


def test_fork_review_without_run_association_reconciles_from_live_data():
    items = [pr()]
    event = {"workflow_run": {"event": "pull_request_review", "pull_requests": []}}
    assert gate.targets(items, "workflow_run", event) == items


def test_status_writer_does_not_execute_code_from_review_workflow():
    directory = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    signal = yaml.load((directory / "approval-review-event.yml").read_text(encoding="utf-8"),
                       Loader=yaml.BaseLoader)
    writer = yaml.load((directory / "independent-approvals.yml").read_text(encoding="utf-8"),
                       Loader=yaml.BaseLoader)
    assert signal["permissions"] == {}
    assert writer["on"]["workflow_run"]["workflows"] == [signal["name"]]
    assert writer["jobs"]["reconcile"]["steps"][0]["with"] == {
        "ref": "main", "persist-credentials": "false",
    }
