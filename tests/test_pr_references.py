"""CPU-only checks for the advisory PR-body guard; no GitHub writes."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.check_pr_references import main, violation_lines

ROOT = Path(__file__).resolve().parents[1]


class ReferenceSyntaxTests(unittest.TestCase):
    def test_keyword_and_reference_forms(self):
        for keyword in ("close", "closes", "closed", "fix", "fixes", "fixed",
                        "resolve", "resolves", "resolved"):
            for spelling in (keyword, keyword.upper(), keyword.title() + ":"):
                for reference in ("#123", "some-owner/some.repo#123",
                                  "https://github.com/some-owner/some.repo/issues/123"):
                    with self.subTest(spelling=spelling, reference=reference):
                        directive = f"{spelling} {reference}"
                        self.assertEqual(violation_lines(directive), [])
                        self.assertEqual(violation_lines("This does not " + directive), [1])
                        self.assertEqual(violation_lines(directive + " automatically"), [1])

    def test_historical_failure_shapes(self):
        # Synthetic numbers preserve the failure shapes, not campaign identities.
        for body in (
            "this PR does not close #123",
            "this PR does not close #123 automatically",
            "This PR does not automatically close #123",
            "This PR does not close #123/#456 automatically",
            "Do not promote the candidate or close #123",
            "neither this software PR nor green CI closes #123",
            "this does not establish accuracy improvement or close #123",
        ):
            with self.subTest(body=body):
                self.assertEqual(violation_lines(body), [1])

    def test_explicit_closing_only_lines(self):
        for body in (
            "Summary\n\nCloses #123\n",
            "\tCloses: #123.  ",
            "Resolves #123, resolves #456, resolves owner/repo#789",
            "Fixes #123 and closes #456",
            "Closes #123, and fixes #456",
            "Closes #123\nFixes #456",
            "Summary\r\n\r\nCloses #123\r\n",
        ):
            with self.subTest(body=body):
                self.assertEqual(violation_lines(body), [])

    def test_neutral_text_and_placeholders(self):
        for body in ("", "Refs #123", "fix the parser", "Closes #N", "encloses #123",
                     "prefixes #123", "resolver #123", "A fix for #123"):
            self.assertEqual(violation_lines(body), [])

    def test_raw_markdown_is_not_a_negation_escape(self):
        for body in ("> Closes #123", "- Closes #123", "`Closes #123`",
                     "Example: **Closes #123**", "<!-- Does not close #123 -->",
                     "Do not\nclose\n#123", "Closes #123; not really",
                     "Closes #123, but acceptance is pending"):
            with self.subTest(body=body):
                self.assertTrue(violation_lines(body))

    def test_line_numbers_and_one_report_per_line(self):
        self.assertEqual(violation_lines(
            "Summary\nNo close #123 or fix #456\n\nCloses #789\nDo not resolve #456"
        ), [2, 5])
        self.assertEqual(violation_lines("text\u2028not close #123"), [1])
        self.assertEqual(violation_lines("Do not close\r\n#123"), [1])


class EventInputTests(unittest.TestCase):
    def run_event(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(["--event", str(path)])
            return status, output.getvalue()

    def test_empty_null_and_valid_body(self):
        for body in (None, "", "Refs #123", "Closes #123"):
            self.assertEqual(self.run_event({"pull_request": {"body": body}})[0], 0)

    def test_missing_and_malformed_events_fail_closed(self):
        for payload in ({}, [], None, {"pull_request": None},
                        {"pull_request": {}}, {"pull_request": {"body": []}}):
            self.assertEqual(self.run_event(payload)[0], 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("not json", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--event", str(path)]), 2)
                self.assertEqual(main(["--event", str(path.with_name("missing"))]), 2)

    def test_untrusted_content_is_not_executed_or_echoed(self):
        body = "Do not close #123\n::error::forged\n$(exit 99) `${{ secrets.TOKEN }}`"
        status, output = self.run_event({"pull_request": {"body": body}})
        self.assertEqual(status, 1)
        self.assertIn("line 1", output)
        self.assertNotIn("forged", output)
        self.assertNotIn("secrets", output)
        self.assertNotIn("exit 99", output)


class WorkflowContractTests(unittest.TestCase):
    def test_ready_events_and_job_safety(self):
        workflow = (ROOT / ".github/workflows/ci-ready.yml").read_text(encoding="utf-8")
        self.assertIn("types: [opened, synchronize, reopened, ready_for_review]", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertNotIn("edited", workflow)
        job = workflow.split("  pr-references:\n", 1)[1].split("  installed-package:", 1)[0]
        self.assertIn("contents: read", job)
        self.assertIn("persist-credentials: false", job)
        self.assertIn('env -i PATH=/usr/bin:/bin LANG=C.UTF-8', job)
        self.assertIn('python3 -I tools/check_pr_references.py --event "$GITHUB_EVENT_PATH"', job)
        self.assertNotIn("${{", job)
        self.assertNotIn("secrets", job)


if __name__ == "__main__":
    unittest.main()
