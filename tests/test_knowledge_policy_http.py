"""Offline HTTP diagnostics; all transport calls are replaced by fixtures."""

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from tools import check_knowledge_model_policy as policy


def failure(code, message="", headers=None):
    return HTTPError("https://example.invalid/private?token=FAKE_SECRET", code,
                     "FAKE_SECRET", headers or {},
                     io.BytesIO(json.dumps({"message": message,
                                           "errors": ["FAKE_SECRET"]}).encode()))


class DiagnosticsTests(unittest.TestCase):
    def test_permission_is_not_rate_limit(self):
        error = policy.GitHubHTTPError(failure(403, "Resource not accessible by integration"))
        self.assertEqual(error.category, "permission")
        self.assertIsNone(error.delay)

    def test_unknown_403_and_validation_do_not_infer_cause(self):
        self.assertEqual(policy.GitHubHTTPError(failure(403)).category, "unknown")
        error = policy.GitHubHTTPError(failure(422, "Validation Failed"))
        self.assertEqual(error.category, "validation")
        self.assertNotIn("capacity", str(error))

    def test_allowlist_does_not_echo_secrets(self):
        error = policy.GitHubHTTPError(failure(403, "FAKE_SECRET", {
            "Authorization": "FAKE_SECRET", "Retry-After": "FAKE_SECRET",
            "X-GitHub-Request-Id": "FAKE_SECRET", "X-RateLimit-Remaining": "0"}))
        self.assertNotIn("FAKE_SECRET", policy.evaluation_failure(error)["errors"][0])
        self.assertNotIn("example.invalid", str(error))
        self.assertIn('"x-ratelimit-remaining": 0', str(error))

    def test_explicit_status_capacity_reason_is_recognized(self):
        body = {"message": "Validation Failed", "errors": [{"resource": "Status",
                "code": "custom", "message":
                "This SHA and context has reached the maximum number of statuses."}]}
        original = HTTPError("https://example.invalid", 422, "", {},
                             io.BytesIO(json.dumps(body).encode()))
        error = policy.GitHubHTTPError(original)
        self.assertEqual(error.category, "validation")
        self.assertIn('"reason": "status-capacity"', str(error))
        self.assertNotIn("This SHA", str(error))

    def test_unknown_validation_is_redacted_and_not_inferred_as_capacity(self):
        capacity = "This SHA and context has reached the maximum number of statuses."
        for item in ({"resource": "Status", "code": "custom", "message": "FAKE_SECRET"},
                     {"resource": "Status", "code": "custom",
                      "message": capacity + " FAKE_SECRET"},
                     {"resource": "Other", "code": "custom", "message": capacity},
                     "FAKE_SECRET", None):
            with self.subTest(item=item):
                body = {"message": "FAKE_SECRET", "errors": [item]}
                original = HTTPError("https://example.invalid", 422, "", {},
                                     io.BytesIO(json.dumps(body).encode()))
                error = policy.GitHubHTTPError(original)
                self.assertIn('"reason": "unknown"', str(error))
                self.assertNotIn("status-capacity", str(error))
                self.assertNotIn("FAKE_SECRET", str(error))

    def test_body_read_is_bounded_and_invalid_json_is_safe(self):
        body = io.BytesIO(b"x" * 20000)
        error = HTTPError("https://example.invalid", 403, "", {}, body)
        with patch.object(body, "read", wraps=body.read) as read:
            self.assertEqual(policy.GitHubHTTPError(error).category, "unknown")
            read.assert_called_once_with(8192)

    def test_one_header_evidenced_get_retry(self):
        response = io.BytesIO(b"{}")
        response.headers = {}
        api = policy.GitHub("example/repository", None)
        with patch.object(policy, "urlopen", side_effect=[
                failure(403, headers={"Retry-After": "1"}), response]) as transport, \
                patch.object(policy.time, "sleep") as sleep:
            self.assertEqual(api.get("pulls"), {})
            self.assertEqual(transport.call_count, 2)
            sleep.assert_called_once_with(1)

    def test_retry_timeout_shrinks_after_wait_and_request_time(self):
        response = io.BytesIO(b"{}")
        response.headers = {}
        with patch.object(policy, "urlopen", side_effect=[
                failure(429, headers={"Retry-After": "2"}), response]) as transport, \
                patch.object(policy.time, "monotonic", side_effect=[100, 100, 103, 105]), \
                patch.object(policy.time, "sleep") as sleep:
            self.assertEqual(policy.GitHub("example/repository", None).get("pulls"), {})
            self.assertEqual([call.kwargs["timeout"] for call in transport.call_args_list],
                             [30, 25])
            sleep.assert_called_once_with(2)

    def test_reset_header_fallback_request_id_and_response_closed(self):
        original = failure(403, headers={"X-RateLimit-Remaining": "0",
                                        "X-RateLimit-Reset": "105",
                                        "X-GitHub-Request-Id": "ABCD:1234:EF56"})
        with patch.object(policy.time, "time", return_value=100), \
                patch.object(original, "close", wraps=original.close) as close:
            error = policy.GitHubHTTPError(original)
            self.assertEqual(error.category, "rate-limit")
            self.assertEqual(error.delay, 6)
            self.assertIn('"request_id": "ABCD:1234:EF56"', str(error))
            close.assert_called_once_with()

    def test_no_guessed_or_unbounded_wait(self):
        for code, headers, timeout in [(403, {}, 30), (422, {}, 30),
                                       (429, {"Retry-After": "120"}, 30),
                                       (403, {"Retry-After": "5"}, 3)]:
            with self.subTest(code=code, headers=headers), \
                    patch.object(policy, "urlopen", side_effect=failure(code, headers=headers)) \
                    as transport, patch.object(policy.time, "sleep") as sleep:
                with self.assertRaises(policy.GitHubHTTPError):
                    policy.GitHub("example/repository", None).request("pulls", timeout=timeout)
                self.assertEqual(transport.call_count, 1)
                sleep.assert_not_called()

    def test_never_replay_status_post(self):
        with patch.object(policy, "urlopen", side_effect=failure(
                429, headers={"Retry-After": "1"})) as transport, \
                patch.object(policy.time, "sleep") as sleep:
            with self.assertRaises(policy.GitHubHTTPError):
                policy.GitHub("example/repository", None).status("a" * 40, "failure", "test")
            self.assertEqual(transport.call_count, 1)
            sleep.assert_not_called()

    def test_retry_is_at_most_once(self):
        with patch.object(policy, "urlopen", side_effect=[
                failure(429, headers={"Retry-After": "1"}),
                failure(429, headers={"Retry-After": "1"})]) as transport, \
                patch.object(policy.time, "sleep"):
            with self.assertRaises(policy.GitHubHTTPError):
                policy.GitHub("example/repository", None).get("pulls")
            self.assertEqual(transport.call_count, 2)



if __name__ == "__main__":
    unittest.main()
