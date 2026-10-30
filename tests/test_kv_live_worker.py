"""Synthetic-key/fake-HTTP controls only; never provider calls or live ledger access."""

import copy
import time
from unittest.mock import Mock

import pytest

from inferrsi.model import anthropic_agent as provider
from tests.test_anthropic_edit_agent import read_task
from tools import kv_live_worker as worker

GATE = {"SKILL_EVAL_GATE_PORT": "1234", "SKILL_EVAL_GATE_TOKEN": "a" * 64,
        "SKILL_EVAL_GATE_CONTEXT": "b" * 64}


def sender(tmp_path, *, transport=None):
    config = {"model": "claude-opus-5-5", "input_token_ceiling": 1000000,
              "client": {"max_requests": 8, "max_output_tokens": 4096}}
    http = transport or Mock(return_value=read_task())
    ipc = Mock()
    value = worker.GrantedSender(config, tmp_path, time.monotonic() + 600,
        key="OFFLINE-FAKE-KEY", gate=GATE, transport=http, authorize_ipc=ipc)
    return value, http, ipc


def grant(payload, slot=1):
    return {"request_sha256": worker.edit.digest(provider.canonical(payload).encode()),
            "slot": slot}


def test_exactly_one_gate_and_http_per_slot_with_no_implicit_second_gate(tmp_path):
    value, http, ipc = sender(tmp_path)
    payload = {"model": "claude-opus-5-5"}
    for slot in range(1, 9):
        assert value.authorize(grant(payload, slot), value.deadline)
        value.send(payload, value.config["client"], 100)
    assert value.attempts == ipc.call_count == http.call_count == 8
    assert http.call_args.kwargs == {"environment": {}, "require_authorization": False}
    assert http.call_args.args[2] == "OFFLINE-FAKE-KEY"
    with pytest.raises(provider.AgentError):
        value.send(payload, value.config["client"], 100)
    assert http.call_count == 8
    raw = worker.scripted._read_json(tmp_path / "complete.json")
    assert raw["usage"] == read_task()["usage"]  # RAW cache classes, not normalized totals.
    assert "OFFLINE-FAKE-KEY" not in (tmp_path / "complete.json").read_text()


@pytest.mark.parametrize("failure", ["transport", "lost_gate", "hash", "spec", "deadline"])
def test_no_retry_or_http_without_one_exact_valid_grant(tmp_path, failure):
    value, http, ipc = sender(tmp_path)
    payload = {"model": "claude-opus-5-5"}
    if failure == "lost_gate":
        ipc.side_effect = OSError("offline lost reply")
        with pytest.raises(OSError):
            value.authorize(grant(payload), value.deadline)
    else:
        value.authorize(grant(payload), value.deadline)
    spec = value.config["client"]
    if failure == "transport":
        http.side_effect = OSError("OFFLINE-FAKE-KEY must not enter error")
    elif failure == "hash":
        payload["changed"] = True
    elif failure == "spec":
        spec = {**spec, "max_requests": 9}
    elif failure == "deadline":
        value.deadline = time.monotonic() - 1
    with pytest.raises(provider.AgentError) as error:
        value.send(payload, spec, 100)
    assert "OFFLINE-FAKE-KEY" not in str(error.value)
    with pytest.raises(provider.AgentError):
        value.send(payload, spec, 100)
    assert http.call_count == (1 if failure == "transport" else 0)


@pytest.mark.parametrize("change", ["missing", "late", "wrong_model", "over_bound"])
def test_unknown_response_usage_is_relayed_as_unresolved_not_refunded(tmp_path, change):
    response = copy.deepcopy(read_task())
    if change == "missing":
        response["usage"].pop("cache_creation_input_tokens")
    elif change == "wrong_model":
        response["model"] = "other"
    elif change == "over_bound":
        response["usage"]["output_tokens"] = 4097
    value, _, _ = sender(tmp_path, transport=Mock(return_value=response))
    if change == "late":
        def late(*args, **kwargs):
            value.deadline = time.monotonic() - 1
            return response
        value.transport = late
    payload = {"model": "claude-opus-5-5"}
    value.authorize(grant(payload), value.deadline)
    value.send(payload, value.config["client"], 100)
    assert worker.scripted._read_json(tmp_path / "complete.json")["usage"] is None



def test_ninth_authorized_send_cannot_make_a_ninth_http_attempt(tmp_path):
    value, http, _ = sender(tmp_path)
    payload = {"model": "claude-opus-5-5"}
    for slot in range(1, 9):
        value.authorize(grant(payload, slot), value.deadline)
        value.send(payload, value.config["client"], 100)
    value.authorize(grant(payload, 9), value.deadline)
    with pytest.raises(provider.AgentError):
        value.send(payload, value.config["client"], 100)
    assert http.call_count == 8
