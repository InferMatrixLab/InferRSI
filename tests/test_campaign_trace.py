"""Correlation preserves original agent fields and existing trace metrics."""

import hashlib
import json

import pytest

from inferrsi.harness.campaign_trace import CampaignTrace
from inferrsi.model import anthropic_agent as agent


def test_correlated_full_context_trace_keeps_existing_metrics(tmp_path):
    manifest = [{"path": "task.json", "bytes": 2, "sha256": "a" * 64}]
    digest = hashlib.sha256(agent.canonical(manifest).encode()).hexdigest()
    usage = {"input_tokens": 10, "output_tokens": 8, "cached_input_tokens": 0}
    events = [
        {"type": "agent.protocol", "client_kind": agent.FULL_CONTEXT_KIND},
        {"type": "agent.context", "client_kind": agent.FULL_CONTEXT_KIND,
         "files": manifest, "manifest_sha256": digest},
        {"type": "agent.request", "request": 1},
        {"type": "agent.response", "request": 1, "usage": usage, "provider_model": "fixture"},
        {"type": "agent.tool", "request": 1, "name": "submit_answer"},
        {"type": "agent.completed", "requests": 1, "usage": usage},
    ]
    original = tmp_path / "original.jsonl"
    original.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    path = tmp_path / "correlated.jsonl"
    writer = CampaignTrace(path, campaign_id="campaign", candidate_id="candidate", stage="search",
                           run_id="run", round_number=1)
    for event in events:
        writer(event)
    correlated = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert all(all(row[key] == value for key, value in original_event.items())
               for row, original_event in zip(correlated, events))
    before, after = agent.trace_metrics(original), agent.trace_metrics(path)
    for key in ("usage", "observed_usage", "usage_complete", "completed_turns", "api_requests",
                "client_kind", "provider_model"):
        assert after[key] == before[key]
    assert after["usage_complete"] is True

    correlated[0]["stage"] = "invalid-stage"
    path.write_text("".join(json.dumps(event) + "\n" for event in correlated), encoding="utf-8")
    assert agent.trace_metrics(path)["usage_complete"] is False


def test_trace_rejects_envelope_collisions(tmp_path):
    writer = CampaignTrace(tmp_path / "trace.jsonl", campaign_id="c", candidate_id="a",
                           stage="search")
    with pytest.raises(ValueError, match="correlation fields"):
        writer({"type": "agent.tool", "stage": "execution"})
    assert not (tmp_path / "trace.jsonl").exists()
