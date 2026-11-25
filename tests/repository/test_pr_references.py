from io import BytesIO
from pathlib import Path

import pytest

from tools import check_pr_references as check

ROOT = Path(__file__).resolve().parents[2]

# Negated sentences from merged PR bodies that GitHub still treated as closing syntax.
HISTORICAL = [
    "Acceptance stays with the maintainer; this PR does not close #43.",
    "Issue acceptance/closure remains pending; this PR does not close #40 automatically.",
    "This PR does not automatically close #29 and does not claim hardware validation.",
    "**Closure delegation:** @owner (issue author); this PR does not close #49.",
    "This PR does not close #50/#140 automatically.",
    "**Do not promote the candidate or close #255.**",
    "It remains valid evidence; neither this software PR nor green CI closes #253.",
    "Therefore this does not establish accuracy improvement or close #255.",
]


@pytest.mark.parametrize("line", HISTORICAL)
def test_negated_closing_sentences_fail(line):
    assert check.violations(f"Refs #1\n\n{line}\n") == [(3, line)]


@pytest.mark.parametrize("line", [
    "This fixes InferMatrixLab/InferRSI#12 partially.",
    "It also resolves https://github.com/InferMatrixLab/InferRSI/issues/12 here.",
    "- Closes #12",
    "Closes #12 and #13",
    "FIXED: #7 in the parser",
])
def test_closing_syntax_inside_other_text_fails(line):
    assert check.violations(line) == [(1, line)]


@pytest.mark.parametrize("line", [
    "Closes #12",
    "  fixes: #12  ",
    "Resolves InferMatrixLab/InferRSI#12",
])
def test_standalone_closing_syntax_fails(line):
    assert check.violations(f"Refs #1\n\n{line}\n") == [(3, line.strip())]


@pytest.mark.parametrize("body", [
    "Refs #273",
    "#255 stays open for the owner's acceptance.",
    "This does not close the campaign.",
    "Disclosed #5 during review; an unfixed #6 remains.",
    "",
])
def test_references_without_closing_syntax_pass(body):
    assert check.violations(body) == []


def test_crlf_body_reports_the_original_line_number():
    assert check.violations("Refs #1\r\nthis PR does not close #2\r\n") == [
        (2, "this PR does not close #2")
    ]


def test_pull_request_template_passes():
    template = (ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    assert check.violations(template) == []


def test_main_reports_each_line_and_fails(monkeypatch, capsys):
    monkeypatch.setenv("PR_BODY", "Refs #1\nThis PR does not close #2.\nCloses #3\n")
    assert check.main() == 1
    out = capsys.readouterr().out.splitlines()
    assert out[:2] == [
        "line 2: closing syntax in PR body: This PR does not close #2.",
        "line 3: closing syntax in PR body: Closes #3",
    ]
    assert len(out) == 3 and "Refs #N" in out[2]


def test_main_passes_silently(monkeypatch, capsys):
    monkeypatch.setenv("PR_BODY", "Refs #1\nRefs #3\n")
    assert check.main() == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(("changes", "before", "after", "expected"), [
    ("", "", "", False),
    ("M\0docs/contracts/current-design.md\0", "", "", True),
    ("D\0docs/module-layout.md\0", "", "", True),
    ("A\0docs/legacy-knowledge-manifest.json\0", "", "", True),
    ("M\0docs/architecture.md\0", "Before", "After", False),
    (
        "M\0docs/architecture.md\0",
        "## Architecture anchors\nA1\n## Other\nBefore",
        "## Architecture anchors\nA1\n## Other\nAfter",
        False,
    ),
    (
        "M\0docs/architecture.md\0",
        "## Architecture anchors\nOld",
        "## Architecture anchors\nNew",
        True,
    ),
    ("D\0docs/architecture.md\0", "## Architecture anchors\nA1", None, True),
    ("A\0docs/architecture.md\0", None, "## Architecture anchors\nA1", True),
])
def test_contract_diff_at_pr_merge_commit(monkeypatch, changes, before, after, expected):
    git_output = {
        ("show", "-s", "--format=%P", "HEAD"): "base head\n",
        (
            "diff", "--name-status", "--no-renames", "-z", "HEAD^1", "HEAD",
            "--", *check.CONTRACT_PATHS,
        ): changes,
    }
    if before is not None:
        git_output[("show", "HEAD^1:docs/architecture.md")] = before
    if after is not None:
        git_output[("show", "HEAD:docs/architecture.md")] = after
    monkeypatch.setattr(check, "_git", lambda *args: git_output[args])
    assert check.contracts_changed("base", "head") is expected
    with pytest.raises(ValueError, match="Checkout does not match"):
        check.contracts_changed("other-base", "head")


@pytest.mark.parametrize("body", ["Refs owner/repo#574", "See #574", ""])
def test_contract_advice_requires_plain_same_repo_reference(monkeypatch, body):
    def unexpected_lookup(*args):
        pytest.fail("An invalid reference reached the API lookup")

    monkeypatch.setattr(check, "_load_issue", unexpected_lookup)
    level, advice = check.scope_advice(body, "https://api.github.test/repos/org/repo")
    assert level == "warning"
    assert "plain Refs #N" in advice


@pytest.mark.parametrize(("issue", "level"), [
    ({}, "warning"),
    ({"labels": []}, "warning"),
    ({"pull_request": {}, "labels": [{"name": "status:accepted"}]}, "warning"),
    (
        {"repository_url": "https://api.github.test/repos/org/other",
         "labels": [{"name": "status:accepted"}]},
        "warning",
    ),
    ({"labels": [{"name": "status:accepted"}]}, "notice"),
])
def test_contract_advice_verifies_label_and_leaves_scope_to_review(monkeypatch, issue, level):
    repo_url = "https://api.github.test/repos/org/repo"

    def get_issue(url, number):
        assert (url, number) == (repo_url, "574")
        return {"repository_url": url, **issue}

    monkeypatch.setattr(check, "_load_issue", get_issue)
    annotation, advice = check.scope_advice("Refs #574\r\n", repo_url)
    assert annotation == level
    assert "#574" in advice
    if level == "notice":
        assert "decision recorded" in advice


def test_issue_lookup_uses_public_api_without_credentials(monkeypatch):
    repo_url = "https://api.github.test/repos/org/repo"

    def open_public_issue(request, timeout):
        assert request.full_url == f"{repo_url}/issues/574"
        assert dict(request.header_items()) == {"Accept": "application/vnd.github+json"}
        assert timeout == 10
        return BytesIO(b'{"number": 574}')

    monkeypatch.setattr(check, "urlopen", open_public_issue)
    assert check._load_issue(repo_url, "574") == {"number": 574}


def test_contract_advice_unavailable_leaves_the_existing_result(monkeypatch, capsys):
    def unavailable(*args):
        raise TimeoutError

    monkeypatch.setenv("PR_BASE_SHA", "base")
    monkeypatch.setenv("PR_HEAD_SHA", "head")
    monkeypatch.setattr(check, "contracts_changed", unavailable)
    monkeypatch.setenv("PR_BODY", "Refs #574")
    assert check.main() == 0
    assert "::warning::" in capsys.readouterr().out
    monkeypatch.setenv("PR_BODY", "Closes #574")
    assert check.main() == 1
    assert "::warning::" in capsys.readouterr().out
