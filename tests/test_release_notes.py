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
    payload = json.loads(request.data)
    assert payload["model"] == "gpt-5.4-mini" and payload["store"] is False
    assert payload["max_output_tokens"] == 1600
    assert "temperature" not in payload and "tools" not in payload
    assert KEY not in request.data.decode()
    assert "untrusted" in payload["instructions"]
    captured = capsys.readouterr()
    assert captured.out == "GPT release overview generated.\n" and captured.err == ""


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
