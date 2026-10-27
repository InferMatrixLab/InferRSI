"""Offline checks at the publisher's real urllib boundary; no API calls or model runs."""

import io
import json
import subprocess
import sys
import traceback
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.parse import urlsplit

import pytest

from tools import skill_eval_pr as integration

SECRET = "FAKE_SECRET_NOT_A_CREDENTIAL"


def http_error(status=403, body=b"{}", headers=None):
    return HTTPError("https://example.invalid/private?signature=" + SECRET, status,
                     SECRET, headers or {}, io.BytesIO(body))


def request_failure(monkeypatch, error, *, method="POST", path="/issues/7/comments"):
    opener = Mock()
    opener.open.side_effect = error
    monkeypatch.setattr(integration.urllib.request, "build_opener", lambda *args: opener)
    api = integration.GitHub("example/fixture", SECRET)
    with pytest.raises(OSError) as caught:
        api.request(method, path, {"body": SECRET})
    assert opener.open.call_count == 1  # In particular, never replay a refused POST.
    assert caught.value.__context__ is error
    assert caught.value.__suppress_context__
    rendered = "".join(traceback.format_exception(caught.value))
    assert SECRET not in rendered
    assert "example.invalid" not in rendered
    assert len(str(caught.value)) < 1024
    return str(caught.value)


@pytest.mark.parametrize("status,message,headers,category", [
    (403, "Resource not accessible by integration", {}, "permission"),
    (403, "API rate limit exceeded", {}, "rate-limit"),
    (403, "You have exceeded a secondary rate limit", {}, "rate-limit"),
    (403, "", {"X-RateLimit-Remaining": "0"}, "rate-limit"),
    (403, "", {"Retry-After": "3"}, "rate-limit"),
    (429, "", {}, "rate-limit"),
    (403, "", {}, "unknown"),
    (503, "", {}, "unknown"),
])
def test_failure_categories_require_supported_evidence(
    monkeypatch, status, message, headers, category,
):
    body = json.dumps({"message": message, "errors": [SECRET]}).encode()
    text = request_failure(monkeypatch, http_error(status, body, headers))
    assert f'"http_status": {status}' in text
    assert f'"category": "{category}"' in text
    assert '"method":"POST"' in text
    assert '"endpoint":"/issues/{number}/comments"' in text


def test_only_allowlisted_metadata_is_retained(monkeypatch):
    headers = {"Authorization": SECRET, "Set-Cookie": SECRET, "Location": SECRET,
               "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1234567890",
               "Retry-After": "3", "X-GitHub-Request-Id": "ABCD:1234:EF56"}
    text = request_failure(monkeypatch, http_error(headers=headers))
    for field in ('"x-ratelimit-remaining": 0', '"x-ratelimit-reset": 1234567890',
                  '"retry-after": 3', '"request_id": "ABCD:1234:EF56"'):
        assert field in text
    assert "Authorization" not in text and "Set-Cookie" not in text


@pytest.mark.parametrize("value", [SECRET, "9" * 81, "-1", "3\n" + SECRET, None, 0])
def test_hostile_metadata_is_not_echoed_or_used_as_rate_evidence(monkeypatch, value):
    headers = {name: value for name in (
        "Retry-After", "X-RateLimit-Remaining", "X-RateLimit-Reset", "X-GitHub-Request-Id")}
    text = request_failure(monkeypatch, http_error(headers=headers))
    assert '"category": "unknown"' in text
    assert "request_id" not in text and "retry-after" not in text


@pytest.mark.parametrize("body", [b"not JSON", b"\xff", b"[]", b"null",
                                  b'{"message": 123}', b"[" * 3000],
                         ids=["text", "encoding", "array", "null", "type", "deep"])
def test_malformed_responses_remain_unknown(monkeypatch, body):
    text = request_failure(monkeypatch, http_error(body=body))
    assert '"category": "unknown"' in text


def test_oversized_body_with_valid_json_prefix_cannot_establish_cause(monkeypatch):
    body = json.dumps({"message": "Resource not accessible by integration"}).encode()
    stream = io.BytesIO(body + b" " * 20000)
    error = HTTPError("https://example.invalid/?token=" + SECRET, 403, SECRET, {}, stream)
    read = Mock(wraps=error.read)
    error.read = read
    text = request_failure(monkeypatch, error)
    read.assert_called_once_with(8193)
    assert '"category": "unknown"' in text
    assert stream.closed


def test_unreadable_body_and_close_failure_do_not_replace_http_failure(monkeypatch):
    error = http_error()
    error.read = Mock(side_effect=OSError(SECRET))
    error.close = Mock(side_effect=RuntimeError(SECRET))
    text = request_failure(monkeypatch, error)
    assert '"http_status": 403' in text and '"category": "unknown"' in text
    error.close.assert_called_once_with()


def test_formatter_failure_is_fail_closed(monkeypatch):
    monkeypatch.setattr(integration, "GitHubHTTPError", Mock(side_effect=RuntimeError(SECRET)))
    text = request_failure(monkeypatch, http_error())
    assert '"http_status": 403' in text and '"category": "unknown"' in text


@pytest.mark.parametrize("path,endpoint", [
    ("/actions/artifacts/9/zip?signature=" + SECRET, "/actions/artifacts/{id}/zip"),
    ("/issues/7/comments?private=" + SECRET, "/issues/{number}/comments"),
    ("/private/" + SECRET, "<redacted>"),
    ("/issues/" + SECRET + "/comments", "<redacted>"),
])
def test_endpoint_is_a_template_without_queries_or_private_path(monkeypatch, path, endpoint):
    text = request_failure(monkeypatch, http_error(), method="GET", path=path)
    assert f'"endpoint":"{endpoint}"' in text
    assert '"method":"GET"' in text


def test_missing_body_and_headers_do_not_mask_failure(monkeypatch):
    error = HTTPError("https://example.invalid/?token=" + SECRET, 403, SECRET, None, None)
    text = request_failure(monkeypatch, error)
    assert '"category": "unknown"' in text


def test_accepted_post_with_http_failure_reconciles_without_duplicate_summary(monkeypatch):
    comments, writes = [], []
    current = {"base": {"sha": "a" * 40}, "head": {"sha": "b" * 40}, "state": "open"}

    def transport(request, **kwargs):
        path = urlsplit(request.full_url).path
        if request.method == "GET":
            result = comments if path.endswith("/comments") else current
        else:
            writes.append(request.method)
            body = json.loads(request.data)["body"]
            if request.method == "POST":
                comments.append({"id": 1, "user": {"login": "github-actions[bot]"},
                                 "body": body})
                raise http_error(503)
            comments[0]["body"] = body
            result = {"html_url": "https://example.invalid/comment/1"}
        return io.BytesIO(json.dumps(result).encode())

    opener = Mock()
    opener.open.side_effect = transport
    monkeypatch.setattr(integration.urllib.request, "build_opener", lambda *args: opener)
    api = integration.GitHub("example/fixture", SECRET)
    plan = {"pr": 7, "base": "a" * 40, "head": "b" * 40}
    with pytest.raises(OSError, match='"http_status": 503'):
        api.publish(plan, integration.MARKER + "\nSummary", 10)
    assert writes == ["POST"]
    api.publish(plan, integration.MARKER + "\nSummary", 11)
    assert writes == ["POST", "PATCH"] and len(comments) == 1


def test_uncaught_failure_exits_nonzero_with_safe_traceback():
    script = """
import sys
sys.path.insert(0, 'src')
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from tools.skill_eval_pr import GitHub
error = HTTPError('https://example.invalid/?token=FAKE_SECRET', 403, 'FAKE_SECRET', None, None)
api = GitHub('example/fixture', 'FAKE_SECRET')
with patch('urllib.request.build_opener', return_value=Mock(open=Mock(side_effect=error))):
    api.request('POST', '/issues/7/comments')
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=integration.ROOT,
                            text=True, capture_output=True)
    assert result.returncode != 0
    assert '"http_status": 403' in result.stderr
    assert "FAKE_SECRET" not in result.stderr and "example.invalid" not in result.stderr
