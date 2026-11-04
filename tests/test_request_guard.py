"""Credential-free checks: only loopback traffic and injected provider transports."""

import concurrent.futures
import hashlib
import http.client
import json

import pytest

from inferrsi.model import anthropic_agent as agent
from inferrsi.model import request_guard as guard


def request(env, *, token=None, context=None, identity="a" * 64):
    connection = http.client.HTTPConnection("127.0.0.1", int(env[guard.ENV_KEYS[0]]), timeout=2)
    body = {"context": context or env[guard.ENV_KEYS[2]], "request_id": identity,
            "payload_sha256": hashlib.sha256(b"payload").hexdigest()}
    try:
        connection.request("POST", "/authorize", json.dumps(body), {
            "Authorization": "Bearer " + (token or env[guard.ENV_KEYS[1]])})
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def test_each_request_checks_live_authorization_and_revocation_latches():
    calls = []

    def check():
        calls.append(1)
        return len(calls) == 1

    with guard.authorization_broker(check, 5, context="plan:run") as env:
        guard.authorize_request(b"first", environment=env)
        with pytest.raises(guard.AuthorizationError):
            guard.authorize_request(b"second", environment=env)
        with pytest.raises(guard.AuthorizationError):
            guard.authorize_request(b"third", environment=env)
    assert len(calls) == 2


def test_failed_callback_fails_closed_without_disclosing_details():
    def check():
        raise RuntimeError("private GitHub credential failure detail")

    with guard.authorization_broker(check, 2, context="plan:run") as env:
        with pytest.raises(guard.AuthorizationError, match="^request_authorization_denied$"):
            guard.authorize_request(b"request", environment=env)


def test_unauthenticated_wrong_context_and_replays_do_not_consume_extra_grants():
    calls = []
    with guard.authorization_broker(lambda: calls.append(1), 2, context="plan:run") as env:
        assert request(env, token="b" * 64) == 403
        assert request(env, context="c" * 64) == 403
        assert calls == []
        assert request(env) == 200
        assert request(env) == 403
        assert request(env, identity="d" * 64) == 200
        assert request(env, identity="e" * 64) == 403
    assert calls == [1, 1]


def test_concurrent_requests_cannot_exceed_total_bound():
    calls = []
    with guard.authorization_broker(lambda: calls.append(1), 3, context="plan:run") as env:
        def send(index):
            return request(env, identity=f"{index:064x}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(send, range(6)))
    assert statuses.count(200) == 3 and len(calls) == 3


def test_broker_loss_missing_and_partial_configuration_fail_closed():
    with guard.authorization_broker(lambda: None, 1, context="plan:run") as env:
        pass
    for value in ({}, {guard.ENV_KEYS[0]: "1234"}, env):
        with pytest.raises(guard.AuthorizationError):
            guard.authorize_request(b"request", environment=value)


def test_capability_cannot_be_reused_for_other_plan_or_run():
    with guard.authorization_broker(lambda: None, 1, context="plan:run-one") as first:
        with guard.authorization_broker(lambda: None, 1, context="plan:run-two") as second:
            mixed = {**second, guard.ENV_KEYS[1]: first[guard.ENV_KEYS[1]]}
            with pytest.raises(guard.AuthorizationError):
                guard.authorize_request(b"request", environment=mixed)
            guard.authorize_request(b"request", environment=second)


def test_required_provider_guard_stops_before_network(monkeypatch):
    spec = {"kind": agent.KIND, "provider": "yibuapi", "endpoint": agent.ENDPOINT,
            "api_version": "2023-06-01", "max_requests": 2, "max_output_tokens": 256,
            "max_request_bytes": 8192, "max_read_bytes": 1024, "max_tool_calls": 8}
    monkeypatch.setattr(agent.urllib.request, "build_opener",
                        lambda *args: pytest.fail("Provider must not be contacted"))
    with pytest.raises(agent.AgentError, match="request_authorization_denied"):
        agent.send_message({"model": "claude-opus-5-5"}, spec, "offline-key", 2,
                           environment={}, require_authorization=True)


def test_runtime_environment_passes_only_gate_and_provider_not_github():
    with guard.authorization_broker(lambda: None, 1, context="plan:run") as env:
        runtime = agent.execution_environment({**env, agent.KEY_ENV: "offline-key",
                                               "GH_TOKEN": "not-a-real-token",
                                               "GITHUB_TOKEN": "not-a-real-token"})
        assert all(runtime[key] == env[key] for key in guard.ENV_KEYS)
        assert "GH_TOKEN" not in runtime and "GITHUB_TOKEN" not in runtime
        verifier = agent.execution_environment(runtime, with_key=False)
        assert all(key not in verifier for key in guard.ENV_KEYS)
        assert agent.KEY_ENV not in verifier


def test_real_transport_hook_checks_each_call_and_stops_after_revocation(monkeypatch):
    import io

    spec = {"kind": agent.KIND, "provider": "yibuapi", "endpoint": agent.ENDPOINT,
            "api_version": "2023-06-01", "max_requests": 3, "max_output_tokens": 256,
            "max_request_bytes": 8192, "max_read_bytes": 1024, "max_tool_calls": 8}
    checks, sends = [], []

    def check():
        checks.append(1)
        return len(checks) < 3

    class OfflineProvider:
        def open(self, request, timeout):
            sends.append(request)
            return io.BytesIO(b'{"type":"message"}')

    monkeypatch.setattr(agent.urllib.request, "build_opener", lambda *args: OfflineProvider())
    with guard.authorization_broker(check, 5, context="plan:run") as env:
        for _ in range(2):
            agent.send_message({"model": "claude-opus-5-5"}, spec, "offline-key", 2,
                               environment=env, require_authorization=True)
        with pytest.raises(agent.AgentError, match="request_authorization_denied"):
            agent.send_message({"model": "claude-opus-5-5"}, spec, "offline-key", 2,
                               environment=env, require_authorization=True)
    assert len(checks) == 3 and len(sends) == 2
