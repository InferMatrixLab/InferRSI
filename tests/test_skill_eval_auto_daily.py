"""Offline controller fault matrix; stdlib only, no provider or remote calls."""
import contextlib
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools import skill_eval_auto as auto
from tools import skill_eval_budget as b

DAY = "2026-10-29"
NEXT = "2026-10-30"
KEY = b.PRKey(123, 7)
GLOBAL = b.DailyKey(123)
BUDGET = {"currency": "USD", "amount": "1000", "timezone": "Asia/Shanghai",
          "anchor": {"ref": "refs/heads/skill-eval-budget/123/daily",
                     "genesis_commit": "a" * 40, "checkpoint_commit": "a" * 40}}


class Store:
    def __init__(self, ledger, snapshot, name, events, fault=None):
        self.ledger, self.snapshot, self.name = ledger, snapshot, name
        self.events, self.fault, self.writes = events, fault, 0

    def read_verified(self, key):
        assert key == self.ledger.key
        return self.snapshot(str(self.ledger.revision), self.ledger)

    def compare_and_swap(self, before, after):
        self.writes += 1
        self.events.append((self.name, after.entries[-1].phase))
        assert before.ledger == self.ledger
        fault = self.fault and self.fault[0] == self.writes
        if fault and self.fault[1] == "conflict":
            return b.WriteResult.CONFLICT
        self.ledger = after
        if fault and self.fault[1] == "crash":
            raise RuntimeError("crash after durable write")
        return b.WriteResult.UNKNOWN if fault else b.WriteResult.COMMITTED


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.plan = {"pr": 7, "reservation": {"amount": "10", "requests": 2}}
        (self.output / "pr-plan.json").write_text(json.dumps(self.plan))
        self.config = {"schema_version": 2, "repository_id": 123,
                       "daily_budget": copy.deepcopy(BUDGET)}
        self.events = []
        self.pr_store = Store(b.Ledger(KEY, b.Genesis("offline audited history", 0)),
                              b.Snapshot, "pr", self.events)
        self.global_store = Store(b.DailyLedger(GLOBAL, "offline audited history"),
                                  b.DailySnapshot, "daily", self.events)
        self.day = DAY
        self.callback = None
        self.launch = Mock()

    @contextlib.contextmanager
    def broker(self, check, max_requests, *, context):
        self.callback = check
        yield {}

    def execute(self, run=42):
        with contextlib.ExitStack() as stack:
            for target, value in (
                ("configuration", lambda *a, **k: self.config),
                ("eligible", lambda *a: None),
                ("live_label", lambda *a: {"actor": "offline", "label_event_id": 1}),
                ("ledger_store", lambda *a: (self.pr_store, KEY)),
                ("daily_store", lambda *a: (self.global_store, GLOBAL)),
                ("shanghai_day", lambda: self.day)):
                stack.enter_context(patch.object(auto, target, value))
            stack.enter_context(patch.object(auto.pr, "execution_id", return_value="offline"))
            stack.enter_context(patch.dict(auto.os.environ,
                                          {"SKILL_EVAL_YIBUAPI_KEY": "offline-fixture"}))
            stack.enter_context(patch("inferrsi.model.request_guard.authorization_broker",
                                      self.broker))
            auto.controlled_execute(Mock(), self.output, run_id=run, attempt=1,
                                    launch=self.launch)

    def test_both_new_reservations_and_claims_precede_launch(self):
        def launch(*args, **kwargs):
            self.assertEqual(self.events, [("daily", "reserved"), ("pr", "reserved"),
                                          ("daily", "claimed"), ("pr", "claimed")])
            self.callback()
        self.launch.side_effect = launch
        self.execute()
        self.assertEqual(self.pr_store.ledger.charged, 10_000_000)
        self.assertEqual(self.global_store.ledger.charged_on(NEXT), 10_000_000)

    def test_every_write_conflict_unknown_or_crash_blocks_and_retry_never_launches(self):
        for name in ("pr_store", "global_store"):
            for write in (1, 2):
                for failure in ("conflict", "unknown", "crash"):
                    with self.subTest(store=name, write=write, failure=failure):
                        self.setUp()
                        store = getattr(self, name)
                        store.fault = (write, failure)
                        with self.assertRaises((b.BudgetError, RuntimeError)):
                            self.execute()
                        self.launch.assert_not_called()
                        store.fault = None
                        # A conflict on the very first global write leaves no state,
                        # so a new invocation can genuinely reserve. All partial
                        # or ambiguous commits are non-replayable.
                        if name == "global_store" and write == 1 and failure == "conflict":
                            continue
                        with self.assertRaises(b.BudgetError):
                            self.execute()
                        self.launch.assert_not_called()

    def test_midnight_after_claim_blocks_launch(self):
        original = self.pr_store.compare_and_swap
        def write(before, after):
            result = original(before, after)
            if after.entries[-1].phase == "claimed":
                self.day = NEXT
            return result
        self.pr_store.compare_and_swap = write
        with self.assertRaisesRegex(b.BudgetError, "day ended"):
            self.execute()
        self.launch.assert_not_called()

    def test_midnight_before_daily_claim_blocks_launch(self):
        original = self.pr_store.compare_and_swap
        def write(before, after):
            result = original(before, after)
            self.day = NEXT
            return result
        self.pr_store.compare_and_swap = write
        with self.assertRaisesRegex(b.BudgetError, "admission day"):
            self.execute()
        self.launch.assert_not_called()

    def test_midnight_next_request_denied_and_crash_retains_bounds(self):
        def launch(*args, **kwargs):
            self.callback()
            self.day = NEXT
            with self.assertRaisesRegex(b.BudgetError, "day ended"):
                self.callback()
            raise RuntimeError("worker crashed after first request")
        self.launch.side_effect = launch
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertEqual(self.pr_store.ledger.charged, 10_000_000)
        self.assertEqual(self.global_store.ledger.charged_on(NEXT), 10_000_000)
        with self.assertRaises(b.BudgetError):
            self.execute()
        self.assertEqual(self.launch.call_count, 1)

    def test_missing_global_claim_revokes_next_request(self):
        def launch(*args, **kwargs):
            self.callback()
            binding = self.global_store.ledger.entries[0].binding
            self.global_store.ledger = b.daily_advance(
                self.global_store.ledger, KEY, binding, "finished", DAY, actual_cost=1)
            with self.assertRaisesRegex(b.BudgetError, "global claim"):
                self.callback()
        self.launch.side_effect = launch
        self.execute()

    def test_quarantine_revokes_next_request(self):
        def launch(*args, **kwargs):
            self.callback()
            self.global_store.ledger = b.daily_quarantine(
                self.global_store.ledger, "offline externally verified unknown exposure")
            with self.assertRaisesRegex(b.BudgetError, "quarantin"):
                self.callback()
        self.launch.side_effect = launch
        self.execute()
        with self.assertRaises(b.BudgetError):
            self.execute(run=43)
        self.assertEqual(self.launch.call_count, 1)

    def test_missing_global_history_never_writes_pr_reservation(self):
        self.global_store.read_verified = Mock(side_effect=b.BudgetError("missing genesis"))
        with self.assertRaisesRegex(b.BudgetError, "missing genesis"):
            self.execute()
        self.assertEqual(self.events, [])
        self.launch.assert_not_called()

    def test_configuration_migration_preserves_legacy_read_only(self):
        legacy = json.loads(auto.CONFIG.read_text())
        legacy["schema_version"] = 1
        legacy.pop("daily_budget", None)
        legacy["anchors"].pop("133", None)
        path = self.output / "config.json"
        path.write_text(json.dumps(legacy))
        self.assertEqual(auto.configuration(path, now=0), legacy)
        with self.assertRaises(b.BudgetError):
            auto.daily_anchor(legacy)
        migrated = {**legacy, "schema_version": 2, "daily_budget": copy.deepcopy(BUDGET)}
        migrated["daily_budget"]["anchor"]["ref"] = (
            f"refs/heads/skill-eval-budget/{legacy['repository_id']}/daily")
        path.write_text(json.dumps(migrated))
        self.assertEqual(auto.configuration(path, now=0), migrated)
        self.assertEqual(migrated["anchors"], legacy["anchors"])

    def test_daily_schema_is_explicit_no_legacy_bootstrap(self):
        self.assertEqual(auto.daily_anchor(self.config).key, GLOBAL)
        for mutation in ({"schema_version": 1}, {"daily_budget": None},
                         {"daily_budget": {**BUDGET, "amount": "2000"}},
                         {"daily_budget": {**BUDGET, "timezone": "UTC"}}):
            with self.subTest(mutation=mutation), self.assertRaises(b.BudgetError):
                auto.daily_anchor({**self.config, **mutation})


if __name__ == "__main__":
    unittest.main()
