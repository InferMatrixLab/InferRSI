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


def vote(login, state="APPROVED", body="LGTM", head=HEAD, can_push=True):
    return {"author": {"login": login}, "state": state, "body": body,
            "commit": {"oid": head}, "authorCanPushToRepository": can_push}


def test_only_current_eligible_approvals_count():
    reviews = [vote("A", body="\n LGTM \n\nVerified"), vote("a"), vote("B"),
               vote("dissent", state="CHANGES_REQUESTED"), vote("revoked", state="DISMISSED"),
               vote("old", head=OLD), vote("reader", can_push=False), vote("author"),
               vote("commit-author"), vote("case", body="lgtm"), vote("late", body="PASS\nLGTM")]
    assert gate.review_candidates(reviews, HEAD, {"author", "commit-author"}) == {"a", "b"}


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
