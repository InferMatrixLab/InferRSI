"""Offline full-context protocol tests: no credentials or network transport."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from inferrsi.model import anthropic_agent as agent


class FullContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name) / "workspace"
        self.workspace.mkdir()
        (self.workspace / "task.json").write_text('{"input":"observations"}\n')
        (self.workspace / "SKILL.md").write_text("Complete knowledge: αβ.\n", encoding="utf-8")
        self.schema = {"type": "object", "properties": {"answer": {"type": "string"}},
                       "required": ["answer"], "additionalProperties": False}
        self.spec = {"kind": agent.FULL_CONTEXT_KIND, "provider": "yibuapi",
                     "endpoint": agent.ENDPOINT, "api_version": "2023-06-01",
                     "max_requests": 1, "max_output_tokens": 4096,
                     "max_request_bytes": 262144, "max_read_bytes": 32768,
                     "max_tool_calls": 1}
        self.model = "claude-opus-5-5"
        self.answer = {"answer": "synthetic protocol fixture"}
        self.response = {"type": "message", "role": "assistant", "model": self.model,
                         "stop_reason": "tool_use", "content": [
                             {"type": "thinking", "thinking": "fixture", "signature": "fake"},
                             {"type": "tool_use", "id": "fixture-one", "name": "submit_answer",
                              "input": self.answer}],
                         "usage": {"input_tokens": 10, "output_tokens": 8,
                                   "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
        self.events, self.requests = [], []

    def run_fixture(self):
        def send(payload, spec, timeout):
            self.requests.append(copy.deepcopy(payload))
            return copy.deepcopy(self.response)
        return agent.run_agent(self.workspace, self.schema, "Fixture prompt", self.model,
                               self.spec, 30, self.events.append, send=send,
                               input_token_ceiling=1000000)

    def trace(self):
        path = Path(self.temporary.name) / "trace.jsonl"
        path.write_text("".join(agent.canonical(e) + "\n" for e in self.events))
        return agent.trace_metrics(path)

    def test_complete_context_single_call_and_true_provenance(self):
        self.assertEqual(self.run_fixture(), self.answer)
        self.assertEqual(len(self.requests), 1)
        payload = self.requests[0]
        self.assertEqual(payload["tool_choice"], {"type": "auto"})
        self.assertEqual([t["name"] for t in payload["tools"]], ["submit_answer"])
        entries = json.loads(payload["messages"][0]["content"].split("\n", 2)[-1])
        self.assertEqual([e["path"] for e in entries], ["SKILL.md", "task.json"])
        for entry in entries:
            data = (self.workspace / entry["path"]).read_bytes()
            self.assertEqual(entry["content"].encode(), data)
            self.assertEqual(entry["bytes"], len(data))
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
        self.assertTrue(self.trace()["usage_complete"])
        self.assertEqual(self.trace()["client_kind"], agent.FULL_CONTEXT_KIND)
        self.assertEqual([e["name"] for e in self.events if e["type"] == "agent.tool"],
                         ["submit_answer"])
        self.assertNotIn("Complete knowledge", agent.canonical(self.events))

    def test_oversize_preflight_sends_nothing(self):
        self.spec["max_request_bytes"] = 100
        with self.assertRaisesRegex(agent.AgentError, "request_bytes_limit"):
            self.run_fixture()
        self.assertFalse(self.requests)

    def test_file_read_limit_is_not_truncation(self):
        self.spec["max_read_bytes"] = 2
        with self.assertRaisesRegex(agent.AgentError, "tool_read_limit"):
            self.run_fixture()
        self.assertFalse(self.requests)

    def test_symlink_is_rejected(self):
        (self.workspace / "escape").symlink_to(Path(self.temporary.name))
        with self.assertRaisesRegex(agent.AgentError, "workspace_symlink"):
            self.run_fixture()
        self.assertFalse(self.requests)

    def test_non_utf8_is_rejected(self):
        (self.workspace / "SKILL.md").write_bytes(b"\xff")
        with self.assertRaisesRegex(agent.AgentError, "invalid_tool_utf8"):
            self.run_fixture()
        self.assertFalse(self.requests)

    def test_plain_text_is_not_submission(self):
        self.response.update(stop_reason="end_turn", content=[{"type": "text", "text": "answer"}])
        with self.assertRaisesRegex(agent.AgentError, "incompatible_response"):
            self.run_fixture()
        self.assertEqual(len(self.requests), 1)
        self.assertFalse(self.trace()["usage_complete"])

    def test_read_or_invalid_submission_never_retries(self):
        for change in ({"name": "read_file"}, {"input": {}}, {"id": ""}):
            with self.subTest(change=change):
                original = copy.deepcopy(self.response)
                self.response["content"][-1].update(change)
                with self.assertRaisesRegex(agent.AgentError, "invalid_or_premature_answer"):
                    self.run_fixture()
                self.response = original
        self.assertEqual(len(self.requests), 3)

    def test_duplicate_submission_is_rejected(self):
        self.response["content"].append(copy.deepcopy(self.response["content"][-1]))
        with self.assertRaisesRegex(agent.AgentError, "invalid_or_premature_answer"):
            self.run_fixture()

    def test_unknown_usage_fails_closed(self):
        self.response["usage"] = None
        with self.assertRaisesRegex(agent.AgentError, "unknown_usage"):
            self.run_fixture()
        self.assertFalse(self.trace()["usage_complete"])

    def test_manifest_corruption_is_not_complete(self):
        self.run_fixture()
        next(e for e in self.events if e["type"] == "agent.context")["files"][0]["bytes"] += 1
        self.assertFalse(self.trace()["usage_complete"])

    def test_no_fake_task_read_contract_for_old_mode(self):
        self.run_fixture()
        self.events = [e for e in self.events if e["type"] != "agent.context"]
        self.assertFalse(self.trace()["usage_complete"])

    def test_preflight_failures_retain_protocol_identity(self):
        cases = ("oversize", "non_utf8", "missing_task")
        for case in cases:
            with self.subTest(case=case):
                self.events.clear()
                self.spec["max_request_bytes"] = 100 if case == "oversize" else 262144
                (self.workspace / "SKILL.md").write_bytes(b"\xff" if case == "non_utf8" else b"ok")
                if case == "missing_task":
                    (self.workspace / "task.json").unlink()
                with self.assertRaises(agent.AgentError):
                    self.run_fixture()
                trace = self.trace()
                self.assertEqual(trace["client_kind"], agent.FULL_CONTEXT_KIND)
                self.assertFalse(trace["usage_complete"])
                self.assertEqual(trace["completed_turns"], 0)
                self.assertFalse(self.requests)
                self.assertFalse(any(e["type"] == "agent.context" for e in self.events))

    def test_exact_payload_cap_and_no_hidden_input(self):
        private = Path(self.temporary.name) / "oracle-private.json"
        private.write_text('{"secret":"opaque-answer-key-fixture"}')
        payload, _ = agent.full_context_payload(self.workspace, self.schema, "Fixture prompt",
                                                self.model, self.spec)
        raw = agent.canonical(payload).encode()
        self.assertNotIn(b"opaque-answer-key-fixture", raw)
        self.spec["max_request_bytes"] = len(raw)
        self.run_fixture()
        self.spec["max_request_bytes"] -= 1
        with self.assertRaisesRegex(agent.AgentError, "request_bytes_limit"):
            self.run_fixture()
        self.assertEqual(len(self.requests), 1)

    def test_old_read_submit_round_trip_unchanged(self):
        self.spec.update(kind=agent.KIND, max_requests=2, max_request_bytes=131072,
                         max_tool_calls=2)
        responses = [copy.deepcopy(self.response), copy.deepcopy(self.response)]
        responses[0]["content"] = [{"type": "tool_use", "name": "read_file",
                                    "id": "read-one", "input": {"path": "task.json"}}]
        def send(payload, spec, timeout):
            self.requests.append(copy.deepcopy(payload))
            return responses[len(self.requests) - 1]
        self.assertEqual(agent.run_agent(self.workspace, self.schema, "Fixture", self.model,
                                         self.spec, 30, self.events.append, send=send), self.answer)
        self.assertTrue(self.trace()["usage_complete"])
        self.assertEqual(self.trace()["client_kind"], agent.KIND)
        self.assertEqual(len(self.requests), 2)
        self.assertFalse(any(e["type"] == "agent.context" for e in self.events))

    def test_separate_limits_and_cost(self):
        for changes in ({"max_requests": 2}, {"max_request_bytes": 262145},
                        {"kind": agent.KIND}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                agent.validate_spec({"name": self.model, "effort": "not_applicable"},
                                    {**self.spec, **changes})
        pricing = {"currency": "USD", "unit": "per_million_tokens", "model": self.model,
                   "group": "fixture", "rates": {"input": "8", "output": "40",
                   "cache_read": "0.4", "cache_write": "10"}, "request_fee": "0",
                   "max_input_tokens": 1000000, "expires_at": 2000000000,
                   "rate_evidence": "https://github.com/example/project/issues/1#issuecomment-1"}
        reserved = agent.reservation(self.model, self.spec, pricing,
                                     {"currency": "USD", "amount": "77.96"}, 2, now=0)
        self.assertEqual(reserved["amount"], "20.34")
        self.assertEqual(reserved["requests"], 2)


if __name__ == "__main__":
    unittest.main()
