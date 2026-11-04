"""Unpaid notifications retain exact-plan evidence using authenticated provenance."""
import copy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from inferrsi.infra.artifacts import write_json
from tests import test_skill_eval_auto as auto_tests
from tests.fixtures.skill_eval_compare_support import FixedOutputClient
from tests.fixtures.skill_eval_pr_support import SimulatedGitHub, approval, setup
from tests.test_skill_eval_pr import dispatch_event
from tools import skill_eval_auto as auto
from tools import skill_eval_pr as pr
from tools.skill_eval_budget import Binding, BudgetError, Entry


@pytest.fixture
def config():
    return auto_tests.config.__wrapped__()


def prepared_evidence(tmp_path, monkeypatch, config):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    output = tmp_path / "prepared"
    plan = pr.prepare(repo, mapping, identity, output)
    client = FixedOutputClient(tmp_path)
    pr.execute(output, approval(plan), client=client)
    data = pr.result_archive(output).read_bytes()
    # The publisher fixture is synthetic, not a provider execution: attach the
    # reviewed provider identity only after generating offline injected answers.
    plan["provider_config"] = config["provider"]
    plan["reservation"] = pr.provider_reservation(plan)
    write_json(output / "pr-plan.json", plan)
    api = SimulatedGitHub(plan, data)
    api.run.update(event="pull_request_target", head_sha=plan["head"],
                   display_title="skill-eval plan or publish PR 7")
    entries = [Entry(Binding(pr.fingerprint(plan), "10.1", 100), "claimed")]
    store = SimpleNamespace(read_verified=lambda key: SimpleNamespace(
        ledger=SimpleNamespace(entries=entries)))
    monkeypatch.setattr(auto, "configuration", lambda **kw: {**config, "anchors": {"7": {}}})
    monkeypatch.setattr(auto, "ledger_store", lambda *a: (store, "offline-key"))
    monkeypatch.setattr(auto, "report_control", lambda *a: {"state": "blocked"})
    monkeypatch.setattr(pr, "GitHub", lambda *a: api)
    monkeypatch.setattr(auto, "controlled_execute", Mock(side_effect=AssertionError("No paid run")))
    monkeypatch.setattr(pr, "execute", Mock(side_effect=AssertionError("No model calls")))
    return plan, output, api, entries, store


@pytest.mark.parametrize("event", ["unlabeled", "duplicate", "unpaid"])
def test_unpaid_event_reuses_original_run_and_does_not_erase_results(
        tmp_path, monkeypatch, config, event):
    plan, output, api, entries, store = prepared_evidence(tmp_path, monkeypatch, config)
    before = copy.deepcopy(entries)
    pr.publish_retained(api, output, 10, 10, 1)
    assert '"unchanged_correct":1' in api.comments[0]["body"]
    dispatch_event(monkeypatch, tmp_path, output, {}, "publish", run_id=11)
    write_json(tmp_path / "event.json", {"action": event, "pull_request": {"number": 7}})
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_target")
    monkeypatch.setenv("SKILL_EVAL_AUTO_SOURCE", "true" if event == "duplicate" else "false")
    pr.main()
    body = api.comments[0]["body"]
    assert '"unchanged_correct":1' in body
    assert "/actions/runs/10" in body and "skill-eval-writer:11" in body
    assert "/actions/runs/11" not in api.reads
    assert entries == before
    auto.controlled_execute.assert_not_called()
    pr.execute.assert_not_called()


@pytest.mark.parametrize("field", ["head", "base", "version", "exam"])
def test_changed_frozen_plan_never_reuses_old_evidence(tmp_path, monkeypatch, config, field):
    plan, output, api, entries, store = prepared_evidence(tmp_path, monkeypatch, config)
    if field == "exam":
        plan["comparisons"][0]["exam"]["grader"] = "f" * 64
    else:
        plan[field] = "f" * 40
    assert auto.retained_source(api, plan) is None
    write_json(output / "pr-plan.json", plan)
    api.current.update({key: plan[key] for key in ("base", "head")})
    dispatch_event(monkeypatch, tmp_path, output, {}, "publish")
    write_json(tmp_path / "event.json", {"pull_request": {"number": 7}})
    monkeypatch.setenv("SKILL_EVAL_AUTO_SOURCE", "false")
    pr.main()
    assert '"unchanged_correct":1' not in api.comments[0]["body"]
    assert not any("/artifacts" in path for path in api.reads)


@pytest.mark.parametrize("damage", ["pending", "event", "head", "repository", "ledger",
                                     "attempt", "ambiguous", "original_plan"])
def test_untrusted_retained_source_cannot_replace_available_evidence(
        tmp_path, monkeypatch, config, damage):
    plan, output, api, entries, store = prepared_evidence(tmp_path, monkeypatch, config)
    pr.publish_retained(api, output, 10, 10, 1)
    before = copy.deepcopy(api.comments)
    if damage == "pending":
        api.run["status"] = "in_progress"
    elif damage == "event":
        api.run["event"] = "pull_request"
    elif damage == "head":
        api.run["head_sha"] = "f" * 40
    elif damage == "repository":
        api.run["repository"]["id"] = 456
    elif damage == "ledger":
        store.read_verified = Mock(side_effect=BudgetError("Unknown ledger"))
    elif damage == "attempt":
        entries[0] = Entry(Binding(pr.fingerprint(plan), "10.2", 100), "claimed")
    elif damage == "ambiguous":
        entries.append(entries[0])
    else:
        # Forged matching ledger cannot override the original source artifact.
        plan["version"] = "f" * 40
        entries[0] = Entry(Binding(pr.fingerprint(plan), "10.1", 100), "claimed")
        write_json(output / "pr-plan.json", plan)
    dispatch_event(monkeypatch, tmp_path, output, {}, "publish")
    write_json(tmp_path / "event.json", {"pull_request": {"number": 7}})
    monkeypatch.setenv("SKILL_EVAL_AUTO_SOURCE", "false")
    if damage == "original_plan":
        pr.main()
        assert "artifacts are invalid" in api.comments[0]["body"]
        assert '"unchanged_correct":1' not in api.comments[0]["body"]
    else:
        with pytest.raises(ValueError):
            pr.main()
        assert api.comments == before
    auto.controlled_execute.assert_not_called()
    pr.execute.assert_not_called()


def test_unconfigured_pr_has_no_invented_retained_source(tmp_path, monkeypatch, config):
    plan, output, api, entries, store = prepared_evidence(tmp_path, monkeypatch, config)
    monkeypatch.setattr(auto, "configuration", lambda **kw: config)
    assert auto.retained_source(api, plan) is None  # No trusted anchor for PR7.
    monkeypatch.setattr(auto, "configuration", Mock(side_effect=FileNotFoundError))
    assert auto.retained_source(api, plan) is None


def test_unclaimed_reservation_is_not_execution_provenance(tmp_path, monkeypatch, config):
    plan, output, api, entries, store = prepared_evidence(tmp_path, monkeypatch, config)
    entries[0] = Entry(entries[0].binding, "reserved")
    assert auto.retained_source(api, plan) is None
