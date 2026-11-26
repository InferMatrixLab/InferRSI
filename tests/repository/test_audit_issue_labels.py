import json
from copy import deepcopy

import pytest

from tools import audit_issue_labels as audit
from tools.label_cutover import handoff_gaps, hourly_area_plan_current, merge_event, replay_pr_kind

BASE = "https://github.com/InferMatrixLab/InferRSI"
HEAD = "a" * 40
ORIGINAL = "2026-11-24T12:00:00Z"
T = "2026-11-25T04:00:00Z"
MERGE = {"at": T, "event_id": 45, "sha": HEAD, "url": f"{BASE}/pull/20#event-45"}
BEFORE = "2026-11-25T03:59:59Z"
AFTER = "2026-11-25T04:00:01Z"
LATER = "2026-11-25T04:00:02Z"
KIND = "kind:task"


def obj(labels=(), pr=True):
    item = {
        "number": 7,
        "html_url": f"{BASE}/{'pull' if pr else 'issues'}/7",
        "state": "open",
        "created_at": "2026-11-07T00:00:00Z",
        "updated_at": LATER,
        "labels": [{"name": v} for v in labels],
        "body": "",
    }
    if pr:
        item.update(pull_request={}, head_sha=HEAD)
    return item


def change(n, op, at, label=KIND):
    return {"id": n, "event": op, "created_at": at, "label": {"name": label}}


def replay(labels, changes, original, **overrides):
    item = obj(labels)
    item.update(overrides)
    return replay_pr_kind(item, changes, {"at": ORIGINAL, "objects": {"7": original}}, MERGE)


def test_cutover_is_native_event_with_matching_sha():
    event = {"event": "merged", "id": 45, "created_at": T, "commit_id": HEAD}
    assert merge_event([event], HEAD, f"{BASE}/pull/20") == MERGE
    for events, sha in (([], HEAD), ([event, event], HEAD), ([event], "b" * 40)):
        with pytest.raises(ValueError):
            merge_event(events, sha, f"{BASE}/pull/20")


def test_unchanged_old_kind_stays_in_baseline():
    report = replay([KIND], [], [KIND])
    assert report == {"at_cutover": [KIND], "replayed": [], "new_additions": [], "pending": []}


def test_pre_cutover_changes_are_replayed_only_in_baseline():
    report = replay([], [change(1, "unlabeled", BEFORE)], [KIND])
    assert report["at_cutover"] == []
    assert [e["id"] for e in report["replayed"]] == [1]
    assert not report["new_additions"] and not report["pending"]


def test_post_cutover_remove_and_readd_on_an_old_pr_count_once():
    addition = change(3, "labeled", LATER)
    report = replay([KIND], [change(2, "unlabeled", AFTER), addition, deepcopy(addition)], [KIND])
    assert report["at_cutover"] == [KIND]
    assert [e["id"] for e in report["new_additions"]] == [3]
    assert not report["pending"]


@pytest.mark.parametrize(
    "history",
    [
        [change(1, "labeled", T)],
        [change(1, "labeled", ORIGINAL)],
        [change(1, "labeled", AFTER), change(1, "unlabeled", AFTER)],
        [change(1, "unlabeled", AFTER)],
        [{"event": "labeled", "label": {"name": KIND}}],
    ],
)
def test_ambiguous_or_incomplete_history_never_counted(history):
    result = replay([KIND], history, [])
    assert result["pending"] and result["at_cutover"] is None and not result["new_additions"]


def test_missing_original_fields_and_new_object_are_distinct():
    for snapshot in ({}, {"at": ORIGINAL, "objects": {}}):
        assert replay_pr_kind(obj([KIND]), [], snapshot, MERGE)["pending"]
    new = obj([KIND])
    new["created_at"] = AFTER
    row = replay_pr_kind(new, [change(9, "labeled", AFTER)], {}, MERGE)
    assert not row["pending"] and [e["id"] for e in row["new_additions"]] == [9]


def comment(number, body, who="owner", when=BEFORE):
    return {
        "event": "commented",
        "id": number,
        "html_url": f"{BASE}/issues/7#issuecomment-{number}",
        "body": body,
        "user": {"login": who},
        "created_at": when,
    }


def proof(c):
    return {"url": c["html_url"], "quote": c["body"]}


def codes(row):
    return {f["code"] for f in row["findings"]}


def test_shared_login_is_not_delegation():
    issue = obj(["area:process", KIND], pr=False)
    issue.update(state="closed", closed_by={"login": "owner"})
    c = comment(13, "I am acting on behalf of the issue owner. The owner accepted this scope.")
    closed = {"id": 19, "event": "closed", "actor": {"login": "owner"}, "created_at": AFTER}
    evidence = {
        k: proof(c)
        for k in ("closer_identity", "owner_authority", "closure_summary", "goal_decision")
    }
    evidence.update(closer_login="owner", closer_role="delegate")
    row = audit.audit_object(issue, [c, closed], evidence, {}, None)
    assert row["closure"]["role"] == "delegate" and "closure_delegation" in codes(row)
    evidence["closer_role"] = "owner"
    assert "closure-identity" in codes(audit.audit_object(issue, [c, closed], evidence, {}, None))
    c["body"] = "I am the issue owner and personally accept and close this scope."
    owner = {
        k: proof(c)
        for k in ("closer_identity", "owner_authority", "closure_summary", "goal_decision")
    }
    owner.update(closer_login="owner", closer_role="owner")
    assert not codes(audit.audit_object(issue, [c, closed], owner, {}, None))
    reopened = {"event": "reopened", "id": 2, "created_at": T}
    assert "goal_decision" in codes(
        audit.audit_object(issue, [c, reopened, closed], owner, {}, None)
    )


@pytest.mark.parametrize(
    ("created", "edited", "pending"),
    [
        (BEFORE, None, False),
        (T, None, True),
        (AFTER, None, True),
        (BEFORE, T, True),
        (BEFORE, AFTER, True),
    ],
)
def test_only_decisions_and_delegations_verifiable_before_closure_count(created, edited, pending):
    item = obj(["area:process", KIND], pr=False)
    item["state"] = "closed"
    identity = comment(10, "I am acting on behalf of the issue owner.", "delegate")
    decision = comment(11, "I accept the result and delegate closure.", when=created)
    if edited:
        decision["updated_at"] = edited
    close = {"event": "closed", "id": 20, "actor": {"login": "delegate"}, "created_at": T}
    data = {
        "closer_login": "delegate",
        "closer_role": "delegate",
        "closer_identity": proof(identity),
        "goal_decision": proof(decision),
        "closure_delegation": proof(decision),
    }
    row = audit.audit_object(item, [identity, decision, close], data, {}, None)
    assert row["closure"]["role"] == "delegate"
    for key in ("goal_decision", "closure_delegation"):
        assert (key in codes(row)) == pending
    assert (decision["html_url"] in row["closure"]["sources"]) != pending


def test_parent_decision_needs_a_reference_from_the_close_cycle():
    item = obj(["area:process", KIND], pr=False)
    item["state"] = "closed"
    parent = comment(10, "I accept the result.")
    parent["html_url"] = f"{BASE}/issues/8#issuecomment-10"
    reference = comment(11, parent["html_url"])
    evidence = {"goal_decision": {**proof(parent), "via": reference["html_url"]}}
    groups = {parent["html_url"]: parent}
    close = {"event": "closed", "id": 20, "actor": {"login": "owner"}, "created_at": T}
    assert "goal_decision" not in codes(
        audit.audit_object(item, [reference, close], evidence, {}, None, groups)
    )
    reference["updated_at"] = AFTER
    assert "goal_decision" in codes(
        audit.audit_object(item, [reference, close], evidence, {}, None, groups)
    )


def test_frozen_writer_rejects_old_queue_and_retry_before_each_remote_call():
    pr_labels = {"area:process"}
    remote_calls = []

    def send(plan, writer):
        if hourly_area_plan_current(plan, writer):
            remote_calls.append(plan["label"])
            pr_labels.add(plan["label"])

    def readback():
        return sorted(pr_labels)

    before = readback()
    stale_kind = {"operation": "add", "label": KIND, "generation": "old", "area_evidence": "diff"}
    stale_area = {**stale_kind, "label": "area:harness"}
    for writer in (
        {"mode": "frozen", "generation": "old"},
        {"mode": "trial", "generation": "new"},
        {"mode": "resumed", "generation": "new"},
    ):
        for stale in (stale_kind, stale_area):
            send(stale, writer)  # Previously queued.
            send(stale, writer)  # Previously scheduled retry.
    assert remote_calls == [] and readback() == before
    writer = {"mode": "resumed", "generation": "new"}
    send({**stale_kind, "generation": "new"}, writer)
    send({**stale_area, "generation": "new", "area_evidence": ""}, writer)
    assert remote_calls == []
    send({**stale_area, "generation": "new"}, writer)
    assert remote_calls == ["area:harness"] and readback() == ["area:harness", "area:process"]


def test_operator_receipts_require_separate_post_merge_readback_and_zero_writes():
    freeze = {
        "at": BEFORE,
        "url": f"{BASE}/pull/20#issuecomment-100",
        "scope": "all-label-writes",
        "invalidated_generation": "old",
        "queued": 0,
        "retries": 0,
        "in_flight": 0,
    }
    trial = {
        "at": AFTER,
        "url": f"{BASE}/pull/20#issuecomment-101",
        "run_id": "hourly-678",
        "pr_url": f"{BASE}/pull/7",
        "head": HEAD,
        "inspected": True,
        "existing_open_pr": True,
        "readback_url": f"{BASE}/pull/20#issuecomment-102",
        "remote_label_requests": 0,
        "kinds_before": [],
        "kinds_after": [],
    }
    assert handoff_gaps({"freeze": freeze, "trial": trial}, MERGE) == []
    for k, v in (
        ("remote_label_requests", 1),
        ("kinds_after", [KIND]),
        ("at", T),
        ("readback_url", ""),
        ("readback_url", trial["url"]),
        ("run_id", ""),
        ("inspected", False),
    ):
        assert handoff_gaps({"freeze": freeze, "trial": {**trial, k: v}}, MERGE)
    assert handoff_gaps({"freeze": {**freeze, "retries": 1}, "trial": trial}, MERGE)


def test_standing_activity_needs_affirmative_account_and_revision_evidence():
    pr = obj(["area:process"])
    action = comment(
        9, "I am a standing reviewer. I started this review without an invitation.", "bot", LATER
    )
    action.update(event="reviewed", commit_id=HEAD)
    assert audit.audit_object(pr, [action], {}, {}, None)["uninvited_standing_reviews"] == 1
    action["body"] = "I am a standing reviewer. I reviewed this."
    mention = comment(8, f"@bot please review {HEAD}")
    evidence = {
        "standing_reviews": [{"activity": action["html_url"], "invitation": proof(mention)}]
    }
    assert not codes(audit.audit_object(pr, [mention, action], evidence, {}, None))
    mention["body"] = "@bot please review an unrelated commit"
    assert "review-invitation" in codes(
        audit.audit_object(pr, [mention, action], evidence, {}, None)
    )
    action["body"] = "I reviewed this as a human."
    assert not codes(audit.audit_object(pr, [action], {}, {}, None))
    action.update(
        body="I am a standing reviewer. I started this review without an invitation.",
        commit_id="b" * 40,
    )
    assert audit.audit_object(pr, [action], {}, {}, None)["uninvited_standing_reviews"] == 0


@pytest.mark.parametrize(("edited", "pending"), [(BEFORE, False), (T, True), (AFTER, True)])
def test_invitation_comment_text_must_predate_the_review(edited, pending):
    invite = comment(10, f"@bot please review {HEAD}", when=ORIGINAL)
    invite["updated_at"] = edited
    review = comment(11, "I am a standing reviewer. I reviewed this.", "bot", T)
    review.update(event="reviewed", commit_id=HEAD)
    data = {"standing_reviews": [{"activity": review["html_url"], "invitation": proof(invite)}]}
    row = audit.audit_object(obj(["area:process"]), [invite, review], data, {}, None)
    assert ("review-invitation" in codes(row)) == pending
    assert row["uninvited_standing_reviews"] == 0


def test_status_decision_is_cited_and_suggestions_are_separate_from_authority():
    issue = obj(["area:process", KIND, "status:proposed"], pr=False)
    issue["body"] = (
        "**Current state:** delivered\n**Decision needed:** none\n**Next action:** verify"
    )
    decision = comment(10, "I accept the entire scope.")
    evidence = {"whole_scope_acceptance": proof(decision), "scope_decision": proof(decision)}
    row = audit.audit_object(issue, [decision], evidence, {}, None)
    assert {"scope-update", "delivery", "progress-decision", "label-authority"} <= codes(row)
    assert next(r for r in row["findings"] if r["code"] == "scope-update")["add"] == [
        "status:accepted"
    ]
    wrong = {
        **evidence,
        "whole_scope_acceptance": {"url": decision["html_url"], "quote": "another decision"},
    }
    assert "scope-update" not in codes(audit.audit_object(issue, [decision], wrong, {}, None))
    issue["state"] = "closed"
    pending = audit.audit_object(issue, [decision], {}, {}, None)
    f = next(x for x in pending["findings"] if x["code"] == "closed-proposed")
    assert f["state"] == "pending" and not f["remove"]


def test_empty_fields_quotes_and_code_examples_do_not_set_progress():
    fields = audit.progress_fields(
        "> **Current state:** done\n~~~\n**Current state:** active\n~~~\n"
        "<!-- **Decision needed:** none -->\n**Current state:** \n**Next action:** ask"
    )
    assert fields["word"] == "" and "decision needed" not in fields


def test_quoted_review_and_conflicting_decisions_are_not_positive_findings():
    activity = comment(
        9, "I am a standing reviewer.\n> I started this review without an invitation.", "bot"
    )
    activity.update(event="reviewed", commit_id=HEAD)
    assert audit.audit_object(obj(), [activity], {}, {}, None)["uninvited_standing_reviews"] == 0
    activity["body"] = (
        "~~~\n<!-- always-on-bot:v1 -->\nI started this review without an invitation.\n~~~"
    )
    assert "review-invitation" not in codes(audit.audit_object(obj(), [activity], {}, {}, None))
    accepted, deferred = comment(10, "I accept the scope."), comment(11, "I defer this.")
    issue = obj([KIND, "status:proposed"], pr=False)
    data = {"whole_scope_acceptance": proof(accepted), "deferral": proof(deferred)}
    items = audit.audit_object(issue, [accepted, deferred], data, {}, None)["findings"]
    update = [item for item in items if item["code"] == "scope-update"]
    assert len(update) == 1 and update[0]["state"] == "pending" and not update[0]["add"]


def test_a_reopened_issue_cannot_borrow_prior_close_identity_and_event():
    issue = obj([KIND], pr=False)
    issue["body"] = "**Current state:** done"
    c = comment(13, "I am the issue owner and close this scope.")
    close = {"id": 18, "event": "closed", "actor": {"login": "owner"}, "created_at": BEFORE}
    reopen = {"id": 19, "event": "reopened", "created_at": AFTER}
    data = {"closer_login": "owner", "closer_role": "owner", "closer_identity": proof(c)}
    row = audit.audit_object(issue, [c, close, reopen], data, {}, None)
    assert row["closure"]["role"] is None and row["closure"]["close_event"] is None
    assert "closure-identity" in codes(row)


def test_cited_multiple_areas_only_suggest_missing_known_labels():
    item = obj(["area:process"])
    reason = comment(10, "The delivery covers both engineering process and the execution harness.")
    data = {"area_scope": proof(reason), "suggested_areas": ["area:process", "area:harness"]}
    findings = audit.audit_object(item, [reason], data, {}, None)["findings"]
    assert (
        len(findings) == 1 and findings[0]["add"] == ["area:harness"] and not findings[0]["remove"]
    )


def test_live_reader_uses_get_only_paginates_and_returns_findings_as_data(monkeypatch, capsys):
    calls = []
    item = obj([], pr=False)

    def run(command, **kwargs):
        assert command[:4] == ["gh", "api", "--method", "GET"]
        path = command[-1]
        calls.append(path)
        if "/timeline?" in path:
            value = []
        elif "/issues?" in path:
            value = [item] * 100 if path.endswith("page=1") else []
        else:
            value = item

        class Response:
            returncode = 0
            stdout = json.dumps(value)

        return Response()

    monkeypatch.setattr(audit.subprocess, "run", run)
    assert audit.main(["--recent-hours", "48"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report["objects"]) == 1 and "issue-kind" in codes(report["objects"][0])
    assert any("page=2" in p for p in calls)
