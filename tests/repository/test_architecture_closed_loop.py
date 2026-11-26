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

from inferrsi.knowledge.knowledge_operations import KnowledgeReader
from tests.repository.architecture_closed_loop import MemoryArchive, _canonical, _digest, run_loop
from tests.repository.architecture_real_ports import (
    PACKAGE_READ,
    CpuOfflineHarnessRecord,
    OfflineBenchmarkAssessment,
    PackageKnowledgeRead,
)

LOOP = Path(__file__).with_name("architecture_closed_loop.py")
PORTS = Path(__file__).with_name("architecture_real_ports.py")
LAYOUT = Path(__file__).resolve().parents[2] / "docs" / "guides" / "module-layout.md"
ROOT = Path(__file__).resolve().parents[2]
# Families the CPU/offline assembler must not couple to: the CLI, its parser, the
# Harness runner, and Apps, Knowledge or Benchmark as packages.
BANNED_FAMILIES = (
    "inferrsi.cli",
    "inferrsi.arguments",
    "inferrsi.harness.runner",
    "inferrsi.harness.manager._runner",
    "inferrsi.harness.manager.run_experiment",
    "inferrsi.apps",
    "inferrsi.knowledge",
    "inferrsi.benchmark",
)
# #412 R1 deleted the root shells through which the assembler reached Knowledge and the
# old evaluator, so those two seams are now canonical modules inside two banned
# families. They are exempt by exact module name only. The package above a seam, a
# module beside it and a module below it stay banned.
EXACT_SEAMS = frozenset(
    {"inferrsi.knowledge.knowledge_operations", "inferrsi.apps.legacy.evaluation"}
)


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
        self.assertRegex(knowledge.revision, r"^sha256:[0-9a-f]{64}(?![\s\S])")
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
        self.assertIn("inferrsi.knowledge.knowledge_operations", imported)
        self.assertIn("inferrsi.harness.trials.external", imported)
        self.assertIn("inferrsi.apps.legacy.evaluation", imported)
        # The six banned families are unchanged. Two of the three seams are canonical
        # Knowledge and Apps modules since #412 R1; the guard exempts those two exact
        # names and nothing else in either family.
        source = PORTS.read_text(encoding="utf-8")
        self.assertEqual(_seam_violations(source), [])
        # Each exempt name is a seam this assembler really imports; none is spare.
        self.assertLessEqual(EXACT_SEAMS, set(imported))
        # The guard reads every name the earlier per-module view read, and more.
        self.assertLessEqual(set(imported), set(_named_modules(source)))
        calls = _call_names(PORTS)
        self.assertIn("read", calls)
        self.assertIn("execute_trial", calls)
        self.assertIn("evaluate", calls)
        self.assertNotIn("search_knowledge", calls)
        self.assertNotIn("collect", calls)
        # #412 R1 deleted the root shell; these are the implementation's own imports.
        knowledge = _import_modules(ROOT / "src/inferrsi/knowledge/knowledge_operations.py")
        harness = _import_modules(ROOT / "src/inferrsi/harness/trials/external.py")
        self.assertFalse(any("harness" in name or "evaluation" in name for name in knowledge))
        self.assertFalse(any("knowledge" in name or "evaluation" in name for name in harness))
        text = LAYOUT.read_text(encoding="utf-8")
        self.assertIn("does not call `collect` or `search_knowledge`", text)
        self.assertIn("campaign `PASS`", text)

    def test_seam_guard_exempts_only_the_two_exact_seams(self) -> None:
        # The guard that passes the real assembler above, on single import lines.
        allowed = (
            "from inferrsi.knowledge.knowledge_operations import KnowledgeReader\n",
            "from inferrsi.apps.legacy.evaluation import evaluate\n",
            "import inferrsi.knowledge.knowledge_operations\n",
            "import inferrsi.apps.legacy.evaluation as old_evaluate\n",
            "from inferrsi.harness.trials.external import execute_trial\n",
            "from inferrsi.contracts import RunSpec\n",
            "import json\nfrom pathlib import Path\n",
        )
        for source in allowed:
            with self.subTest(allowed=source):
                self.assertEqual(_seam_violations(source), [])
        refused = (
            # A module beside a seam, including one whose name only starts like it.
            ("from inferrsi.apps.legacy.run import run_experiment\n", "inferrsi.apps.legacy.run"),
            ("from inferrsi.apps.legacy.reporting import write_report\n",
             "inferrsi.apps.legacy.reporting"),
            ("import inferrsi.apps.legacy.evaluation_extra\n",
             "inferrsi.apps.legacy.evaluation_extra"),
            ("from inferrsi.knowledge.catalog import search_knowledge\n",
             "inferrsi.knowledge.catalog"),
            ("from inferrsi.knowledge.knowledge_store import KnowledgeStore\n",
             "inferrsi.knowledge.knowledge_store"),
            ("import inferrsi.knowledge.knowledge_operations_v2\n",
             "inferrsi.knowledge.knowledge_operations_v2"),
            # Another Apps or Knowledge module that is no seam of this assembler.
            ("from inferrsi.apps.host.prepared_environment import inspect_environment\n",
             "inferrsi.apps.host.prepared_environment"),
            ("from inferrsi.apps.api import read_attempt_view\n", "inferrsi.apps.api"),
            ("from inferrsi.knowledge.skill_catalog import get_skill\n",
             "inferrsi.knowledge.skill_catalog"),
            # The package above a seam, by any spelling. Binding a seam as a module
            # object names its package, so only the plain from-import form passes.
            ("import inferrsi.apps\n", "inferrsi.apps"),
            ("import inferrsi.apps.legacy\n", "inferrsi.apps.legacy"),
            ("import inferrsi.knowledge\n", "inferrsi.knowledge"),
            ("from inferrsi import apps\n", "inferrsi.apps"),
            ("from inferrsi import knowledge\n", "inferrsi.knowledge"),
            ("from inferrsi.apps import legacy\n", "inferrsi.apps.legacy"),
            ("from inferrsi.apps.legacy import evaluation\n", "inferrsi.apps.legacy"),
            ("from inferrsi.knowledge import knowledge_operations\n", "inferrsi.knowledge"),
            ("from inferrsi.knowledge import *\n", "inferrsi.knowledge"),
            # A module below a seam.
            ("import inferrsi.apps.legacy.evaluation.rules\n",
             "inferrsi.apps.legacy.evaluation.rules"),
            ("from inferrsi.apps.legacy.evaluation.rules import VALUE\n",
             "inferrsi.apps.legacy.evaluation.rules"),
            ("import inferrsi.knowledge.knowledge_operations.bundle\n",
             "inferrsi.knowledge.knowledge_operations.bundle"),
            # An alias, a nested import and a seam on the line before change nothing.
            ("import inferrsi.apps.legacy.run as evaluation\n", "inferrsi.apps.legacy.run"),
            ("def late():\n    from inferrsi.knowledge.catalog import search_knowledge\n",
             "inferrsi.knowledge.catalog"),
            ("from inferrsi.apps.legacy.evaluation import evaluate\n"
             "from inferrsi.apps.legacy import run\n", "inferrsi.apps.legacy.run"),
        )
        for source, expected in refused:
            with self.subTest(refused=source):
                self.assertIn(expected, _seam_violations(source))
        # A name taken from a seam is an attribute while no module of that name exists
        # below it. If a seam ever becomes a package, such a module is refused too.
        self.assertTrue(_is_module("inferrsi.apps.legacy.evaluation"))
        self.assertTrue(_is_module("inferrsi.apps.legacy"))
        self.assertFalse(_is_module("inferrsi.apps.legacy.evaluation.evaluate"))
        below = "from inferrsi.apps.legacy.evaluation import rules\n"
        self.assertEqual(_seam_violations(below), [])
        with patch.object(sys.modules[__name__], "_is_module", return_value=True):
            self.assertEqual(
                _seam_violations(below), ["inferrsi.apps.legacy.evaluation.rules"]
            )

    def test_seam_guard_keeps_the_cli_parser_runner_and_benchmark_bans(self) -> None:
        refused = (
            ("from inferrsi.cli import main\n", "inferrsi.cli"),
            ("import inferrsi.cli\n", "inferrsi.cli"),
            ("from inferrsi import cli\n", "inferrsi.cli"),
            ("from inferrsi.arguments import parser\n", "inferrsi.arguments"),
            ("import inferrsi.arguments as options\n", "inferrsi.arguments"),
            ("from inferrsi import arguments\n", "inferrsi.arguments"),
            ("from inferrsi.harness.runner import run_experiment\n", "inferrsi.harness.runner"),
            ("from inferrsi.harness.manager import run_experiment\n",
             "inferrsi.harness.manager.run_experiment"),
            ("import inferrsi.harness.manager._runner as loop\n",
             "inferrsi.harness.manager._runner"),
            ("import inferrsi.harness.runner as loop\n", "inferrsi.harness.runner"),
            ("from inferrsi.harness import runner\n", "inferrsi.harness.runner"),
            ("from inferrsi.benchmark.legacy_run_v0 import evaluate\n",
             "inferrsi.benchmark.legacy_run_v0"),
            ("import inferrsi.benchmark\n", "inferrsi.benchmark"),
            ("from inferrsi import benchmark\n", "inferrsi.benchmark"),
            ("from inferrsi.benchmark import registry\n", "inferrsi.benchmark.registry"),
            ("def late():\n    import inferrsi.cli\n", "inferrsi.cli"),
        )
        for source, expected in refused:
            with self.subTest(refused=source):
                self.assertIn(expected, _seam_violations(source))
        # Harness is not banned whole: only its runner is, and a lookalike is not it.
        self.assertEqual(_seam_violations("from inferrsi.harness import atomic_json\n"), [])
        self.assertEqual(_seam_violations("import inferrsi.harness.runner_notes\n"), [])

    def test_real_assembler_fails_the_same_guard_once_a_coupling_is_added(self) -> None:
        text = PORTS.read_text(encoding="utf-8")
        seam = "from inferrsi.apps.legacy.evaluation import evaluate\n"
        self.assertEqual(text.count(seam), 1)
        self.assertEqual(_seam_violations(text), [])
        mutations = (
            (text.replace(seam, "from inferrsi.apps.legacy.run import run_experiment\n"),
             "inferrsi.apps.legacy.run"),
            (text.replace(seam, "from inferrsi.apps.legacy import evaluation\n"),
             "inferrsi.apps.legacy"),
            (text + "\nfrom inferrsi.knowledge.catalog import search_knowledge\n",
             "inferrsi.knowledge.catalog"),
            (text + "\nfrom inferrsi.cli import main\n", "inferrsi.cli"),
            (text + "\nfrom inferrsi.arguments import parser\n", "inferrsi.arguments"),
            (text + "\nfrom inferrsi.harness.manager import run_experiment\n",
             "inferrsi.harness.manager.run_experiment"),
            (text + "\nfrom inferrsi.benchmark.legacy_run_v0 import evaluate\n",
             "inferrsi.benchmark.legacy_run_v0"),
        )
        for source, expected in mutations:
            with self.subTest(expected=expected):
                self.assertIn(expected, _seam_violations(source))
        # Both families are still banned whole: without the exact exemption, the two
        # canonical seams of the unchanged assembler are refused as well.
        seams = sorted(EXACT_SEAMS)
        with patch.object(sys.modules[__name__], "EXACT_SEAMS", frozenset()):
            unexempted = _seam_violations(text)
        for name in seams:
            self.assertIn(name, unexempted)


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


def _is_module(name: str) -> bool:
    path = ROOT.joinpath("src", *name.split("."))
    return path.with_name(path.name + ".py").is_file() or (path / "__init__.py").is_file()


def _named_modules(source: str) -> list[str]:
    """Every module a source may import.

    This holds each name ``_import_modules`` records, and adds ``package.name`` for an
    absolute ``from package import name``, which that helper cannot see. A name taken
    from an exact seam module is one of its attributes, so it is added only when a
    module of that name exists below the seam.
    """
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
            if node.level:
                continue
            for alias in node.names:
                candidate = f"{node.module}.{alias.name}"
                if alias.name != "*" and (
                    node.module not in EXACT_SEAMS or _is_module(candidate)
                ):
                    names.append(candidate)
    return names


def _seam_violations(source: str) -> list[str]:
    """Banned-family modules that assembler source imports, other than an exact seam."""
    return [
        name
        for name in _named_modules(source)
        if name not in EXACT_SEAMS
        and any(name == prefix or name.startswith(prefix + ".") for prefix in BANNED_FAMILIES)
    ]


if __name__ == "__main__":
    unittest.main()
