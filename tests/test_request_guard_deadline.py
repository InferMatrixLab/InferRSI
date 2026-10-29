"""Offline deadline regressions: fake clock/transport, plus loopback disconnect."""

import io
import json
import socketserver
import unittest
from unittest.mock import patch

from inferrsi.model import anthropic_agent as agent
from inferrsi.model import request_guard as guard


class AuthorizationDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.clock = 100.0
        self.delay = 12
        self.status = 200
        self.corrupt = self.lost = False
        self.connections, self.requests, self.sends = [], [], []
        self.closed = 0
        self.env = dict(zip(guard.ENV_KEYS, ("12345", "a" * 64, "b" * 64)))
        owner = self

        class Connection:
            def __init__(self, host, port, timeout):
                owner.assertEqual((host, port), ("127.0.0.1", 12345))
                owner.connections.append(timeout)

            def request(self, method, path, body, headers):
                owner.assertEqual((method, path), ("POST", "/authorize"))
                self.body = body
                owner.requests.append(json.loads(body))

            def getresponse(self):
                return self

            @property
            def status(self):
                return owner.status

            def read(self, size):
                owner.assertEqual(size, 1025)
                owner.clock += owner.delay
                if owner.lost:
                    raise TimeoutError("lost grant")
                return b'{}' if owner.corrupt else self.body

            def close(self):
                owner.closed += 1

        class Provider:
            def open(self, request, timeout):
                owner.sends.append(timeout)
                return io.BytesIO(b'{"type":"message"}')

        for replacement in (
            patch.object(guard.time, "monotonic", lambda: self.clock),
            patch.object(guard.http.client, "HTTPConnection", Connection),
            patch.object(agent, "authorize_request", guard.authorize_request),
            patch.object(agent.urllib.request, "build_opener", lambda *args: Provider()),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)

    def send(self, timeout=180):
        spec = {"kind": agent.FULL_CONTEXT_KIND, "provider": "yibuapi", "endpoint": agent.ENDPOINT,
                "api_version": "2023-06-01", "max_requests": 1, "max_output_tokens": 256,
                "max_request_bytes": 8192, "max_read_bytes": 1024, "max_tool_calls": 8}
        return agent.send_message({"model": "claude-opus-5-5"}, spec, "offline-key", timeout,
                                  environment=self.env, require_authorization=True)

    def test_delayed_valid_grant_debits_provider_timeout(self):
        self.assertEqual(self.send(), {"type": "message"})
        self.assertEqual(self.connections, [60])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.closed, 1)
        self.assertEqual(self.sends, [168])

    def test_gate_wait_is_bounded_by_remaining_and_sixty_seconds(self):
        for timeout, delay in [(20, 12), (180, 59)]:
            with self.subTest(timeout=timeout):
                self.delay = delay
                guard.authorize_request(b"request", environment=self.env, timeout=timeout)
                self.assertEqual(self.connections[-1], min(timeout, 60))

    def test_late_unknown_or_denied_grants_never_contact_provider_or_retry(self):
        cases = [(180, {"delay": 60}), (180, {"delay": 61}), (12, {"delay": 12}),
                 (0, {}), (-1, {}), (float("nan"), {}), (float("inf"), {}),
                 (180, {"status": 403}), (180, {"corrupt": True}), (180, {"lost": True})]
        for timeout, changes in cases:
            with self.subTest(timeout=timeout, changes=changes):
                self.delay, self.status, self.corrupt, self.lost = 12, 200, False, False
                self.connections.clear()
                self.requests.clear()
                self.closed = 0
                for key, value in changes.items():
                    setattr(self, key, value)
                with self.assertRaisesRegex(agent.AgentError, "^request_authorization_denied$"):
                    self.send(timeout)
                self.assertEqual(self.sends, [])
                self.assertLessEqual(len(self.requests), 1)
                self.assertEqual(self.closed, len(self.connections))

    def test_trial_exhausted_after_grant_never_contacts_provider(self):
        def consumed_deadline(*args, **kwargs):
            self.clock = 280.0

        with patch.object(agent, "authorize_request", consumed_deadline):
            with self.assertRaisesRegex(agent.AgentError, "^timeout$"):
                self.send()
        self.assertEqual(self.sends, [])


class DroppedGrantTests(unittest.TestCase):
    def test_dropped_grant_keeps_slot_consumed_and_sends_no_second_response(self):
        statuses, checks = [], []
        original = guard.BaseHTTPRequestHandler.send_response
        original_write = socketserver._SocketWriter.write

        def drop_grant(handler, code, message=None):
            statuses.append(code)
            return original(handler, code, message)

        def drop_body(writer, data):
            if data.startswith(b'{"context":'):
                raise BrokenPipeError("disconnected client")
            return original_write(writer, data)

        with patch.object(guard.BaseHTTPRequestHandler, "send_response", drop_grant), \
                patch.object(socketserver._SocketWriter, "write", drop_body):
            with guard.authorization_broker(lambda: checks.append(1), 1,
                                            context="plan:run") as env:
                for payload in (b"first", b"second"):
                    with self.assertRaisesRegex(guard.AuthorizationError,
                                                "^request_authorization_denied$"):
                        guard.authorize_request(payload, environment=env)
        self.assertEqual(statuses, [200, 403])
        self.assertEqual(checks, [1])


if __name__ == "__main__":
    unittest.main()
