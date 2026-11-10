"""Handoff loop. Refusal cases inject outcomes. The CPU path uses real ports."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from inferrsi.knowledge_operations import KnowledgeReader
from tests.architecture_closed_loop import MemoryArchive, _canonical, _digest, run_loop
from tests.architecture_real_ports import (
    PACKAGE_READ,
    CpuOfflineHarnessRecord,
    OfflineBenchmarkAssessment,
    PackageKnowledgeRead,
)

LOOP = Path(__file__).with_name("architecture_closed_loop.py")
PORTS = Path(__file__).with_name("architecture_real_ports.py")
LAYOUT = Path(__file__).resolve().parents[1] / "docs" / "module-layout.md"
ROOT = Path(__file__).resolve().parents[1]


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

        # os.system is not patched; this loop does not call it.
        with patch.object(subprocess, "run", refuse_process), patch.object(
            subprocess, "Popen", refuse_process
        ):
            result = run_loop(
                knowledge=knowledge,
                harness=harness,
                benchmark=benchmark,
                archive=archive,
            )

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
        self.assertEqual(result.reason, "completed")
        self.assertEqual(result.verdict, "INCONCLUSIVE")
        self.assertIsNotNone(result.assessment_ref)

    def test_foreign_attempt_is_not_assessed(self) -> None:
        class Foreign(FakeHarness):
            def execute(self, spec):
                outcome = super().execute(spec)
                outcome["record_ref"]["attempt_id"] = "attempt-other"
                return outcome

        benchmark = FakeBenchmark()
        archive = MemoryArchive()
        result = run_loop(
            knowledge=FakeKnowledge(),
            harness=Foreign(),
            benchmark=benchmark,
            archive=archive,
        )
        self.assertEqual(result.reason, "record_mismatch")
        self.assertIsNone(result.record_ref)
        self.assertEqual(benchmark.assesses, 0)
        self.assertIsNone(result.assessment_ref)
        self.assertEqual(archive.assessments, {})

    def test_foreign_attempt_is_rejected_for_recovery_and_not_started(self) -> None:
        def foreign(kind: str) -> FakeHarness:
            class Foreign(FakeHarness):
                def execute(self, spec):
                    outcome = super().execute(spec)
                    outcome["record_ref"]["attempt_id"] = "attempt-other"
                    return outcome

            return Foreign(kind)

        for kind in ("recovery_required", "not_started"):
            with self.subTest(kind=kind):
                benchmark = FakeBenchmark()
                archive = MemoryArchive()
                result = run_loop(
                    knowledge=FakeKnowledge(),
                    harness=foreign(kind),
                    benchmark=benchmark,
                    archive=archive,
                )
                self.assertEqual(result.reason, "record_mismatch")
                self.assertIsNone(result.record_ref)
                self.assertIsNone(result.assessment_ref)
                self.assertEqual(benchmark.assesses, 0)
                self.assertEqual(archive.assessments, {})

    def test_unknown_kind_is_not_assessed(self) -> None:
        benchmark = FakeBenchmark()
        archive = MemoryArchive()
        result = run_loop(
            knowledge=FakeKnowledge(),
            harness=FakeHarness("finished"),
            benchmark=benchmark,
            archive=archive,
        )
        self.assertEqual(result.reason, "outcome_rejected")
        self.assertEqual(benchmark.assesses, 0)
        self.assertIsNone(result.assessment_ref)
        self.assertEqual(archive.assessments, {})

    def test_missing_evidence_does_not_call_assess(self) -> None:
        class NoEvidence(FakeHarness):
            def execute(self, spec):
                outcome = super().execute(spec)
                outcome.pop("evidence", None)
                return outcome

        benchmark = FakeBenchmark()
        result = run_loop(
            knowledge=FakeKnowledge(),
            harness=NoEvidence(),
            benchmark=benchmark,
            archive=MemoryArchive(),
        )
        self.assertEqual(result.reason, "evidence_missing")
        self.assertEqual(result.verdict, "INCONCLUSIVE")
        self.assertEqual(benchmark.assesses, 0)
        self.assertIsNone(result.assessment_ref)

    def test_coordinator_does_not_import_production_cores(self) -> None:
        # Static import names only. importlib.import_module is not detected.
        for name in _import_modules(LOOP):
            self.assertFalse(name.startswith("inferrsi"))

    def test_real_cpu_offline_ports_connect_three_refs(self) -> None:
        knowledge = PackageKnowledgeRead()
        benchmark = OfflineBenchmarkAssessment()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            harness = CpuOfflineHarnessRecord(root)
            archive = MemoryArchive()
            result = run_loop(
                knowledge=knowledge,
                harness=harness,
                benchmark=benchmark,
                archive=archive,
            )
            self.assertEqual(result.reason, "completed")
            self.assertIsNotNone(result.prepared_ref)
            self.assertIsNotNone(result.record_ref)
            self.assertIsNotNone(result.assessment_ref)
            execution = json.loads((root / "trial" / "execution.json").read_text(encoding="utf-8"))
            probe = json.loads((root / "trial" / "result.json").read_text(encoding="utf-8"))
            prepared = json.loads(archive.read_prepared(result.prepared_ref))
            assessment = json.loads(archive.assessments[result.assessment_ref.digest])

        again = KnowledgeReader().read(PACKAGE_READ)
        self.assertEqual(result.verdict, "INCONCLUSIVE")
        self.assertEqual(knowledge.calls, 1)
        self.assertEqual(harness.executes, 1)
        self.assertEqual(benchmark.prepares, 1)
        self.assertEqual(benchmark.assesses, 1)
        self.assertEqual(again.revision, knowledge.revision)
        self.assertEqual(set(again.content), {"record.json"})
        self.assertEqual(again.metadata["id"], PACKAGE_READ)
        self.assertEqual(again.metadata["kind"], "knowledge")
        self.assertRegex(knowledge.revision, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(prepared["knowledge_revision"], knowledge.revision)
        self.assertEqual(prepared["knowledge_id"], PACKAGE_READ)
        self.assertEqual(prepared["candidate"], "unbound")
        self.assertEqual(harness.fact["prepared_digest"], result.prepared_ref.digest)
        self.assertEqual(result.record_ref.digest, _digest(_canonical(harness.fact)))
        self.assertEqual(result.record_ref.attempt_id, harness.attempt_id)
        self.assertEqual(execution["status"], "completed")
        self.assertEqual(execution["returncode"], 0)
        self.assertEqual(execution["argv"][0], sys.executable)
        self.assertIsInstance(execution["pid"], int)
        self.assertGreater(execution["elapsed_seconds"], 0)
        self.assertEqual(probe, {"probe": "cpu-offline", "device": None})
        self.assertEqual(assessment["verdict"], "INCONCLUSIVE")
        self.assertEqual(assessment["knowledge_revision"], knowledge.revision)
        self.assertEqual(assessment["record_status"], "completed")
        self.assertEqual(assessment["record_returncode"], 0)
        self.assertIn("quality validation command was not supplied", assessment["reasons"])
        self.assertIn(
            "cpu offline record has no source snapshot",
            assessment["reasons"],
        )
        self.assertEqual(benchmark.last["verdict"], "INCONCLUSIVE")
        self.assertIsNone(benchmark.last["improvement_pct"])
        self.assertIn("Alternating AB/BA", benchmark.last["measurement_method"])
        self.assertEqual(benchmark.last["statistical_significance"], "not established")
        self.assertIn(result.prepared_ref.digest, archive.prepared)
        self.assertIn(result.assessment_ref.digest, archive.assessments)
        self.assertNotIn(result.record_ref.digest, archive.prepared)
        self.assertNotEqual(result.record_ref.digest, "sha256:" + ("ab" * 32))

    def test_real_ports_stay_on_three_existing_seams(self) -> None:
        imported = _import_modules(PORTS)
        self.assertIn("inferrsi.knowledge_operations", imported)
        self.assertIn("inferrsi.harness.scenarios.external", imported)
        self.assertIn("inferrsi.evaluation", imported)
        banned = (
            "inferrsi.cli",
            "inferrsi.arguments",
            "inferrsi.harness.runner",
            "inferrsi.apps",
            "inferrsi.knowledge",
            "inferrsi.benchmark",
        )
        for name in imported:
            for prefix in banned:
                self.assertFalse(name == prefix or name.startswith(prefix + "."))
        calls = _call_names(PORTS)
        self.assertIn("read", calls)
        self.assertIn("execute_trial", calls)
        self.assertIn("evaluate", calls)
        self.assertNotIn("search_knowledge", calls)
        self.assertNotIn("collect", calls)
        knowledge = _import_modules(ROOT / "src/inferrsi/knowledge_operations.py")
        harness = _import_modules(ROOT / "src/inferrsi/harness/scenarios/external.py")
        self.assertFalse(any("harness" in name or "evaluation" in name for name in knowledge))
        self.assertFalse(any("knowledge" in name or "evaluation" in name for name in harness))
        text = LAYOUT.read_text(encoding="utf-8")
        self.assertIn("does not call `collect` or `search_knowledge`", text)
        self.assertIn("campaign `PASS`", text)


def _import_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    return imported


def _call_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


if __name__ == "__main__":
    unittest.main()
