"""Offline incident-writer races and uncertain durable outcomes; stdlib only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tests.test_skill_eval_daily_budget import API, DAY, KEY, PR, binding
from tools import skill_eval_budget as b
from tools import skill_eval_quarantine as q
from tools.skill_eval_budget_git import GitHubDailyStore

EVIDENCE = "https://github.com/example/repo/issues/1#issuecomment-2"


class QuarantineTests(unittest.TestCase):
    def test_concurrent_admission_is_preserved_then_stopped(self):
        api = API()
        store = GitHubDailyStore(api, api.anchor)
        other = GitHubDailyStore(api, api.anchor)
        def admission():
            snapshot = other.read_verified(KEY)
            self.assertIs(other.compare_and_swap(snapshot, b.daily_reserve(
                snapshot.ledger, PR, binding(1), DAY)), b.WriteResult.COMMITTED)
        api.before_patch = admission
        stopped = q.persist_quarantine(store, KEY, EVIDENCE)
        self.assertEqual(stopped.ledger.quarantine, EVIDENCE)
        self.assertEqual(len(stopped.ledger.entries), 1)
        with self.assertRaises(b.BudgetError):
            b.daily_claim_once(other, PR, binding(1), DAY)

    def test_lost_write_receipt_reconciles_only_into_stop(self):
        api = API()
        api.lose_response = True
        stopped = q.persist_quarantine(GitHubDailyStore(api, api.anchor), KEY, EVIDENCE)
        self.assertEqual(stopped.ledger.quarantine, EVIDENCE)
        self.assertEqual(stopped.ledger.revision, 1)

    def test_repeated_stop_preserves_original_evidence_without_new_write(self):
        api = API()
        store = GitHubDailyStore(api, api.anchor)
        first = q.persist_quarantine(store, KEY, EVIDENCE)
        tip = api.tip
        self.assertEqual(q.persist_quarantine(store, KEY, EVIDENCE), first)
        self.assertEqual(q.persist_quarantine(store, KEY,
                         "https://github.com/example/repo/issues/2"), first)
        self.assertEqual(api.tip, tip)

    def test_success_receipt_without_verified_readback_is_failure(self):
        api = API()
        store = GitHubDailyStore(api, api.anchor)
        snapshot = store.read_verified(KEY)
        # Even COMMITTED is not enough for incident completion without readback.
        store.read_verified = Mock(side_effect=[snapshot] + [OSError("offline")] * 3)
        store.compare_and_swap = Mock(return_value=b.WriteResult.COMMITTED)
        with self.assertRaisesRegex(b.BudgetError, "NOT verified"):
            q.persist_quarantine(store, KEY, EVIDENCE)
        self.assertEqual(store.read_verified.call_count, 4)

    def test_conflicts_exhaust_bound_without_false_success(self):
        api = API()
        store = GitHubDailyStore(api, api.anchor)
        store.compare_and_swap = Mock(return_value=b.WriteResult.CONFLICT)
        with self.assertRaisesRegex(b.BudgetError, "NOT verified"):
            q.persist_quarantine(store, KEY, EVIDENCE)
        self.assertEqual(store.compare_and_swap.call_count, 3)
        self.assertIsNone(store.read_verified(KEY).ledger.quarantine)

    def test_expired_pricing_does_not_block_emergency_stop(self):
        api = API()
        config = {"schema_version": 2, "repository_id": 123, "expires_at": 1,
                  "provider": {"pricing": "not needed for monotonic stop"},
                  "daily_budget": {"currency": "USD", "amount": "1000",
                      "timezone": "Asia/Shanghai", "anchor": {
                          "ref": api.anchor.ref, "genesis_commit": api.genesis,
                          "checkpoint_commit": api.genesis}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config))
            self.assertEqual(q.quarantine(api, EVIDENCE, config_path=path).ledger.quarantine,
                             EVIDENCE)

    def test_invalid_evidence_does_not_access_storage(self):
        store = Mock()
        for evidence in ("raw billing error", EVIDENCE + "?token=private", "", None):
            with self.assertRaises(b.BudgetError):
                q.persist_quarantine(store, KEY, evidence)
        store.read_verified.assert_not_called()

    def test_cli_failure_never_reports_verified(self):
        with patch("sys.argv", ["quarantine", "--repository", "example/repo",
                                "--evidence", EVIDENCE]), \
                patch.object(q, "GitHub", return_value=Mock()), \
                patch.dict(q.os.environ, {"GITHUB_TOKEN": "offline-fixture"}), \
                patch.object(q, "quarantine", side_effect=b.BudgetError("unavailable")), \
                patch("builtins.print") as output:
            with self.assertRaises(SystemExit) as error:
                q.main()
            self.assertEqual(error.exception.code, 1)
            output.assert_not_called()


if __name__ == "__main__":
    unittest.main()
