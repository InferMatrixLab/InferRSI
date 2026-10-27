import copy
import json
import sys
from pathlib import Path
from decimal import Decimal

import pytest
import yaml

from inferrsi.harness import skill_evaluation as harness
from inferrsi.infra.artifacts import write_json
from inferrsi.model import anthropic_agent as agent
from tests.fixtures.skill_eval_compare_support import DATA
from tests.fixtures.skill_eval_pr_support import SimulatedGitHub, approval, setup
from tests.test_anthropic_agent import ANSWER, MODEL, SCHEMA_SMALL, read, submit
from tools import skill_eval_compare as compare
from tools import skill_eval_pr as integration
from tools import skill_eval_verifier as verifier

FAKE_KEY = "fake-provider-key-offline-only"


def configuration():
    # Synthetic prices exercise arithmetic; these are not the owner's provider rates.
    return {"model": {"name": MODEL, "effort": "not_applicable"},
            "client": {"kind": agent.KIND, "provider": "yibuapi", "endpoint": agent.ENDPOINT,
                       "api_version": "2023-06-01", "max_requests": 3, "max_output_tokens": 256,
                       "max_request_bytes": 32768, "max_read_bytes": 16384, "max_tool_calls": 8},
            "pricing": {"currency": "USD", "unit": "per_million_tokens", "model": MODEL,
                        "group": "offline-fixture", "rates": {"input": "2", "output": "4",
                        "cache_read": "0.1", "cache_write": "5"}, "request_fee": "0",
                        "max_input_tokens": 1000000, "expires_at": 4102444800,
                        "rate_evidence":
                        "https://github.com/example/fixture/issues/1#issuecomment-1"},
            "spend_limit": {"currency": "USD", "amount": "100"}}


def client(profile):
    return agent.AnthropicAgentClient(MODEL, profile["client"], 30,
                                      profile["pricing"], profile["spend_limit"])


def test_full_context_reservation_uses_highest_cache_rate_and_all_attempts():
    p = configuration()
    value = agent.reservation(MODEL, p["client"], p["pricing"], p["spend_limit"], 2)
    expected = (Decimal(1000000) * 5 + Decimal(256) * 4) / 1000000 * 6
    assert value["requests"] == 6 and value["currency"] == "USD"
    assert Decimal(value["amount"]) >= expected
    assert value["group"] == p["pricing"]["group"]
    p["spend_limit"]["amount"] = "1"
    with pytest.raises(ValueError, match="exceeds"):
        client(p).require_live_readiness(2)


@pytest.mark.parametrize("change", [
    lambda p: p["pricing"].pop("unit"),
    lambda p: p["pricing"]["rates"].pop("cache_write"),
    lambda p: p["pricing"]["rates"].update(input="NaN"),
    lambda p: p["pricing"].update(max_input_tokens=999999),
    lambda p: p["pricing"].update(expires_at=1),
    lambda p: p["pricing"].update(currency="CNY"),
    lambda p: p["pricing"].update(group=""),
])
def test_missing_unknown_stale_or_understated_cost_facts_fail_closed(change):
    p = configuration()
    change(p)
    with pytest.raises(ValueError):
        client(p).require_live_readiness(2)


def test_worker_argv_environment_and_verifier_keep_credentials_separate(tmp_path):
    p = configuration()
    c = client(p)
    command = c.command(tmp_path, tmp_path / "answer", tmp_path / "schema", "public prompt")
    assert command[:2] == (sys.executable, "-I")
    assert FAKE_KEY not in " ".join(command) and "codex" not in command
    values = {"PATH": "fixture", agent.KEY_ENV: FAKE_KEY, "GITHUB_TOKEN": "fake-github",
              "ACTIONS_RUNTIME_TOKEN": "fake-runtime", "OTHER_SECRET": "fake-other"}
    model = agent.execution_environment(values)
    grading = agent.execution_environment(values, with_key=False)
    assert model[agent.KEY_ENV] == FAKE_KEY and agent.KEY_ENV not in grading
    assert all(k not in model and k not in grading for k in
               ("GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN", "OTHER_SECRET"))
    with pytest.raises(ValueError, match="credential"):
        agent.execution_environment({})


def test_worker_runs_read_submit_with_fake_transport_and_no_key_in_evidence(tmp_path):
    p = configuration()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_json(workspace / "task.json", {"input": "public fixture"})
    schema, final = tmp_path / "schema.json", tmp_path / "answer.json"
    write_json(schema, SCHEMA_SMALL)
    events, calls = [], []

    def transport(payload, spec, key, timeout):
        assert key == FAKE_KEY
        calls.append(copy.deepcopy(payload))
        return read() if len(calls) == 1 else submit()

    args = ["--workspace", str(workspace), "--final", str(final), "--schema", str(schema),
            "--settings", agent.canonical(p), "--prompt", "public fixture", "--timeout", "30"]
    assert agent.main(args, environment={agent.KEY_ENV: FAKE_KEY},
                      transport=transport, emit=events.append) == 0
    assert json.loads(final.read_text()) == ANSWER and len(calls) == 2
    assert FAKE_KEY not in agent.canonical(events) and FAKE_KEY not in agent.canonical(calls)
    before = len(calls)
    assert agent.main(args, environment={}, transport=transport, emit=events.append) == 1
    assert len(calls) == before


def install_fake_worker(monkeypatch):
    sent = []

    def environment(self):
        return {agent.KEY_ENV: FAKE_KEY}

    def execute(command, cwd, folder, deadline, **options):
        folder.mkdir(parents=True)
        (folder / "stderr.log").write_text("", encoding="utf-8")
        if folder.name == "agent":
            assert options["environment"] == {agent.KEY_ENV: FAKE_KEY}
            events = []

            def transport(payload, spec, key, timeout):
                sent.append(copy.deepcopy(payload))
                assert key == FAKE_KEY
                if len(payload["messages"]) == 1:
                    return read()
                return submit(DATA["cases"][0]["answer"])

            status = agent.main(command[3:], environment=options["environment"],
                                transport=transport, emit=events.append)
            (folder / "stdout.log").write_text(
                "".join(agent.canonical(e) + "\n" for e in events), encoding="utf-8")
        else:
            assert agent.KEY_ENV not in options["environment"]
            checks = verifier.verify(json.loads((cwd / "task.json").read_text()),
                                     json.loads(Path(command[-1]).read_text(encoding="utf-8")))
            write_json(folder / "result.json", checks)
            (folder / "stdout.log").write_text("", encoding="utf-8")
            status = 0 if checks["passed"] else 1
        return {"status": "completed" if status == 0 else "failed",
                "returncode": status, "elapsed_seconds": 0}

    monkeypatch.setattr(agent.AnthropicAgentClient, "environment", environment)
    monkeypatch.setattr(agent.AnthropicAgentClient, "verifier_environment", lambda self: {})
    monkeypatch.setattr(harness, "execute_command", execute)
    return sent


@pytest.mark.parametrize("mode", ["addition", "update"])
def test_configured_paired_execute_retained_feedback_and_one_shot(tmp_path, monkeypatch, mode):
    repo, mapping, identity = setup(tmp_path, mode, ids=("one",))
    p, output = configuration(), tmp_path / "run"
    plan = integration.prepare(repo, mapping, identity, output, provider=p)
    frozen = compare.load_plan(output / "selected")
    assert frozen["client"]["runtime_state"] == "configured"
    assert plan["reservation"]["requests"] == 6
    assert integration.budget(plan)["provider_config_sha256"] == integration.fingerprint(p)
    sent = install_fake_worker(monkeypatch)
    integration.execute(output, approval(plan))
    results = integration.reports(output)
    assert len(sent) == 4 and results[0]["counts"]["unchanged_correct"] == 1
    assert results[0]["status"]["execution_state"] == "completed"
    with pytest.raises(FileExistsError):
        integration.execute(output, approval(plan))
    assert len(sent) == 4
    data = integration.result_archive(output).read_bytes()
    published = tmp_path / "publisher"
    integration.prepare(repo, mapping, identity, published, provider=p)
    api = SimulatedGitHub(plan, data)
    integration.publish_retained(api, published, 10, 11, 1)
    assert len(api.comments) == 1 and '"unchanged_correct":1' in api.comments[0]["body"]
    for path in output.rglob("*"):
        if path.is_file():
            assert FAKE_KEY.encode() not in path.read_bytes()


def test_missing_key_and_stale_rates_precede_local_claim(tmp_path, monkeypatch):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    p, output = configuration(), tmp_path / "run"
    plan = integration.prepare(repo, mapping, identity, output, provider=p)

    def missing(self):
        raise ValueError("Provider credential is missing")

    monkeypatch.setattr(agent.AnthropicAgentClient, "environment", missing)
    with pytest.raises(ValueError, match="credential"):
        integration.execute(output, approval(plan))
    assert not (output / "execution-claim.json").exists()
    assert not list((output / "selected/results").iterdir())
    p["pricing"]["expires_at"] = 1
    expired = integration.prepare(repo, mapping, identity, tmp_path / "expired", provider=p)
    with pytest.raises(ValueError, match="expired"):
        approval(expired)


def test_paid_path_stops_on_unknown_usage_and_never_retries(tmp_path, monkeypatch):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    p, output = configuration(), tmp_path / "run"
    plan = integration.prepare(repo, mapping, identity, output, provider=p)
    monkeypatch.setattr(agent.AnthropicAgentClient, "environment", lambda self: {})
    calls = []

    def stopped(folder, digest, **kwargs):
        calls.append(kwargs)
        assert kwargs["stop_on_unknown_usage"] is True
        return {"status": {"execution_state": "stopped", "stop_reason": "unknown_usage"}}

    monkeypatch.setattr(compare, "execute", stopped)
    integration.execute(output, approval(plan))
    assert len(calls) == 1
    with pytest.raises(FileExistsError):
        integration.execute(output, approval(plan))
    assert len(calls) == 1


def test_secret_only_exists_on_conditional_model_execution_step():
    workflow = yaml.safe_load((compare.ROOT / integration.WORKFLOW).read_text(encoding="utf-8"))
    grants = []
    for job, definition in workflow["jobs"].items():
        for step in definition["steps"]:
            if agent.KEY_ENV in step.get("env", {}):
                grants.append((job, step))
    assert len(grants) == 1 and grants[0][0] == "execute"
    step = grants[0][1]
    assert agent.KIND in step["if"] and "skill_eval_pr execute" in step["run"]
    assert set(step["env"]) == {agent.KEY_ENV}
    assert "secrets.SKILL_EVAL_YIBUAPI_KEY" in step["env"][agent.KEY_ENV]
    assert agent.KEY_ENV not in workflow.get("env", {}) and "GITHUB_TOKEN" not in step["env"]
    codex = next(s for s in workflow["jobs"]["execute"]["steps"]
                 if s.get("run") == "codex --version")
    assert "codex" in codex["if"]


def test_thinking_blocks_are_preserved_opaquely_in_tool_round_trip(tmp_path):
    p = configuration()
    write_json(tmp_path / "task.json", {"input": "public fixture"})
    messages = []

    def send(payload, spec, timeout):
        messages.append(copy.deepcopy(payload))
        if len(messages) == 1:
            value = read()
            value["content"].insert(0, {"type": "thinking", "thinking": "",
                                        "signature": "opaque-fixture-signature"})
            return value
        return submit()

    assert agent.run_agent(tmp_path, SCHEMA_SMALL, "fixture", MODEL, p["client"], 30,
                           lambda e: None, send=send) == ANSWER
    assert messages[1]["messages"][1]["content"][0]["signature"] == "opaque-fixture-signature"


@pytest.mark.parametrize("block", [
    {"type": "thinking", "thinking": None, "signature": "opaque"},
    {"type": "thinking", "thinking": "", "signature": None},
    {"type": "redacted_thinking", "data": None},
])
def test_malformed_thinking_blocks_fail_before_replay(block):
    assert not agent.valid_content_block(block)
