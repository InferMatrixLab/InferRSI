"""Offline push reconciliation: execution completion is not admission success."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError

from tools import check_knowledge_model_policy as policy

SHA = "a" * 40
HEAD = "b" * 40


def http_error(code=422, capacity=True):
    body = {"message": "Validation Failed", "errors": (
        "This SHA and context has reached the maximum number of statuses."
        if capacity else "Unknown validation error")}
    return policy.GitHubHTTPError(HTTPError(
        "https://example.invalid", code, "", {}, io.BytesIO(json.dumps(body).encode())))


def row(outcome, number=1):
    return {**outcome, "pull_request": number, "head_sha": HEAD, "policy_sha": SHA,
            "dry_run": False, "rerun": outcome["kind"] in policy.RERUN_KINDS}


def verdict(kind="compliant"):
    return {"state": "success" if kind == "compliant" else "failure", "kind": kind,
            "description": "Fixture", "errors": [] if kind == "compliant" else ["Fixture"]}


def saturated():
    api = Mock()
    api.history.return_value = [{"state": "success"}] * policy.STATUS_LIMIT
    outcome, publish = policy.invalidated(api, HEAD, False, 100)
    assert not publish
    api.status.assert_not_called()
    return row(outcome)


class PushHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "report.json"
        self.event = Path(self.temp.name) / "event.json"
        self.event.write_text(json.dumps({"ref": "refs/heads/main", "before": "c" * 40}))
        self.binding = policy.report_binding("owner/repo", "push", self.event, SHA, "final")

    def project(self, results, event="push", reconciliation=None, routing=None):
        binding = dict(self.binding, event_name=event)
        if event == "pull_request_target":
            binding.update(trigger=1, expected_head=HEAD)
        reconciliation = reconciliation if reconciliation is not None else {
            "complete": True, "targets": sorted(r["pull_request"] for r in results)}
        policy.write_report(self.path, binding, results, routing or {
            "mode": "full-sweep", "reason": "policy-inputs-changed"}, reconciliation)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = policy.report_exit(self.path, binding, policy.exit_code(results))
        return code, output.getvalue()

    def test_complete_capacity_and_rejection_are_findings_not_admission_pass(self):
        results = [saturated(), row(verdict("noncompliant"), 2)]
        code, output = self.project(results)
        self.assertEqual(code, 0)
        self.assertIn("complete-with-findings", output)
        self.assertIn("budget-saturated", output)
        self.assertIn("noncompliant", output)
        self.assertIn("::warning::", output)
        self.assertEqual(policy.exit_code(results), 1)
        self.assertEqual(policy.summarize(results)["execution"], "failed")

    def test_old_remote_success_remains_explicitly_unresolved(self):
        code, output = self.project([saturated()])
        self.assertEqual(code, 0)
        self.assertIn("old success may remain", output.lower())

    def test_recognized_capacity_post_is_eligible(self):
        api = Mock()
        api.history.return_value = []
        api.status.side_effect = http_error()
        outcome, publish = policy.invalidated(api, HEAD, False, 100)
        self.assertFalse(publish)
        self.assertEqual(self.project([row(outcome)])[0], 0)
        self.assertEqual(api.status.call_count, 1)

    def test_capacity_reserve_is_eligible_without_repeated_writes(self):
        for recorded in (False, True):
            with self.subTest(recorded=recorded):
                api = Mock()
                entries = [{}] * (policy.STATUS_LIMIT - policy.STATUS_RESERVE)
                if recorded:
                    entries[0] = {"state": "failure", "description": policy.BUDGET_DESCRIPTION}
                api.history.return_value = entries
                outcome, publish = policy.invalidated(api, HEAD, False, 100)
                self.assertFalse(publish)
                self.assertEqual(outcome["kind"], "budget-exhausted")
                self.assertEqual(self.project([row(outcome)])[0], 0)
                self.assertEqual(api.status.call_count, 0 if recorded else 1)

    def test_history_failure_then_capacity_never_hides_prior_failure(self):
        for error in (http_error(401, False), http_error(403, False), OSError("Offline")):
            with self.subTest(error=type(error).__name__, code=getattr(error, "code", None)):
                api = Mock()
                api.history.side_effect = error
                api.status.side_effect = http_error()
                outcome, publish = policy.invalidated(api, HEAD, False, 100)
                self.assertFalse(publish)
                self.assertEqual(outcome["kind"], "budget-saturated")
                self.assertEqual(self.project([row(outcome)])[0], 1)

    def test_evaluator_error_then_capacity_never_hides_prior_failure(self):
        outcome = policy.status_write_failure(http_error(), verdict("evaluator-error"))
        self.assertEqual(self.project([row(outcome)])[0], 1)

    def test_unknown_validation_permissions_and_network_fail(self):
        for error in (http_error(422, False), http_error(401, False),
                      http_error(403, False), OSError("Offline")):
            with self.subTest(error=type(error).__name__, code=getattr(error, "code", None)):
                outcome = policy.status_write_failure(error, verdict())
                self.assertEqual(self.project([row(outcome)])[0], 1)

    def test_other_target_or_global_failure_is_not_swallowed(self):
        for kind in policy.ERROR_KINDS - {"budget-exhausted", "budget-saturated"}:
            with self.subTest(kind=kind):
                self.assertEqual(self.project([saturated(), row(verdict(kind), 2)])[0], 1)
        self.assertEqual(self.project([saturated(), row(verdict("unverified"), 0)])[0], 1)

    def test_pr_and_manual_capacity_remain_red(self):
        for event in ("pull_request_target", "workflow_dispatch"):
            with self.subTest(event=event):
                self.assertEqual(self.project([saturated()], event=event)[0], 1)

    def test_incomplete_or_mismatched_enumeration_cannot_make_push_green(self):
        for evidence in ({"complete": False, "targets": [1]},
                         {"complete": True, "targets": []},
                         {"complete": True, "targets": [1, 2]},
                         {"complete": True, "targets": [1, 1]},
                         {"complete": True, "targets": [True]},
                         {"complete": 1, "targets": [1]}):
            with self.subTest(evidence=evidence):
                try:
                    code, _ = self.project([saturated()], reconciliation=evidence)
                except (ValueError, TypeError):
                    continue
                self.assertEqual(code, 1)

    def test_missing_reconciliation_cannot_make_push_green(self):
        results = [saturated()]
        policy.write_report(self.path, self.binding, results,
                            {"mode": "full-sweep", "reason": "policy-inputs-changed"})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(policy.report_exit(self.path, self.binding, 1), 1)

    def test_missing_stale_malformed_and_crash_report_fail(self):
        with self.assertRaises(OSError):
            policy.report_exit(self.path, self.binding, 1)
        self.project([saturated()])
        with self.assertRaises(ValueError):
            policy.report_exit(self.path, dict(self.binding, report_id="next"), 1)
        with self.assertRaises(ValueError):
            policy.report_exit(self.path, self.binding, 2)
        self.path.write_text("not json")
        with self.assertRaises(ValueError):
            policy.report_exit(self.path, self.binding, 1)

    def test_full_sweep_processes_every_target_and_carries_typed_provenance(self):
        api = Mock()
        prs = {number: {"number": number, "state": "open", "body": "Fixture",
                        "head": {"sha": str(number) * 40},
                        "base": {"ref": "main", "sha": SHA}} for number in (1, 2)}
        api.pages.return_value = list(prs.values())
        api.get.side_effect = lambda path: prs[int(path.split("/")[-1])]
        api.history.return_value = [{"state": "success"}] * policy.STATUS_LIMIT
        plan = {"policy_sha": SHA, "completed": {}}
        reconciliation = {}
        results = policy.check_prs(api, {"base_branch": "main"}, SHA, False,
                                   plan=plan, report_scope=True, reconciliation=reconciliation)
        self.assertEqual(reconciliation, {"complete": True, "targets": [1, 2]})
        self.assertEqual({r["pull_request"] for r in results}, {1, 2})
        self.assertEqual(api.history.call_count, 2)
        api.status.assert_not_called()
        self.assertEqual(self.project(results, reconciliation=reconciliation)[0], 0)
        carried = policy.check_prs(api, {"base_branch": "main"}, SHA, False,
                                   plan=plan, report_scope=True, reconciliation=reconciliation)
        self.assertEqual(api.history.call_count, 2)
        self.assertEqual(carried, results)
        self.assertEqual(self.project(carried, reconciliation=reconciliation)[0], 0)

    def test_newly_discovered_target_makes_full_sweep_incomplete(self):
        api = Mock()
        prs = [{"number": number, "state": "open", "body": "Fixture",
                "head": {"sha": str(number) * 40},
                "base": {"ref": "main", "sha": SHA}} for number in (1, 2)]
        api.pages.side_effect = [[prs[0]], prs]
        api.get.return_value = prs[0]
        api.history.return_value = [{"state": "success"}] * policy.STATUS_LIMIT
        reconciliation = {}
        results = policy.check_prs(api, {"base_branch": "main"}, SHA, False,
                                   report_scope=True, reconciliation=reconciliation)
        self.assertFalse(reconciliation["complete"])
        self.assertEqual(self.project(results, reconciliation=reconciliation)[0], 1)

    def test_malformed_or_error_provenance_cannot_make_push_green(self):
        for key, value in (("source", "unknown"), ("prior_execution_error", 0),
                           ("prior_execution_error", True),
                           ("prior_kind", "evaluator-error")):
            with self.subTest(key=key, value=value):
                outcome = saturated()
                outcome["capacity_evidence"][key] = value
                self.assertEqual(self.project([outcome])[0], 1)

    def test_missing_capacity_provenance_cannot_make_push_green(self):
        outcome = saturated()
        outcome.pop("capacity_evidence", None)
        self.assertEqual(self.project([outcome])[0], 1)


if __name__ == "__main__":
    unittest.main()
