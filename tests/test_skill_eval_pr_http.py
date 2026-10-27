"""Offline checks at the publisher's real urllib boundary; no API calls or model runs."""

import io
import json
import subprocess
import sys
import traceback
from email.message import Message
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


def accepted_permissions(text):
    return json.loads(text.split(" accepted_permissions=", 1)[1])


@pytest.mark.parametrize("method,path", [
    ("POST", "/issues/7/comments"), ("PATCH", "/issues/comments/9"),
])
@pytest.mark.parametrize("value,sets", [
    ("issues=write", [{"issues": "write"}]),
    ("pull_requests=write", [{"pull_requests": "write"}]),
    ("issues=write; pull_requests=write", [{"issues": "write"}, {"pull_requests": "write"}]),
    ("\tissues \t= write, contents=read ; metadata=read\t",
     [{"issues": "write", "contents": "read"}, {"metadata": "read"}]),
    ("issues=read;issues=write;pull_requests=read;pull_requests=write",
     [{"issues": "read"}, {"issues": "write"},
      {"pull_requests": "read"}, {"pull_requests": "write"}]),
    ("issues=write,pull_requests=read,contents=write,metadata=read",
     [{"issues": "write", "pull_requests": "read", "contents": "write", "metadata": "read"}]),
    (";".join(("issues=write,pull_requests=write,contents=write,metadata=read",
               "issues=read,pull_requests=write,contents=write,metadata=read",
               "issues=write,pull_requests=read,contents=write,metadata=read",
               "issues=write,pull_requests=write,contents=read,metadata=read")),
     [{"issues": "write", "pull_requests": "write", "contents": "write", "metadata": "read"},
      {"issues": "read", "pull_requests": "write", "contents": "write", "metadata": "read"},
      {"issues": "write", "pull_requests": "read", "contents": "write", "metadata": "read"},
      {"issues": "write", "pull_requests": "write", "contents": "read", "metadata": "read"}]),
    ("issues=write".ljust(256), [{"issues": "write"}]),
])
def test_accepted_permissions_preserve_bounded_and_or_requirements(
    monkeypatch, method, path, value, sets,
):
    headers = Message()
    headers["x-accepted-github-permissions"] = value
    body = b'{"message":"Resource not accessible by integration"}'
    text = request_failure(monkeypatch, http_error(body=body, headers=headers),
                           method=method, path=path)
    assert accepted_permissions(text) == {"status": "available", "sets": sets}
    assert '"category": "permission"' in text and '"http_status": 403' in text
    assert headers["X-Accepted-GitHub-Permissions"] == value


@pytest.mark.parametrize("value", [
    "", " \t", "Issues=write", "issues=WRITE", "issues=none", "metadata=write",
    "checks=write", "issues=write;authorization=write", "issues=write,",
    ";issues=write", "issues=write;", "issues=write,,contents=read",
    "issues=write;;contents=read", "issues:write", 'issues="write"', "issues==write",
    "issues=write,issues=write", "issues=read,issues=write", "issues=write;issues=write",
    "issues=write,contents=read;contents=read,issues=write",
    "issues=read;issues=write;pull_requests=read;pull_requests=write;metadata=read",
    "issues=write,pull_requests=write,contents=read,metadata=read,issues=read",
    "issues=write".ljust(257), "issues=write;" + SECRET * 30,
    "issues=write\r\nAuthorization: " + SECRET, "issues=write\n", "issues=write\x00",
    "issues=write\x7f", "issues=write\v", "issues=write;\u00e9=read",
    "issues=write\uff1bcontents=read", "https://example.invalid/" + SECRET,
    None, 0, b"issues=write", ["issues=write"], {"issues": "write"},
])
def test_invalid_accepted_permissions_are_wholly_unavailable_without_leaks(monkeypatch, value):
    text = request_failure(monkeypatch, http_error(headers={
        "X-Accepted-GitHub-Permissions": value}))
    assert accepted_permissions(text) == {"status": "unavailable"}
    assert '"category": "unknown"' in text


def test_duplicate_accepted_permission_headers_are_unavailable(monkeypatch):
    headers = Message()
    headers["X-Accepted-GitHub-Permissions"] = "issues=write"
    headers["x-accepted-github-permissions"] = "pull_requests=write"
    text = request_failure(monkeypatch, http_error(headers=headers))
    assert accepted_permissions(text) == {"status": "unavailable"}


@pytest.mark.parametrize("mode", ["raise", "wrong-type", "multiple", "attribute", "get"])
def test_hostile_accepted_permission_headers_do_not_mask_http_failure(monkeypatch, mode):
    class Headers(dict):
        @property
        def get_all(self):
            if mode == "attribute":
                raise RuntimeError(SECRET)
            if mode == "get":
                return None
            if mode == "raise":
                return Mock(side_effect=RuntimeError(SECRET))
            return Mock(return_value="issues=write" if mode == "wrong-type"
                        else ["issues=write", SECRET])

        def get(self, name, default=""):
            if mode == "get":
                raise RuntimeError(SECRET)
            return super().get(name, default)

    text = request_failure(monkeypatch, http_error(headers=Headers({"present": True})))
    assert accepted_permissions(text) == {"status": "unavailable"}
    assert '"http_status": 403' in text


@pytest.mark.parametrize("failure", ["parser", "serialization"])
def test_permission_diagnostic_failure_preserves_original_http_error(monkeypatch, failure):
    replacement = (Mock(side_effect=RuntimeError(SECRET)) if failure == "parser"
                   else Mock(return_value={"unexpected": object()}))
    monkeypatch.setattr(integration, "comment_permission_requirements", replacement)
    text = request_failure(monkeypatch, http_error(
        body=b'{"message":"Resource not accessible by integration"}'))
    assert accepted_permissions(text) == {"status": "unavailable"}
    assert '"category": "permission"' in text and '"http_status": 403' in text


@pytest.mark.parametrize("method,path", [
    ("GET", "/issues/7/comments"), ("GET", "/issues/comments/9"),
    ("POST", "/actions/runs/7"), ("PATCH", "/pulls/7"),
    ("PATCH", "/issues/7/comments"), ("POST", "/issues/comments/9"),
    ("POST", "/private/" + SECRET),
])
def test_accepted_permission_header_is_only_read_for_comment_writes(monkeypatch, method, path):
    headers = Message()
    headers["X-GitHub-Request-Id"] = "ABCD:1234"
    headers.get_all = Mock(side_effect=AssertionError(SECRET))
    text = request_failure(monkeypatch, http_error(headers=headers), method=method, path=path)
    assert " accepted_permissions=" not in text
    headers.get_all.assert_not_called()


@pytest.mark.parametrize("status,category", [(403, "unknown"), (429, "rate-limit"),
                                            (503, "unknown")])
def test_accepted_requirements_do_not_establish_granted_access_or_failure_cause(
    monkeypatch, status, category,
):
    text = request_failure(monkeypatch, http_error(status, headers={
        "X-Accepted-GitHub-Permissions": "issues=write"}))
    assert accepted_permissions(text) == {"status": "available", "sets": [{"issues": "write"}]}
    assert f'"category": "{category}"' in text


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
    assert accepted_permissions(text) == {"status": "absent"}
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
