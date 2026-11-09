"""Observable test-double loop. Fakes are injected; the loop under test is real."""

from __future__ import annotations

import ast
import subprocess
import unittest
from pathlib import Path

from tests.architecture_closed_loop import MemoryArchive, run_loop

LOOP = Path(__file__).with_name("architecture_closed_loop.py")


class FakeKnowledge:
    def __init__(self) -> None:
        self.calls = 0

    def deliver(self) -> dict:
        self.calls += 1
        return {"pin": "test-pin", "body": "fixture"}


class FakeBenchmark:
    def __init__(self) -> None:
        self.prepares = 0
        self.assesses = 0

    def prepare(self, delivered: dict) -> dict:
        self.prepares += 1
        return {"task": "cpu-fixture", "delivered_pin": delivered["pin"]}

    def assess(self, prepared_bytes: bytes, evidence: dict) -> dict:
        self.assesses += 1
        if evidence.get("samples") != "retained":
            return {"verdict": "INCONCLUSIVE"}
        return {"verdict": "PASS", "prepared_bytes": len(prepared_bytes)}


class FakeHarness:
    def __init__(self, kind: str = "completed") -> None:
        self.kind = kind
        self.executes = 0
        self.records: list[str] = []

    def allocate_attempt(self) -> dict:
        return {"attempt_id": "attempt-1", "retry_of": None}

    def execute(self, spec: dict) -> dict:
        self.executes += 1
        if self.kind == "no_record":
            return {"kind": "no_record"}
        record = {
            "attempt_id": spec["attempt_id"],
            "record_version": 1,
            "digest": "sha256:" + ("ab" * 32),
        }
        self.records.append(record["digest"])
        outcome = {"kind": self.kind, "record_ref": record}
        if self.kind == "completed":
            outcome["evidence"] = {"samples": "retained", "exit_code": 0}
        return outcome


class ClosedLoopTest(unittest.TestCase):
    def test_success_path_keeps_facts_and_verdict_apart(self) -> None:
        knowledge = FakeKnowledge()
        harness = FakeHarness()
        benchmark = FakeBenchmark()
        archive = MemoryArchive()

        def refuse_process(*_args, **_kwargs):
            raise AssertionError("closed loop started a process")

        original_run, original_popen = subprocess.run, subprocess.Popen
        subprocess.run = refuse_process
        subprocess.Popen = refuse_process
        try:
            result = run_loop(
                knowledge=knowledge,
                harness=harness,
                benchmark=benchmark,
                archive=archive,
            )
        finally:
            subprocess.run, subprocess.Popen = original_run, original_popen

        self.assertEqual(result.reason, "completed")
        self.assertEqual(result.verdict, "PASS")
        self.assertIsNotNone(result.prepared_ref)
        self.assertIsNotNone(result.record_ref)
        self.assertIsNotNone(result.assessment_ref)
        self.assertEqual(knowledge.calls, 1)
        self.assertEqual(benchmark.prepares, 1)
        self.assertEqual(benchmark.assesses, 1)
        self.assertEqual(harness.executes, 1)
        self.assertIn(result.prepared_ref.digest, archive.prepared)
        self.assertIn(result.assessment_ref.digest, archive.assessments)
        self.assertNotIn(result.record_ref.digest, archive.prepared)

    def test_failed_prepared_archive_does_not_execute(self) -> None:
        harness = FakeHarness()
        result = run_loop(
            knowledge=FakeKnowledge(),
            harness=harness,
            benchmark=FakeBenchmark(),
            archive=MemoryArchive(fail_prepared=True),
        )
        self.assertEqual(result.reason, "archive_prepared_failed")
        self.assertIsNone(result.prepared_ref)
        self.assertIsNone(result.record_ref)
        self.assertEqual(harness.executes, 0)

    def test_bind_rejects_a_digest_mismatch_without_writing_records(self) -> None:
        class Mismatched(MemoryArchive):
            def read_prepared(self, ref):
                return b"not-the-archived-bytes"

        harness = FakeHarness()
        before = list(harness.records)
        result = run_loop(
            knowledge=FakeKnowledge(),
            harness=harness,
            benchmark=FakeBenchmark(),
            archive=Mismatched(),
        )
        self.assertEqual(result.reason, "bind_rejected")
        self.assertIsNotNone(result.prepared_ref)
        self.assertIsNone(result.record_ref)
        self.assertEqual(harness.executes, 0)
        self.assertEqual(harness.records, before)

    def test_not_started_record_is_not_a_successful_assessment(self) -> None:
        benchmark = FakeBenchmark()
        result = run_loop(
            knowledge=FakeKnowledge(),
            harness=FakeHarness("not_started"),
            benchmark=benchmark,
            archive=MemoryArchive(),
        )
        self.assertEqual(result.reason, "not_started")
        self.assertIsNotNone(result.record_ref)
        self.assertIsNone(result.assessment_ref)
        self.assertEqual(benchmark.assesses, 0)

    def test_missing_commit_has_no_record_ref(self) -> None:
        result = run_loop(
            knowledge=FakeKnowledge(),
            harness=FakeHarness("no_record"),
            benchmark=FakeBenchmark(),
            archive=MemoryArchive(),
        )
        self.assertEqual(result.reason, "no_record")
        self.assertIsNone(result.record_ref)
        self.assertIsNone(result.assessment_ref)

    def test_unknown_controller_is_not_cancelled(self) -> None:
        result = run_loop(
            knowledge=FakeKnowledge(),
            harness=FakeHarness("recovery_required"),
            benchmark=FakeBenchmark(),
            archive=MemoryArchive(),
        )
        self.assertEqual(result.reason, "recovery_required")
        self.assertFalse(result.cancelled)
        self.assertIsNotNone(result.record_ref)
        self.assertIsNone(result.assessment_ref)

    def test_assessment_archive_failure_keeps_the_record(self) -> None:
        result = run_loop(
            knowledge=FakeKnowledge(),
            harness=FakeHarness(),
            benchmark=FakeBenchmark(),
            archive=MemoryArchive(fail_assessment=True),
        )
        self.assertEqual(result.reason, "archive_assessment_failed")
        self.assertEqual(result.verdict, "PASS")
        self.assertIsNotNone(result.record_ref)
        self.assertIsNone(result.assessment_ref)

    def test_missing_samples_stay_inconclusive(self) -> None:
        class Bare(FakeHarness):
            def execute(self, spec):
                outcome = super().execute(spec)
                outcome["evidence"] = {"samples": "missing", "exit_code": 0}
                return outcome

        result = run_loop(
            knowledge=FakeKnowledge(),
            harness=Bare(),
            benchmark=FakeBenchmark(),
            archive=MemoryArchive(),
        )
        self.assertEqual(result.verdict, "INCONCLUSIVE")

    def test_coordinator_does_not_import_production_cores(self) -> None:
        tree = ast.parse(LOOP.read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for name in imported:
            self.assertFalse(name.startswith("inferrsi"))


if __name__ == "__main__":
    unittest.main()
