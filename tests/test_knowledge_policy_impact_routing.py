"""Admission impact routing uses object graphs, never executes candidate code."""

import copy
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools import check_knowledge_model_policy as policy

BEFORE = "a" * 40
CURRENT = "b" * 40
HEAD = "c" * 40
REPOSITORY = "example/repository"
POLICY = {"base_branch": "main", "policy_paths": []}


def pr(number=1, head=HEAD, base="main"):
    return {"number": number, "head": {"sha": head}, "state": "open", "body": "fixture",
            "base": {"ref": base, "sha": CURRENT}}


def event(name="push"):
    value = {"repository": {"full_name": REPOSITORY}, "before": BEFORE,
             "ref": "refs/heads/main", "forced": False}
    if name == "closed":
        value.update(number=1, action="closed", pull_request=pr())
    return value


def api(prs=None):
    result = Mock()
    result.pages.return_value = [pr()] if prs is None else prs
    result.get.side_effect = lambda route: ({"object": {"sha": CURRENT}}
                                           if route.startswith("git/ref/") else
                                           {**pr(), "state": "closed"})
    return result


def graph(changed="src/example.py", unchanged=True):
    result = Mock()
    result.git.side_effect = lambda *args: changed if args[0] == "diff" else ""
    result.unchanged.return_value = unchanged
    return result


def route(client=None, payload=None, topology=None, name="push", config=None):
    return policy.admission_route(client or api(), payload or event(), name,
                                  config or POLICY, CURRENT, REPOSITORY, topology or graph())


def test_ordinary_push_skips_unaffected_admissions_without_status_or_history_reads():
    client, topology = api(), graph()
    numbers, routing, snapshot = route(client, topology=topology)
    assert numbers == []
    assert routing["mode"] == "push-impact"
    assert snapshot
    client.history.assert_not_called()
    client.status.assert_not_called()
    topology.prepare.assert_called_once_with([BEFORE, CURRENT, HEAD])
    topology.unchanged.assert_called_once_with(BEFORE, CURRENT, HEAD)
    # A queued push compares its before against freshly fetched current main, not event.after.
    payload = event()
    payload["after"] = "d" * 40
    assert route(payload=payload)[0] == []


@pytest.mark.parametrize("path", sorted(policy.ROUTING_POLICY_INPUTS))
def test_all_fixed_policy_inputs_force_refresh_even_if_policy_list_omits_them(path):
    numbers, routing, _ = route(topology=graph(changed=path))
    assert numbers is None
    assert routing["reason"] == "policy-inputs-changed"


def test_declared_additional_policy_dependency_forces_refresh():
    assert route(topology=graph(changed="tools/new_helper.py"), config={
        **POLICY, "policy_paths": ["tools/new_helper.py"]})[0] is None


def test_changed_merge_base_selects_pr_even_when_policy_is_unchanged():
    # Changed base-relative protected paths can invalidate an exact-path exception approval.
    assert route(topology=graph(unchanged=False))[0] == [1]


def test_shared_head_includes_peer_against_another_base():
    numbers, _, _ = route(client=api([pr(), pr(2, base="release")]))
    assert numbers == [1]


def test_closed_merge_event_targets_only_closed_trigger_and_remaining_head_peers():
    client = api([pr(2), pr(3, head="d" * 40)])
    numbers, routing, _ = route(client, event("closed"), name="pull_request_target")
    assert numbers == [1, 2]
    assert routing["mode"] == "closed-impact"
    client.status.assert_not_called()
    # The paired push does no unrelated writes either; the close itself receives existing N/A.
    assert route(client=api([pr(3, head="d" * 40)]))[0] == []


def test_closed_event_reopened_or_changed_head_falls_back():
    client = api([])
    client.get.side_effect = lambda route: pr() if route.startswith("pulls/") else None
    assert route(client, event("closed"), name="pull_request_target")[0] is None


@pytest.mark.parametrize("mutation", [
    {"before": "0" * 40}, {"before": "bad"}, {"forced": True},
    {"ref": "refs/heads/release"}, {"repository": {"full_name": "other/repository"}},
])
def test_unprovable_push_falls_back(mutation):
    assert route(payload={**event(), **mutation})[0] is None


@pytest.mark.parametrize("method", ["prepare", "git", "unchanged"])
def test_missing_shallow_ambiguous_or_timed_out_graph_does_not_skip(method):
    topology = graph()
    getattr(topology, method).side_effect = subprocess.TimeoutExpired("git", 60)
    assert route(topology=topology)[0] is None


def test_incomplete_or_changing_pr_collection_falls_back():
    client = api()
    client.pages.side_effect = [[pr()], [pr(head="d" * 40)]]
    assert route(client)[0] is None
    assert route(client=api([pr(), pr()]))[0] is None
    client = api()
    client.get.side_effect = lambda route: {"object": {"sha": "d" * 40}}
    assert route(client)[0] is None


@pytest.mark.parametrize("name,payload", [("workflow_dispatch", {}),
    ("pull_request_target", {"action": "edited"}),
    ("pull_request_target", {"action": "synchronize"}),
    ("issue_comment", {"action": "deleted"})])
def test_other_triggers_keep_full_refresh(name, payload):
    assert route(payload=payload or {"fixture": True}, name=name)[0] is None


def test_unique_merge_base_proof_and_criss_cross_ambiguity(tmp_path, monkeypatch):
    def git(*arguments, stdin=None):
        return subprocess.run(["git", *arguments], cwd=tmp_path, input=stdin, text=True,
                              capture_output=True, check=True).stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    tree = git("mktree", stdin="")

    def commit(name, *parents):
        args = [item for parent in parents for item in ("-p", parent)]
        return git("commit-tree", tree, *args, stdin=name)

    root = commit("root")
    before = commit("before", root)
    head = commit("head", root)
    current = commit("unrelated main advance", before)
    monkeypatch.setattr(policy, "ROOT", Path(tmp_path))
    topology = policy.AdmissionGraph(REPOSITORY)
    assert topology.unchanged(before, current, head)
    merged = commit("base now includes candidate ancestry", current, head)
    assert not topology.unchanged(before, merged, head)
    left = commit("left", before, head)
    right = commit("right", head, before)
    left_next = commit("left next", left)
    assert not topology.unchanged(left, left_next, right)  # two merge bases, never proof


def test_routing_snapshot_detects_body_head_base_and_lifecycle_changes():
    client = api()
    snapshot = policy.routing_snapshot([pr()])
    assert policy.routing_current(client, CURRENT, snapshot)
    for key, value in [("body", "edited"), ("head", {"sha": "d" * 40}),
                       ("base", {"ref": "release", "sha": CURRENT})]:
        changed = copy.deepcopy(pr())
        changed[key] = value
        client.pages.return_value = [changed]
        assert not policy.routing_current(client, CURRENT, snapshot)


def test_no_impact_report_never_claims_global_health(tmp_path, capsys):
    binding = {"trigger": None, "event_name": "push", "expected_head": None,
               "policy_sha": CURRENT}
    path = tmp_path / "report.json"
    policy.write_report(path, binding, [], {"mode": "push-impact", "targets": []})
    assert policy.report_exit(path, binding, 0) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["scope"] == "affected-admissions"
    assert summary["global_summary"] is None
    assert summary["scope_note"] == "No affected admissions; not a global health assessment"


def test_main_retries_when_empty_routing_snapshot_advances(tmp_path, monkeypatch, capsys):
    payload = tmp_path / "event.json"
    payload.write_text(json.dumps(event()))
    config = tmp_path / "policy.json"
    config.write_text(json.dumps({"schema_version": 1, **POLICY}))
    client = api()
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_TOKEN", "FAKE_TEST_TOKEN")
    monkeypatch.setattr(policy, "GitHub", lambda *args: client)
    monkeypatch.setattr(policy, "admission_route", lambda *args: (
        [], {"mode": "push-impact", "targets": []}, policy.routing_snapshot([pr()])))
    monkeypatch.setattr(policy, "check_prs", lambda *args, **kwargs: [])
    monkeypatch.setattr(policy, "routing_current", lambda *args: False)
    assert policy.main(["--repository", REPOSITORY, "--policy-sha", CURRENT,
                        "--policy", str(config), "--event-path", str(payload)]) == policy.EXIT_RERUN
    output = capsys.readouterr().out
    assert '"kind": "deferred"' in output
    assert '"pull_request": 0' in output
    client.status.assert_not_called()


def test_graph_prepare_rejects_still_shallow_and_never_uses_candidate_remote(monkeypatch):
    topology = policy.AdmissionGraph(REPOSITORY)
    topology.git = Mock(side_effect=["true", "", "true"])
    with pytest.raises(ValueError, match="Incomplete routing graph"):
        topology.prepare([BEFORE, CURRENT, HEAD])
    assert topology.git.call_args_list[1].args == (
        "fetch", "--quiet", "--no-tags", "--unshallow",
        "https://github.com/example/repository.git", BEFORE, CURRENT, HEAD)
