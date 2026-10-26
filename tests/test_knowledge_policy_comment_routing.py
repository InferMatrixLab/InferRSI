"""Offline routing contracts, not an execution of GitHub's expression engine.

Model the documented truthiness, case-insensitive contains, and short-circuit
operators used by this exact expression. CI additionally parses the workflow YAML.
https://docs.github.com/en/actions/reference/workflows-and-actions/expressions
"""

import re
import unittest
from pathlib import Path

from tools import check_knowledge_model_policy as policy

ROOT = Path(__file__).resolve().parents[1]
ELIGIBILITY = (
    "github.event_name != 'issue_comment' || !github.event.issue || "
    "!github.event.comment || !github.event.action || "
    "(github.event.issue.pull_request && (github.event.action != 'created' || "
    "!github.event.comment.body || "
    "contains(github.event.comment.body, 'knowledge-policy-approval')))"
)
WRITER = "knowledge-policy-status-writer"


def truthy(value):
    # GitHub objects/arrays are truthy, including empty objects/arrays.
    if isinstance(value, (dict, list)):
        return True
    return bool(value)


def eligible(event_name, event):
    """Explicit model of ELIGIBILITY, with absent properties evaluating to null."""
    issue = event.get("issue")
    comment = event.get("comment")
    action = event.get("action")
    if (event_name.casefold() != "issue_comment" or not truthy(issue)
            or not truthy(comment) or not truthy(action)):
        return True
    body = comment.get("body")
    return truthy(issue.get("pull_request")) and (
        action.casefold() != "created" or not truthy(body)
        or "knowledge-policy-approval" in body.casefold()
    )


def group(event_name, event, run_id=1, run_attempt=1):
    return WRITER if eligible(event_name, event) else (
        f"knowledge-policy-skipped-{run_id}-{run_attempt}"
    )


class CommentRoutingTests(unittest.TestCase):
    def test_identical_eligibility_controls_if_and_group(self):
        self.assertIn(f"contains(github.event.comment.body, '{policy.APPROVAL}')", ELIGIBILITY)
        text = (ROOT / ".github/workflows/knowledge-model-policy.yml").read_text()
        expressions = [" ".join(value.split()) for value in re.findall(
            r"\$\{\{ (.*?) \}\}", text, re.S
        )]
        self.assertEqual(expressions[0], ELIGIBILITY)
        self.assertEqual(expressions[1], (
            f"({ELIGIBILITY}) && '{WRITER}' || "
            "format('knowledge-policy-skipped-{0}-{1}', github.run_id, github.run_attempt)"
        ))
        self.assertIn("cancel-in-progress: false", text)
        self.assertIn("ref: main", text)
        self.assertIn("persist-credentials: false", text)

    def test_truth_matrix(self):
        for is_pr in (False, True):
            issue = {"pull_request": {}} if is_pr else {"number": 1}
            for action in ("created", "edited", "deleted"):
                for body in (None, "", "LGTM", "```knowledge-policy-approval\n{}\n```",
                             "KNOWLEDGE-POLICY-APPROVAL"):
                    event = {"issue": issue, "comment": {"body": body}, "action": action}
                    expected = is_pr and (
                        action != "created" or body in (None, "")
                        or "knowledge-policy-approval" in body.casefold()
                    )
                    with self.subTest(is_pr=is_pr, action=action, body=body):
                        self.assertEqual(eligible("issue_comment", event), expected)
                        self.assertEqual(group("issue_comment", event) == WRITER, expected)

    def test_missing_payload_is_conservative(self):
        complete = {"issue": {"pull_request": {}}, "comment": {"body": "LGTM"},
                    "action": "created"}
        for key in complete:
            for missing in (None, ""):
                event = {**complete, key: missing}
                self.assertTrue(eligible("issue_comment", event))
            event = {key_: value for key_, value in complete.items() if key_ != key}
            self.assertTrue(eligible("issue_comment", event))
        self.assertTrue(eligible("issue_comment", {}))
        self.assertTrue(eligible("issue_comment", {**complete, "comment": {}}))

    def test_other_triggers_keep_shared_writer(self):
        for event_name in ("pull_request_target", "push", "workflow_dispatch"):
            self.assertEqual(group(event_name, {}), WRITER)

    def test_irrelevant_comment_never_enters_writer_group(self):
        event = {"issue": {"pull_request": {}}, "comment": {"body": "Thanks!"},
                 "action": "created"}
        groups = {group("issue_comment", event, run, attempt)
                  for run in (1, 2) for attempt in (1, 2)}
        self.assertEqual(len(groups), 4)
        self.assertNotIn(WRITER, groups)


if __name__ == "__main__":
    unittest.main()
