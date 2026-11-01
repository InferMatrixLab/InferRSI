from pathlib import Path

import pytest

from tools import check_pr_references as check

ROOT = Path(__file__).resolve().parents[1]

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


@pytest.mark.parametrize("body", [
    "Refs #273",
    "Closes #12",
    "  fixes: #12  ",
    "Resolves InferMatrixLab/InferRSI#12",
    "#255 stays open for the owner's acceptance.",
    "This does not close the campaign.",
    "Disclosed #5 during review; an unfixed #6 remains.",
    "",
])
def test_references_without_inline_closing_syntax_pass(body):
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
    assert out[0] == "line 2: closing syntax inside text: This PR does not close #2."
    assert "Refs #N" in out[1] and len(out) == 2


def test_main_passes_silently(monkeypatch, capsys):
    monkeypatch.setenv("PR_BODY", "Refs #1\nCloses #3\n")
    assert check.main() == 0
    assert capsys.readouterr().out == ""
