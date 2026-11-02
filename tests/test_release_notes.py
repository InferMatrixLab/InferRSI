"""Release overviews use mocked HTTP and synthetic local source histories only."""

import io
import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from tools import generate_release_notes as notes

KEY = "sk-test-no-access-credential"
SHA = "1" * 40


def completed(text="## Features\n- Preserve source identity."):
    return {"status": "completed", "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "role": "assistant", "status": "completed",
         "content": [{"type": "output_text", "text": text}]},
    ]}


@pytest.fixture
def source_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def git(*args):
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.PIPE).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Release Test")
    git("config", "user.email", "release@example.invalid")
    (tmp_path / "initial.txt").write_text("initial\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "initial subject")
    git("tag", "v0.1.0")
    (tmp_path / "feature.txt").write_text("feature\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "feat: retain identity (#42)\n\n"
        "PRIVATE_BODY_MUST_NOT_BE_SENT\nSigned-off-by: Release Test <release@example.invalid>")
    return git, git("rev-parse", "HEAD")


def test_exact_source_range_contains_subjects_links_and_statistics_only(source_repo, monkeypatch):
    _, sha = source_repo
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setenv("GH_TOKEN", "fake-github-token")
    monkeypatch.setenv("GITHUB_TOKEN", "fake-actions-token")
    original = subprocess.Popen
    calls = []

    def checked(*args, **kwargs):
        env = kwargs["env"]
        assert "OPENAI_API_KEY" not in env and "GH_TOKEN" not in env and "GITHUB_TOKEN" not in env
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", checked)
    result = notes.source_snapshot("v0.1.1", sha, "v0.1.0", "example/release")
    value = json.loads(result)
    assert len(value["commits"]) == 1
    assert value["commits"][0] == {
        "sha": sha, "subject": "feat: retain identity (#42)",
        "url": f"https://github.com/example/release/commit/{sha}",
    }
    assert "feature.txt" in value["file_change_statistics"]
    assert "initial subject" not in result
    assert "PRIVATE_BODY" not in result and "release@example.invalid" not in result
    assert "Signed-off-by" not in result and KEY not in result
    assert calls and not any("--patch" in call or "-p" in call for call in calls)


def test_first_release_uses_complete_history_and_empty_tree_statistics(source_repo):
    _, sha = source_repo
    value = json.loads(notes.source_snapshot("v0.1.1", sha, "", "example/release"))
    assert len(value["commits"]) == 2
    assert "initial.txt" in value["file_change_statistics"]
    assert "feature.txt" in value["file_change_statistics"]


@pytest.mark.parametrize("tag,commit,previous,repository", [
    ("main", SHA, "", "example/release"), ("v01.1.0", SHA, "", "example/release"),
    ("v0.1.1", "main", "", "example/release"),
    ("v0.1.1", SHA, "refs/heads/main", "example/release"),
    ("v0.1.1", SHA, "", "https://example.invalid/repo"),
])
def test_invalid_source_identity_never_runs_git(monkeypatch, tag, commit, previous, repository):
    monkeypatch.setattr(notes, "git", lambda *args: pytest.fail("Git must not run"))
    with pytest.raises(ValueError):
        notes.source_snapshot(tag, commit, previous, repository)


def test_source_checkout_must_match_planned_commit(source_repo):
    with pytest.raises(ValueError, match="does not match"):
        notes.source_snapshot("v0.1.1", SHA, "", "example/release")


def test_previous_release_must_be_an_ancestor(source_repo):
    git, sha = source_repo
    git("checkout", "-b", "unmerged", "v0.1.0")
    git("commit", "--allow-empty", "-m", "unmerged branch")
    git("tag", "v0.9.0")
    git("checkout", "main")
    with pytest.raises(ValueError, match="Source inspection failed"):
        notes.source_snapshot("v0.1.1", sha, "v0.9.0", "example/release")


def test_source_budget_limits_subjects_commits_and_total_utf8_bytes(monkeypatch):
    def git(args, limit=256):
        if args[0] == "rev-parse":
            return SHA, False
        if args[0] == "hash-object":
            return "2" * 40, False
        if args[0] == "log":
            return "".join(f"{number:040x}\t" + "知" * 500 + "\n" for number in range(101)), True
        assert args[0] == "diff" and "--numstat" in args
        return "1\t0\t" + "file" * 2_500, True

    monkeypatch.setattr(notes, "git", git)
    result = notes.source_snapshot("v0.1.1", SHA, "", "example/" + "r" * 150)
    value = json.loads(result)
    assert len(result.encode("utf-8")) <= notes.MAX_SOURCE_BYTES
    assert len(value["commits"]) <= 100
    assert all(len(item["subject"].encode("utf-8")) <= 240 for item in value["commits"])
    assert value["commits_truncated"] and value["file_statistics_truncated"]


def test_git_output_is_bounded_before_capture(monkeypatch):
    original = subprocess.Popen

    def output_process(command, **kwargs):
        assert "OPENAI_API_KEY" not in kwargs["env"]
        return original([sys.executable, "-c", "import sys; sys.stdout.write('x' * 20000)"],
                        **kwargs)

    monkeypatch.setattr(subprocess, "Popen", output_process)
    value, truncated = notes.git(["ignored"], 1024)
    assert len(value) == 1024 and truncated


PRIVATE_METADATA = [
    "operator@example.invalid", "operator@[2001:db8::7]",
    "ssh://operator:fake-password@example.invalid/repo?token=fake-no-access",
    "https://example.invalid/notes?api_key=fake-no-access",
    "192.0.2.7", "192.0.2.10:8080", "192.0.2.10.",
    "[2001:db8::7]", "2001:db8::7", "2001:db8::7.", "[2001:db8::7]:8080",
    r"C:\Users\<USER>\configuration", r"\\example.invalid\share\configuration",
    "/home/<USER>/.config", "/Users/<USER>/.config", "~/.config/private",
    "sk-test-no-access-value", "ghp_test_no_access_value", "github_pat_test_no_access_value",
    "OPENAI_API_KEY=fake-no-access", "password: fake-no-access", "Bearer fake-no-access",
    "Bearer=fake-no-access", '{"api_key": "fake-no-access"}', "api key = fake-no-access",
    "example.invalid.internal", "example.invalid.local",
    "example.invalid.corp", "example.invalid.lan",
]


@pytest.mark.parametrize("private", PRIVATE_METADATA, ids=[
    "email", "user-at-host", "credential-url", "query-url", "ipv4", "ipv4-port", "ipv4-period",
    "ipv6-brackets", "ipv6", "ipv6-period", "ipv6-port",
    "windows-home", "unc", "posix-home", "macos-home", "tilde-home", "openai-token",
    "github-token", "github-pat", "api-key-assignment", "password-assignment", "bearer",
    "bearer-assignment", "json-key-assignment", "spaced-key-assignment",
    "internal-host", "local-host", "corp-host", "lan-host",
])
def test_recognizable_private_metadata_is_omitted_in_full(private):
    text, redacted = notes.metadata_field(f"fix: metadata contains {private}")
    assert redacted and text == "[REDACTED: private metadata]"
    assert private not in text


def test_plain_versions_and_public_change_descriptions_are_retained():
    text = "fix: compatibility with v1.2.3 and Python 3.10"
    assert notes.metadata_field(text) == (text, False)


def test_mocked_api_receives_redacted_subjects_and_statistics_with_commit_provenance(
    monkeypatch, capsys,
):
    def git(args, limit=256):
        if args[0] == "rev-parse":
            return SHA, False
        if args[0] == "hash-object":
            return "2" * 40, False
        if args[0] == "log":
            subject = "fix: operator@example.invalid at 192.0.2.7 token=fake-no-access"
            return f"{SHA}\t{subject}\n", False
        assert args[0] == "diff"
        return ("2\t1\tdocs/public.md\n1\t0\t/home/<USER>/configuration\n"
                "1\t0\t[2001:db8::7]\n"), False

    captured = []

    class Opener:
        def open(self, request, timeout):
            captured.append(json.loads(request.data))
            response = io.BytesIO(json.dumps(completed()).encode())
            response.status = 200
            return response

    monkeypatch.setattr(notes, "git", git)
    monkeypatch.setattr(notes.urllib.request, "build_opener", lambda *args: Opener())
    source = notes.source_snapshot("v0.1.1", SHA, "", "example/release")
    notes.generate(source, notes.DEFAULT_MODEL, KEY)
    sent = captured[0]["input"]
    for private in ("operator@example.invalid", "192.0.2.7", "fake-no-access",
                    "/home/<USER>/configuration", "2001:db8::7"):
        assert private not in sent
    value = json.loads(sent)
    assert value["metadata_redacted"] is True
    assert value["commits"][0]["sha"] == SHA
    assert value["commits"][0]["url"] == f"https://github.com/example/release/commit/{SHA}"
    assert "docs/public.md" in value["file_change_statistics"]
    assert capsys.readouterr().out == ""


@pytest.fixture
def invocation(tmp_path, monkeypatch):
    output = tmp_path / "overview.md"
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setenv("GH_REPO", "example/release")
    monkeypatch.setattr(notes, "source_snapshot", lambda *args: '{"commits": []}')
    arguments = ["--tag", "v0.1.1", "--commit", SHA, "--previous-tag", "", "--output", str(output)]

    def run(body=None, *, error=None, status=200):
        calls = []

        class Response(io.BytesIO):
            pass

        def open_request(request, timeout):
            calls.append((request, timeout))
            if error:
                raise error
            response = Response(body if isinstance(body, bytes) else json.dumps(body).encode())
            response.status = status
            return response

        class Opener:
            open = staticmethod(open_request)

        def build_opener(handler):
            assert isinstance(handler, notes.NoRedirect)
            return Opener()

        monkeypatch.setattr(notes.urllib.request, "build_opener", build_opener)
        return notes.main(arguments), output, calls

    return run, output, arguments


def test_completed_mixed_output_items_make_one_bounded_markdown_file(invocation, capsys):
    run, _, _ = invocation
    response = completed()
    response["output"].append({
        "type": "message", "role": "assistant", "status": "completed",
        "content": [{"type": "output_text", "text": "## Compatibility\n"},
                    {"type": "output_text", "text": "- Existing interfaces remain available."}],
    })
    code, output, calls = run(response)
    assert code == 0 and output.is_file()
    text = output.read_text(encoding="utf-8")
    assert "## Features" in text and "## Compatibility" in text
    request, timeout = calls[0]
    assert len(calls) == 1 and timeout == 45
    assert request.full_url == notes.ENDPOINT and request.method == "POST"
    assert request.get_header("Authorization") == f"Bearer {KEY}"
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("User-agent") == "inferrsi-release-notes/1"
    payload = json.loads(request.data)
    assert request.full_url == "https://api.deepseek.com/responses"
    assert payload["model"] == "deepseek-flash" and payload["store"] is False
    assert payload["reasoning"] == {"effort": "none"}
    assert payload["max_output_tokens"] == 3200
    assert "temperature" not in payload and "tools" not in payload
    assert KEY not in request.data.decode()
    assert "untrusted" in payload["instructions"]
    captured = capsys.readouterr()
    assert captured.out == "AI release overview generated.\n" and captured.err == ""


@pytest.mark.parametrize("body", [
    b"not JSON", [], {"status": "incomplete", "output": []},
    {"status": "completed", "output": [], "error": {"message": KEY}},
    completed(""), completed("## Features\n" + "知" * 8_000),
    completed("## Features\n\x1b[31munsafe"), completed("## Features\n\u202eunsafe"),
    completed("```markdown\n## Features\n```"), completed("## Features\n<script>"),
    completed(f"## Features\n{KEY}"),
    {"status": "completed", "output": [{"type": "message", "role": "assistant",
       "status": "completed", "content": [{"type": "refusal", "refusal": KEY}]}]},
    {"status": "completed", "output": [{"type": "message", "role": "assistant",
       "status": "incomplete", "content": [{"type": "output_text", "text": "## Features"}]}]},
    b"x" * (notes.MAX_RESPONSE_BYTES + 1),
], ids=["invalid-json", "non-object", "incomplete", "api-error", "empty", "unicode-budget",
        "terminal-control", "bidi-control", "code-fence", "html", "secret", "refusal",
        "message-incomplete", "reply-budget"])
def test_invalid_api_output_removes_stale_file_and_never_logs_body(invocation, capsys, body):
    run, output, _ = invocation
    output.write_text("stale overview", encoding="utf-8")
    code, _, calls = run(body)
    assert code == 0 and not output.exists() and len(calls) == 1
    captured = capsys.readouterr()
    assert captured.out == notes.FALLBACK + "\n" and captured.err == ""
    assert KEY not in captured.out


@pytest.mark.parametrize("error", [
    TimeoutError(KEY),
    urllib.error.HTTPError(notes.ENDPOINT, 401, KEY, {}, io.BytesIO(KEY.encode())),
    urllib.error.URLError(KEY),
], ids=["timeout", "http", "network"])
def test_http_failure_and_timeout_fall_back_once_without_disclosure(invocation, capsys, error):
    run, output, _ = invocation
    output.write_text("stale", encoding="utf-8")
    code, _, calls = run(error=error)
    assert code == 0 and not output.exists() and len(calls) == 1
    assert capsys.readouterr().out == notes.FALLBACK + "\n"


def test_missing_key_does_not_inspect_source_or_contact_network(invocation, monkeypatch, capsys):
    _, output, arguments = invocation
    output.write_text("stale", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setattr(notes, "source_snapshot", lambda *args: pytest.fail("No source inspection"))
    monkeypatch.setattr(notes.urllib.request, "build_opener",
                        lambda *args: pytest.fail("No network"))
    assert notes.main(arguments) == 0 and not output.exists()
    assert capsys.readouterr().out == notes.FALLBACK + "\n"


def test_source_failure_never_contacts_api_or_logs_exception(invocation, monkeypatch, capsys):
    _, output, arguments = invocation
    output.write_text("stale", encoding="utf-8")

    def failure(*args):
        raise RuntimeError(KEY)

    monkeypatch.setattr(notes, "source_snapshot", failure)
    monkeypatch.setattr(notes.urllib.request, "build_opener",
                        lambda *args: pytest.fail("No network"))
    assert notes.main(arguments) == 0 and not output.exists()
    assert capsys.readouterr().out == notes.FALLBACK + "\n"


def test_byte_cap_includes_the_final_markdown_newline():
    prefix = "## Features\n"
    exact = prefix + "x" * (notes.MAX_NOTES_BYTES - len(prefix) - 1)
    assert len(notes.response_text(completed(exact)).encode()) == notes.MAX_NOTES_BYTES
    with pytest.raises(ValueError):
        notes.response_text(completed(exact + "x"))


def test_redirects_are_refused_before_authorization_can_be_forwarded():
    request = notes.urllib.request.Request(notes.ENDPOINT,
                                           headers={"Authorization": f"Bearer {KEY}"})
    with pytest.raises(ValueError, match="Redirects are not allowed"):
        notes.NoRedirect().redirect_request(request, None, 307, "redirect", {},
                                            "https://example.invalid/receive")


@pytest.mark.parametrize("base", ["https://yibuapi.com/v1", "https://yibuapi.com/v1/"])
def test_cli_preserves_approved_yibu_base_and_explicit_model(invocation, base):
    run, output, arguments = invocation
    arguments += ["--base-url", base, "--model", "gpt-5.4-mini"]
    code, _, calls = run(completed())
    assert code == 0 and output.is_file() and len(calls) == 1
    request, _ = calls[0]
    assert request.full_url == "https://yibuapi.com/v1/responses"
    assert request.get_header("Authorization") == f"Bearer {KEY}"
    payload = json.loads(request.data)
    assert payload["model"] == "gpt-5.4-mini" and "reasoning" not in payload


@pytest.mark.parametrize("base", ["https://api.deepseek.com", "https://api.deepseek.com/"])
def test_cli_uses_approved_deepseek_base_with_exact_default_model(invocation, base):
    run, output, arguments = invocation
    arguments += ["--base-url", base]
    code, _, calls = run(completed())
    assert code == 0 and output.is_file() and len(calls) == 1
    request, _ = calls[0]
    payload = json.loads(request.data)
    assert request.full_url == "https://api.deepseek.com/responses"
    assert payload["model"] == "deepseek-flash"
    assert payload["reasoning"] == {"effort": "none"} and payload["store"] is False


def test_openai_base_and_explicit_model_remain_unchanged(invocation):
    run, output, arguments = invocation
    arguments += ["--base-url", "https://api.openai.com/v1/", "--model", "gpt-6.1-terra"]
    code, _, calls = run(completed())
    assert code == 0 and output.is_file() and len(calls) == 1
    request, _ = calls[0]
    payload = json.loads(request.data)
    assert request.full_url == "https://api.openai.com/v1/responses"
    assert payload["model"] == "gpt-6.1-terra" and "reasoning" not in payload


def test_deepseek_explicit_model_id_is_transmitted_without_alias_rewriting(invocation):
    run, output, arguments = invocation
    arguments += ["--model", "dsv4.1-flash-1017"]
    code, _, calls = run(completed())
    assert code == 0 and output.is_file() and len(calls) == 1
    payload = json.loads(calls[0][0].data)
    assert payload["model"] == "dsv4.1-flash-1017"
    assert payload["reasoning"] == {"effort": "none"}


@pytest.mark.parametrize("base", [
    "http://yibuapi.com/v1", "https://example.invalid/v1", "https://yibuapi.com.evil.invalid/v1",
    "https://operator:fake-no-access@yibuapi.com/v1", "https://api.openai.com@yibuapi.com/v1",
    "https://yibuapi.com/v1?token=fake-no-access", "https://yibuapi.com/v1#fragment",
    "https://yibuapi.com/v1/responses", "https://yibuapi.com:443/v1", " https://yibuapi.com/v1",
    "https://yibuapi.com/v1/../v1", "https://yibuapi.com/v1\\", "",
    "http://api.deepseek.com", "https://api.deepseek.com/v1",
    "https://operator:fake-no-access@api.deepseek.com", "https://api.deepseek.com?token=fake",
], ids=["http", "arbitrary-host", "suffix-host", "userinfo", "misleading-userinfo", "query",
        "fragment", "full-endpoint", "port", "whitespace", "parent-path", "backslash", "empty",
        "deepseek-http", "deepseek-path", "deepseek-userinfo", "deepseek-query"])
def test_unapproved_base_is_rejected_before_any_http_call(monkeypatch, base):
    monkeypatch.setattr(notes.urllib.request, "build_opener",
                        lambda *args: pytest.fail("No network"))
    with pytest.raises(ValueError, match="Unapproved API base URL"):
        notes.generate("{}", notes.DEFAULT_MODEL, KEY, base)


def test_invalid_cli_base_falls_back_without_network_or_stale_output(invocation, capsys):
    run, output, arguments = invocation
    output.write_text("stale", encoding="utf-8")
    arguments += ["--base-url", "https://example.invalid/v1"]
    code, _, calls = run(completed())
    assert code == 0 and not output.exists() and calls == []
    assert capsys.readouterr().out == notes.FALLBACK + "\n"


def test_output_that_cannot_be_cleared_is_a_failure_not_stale_success(
    invocation, monkeypatch, capsys,
):
    _, output, arguments = invocation
    output.write_text("stale", encoding="utf-8")
    original = Path.unlink

    def failure(path, *args, **kwargs):
        if path == output:
            raise PermissionError(KEY)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failure)
    monkeypatch.setattr(notes, "source_snapshot", lambda *args: pytest.fail("No source inspection"))
    assert notes.main(arguments) == 1
    assert capsys.readouterr().out == notes.FALLBACK + "\n"
