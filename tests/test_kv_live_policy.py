"""All identities, files, API reads and clock values below are offline fixtures."""

import copy
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_kv_pilot_admission import NOW
from tests.test_kv_pilot_admission import policy as sample_policy
from tools import kv_live_policy as live


def write(root, name, value):
    data = json.dumps(value).encode()
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": name, "bytes": len(data), "sha256": live.sha(data)}


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    monkeypatch.setattr(live, "LOCATOR", tmp_path / "locator.json")
    monkeypatch.setattr(live, "DEPENDENCIES", ("code.py",))
    monkeypatch.setattr(live.scripted, "dependencies", lambda: {})
    monkeypatch.setattr(live, "QUALIFICATION_DEPENDENCIES", {"code.py"})
    (tmp_path / "code.py").write_text("# offline code fixture\n")
    sources = {"code.py": live.sha((tmp_path / "code.py").read_bytes())}
    monkeypatch.setattr(live, "qualification_dependencies", lambda: sources)
    actor_config = {"actor_sha256": "4" * 64, "edit_plan": {"files": []},
        "prompt": "offline prompt", "arm": "A2", "model": "claude-opus-5-5",
        "client": {}, "input_token_ceiling": 1000000,
        "suite_sha256": "7" * 64, "baseline_sha256": "8" * 64}
    actor = write(tmp_path, "actor.json", actor_config)
    evidence = b"offline data-only archive fixture"
    qualified = write(tmp_path, "qualified.json", {
        "schema": "kv-scripted-actor-qualification-v1", "revision": "6" * 40,
        "verdict": "PASS", "model_calls": 0, "provider_charges_usd": 0,
        "dependencies": sources, "dependencies_sha256": live.fingerprint(sources),
        "software_checks_passed": True, "source_unchanged": True,
        "cleanup": {"verdict": "PASS"},
        "runtime_isolation": {"verdict": "PASS", "inventory_sha256": "9" * 64,
                              "mount_count": 4},
        "raw_evidence": {"sha256": live.sha(evidence)},
        "arms": {arm: {"executor_status": "completed", "worker_status": "completed",
            "request_completion_known": True,
            "simulated_slots_consumed": 4, "visible_workbench_verified": True,
            "two_revision_receipts_retained": True, "hidden_correctness": {"verdict": "PASS"},
            "exposure": [], "prompt_sha256": live.sha(b"offline prompt"),
            "common_actor_contract_sha256": live.inputs.common_actor_contract_sha256(actor_config)}
            for arm in ("A2", "A3")}})
    with zipfile.ZipFile(tmp_path / "qualified.zip", "w") as archive:
        archive.writestr("qualification.json", (tmp_path / "qualified.json").read_bytes())
        archive.writestr("raw-evidence.zip", evidence)
    raw_archive = (tmp_path / "qualified.zip").read_bytes()
    archive_record = {"path": "qualified.zip", "bytes": len(raw_archive),
                      "sha256": live.sha(raw_archive)}
    suite = write(tmp_path, "suite.json", {})
    plan = {"schema": "kv-live-plan-v1", "repository_id": live.REPOSITORY_ID, "issue": 248,
        "campaign_id": "offline-campaign", "execution_id": "offline-execution",
        "charge_pr": 999, "charge_head": "2" * 40, "expires_at": int(NOW.timestamp()) + 7200,
        "provider": json.loads(sample_policy().provider_json), "dependencies": sources,
        "actors": {arm: {"config": actor, "workspace": [{"path": "candidate.py"}]}
                   for arm in ("A2", "A3")},
        "ledger": {"ref": f"refs/heads/skill-eval-budget/{live.REPOSITORY_ID}/999",
                   "genesis_commit": "3" * 40, "checkpoint_commit": "3" * 40},
        "daily_ledger": {"ref": f"refs/heads/skill-eval-budget/{live.REPOSITORY_ID}/daily",
                   "genesis_commit": "5" * 40, "checkpoint_commit": "5" * 40},
        "qualification": {"run_id": 123, "run_attempt": 1, "head": "6" * 40,
                          "revision": "6" * 40, "artifact_id": 456,
                          "archive": archive_record, "receipt": qualified,
                          "dependencies_sha256": live.fingerprint(sources)},
        "suite": suite, "final_suite": suite, "hidden_traces": suite,
        "arm_order": ["A2", "A3"], "scope": "synthetic feasibility only",
        "price_evidence": "offline synthetic price fixture",
        "prior_owner_group_statement": "offline fixture, not live attestation",
        "final_seconds": 180, "final_repetitions": 8}
    authorization = {"schema": "kv-live-authorization-v1", "plan_sha256": live.fingerprint(plan),
                     "plan": plan}
    body = live.PREFIX + json.dumps(authorization) + live.SUFFIX
    locator = {"schema": "kv-live-authorization-locator-v1", "enabled": True,
        "repository_id": live.REPOSITORY_ID, "issue": 248, "comment_id": 12345,
        "author_login": live.OPERATOR, "body_sha256": live.sha(body.encode())}
    write(tmp_path, "locator.json", locator)
    comment = {"id": 12345, "body": body, "user": {"login": live.OPERATOR, "type": "User"},
        "issue_url": f"https://api.github.com/repos/{live.REPOSITORY}/issues/248"}
    return SimpleNamespace(root=tmp_path, plan=plan, locator=locator, comment=comment,
                           authorization=authorization)


def test_exact_frozen_public_authorization_has_no_spending_side_effect(case):
    actual = live.frozen_authorization(fetch=lambda n: case.comment, now=NOW.timestamp())
    assert actual == (case.authorization, case.locator)
    assert live.policy(case.plan, "7" * 40).binding.worst_case == 162720000


@pytest.mark.parametrize("field,value", [
    ("id", 12346), ("body", "changed"), ("issue_url", "https://example.invalid/other"),
    ("user", {"login": "other", "type": "User"}),
    ("user", {"login": live.OPERATOR, "type": "Bot"}),
])
def test_comment_identity_hash_and_author_are_not_interchangeable(case, field, value):
    case.comment[field] = value
    with pytest.raises(ValueError, match="identity"):
        live.frozen_authorization(fetch=lambda n: case.comment, now=NOW.timestamp())


@pytest.mark.parametrize("change", ["expired", "source", "qualifier", "missing_dependency",
                                    "amount", "requests", "charge_ref", "unknown_field"])
def test_bad_frozen_plan_fails_before_any_request_or_ledger(case, change):
    plan = copy.deepcopy(case.plan)
    if change == "expired":
        plan["expires_at"] = 1
    elif change == "source":
        (case.root / "code.py").write_text("changed")
    elif change == "qualifier":
        plan["qualification"]["dependencies_sha256"] = "0" * 64
    elif change == "missing_dependency":
        plan["dependencies"].clear()
    elif change == "amount":
        plan["provider"]["spend_limit"]["amount"] = "201"
    elif change == "requests":
        plan["provider"]["client"]["max_requests"] = 9
    elif change == "charge_ref":
        plan["ledger"]["ref"] += "1"
    else:
        plan["secret"] = "offline-not-allowed"
    with pytest.raises((ValueError, live.budget.BudgetError)):
        live.validate_plan(plan, now=NOW.timestamp())


def test_disabled_default_does_not_fetch_comment(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "LOCATOR", tmp_path / "locator.json")
    write(tmp_path, "locator.json", {"schema": "kv-live-authorization-locator-v1",
                                     "enabled": False})
    with pytest.raises(ValueError, match="disabled"):
        live.frozen_authorization(fetch=lambda _: pytest.fail("must not fetch"))


@pytest.mark.parametrize("name,value", [("GITHUB_EVENT_NAME", "pull_request"),
    ("GITHUB_REF", "refs/heads/other"), ("GITHUB_RUN_ATTEMPT", "2"),
    ("GITHUB_REPOSITORY", "other/repo"), ("GITHUB_ACTOR", "other"),
    ("GITHUB_TRIGGERING_ACTOR", "other")])
def test_runtime_rejects_other_entry_points(name, value, monkeypatch):
    env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": live.REPOSITORY, "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_ACTOR": live.OPERATOR, "GITHUB_TRIGGERING_ACTOR": live.OPERATOR,
        "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123"}
    env[name] = value
    with pytest.raises(ValueError):
        live.runtime(env)


def test_live_current_main_charge_head_run_and_qualification(case):
    repo = {"id": live.REPOSITORY_ID}
    calls = {"": repo, "/git/ref/heads/main": {"ref": "refs/heads/main",
        "object": {"type": "commit", "sha": "a" * 40}},
        "/pulls/999": {"number": 999, "head": {"sha": "2" * 40}, "draft": False,
                       "base": {"ref": "main", "repo": repo}, "merged": True},
        "/actions/runs/1": {"event": "workflow_dispatch", "head_branch": "main",
            "head_sha": "a" * 40, "run_attempt": 1, "status": "in_progress",
            "path": live.WORKFLOW, "repository": repo,
            "actor": {"login": live.OPERATOR}, "triggering_actor": {"login": live.OPERATOR}},
        "/actions/runs/123": {"head_sha": "6" * 40, "path": ".github/workflows/ci-ready.yml",
                               "status": "completed", "conclusion": "success", "repository": repo,
                               "run_attempt": 1},
        "/actions/artifacts/456": {"id": 456, "name": "kv-actor-qualification-123-1",
            "expired": False, "digest": "sha256:" + case.plan["qualification"]["archive"]["sha256"],
            "workflow_run": {"id": 123, "head_sha": "6" * 40,
                             "head_repository_id": live.REPOSITORY_ID}}}
    api = SimpleNamespace(request=lambda method, path: calls[path])
    live.verify_live(api, case.plan, "a" * 40, "1")
    for path, field, value in [("/pulls/999", "merged", False),
        ("/actions/runs/1", "run_attempt", 2),
        ("/actions/runs/123", "conclusion", "failure"),
        ("/actions/artifacts/456", "digest", "sha256:" + "0" * 64),
        ("/actions/artifacts/456", "name", "kv-qualification-123-1")]:
        previous = calls[path][field]
        calls[path][field] = value
        with pytest.raises(ValueError):
            live.verify_live(api, case.plan, "a" * 40, "1")
        calls[path][field] = previous


@pytest.mark.parametrize("change", ["exposure", "prompt", "suite", "client", "limits",
                                    "receipt", "archive", "dependency"])
def test_hosted_qualification_cannot_be_swapped_for_generic_ci_or_other_actor(case, change):
    plan = copy.deepcopy(case.plan)
    if change in {"exposure", "prompt", "suite", "client", "limits"}:
        actor = live.read_json(case.root / "actor.json")
        if change == "exposure":
            actor["edit_plan"]["files"] = [{"path": "other-file"}]
        elif change == "suite":
            actor["suite_sha256"] = "9" * 64
        elif change == "client":
            actor["client"] = {"max_requests": 9}
        elif change == "limits":
            actor["edit_plan"]["limits"] = {"max_checks": 9}
        else:
            actor["prompt"] = "different prompt"
        for arm in ("A2", "A3"):
            plan["actors"][arm]["config"] = write(case.root, "actor.json", actor)
    elif change == "receipt":
        plan["qualification"]["receipt"] = write(case.root, "other.json", {"verdict": "PASS"})
    elif change == "archive":
        plan["qualification"]["archive"]["sha256"] = "0" * 64
    else:
        (case.root / "code.py").write_text("changed dependency")
    with pytest.raises(ValueError):
        live.validate_qualification(plan)


def add_exception(case):
    from tools import kv_pilot_admission as admission
    value = {"schema": "kv-one-additional-attempt-v1",
        "key": {"repository_id": live.REPOSITORY_ID, "pr_number": case.plan["charge_pr"]},
        "pr_lifetime_cap_microusd": 350_000_000,
        "pilot_lifetime_cap_microusd": 1_000_000_000, "additional_attempts": 1,
        "prior_binding": {"plan_digest": "8" * 64,
            "run_id": admission.CAMPAIGN_NAMESPACE + "original-campaign",
            "worst_case": admission.FULL_RESERVATION_MICROUSD},
        "pr_checkpoint": case.plan["ledger"]["checkpoint_commit"],
        "daily_checkpoint": case.plan["daily_ledger"]["checkpoint_commit"],
        "campaign_id": case.plan["campaign_id"], "execution_id": case.plan["execution_id"]}
    case.plan.update(schema="kv-live-plan-v2", budget_exception=value)
    return value


def test_only_exact_public_v2_freeze_can_resolve_scoped_cap(case):
    value = add_exception(case)
    # Changing local plan/exception cannot change the verified public bytes.
    assert live.frozen_authorization(fetch=lambda _: case.comment, now=NOW.timestamp())[0][
        "plan"]["schema"] == "kv-live-plan-v1"
    case.authorization.update(plan=case.plan, plan_sha256=live.fingerprint(case.plan))
    case.comment["body"] = live.PREFIX + json.dumps(case.authorization) + live.SUFFIX
    with pytest.raises(ValueError, match="exact bytes"):
        live.frozen_authorization(fetch=lambda _: case.comment, now=NOW.timestamp())
    case.locator["body_sha256"] = live.sha(case.comment["body"].encode())
    write(case.root, "locator.json", case.locator)  # Simulated separately reviewed root binding.
    authorization, _ = live.frozen_authorization(fetch=lambda _: case.comment, now=NOW.timestamp())
    resolved = live.policy(authorization["plan"], "7" * 40)
    assert resolved.trusted_limit.key == live.budget.PRKey(live.REPOSITORY_ID, 999)
    assert resolved.trusted_limit.limit_microusd == 350_000_000
    assert resolved.additional_attempt.prior_binding.run_id == value["prior_binding"]["run_id"]
    assert resolved.additional_attempt.pr_checkpoint == case.plan["ledger"]["checkpoint_commit"]
    assert resolved.reservation(now=NOW.timestamp())["amount"] == "162.72"


@pytest.mark.parametrize("field,value", [
    ("key", {"repository_id": 1409534281, "pr_number": 275}),
    ("key", {"repository_id": 1, "pr_number": 999}),
    ("pr_lifetime_cap_microusd", True), ("pr_lifetime_cap_microusd", 200_000_000),
    ("pr_lifetime_cap_microusd", 1_000_000_001),
    ("pilot_lifetime_cap_microusd", 1_000_000_001),
    ("additional_attempts", True), ("additional_attempts", 2),
    ("pr_checkpoint", "9" * 40), ("daily_checkpoint", "9" * 40),
    ("campaign_id", "different"), ("execution_id", "different"),
    ("prior_binding", None), ("prior_binding", {}), ("unexpected", 350_000_000),
])
def test_v2_exception_cannot_change_key_identity_count_or_anchored_history(case, field, value):
    add_exception(case)[field] = value
    with pytest.raises(ValueError):
        live.validate_plan(case.plan, now=NOW.timestamp())


def test_legacy_plan_rejects_exception_without_versioned_freeze(case):
    add_exception(case)
    case.plan["schema"] = "kv-live-plan-v1"
    with pytest.raises(ValueError):
        live.validate_plan(case.plan, now=NOW.timestamp())
    with pytest.raises(ValueError):
        live.policy(case.plan, "7" * 40)


def test_checked_in_second_attempt_is_exactly_owner_scoped_and_preserves_old_binding():
    root = Path(__file__).resolve().parents[1]
    folder = root / 'evidence/kv-live-pilot-20261031/plan'
    old = live.read_json(folder / 'plan.json')
    old_binding = live.policy(old, '3ece458ceaa92c5dad8d8e0b1e782a6961400b96').binding
    extra = live.read_json(folder / 'second-attempt-budget.json')
    assert extra['key'] == {'repository_id': live.REPOSITORY_ID, 'pr_number': 275}
    assert extra['pr_lifetime_cap_microusd'] == 350_000_000
    assert extra['pilot_lifetime_cap_microusd'] == 1_000_000_000
    assert extra['additional_attempts'] == 1
    assert extra['prior_binding'] == {'plan_digest': old_binding.plan_digest,
        'run_id': old_binding.run_id, 'worst_case': old_binding.worst_case}
    new = {**old, 'schema': 'kv-live-plan-v2', 'budget_exception': extra,
        'campaign_id': extra['campaign_id'], 'execution_id': extra['execution_id'],
        'ledger': {**old['ledger'], 'checkpoint_commit': extra['pr_checkpoint']},
        'daily_ledger': {**old['daily_ledger'], 'checkpoint_commit': extra['daily_checkpoint']}}
    resolved = live.additional_attempt(new)
    assert resolved.limit.key == live.budget.PRKey(live.REPOSITORY_ID, 275)
    assert resolved.limit.limit_microusd == 350_000_000
    assert live.additional_attempt(old) is None
    assert live.budget.PR_LIMIT_MICROUSD == 200_000_000
    assert live.budget.DAILY_LIMIT_MICROUSD == 1_000_000_000
