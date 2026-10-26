"""Offline final-attempt report and scope checks (stdlib only)."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools import check_knowledge_model_policy as policy

SHA = "a" * 40


def result(number=1, kind="compliant"):
    return {"pull_request": number, "head_sha": "b" * 40, "policy_sha": SHA,
            "dry_run": False, "rerun": kind in policy.RERUN_KINDS,
            "state": "success" if kind in {"compliant", "closed"} else "failure",
            "kind": kind, "description": "fixture", "errors": []}


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "report.json"
        self.event = Path(self.temp.name) / "event.json"
        self.event.write_text(json.dumps({"number": 1, "pull_request": {"number": 1,
                                                               "head": {"sha": "b" * 40}}}))
        self.binding = policy.report_binding("owner/repo", "pull_request_target",
                                             self.event, SHA, "attempt-3")

    def project(self, results, binding=None):
        binding = binding or self.binding
        policy.write_report(self.path, binding, results)
        with contextlib.redirect_stdout(io.StringIO()):
            return policy.report_exit(self.path, binding, policy.exit_code(results))

    def test_own_success_unrelated_failure(self):
        self.assertEqual(self.project([result(), result(2, "history-unavailable")]), 0)

    def test_each_own_failure_is_red(self):
        for kind in policy.KINDS:
            if kind not in {"compliant", "closed"}:
                with self.subTest(kind=kind):
                    self.assertEqual(self.project([result(1, kind), result(2)]), 1)

    def test_closed_is_explicit_na(self):
        self.assertEqual(self.project([result(1, "closed")]), 0)

    def test_missing_own_and_global_listing_failure_fail(self):
        self.assertEqual(self.project([result(2)]), 1)
        self.assertEqual(self.project([result(), result(0, "unverified")]), 1)

    def test_push_and_dispatch_keep_global_health(self):
        for event in ("push", "workflow_dispatch"):
            binding = dict(self.binding, event_name=event, trigger=None)
            self.assertEqual(self.project([result(), result(2, "history-unavailable")], binding), 1)
            self.assertEqual(self.project([result()], binding), 0)

    def test_unknown_dry_run_and_bad_success_fail_closed(self):
        for key, value in (("dry_run", True), ("kind", "new-kind"), ("head_sha", "bad")):
            row = result()
            row[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.project([row])
        row = result()
        row["errors"] = ["not verified"]
        self.assertEqual(self.project([row]), 1)
        row = result()
        row["state"] = "failure"
        self.assertEqual(self.project([row]), 1)

    def test_duplicate_targets_fail(self):
        with self.assertRaises(ValueError):
            self.project([result(), result()])

    def test_stale_attempt_policy_event_or_repo_fail(self):
        policy.write_report(self.path, self.binding, [result()])
        for key in ("report_id", "policy_sha", "event_digest", "repository", "trigger"):
            binding = dict(self.binding, **{key: "different"})
            with self.subTest(key=key), self.assertRaises(ValueError):
                policy.report_exit(self.path, binding, 0)

    def test_missing_or_invalid_report_fails(self):
        with self.assertRaises(OSError):
            policy.report_exit(self.path, self.binding, 0)
        self.path.write_text("not json")
        with self.assertRaises(ValueError):
            policy.report_exit(self.path, self.binding, 0)

    def test_summary_and_exit_tampering_fail(self):
        policy.write_report(self.path, self.binding, [result()])
        with self.assertRaises(ValueError):
            policy.report_exit(self.path, self.binding, 2)
        report = json.loads(self.path.read_text())
        report["summary"]["results"] = 9
        self.path.write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            policy.report_exit(self.path, self.binding, 0)

    def test_last_attempt_replaces_earlier_success(self):
        self.assertEqual(self.project([result()]), 0)
        self.assertEqual(self.project([result(1, "unverified")]), 1)
        self.assertFalse(self.path.with_name("report.json.tmp").exists())

    def test_issue_comment_scope_and_event_digest(self):
        self.event.write_text(json.dumps({"issue": {"number": 7, "pull_request": {}}}))
        binding = policy.report_binding("owner/repo", "issue_comment", self.event, SHA, "3")
        self.assertEqual(binding["trigger"], 7)
        self.assertNotEqual(binding["event_digest"], self.binding["event_digest"])

    def test_inconsistent_or_boolean_pr_number_rejected(self):
        for event in ({"number": 1, "pull_request": {"number": 2}},
                      {"number": True, "pull_request": {"number": True}}):
            self.event.write_text(json.dumps(event))
            with self.assertRaises(ValueError):
                policy.report_binding("owner/repo", "pull_request_target", self.event, SHA, "3")

    def test_closed_trigger_is_added_to_global_sweep(self):
        api = Mock()
        api.pages.return_value = []
        api.get.return_value = {"number": 1, "head": {"sha": "b" * 40},
                                "base": {"ref": "main"}, "state": "closed"}
        results = policy.check_prs(api, {"base_branch": "main"}, SHA, False,
                                   trigger=1, report_scope=True)
        self.assertEqual([(r["pull_request"], r["kind"]) for r in results], [(1, "closed")])
        self.assertEqual(api.get.call_count, 2)
        api.status.assert_not_called()
        self.assertEqual(self.project(results), 0)

    def test_final_collection_failure_blocks_even_closed_target(self):
        api = Mock()
        api.pages.side_effect = [[], OSError("fixture collection failure")]
        api.get.return_value = {"number": 1, "head": {"sha": "b" * 40},
                                "base": {"ref": "main"}, "state": "closed"}
        results = policy.check_prs(api, {"base_branch": "main"}, SHA, False,
                                   trigger=1, report_scope=True)
        self.assertIn(0, [r["pull_request"] for r in results])
        self.assertEqual(self.project(results), 1)
        api.status.assert_not_called()

    def test_trigger_is_first_without_dropping_other_targets(self):
        api = Mock()
        prs = {number: {"number": number, "head": {"sha": str(number) * 40},
                        "base": {"ref": "main"}, "state": "open"} for number in (1, 2)}
        api.pages.return_value = list(prs.values())
        api.get.side_effect = lambda path: prs[int(path.split("/")[-1])]
        failure = {"state": "failure", "kind": "budget-saturated",
                   "description": "fixture", "errors": []}
        with patch.object(policy, "invalidated", return_value=(failure, False)):
            results = policy.check_prs(api, {"base_branch": "main"}, SHA, False,
                                       trigger=2, report_scope=True)
        self.assertEqual(api.get.call_args_list[0].args, ("pulls/2",))
        self.assertEqual({r["pull_request"] for r in results}, {1, 2})

    def test_boolean_schema_or_exit_is_not_valid_integer(self):
        for field, value in (("schema_version", True), ("sweep_exit", False)):
            policy.write_report(self.path, self.binding, [result()])
            report = json.loads(self.path.read_text())
            report[field] = value
            self.path.write_text(json.dumps(report))
            with self.subTest(field=field), self.assertRaises(ValueError):
                policy.report_exit(self.path, self.binding, 0)

    def test_pull_request_event_head_must_match_evaluated_head(self):
        self.assertEqual(self.project([result()]), 0)
        advanced = result()
        advanced["head_sha"] = "c" * 40
        policy.write_report(self.path, self.binding, [advanced])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(policy.report_exit(self.path, self.binding, 0), 1)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary["projection_reason"], "stale-event-head")
        self.assertEqual(summary["expected_head"], "b" * 40)
        self.assertEqual(summary["evaluated_head"], "c" * 40)

    def test_missing_or_malformed_event_head_fails_closed(self):
        for head in (None, {}, {"sha": "bad"}, {"sha": True}, {"sha": "b" * 39}):
            event = {"number": 1, "pull_request": {"number": 1, "head": head}}
            self.event.write_text(json.dumps(event))
            with self.subTest(head=head), self.assertRaises(ValueError):
                policy.report_binding("owner/repo", "pull_request_target", self.event, SHA, "3")

    def test_issue_comment_still_uses_current_head(self):
        self.event.write_text(json.dumps({"issue": {"number": 1, "pull_request": {}}}))
        binding = policy.report_binding("owner/repo", "issue_comment", self.event, SHA, "3")
        advanced = result()
        advanced["head_sha"] = "c" * 40
        self.assertEqual(self.project([advanced], binding), 0)


class RunnerTests(unittest.TestCase):
    def run_runner(self, mode, event_name="pull_request_target"):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            event = temp / "event.json"
            event.write_text(json.dumps({"number": 1, "pull_request": {"number": 1,
                                                               "head": {"sha": "b" * 40}}}))
            git = temp / "git"
            git.write_text("#!/bin/sh\nif [ \"$1\" = rev-parse ]; then printf '%040d\\n' 0; fi\n")
            python = temp / "python"
            python.write_text("#!" + sys.executable + "\n" + r'''import json, os, runpy, sys
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, os.environ["FIXTURE_ROOT"])
from tools import check_knowledge_model_policy as policy
args = sys.argv[2:]
def arg(name): return args[args.index(name) + 1]
if "--report-exit" in args:
    sys.argv = [sys.argv[1]] + args
    runpy.run_path(str(Path(os.environ["FIXTURE_ROOT"]) / "tools/check_knowledge_model_policy.py"),
                   run_name="__main__")
counter = Path(os.environ["RUNNER_TEMP"]) / "count"
count = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(count))
mode = os.environ["FIXTURE_MODE"]
if mode == "missing-final" and count == 3:
    sys.exit(2)
kind = "history-unavailable" if mode == "own-final-failure" and count == 3 else "compliant"
def row(number, kind):
    return {"pull_request": number, "head_sha": "b" * 40, "policy_sha": arg("--policy-sha"),
            "dry_run": False, "rerun": kind in policy.RERUN_KINDS,
            "state": "success" if kind == "compliant" else "failure", "kind": kind,
            "description": "fixture", "errors": []}
binding = policy.report_binding(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_EVENT_NAME"],
                                os.environ["GITHUB_EVENT_PATH"], arg("--policy-sha"),
                                arg("--report-id"))
policy.write_report(Path(arg("--report")), binding, [row(1, kind), row(2, "history-unavailable")])
sys.exit(2)
''')
            git.chmod(0o700)
            python.chmod(0o700)
            env = {"PATH": str(temp) + ":/usr/bin:/bin", "HOME": directory,
                   "RUNNER_TEMP": directory, "GITHUB_RUN_ID": "fixture",
                   "GITHUB_EVENT_NAME": event_name, "GITHUB_EVENT_PATH": str(event),
                   "GITHUB_REPOSITORY": "owner/repo", "FIXTURE_ROOT": str(root),
                   "FIXTURE_MODE": mode, "PYTHONDONTWRITEBYTECODE": "1"}
            completed = subprocess.run(
                ["/bin/bash", str(root / "tools/run_knowledge_model_policy.sh")],
                cwd=root, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual((temp / "count").read_text(), "3", completed.stderr)
            self.assertFalse(list(temp.glob("knowledge-model-policy-*.json")))
            return completed

    def test_no_early_exit_and_other_pr_failure_only_warns(self):
        outcome = self.run_runner("own-success")
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertIn("::warning::", outcome.stdout)

    def test_final_own_failure_overrides_previous_green(self):
        outcome = self.run_runner("own-final-failure")
        self.assertEqual(outcome.returncode, 1, outcome.stderr)

    def test_missing_final_report_cannot_reuse_previous_green(self):
        outcome = self.run_runner("missing-final")
        self.assertEqual(outcome.returncode, 1, outcome.stderr)

    def test_main_push_stays_global_failure(self):
        outcome = self.run_runner("own-success", "push")
        self.assertEqual(outcome.returncode, 1, outcome.stderr)


if __name__ == "__main__":
    unittest.main()
