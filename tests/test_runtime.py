"""CPU-only runtime contracts with real external commands and Git snapshots."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from inferrsi.contracts import RunSpec
from inferrsi.execution import repository_identity, run_experiment
from inferrsi.harness.evaluation import _summary, evaluate
from inferrsi.harness.runner import run_experiment as run_with_adapters
from inferrsi.harness.scenarios.external import execute_trial
from inferrsi.infra.environment import storage_locations
from inferrsi.reporting import write_report


def benchmark(value: object) -> tuple[str, ...]:
    code = (
        "import json, pathlib, sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2], "
        "encoding='utf-8')"
    )
    return (sys.executable, "-c", code, "{result}", json.dumps({"metrics": {"latency_ms": value}}))


def process_running(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE, no termination rights
        if not handle:
            if ctypes.get_last_error() == 87:  # process has exited
                return False
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return kernel.WaitForSingleObject(handle, 1000) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists() and stat.read_text().split(")", 1)[1].split()[0] == "Z":
        return False
    return True


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "source.txt").write_text("initial source\n", encoding="utf-8")
        self.git("init", "--quiet")
        self.git("add", "source.txt")
        self.git(
            "-c",
            "user.name=InferRSI test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-s",
            "-m",
            "fixture",
        )
        self.spec = RunSpec(
            repo=str(self.repo),
            baseline_command=benchmark(100),
            candidate_command=benchmark(80),
            repetitions=2,
            validation_command=(sys.executable, "-c", "print('caller quality checks passed')"),
            output_dir=str(self.root / "runs"),
            max_minutes=1,
        )

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def run_spec(self, **changes):
        path = run_experiment(replace(self.spec, **changes), {"backend": "cpu", "test": True})
        return path, json.loads((path / "evaluation.json").read_text(encoding="utf-8"))

    def test_positive_gain_with_explicit_quality_passes_and_alternates_order(self):
        path, evaluation = self.run_spec()
        self.assertEqual(evaluation["verdict"], "PASS")
        self.assertAlmostEqual(evaluation["improvement_pct"], 20)
        events = [
            json.loads(line)
            for line in (path / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            [event["side"] for event in events if event["phase"] == "measurement"],
            ["baseline", "candidate", "candidate", "baseline"],
        )
        trial = json.loads((path / "baseline/trial-001/execution.json").read_text(encoding="utf-8"))
        self.assertGreater(trial["pid"], 0)
        self.assertIn(str(path / "baseline/trial-001/result.json"), trial["argv"])
        self.assertEqual(json.loads((path / "status.json").read_text())["state"], "completed")
        self.assertTrue((path / "report.html").is_file())

    def test_missing_quality_evidence_is_inconclusive(self):
        _, evaluation = self.run_spec(validation_command=None)
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertTrue(any("quality" in reason for reason in evaluation["reasons"]))

    def test_tracked_source_mutation_is_detected_inside_output_directory(self):
        source = self.repo / "src" / "implementation.py"
        source.parent.mkdir()
        source.write_text("original\n")
        self.git("add", "src/implementation.py")
        self.git(
            "-c",
            "user.name=InferRSI test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-s",
            "-m",
            "source",
        )
        code = (
            "import json,pathlib,sys; pathlib.Path('src/implementation.py').write_text('changed'); "
            "pathlib.Path(sys.argv[1]).write_text(json.dumps({'metrics':{'latency_ms':80}}))"
        )
        _, result = self.run_spec(
            output_dir=str(source.parent),
            repetitions=1,
            candidate_command=(sys.executable, "-c", code, "{result}"),
        )
        self.assertEqual(result["verdict"], "INCONCLUSIVE")
        self.assertFalse(result["source_integrity"]["verified"])

    def test_quality_failure_is_fail_but_incomplete_benchmark_is_inconclusive(self):
        failure = (sys.executable, "-c", "import sys; print('failed evidence'); sys.exit(7)")
        path, evaluation = self.run_spec(validation_command=failure)
        self.assertEqual(evaluation["verdict"], "FAIL")
        self.assertIn("failed evidence", (path / "validation/stdout.log").read_text())
        path, evaluation = self.run_spec(baseline_command=failure)
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertEqual(json.loads((path / "status.json").read_text())["state"], "failed")
        self.assertFalse((path / "candidate").exists())
        self.assertEqual(
            json.loads((path / "baseline/trial-001/execution.json").read_text())["returncode"], 7
        )

    def test_missing_malformed_nonfinite_and_nonpositive_metrics_are_inconclusive(self):
        commands = [
            (sys.executable, "-c", "pass"),
            (
                sys.executable,
                "-c",
                "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text('{broken')",
                "{result}",
            ),
            benchmark("80"),
            benchmark(True),
            benchmark(float("nan")),
            benchmark(float("inf")),
            benchmark(0),
            benchmark(-1),
        ]
        for command in commands:
            with self.subTest(command=command):
                _, evaluation = self.run_spec(candidate_command=command, repetitions=1)
                self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")

    def test_result_environment_variable_is_supported(self):
        code = (
            "import json, os, pathlib; "
            "pathlib.Path(os.environ['INFERRSI_RESULT_PATH']).write_text(json.dumps({'metrics':{'latency_ms':80}}))"
        )
        _, evaluation = self.run_spec(candidate_command=(sys.executable, "-c", code), repetitions=1)
        self.assertEqual(evaluation["verdict"], "PASS")

    def test_direction_threshold_and_equal_values(self):
        _, evaluation = self.run_spec(min_improvement_pct=21)
        self.assertEqual(evaluation["verdict"], "FAIL")
        _, evaluation = self.run_spec(candidate_command=benchmark(100))
        self.assertEqual(evaluation["verdict"], "FAIL")
        _, evaluation = self.run_spec(direction="maximize", candidate_command=benchmark(120))
        self.assertEqual(evaluation["verdict"], "PASS")
        _, evaluation = self.run_spec(direction="maximize", candidate_command=benchmark(80))
        self.assertEqual(evaluation["verdict"], "FAIL")

    def test_source_change_is_inconclusive_and_existing_dirty_source_is_recorded(self):
        (self.repo / "source.txt").write_text("pre-existing local change\n", encoding="utf-8")
        identity = repository_identity(self.repo)
        self.assertTrue(identity["available"])
        self.assertTrue(identity["dirty"])
        _, evaluation = self.run_spec()
        self.assertEqual(evaluation["verdict"], "PASS")
        code = (
            "import json, pathlib, sys; pathlib.Path('source.txt').write_text('unexpected "
            "change'); "
            "pathlib.Path(sys.argv[1]).write_text(json.dumps({'metrics': {'latency_ms':80}}))"
        )
        path, evaluation = self.run_spec(candidate_command=(sys.executable, "-c", code, "{result}"))
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertIn("source changed", evaluation["source_integrity"]["reason"])
        self.assertTrue((path / "repositories.final.json").is_file())

    def test_source_change_restored_later_still_invalidates_comparison(self):
        changed = (
            "import json, pathlib, sys; pathlib.Path('source.txt').write_text('temporary drift'); "
            "pathlib.Path(sys.argv[1]).write_text(json.dumps({'metrics': {'latency_ms':100}}))"
        )
        restored = (
            "import json, pathlib, sys; pathlib.Path('source.txt').write_text('initial "
            "source\\n'); "
            "pathlib.Path(sys.argv[1]).write_text(json.dumps({'metrics': {'latency_ms':80}}))"
        )
        path, evaluation = self.run_spec(
            baseline_command=(sys.executable, "-c", changed, "{result}"),
            candidate_command=(sys.executable, "-c", restored, "{result}"),
            repetitions=1,
        )
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertEqual((self.repo / "source.txt").read_text(), "initial source\n")
        checks = json.loads((path / "source_checks.json").read_text())
        self.assertNotEqual(
            checks[0]["before"]["snapshot_hash"], checks[0]["after"]["snapshot_hash"]
        )

    def test_derived_metric_overflow_preserves_inconclusive_artifacts(self):
        path, evaluation = self.run_spec(
            baseline_command=benchmark(1e-308), candidate_command=benchmark(1e308), repetitions=1
        )
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertTrue((path / "report.html").is_file())

    def test_unknown_source_identity_is_inconclusive(self):
        plain = self.root / "plain"
        plain.mkdir()
        self.assertFalse(repository_identity(plain)["available"])
        _, evaluation = self.run_spec(candidate_repo=str(plain), repetitions=1)
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")

    def test_outputs_inside_repo_do_not_create_false_source_changes(self):
        _, evaluation = self.run_spec(output_dir=str(self.repo / "runs"))
        self.assertEqual(evaluation["verdict"], "PASS")

    def git_at(self, repo, *args):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def make_superproject(self):
        """A superproject whose only content is a submodule with a tracked file."""
        origin = self.root / "sub-origin"
        origin.mkdir()
        self.git_at(origin, "init", "--quiet")
        (origin / "vendor.py").write_bytes(b"original\n")
        self.git_at(origin, "add", "vendor.py")
        self.git_at(
            origin,
            "-c",
            "user.name=InferRSI test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-s",
            "-m",
            "submodule",
        )
        superproject = self.root / "super"
        superproject.mkdir()
        self.git_at(superproject, "init", "--quiet")
        self.git_at(
            superproject,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "--quiet",
            str(origin),
            "sub",
        )
        self.git_at(
            superproject,
            "-c",
            "user.name=InferRSI test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-s",
            "-m",
            "super",
        )
        return superproject

    def test_submodule_local_edit_changes_snapshot_hash(self):
        # The parent diff records only "<commit>-dirty", so two distinct edits
        # inside a submodule must not share one snapshot hash.
        superproject = self.make_superproject()
        vendor = superproject / "sub" / "vendor.py"
        vendor.write_bytes(b"first edit\n")
        first = repository_identity(superproject)["snapshot_hash"]
        vendor.write_bytes(b"second edit\n")
        second = repository_identity(superproject)["snapshot_hash"]
        self.assertNotEqual(first, second)
        self.assertTrue(repository_identity(superproject)["dirty"])
        vendor.write_bytes(b"original\n")
        self.assertFalse(repository_identity(superproject)["dirty"])

    def test_untracked_nested_repository_is_hashed_not_unavailable(self):
        # Git reports an untracked nested repository as one directory entry;
        # opening that entry as a file used to make identity unavailable.
        nested = self.repo / "nested"
        nested.mkdir()
        self.git_at(nested, "init", "--quiet")
        (nested / "inner.txt").write_bytes(b"inner\n")
        identity = repository_identity(self.repo)
        self.assertTrue(identity["available"], identity.get("error"))
        self.assertEqual(identity["untracked"][0]["path"], "nested/")
        before = identity["snapshot_hash"]
        (nested / "inner.txt").write_bytes(b"changed\n")
        self.assertNotEqual(repository_identity(self.repo)["snapshot_hash"], before)

    def test_non_utf8_untracked_name_reports_the_path(self):
        # A name that is not UTF-8 must name the file instead of surfacing a
        # bare codec offset, and must not reach the artifact writer as a surrogate.
        real_run = subprocess.run

        def ls_files_only(argv, **kwargs):
            if "ls-files" in argv:
                return subprocess.CompletedProcess(
                    argv, 0, stdout=b"source.txt\x00bad-\xff.txt\x00", stderr=b""
                )
            return real_run(argv, **kwargs)

        with patch("subprocess.run", side_effect=ls_files_only):
            identity = repository_identity(self.repo)
        self.assertFalse(identity["available"])
        self.assertIn("bad-", identity["error"])
        self.assertIn("not valid UTF-8", identity["error"])

    def test_non_utf8_name_does_not_cost_a_complete_run_its_artifacts(self):
        # snapshot() runs inside run_experiment's finally block, so an
        # unrepresentable name must not destroy an otherwise complete run.
        (self.repo / "odd\udcff.txt").write_bytes(b"x")
        path, evaluation = self.run_spec(repetitions=1)
        self.assertTrue((path / "evaluation.json").is_file())
        self.assertTrue((path / "report.html").is_file())
        self.assertEqual(json.loads((path / "status.json").read_text())["state"], "completed")
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertFalse(evaluation["source_integrity"]["verified"])

    def test_unreadable_submodule_identity_names_the_path_instead_of_a_key_error(self):
        # repository_identity returns only path/available/error on failure, so
        # reading snapshot_hash raised KeyError inside the run's finally block.
        superproject = self.make_superproject()
        submodule = (superproject / "sub").resolve()
        real_run = subprocess.run

        def ls_files_only(argv, **kwargs):
            if "ls-files" in argv and "--others" in argv:
                target = Path(argv[argv.index("-C") + 1]).resolve()
                stdout = b"bad-\xff.txt\x00" if target == submodule else b""
                return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr=b"")
            return real_run(argv, **kwargs)

        with patch("subprocess.run", side_effect=ls_files_only):
            identity = repository_identity(superproject)
        self.assertFalse(identity["available"])
        self.assertIn("Submodule sub", identity["error"])
        self.assertIn("not valid UTF-8", identity["error"])

    def test_unreadable_submodule_identity_keeps_run_artifacts(self):
        superproject = self.make_superproject()
        submodule = (superproject / "sub").resolve()
        real_run = subprocess.run

        def ls_files_only(argv, **kwargs):
            if "ls-files" in argv and "--others" in argv:
                target = Path(argv[argv.index("-C") + 1]).resolve()
                stdout = b"bad-\xff.txt\x00" if target == submodule else b""
                return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr=b"")
            return real_run(argv, **kwargs)

        with patch("subprocess.run", side_effect=ls_files_only):
            path, evaluation = self.run_spec(candidate_repo=str(superproject), repetitions=1)
        self.assertTrue((path / "evaluation.json").is_file())
        self.assertTrue((path / "report.html").is_file())
        self.assertEqual(json.loads((path / "status.json").read_text())["state"], "completed")
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertFalse(evaluation["source_integrity"]["verified"])
        repositories = json.loads((path / "repositories.lock.json").read_text())
        self.assertIn("Submodule sub", repositories["candidate"]["error"])

    def test_identical_symlink_recreation_keeps_the_directory_digest(self):
        # Two links to the same target must hash the same regardless of the order
        # the filesystem happens to enumerate them in. Unlinking and recreating a
        # link with an identical target is not a source change.
        from inferrsi.infra.targets.git import _directory_digest

        nested = self.repo / "nested"
        nested.mkdir()
        target = nested / "shared"
        target.mkdir()
        (target / "module.py").write_bytes(b"shared\n")
        links = [nested / "a", nested / "b"]
        for link in links:
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"Symlinks unavailable: {exc}")
        before = _directory_digest(nested)
        first = links[0]
        first.unlink()
        first.symlink_to(target, target_is_directory=True)
        self.assertEqual(_directory_digest(nested), before)

    def test_directory_symlink_retarget_changes_directory_digest(self):
        # os.walk does not descend symlinked directories, so an unrecorded link
        # let a dependency swap leave the nested-repository hash unchanged.
        from inferrsi.infra.targets.git import _directory_digest

        nested = self.repo / "nested"
        (nested / "package").mkdir(parents=True)
        for name, body in (("a", b"dependency-A\n"), ("b", b"dependency-B\n")):
            dependency = nested / name
            dependency.mkdir()
            (dependency / "module.py").write_bytes(body)
        package = nested / "package"
        package.rmdir()
        try:
            package.symlink_to(nested / "a", target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        before = _directory_digest(nested)
        package.unlink()
        package.symlink_to(nested / "b", target_is_directory=True)
        self.assertNotEqual(_directory_digest(nested), before)

    def test_tilde_cache_path_cannot_hide_inside_the_source_checkout(self):
        # A cache configured as "~/..." must be compared after expansion; the
        # literal path resolves to <cwd>/~ and would pass the guard.
        home = self.repo / "home"
        home.mkdir()
        args = SimpleNamespace(source_repo=str(self.repo), cache_root=str(self.root / "cache"))
        with (
            patch.dict(
                os.environ, {"HOME": str(home), "USERPROFILE": str(home), "HF_HOME": "~/hf-cache"}
            ),
            self.assertRaisesRegex(ValueError, "HF_HOME"),
        ):
            storage_locations(args, self.root / "trial", require_source=False)
        self.assertFalse((home / "hf-cache").exists())

    def test_unique_runs_do_not_reuse_previous_metrics(self):
        first, _ = self.run_spec(repetitions=1)
        second, evaluation = self.run_spec(
            candidate_command=(sys.executable, "-c", "pass"), repetitions=1
        )
        self.assertNotEqual(first, second)
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertFalse((second / "candidate/trial-001/result.json").exists())

    def test_timeout_kills_child_tree_and_preserves_evidence(self):
        child = "import time; time.sleep(30)"
        parent = (
            "import subprocess, sys, time; p=subprocess.Popen([sys.executable, "
            "'-c', sys.argv[1]]); print(p.pid, flush=True); time.sleep(30)"
        )
        path, evaluation = self.run_spec(
            baseline_command=(sys.executable, "-c", parent, child), max_minutes=0.1, repetitions=1
        )
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertEqual(json.loads((path / "status.json").read_text())["state"], "timeout")
        child_pid = int((path / "baseline/trial-001/stdout.log").read_text().strip())
        self.assertFalse(process_running(child_pid), "benchmark descendant survived the timeout")

    def test_deadline_also_applies_to_validation(self):
        path, evaluation = self.run_spec(
            validation_command=(sys.executable, "-c", "import time; time.sleep(30)"),
            repetitions=1,
            max_minutes=0.25,
        )
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertEqual(
            json.loads((path / "validation/execution.json").read_text())["status"], "timeout"
        )

    def test_successful_command_also_cleans_up_background_descendants(self):
        child = "import time; time.sleep(30)"
        parent = (
            "import json, pathlib, subprocess, sys; "
            "p=subprocess.Popen([sys.executable, '-c', sys.argv[1]]); print(p.pid, flush=True); "
            "pathlib.Path(sys.argv[2]).write_text(json.dumps({'metrics': {'latency_ms':80}}))"
        )
        path, evaluation = self.run_spec(
            candidate_command=(sys.executable, "-c", parent, child, "{result}"), repetitions=1
        )
        self.assertEqual(evaluation["verdict"], "PASS")
        child_pid = int((path / "candidate/trial-001/stdout.log").read_text().strip())
        self.assertFalse(
            process_running(child_pid), "completed benchmark left a background descendant"
        )

    def test_keyboard_interrupt_preserves_cancelled_run(self):
        with patch("inferrsi.execution._execute", side_effect=KeyboardInterrupt):
            path, evaluation = self.run_spec()
        self.assertEqual(json.loads((path / "status.json").read_text())["state"], "cancelled")
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertTrue((path / "report.html").exists())

    def test_execution_exception_preserves_failed_status_and_inconclusive_verdict(self):
        with patch("inferrsi.execution._execute", side_effect=OSError("executor unavailable")):
            path, evaluation = self.run_spec()
        status = json.loads((path / "status.json").read_text())
        self.assertEqual(status["state"], "failed")
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertIn("executor unavailable", evaluation["reasons"])
        self.assertTrue((path / "report.html").exists())

    def test_missing_quality_wins_over_observed_latency_regression(self):
        _, evaluation = self.run_spec(candidate_command=benchmark(120), validation_command=None)
        self.assertEqual(evaluation["verdict"], "INCONCLUSIVE")
        self.assertTrue(any("measured gain" in reason for reason in evaluation["reasons"]))

    def test_report_escapes_html_and_is_regenerable(self):
        path, _ = self.run_spec(scenario="<script>alert('x')</script>", repetitions=1)
        report = (path / "report.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", report)
        self.assertIn("&lt;script&gt;", report)
        (path / "report.html").unlink()
        self.assertEqual(write_report(path), path / "report.html")

    def test_contract_rejects_invalid_inputs_before_allocating_run(self):
        for changes in (
            {"repetitions": 0},
            {"direction": "unknown"},
            {"max_minutes": float("inf")},
            {"min_improvement_pct": -1},
            {"baseline_command": "echo unsafe"},
            {"metric_key": "metrics..latency"},
            {"output_dir": str(self.repo)},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                run_experiment(replace(self.spec, **changes), {})

    def latest_run(self):
        return max((Path(self.root / "runs")).iterdir(), key=lambda path: path.name)

    def test_hook_exception_is_recorded_as_crashed_and_reaches_the_caller(self):
        # A KeyError is outside the documented adapter error contract, so it must
        # not be absorbed. The run directory must not claim completion either.
        def reader(document, key):
            return document["metrics"]["latency"]

        with self.assertRaises(KeyError):
            run_with_adapters(
                self.spec,
                {"backend": "cpu", "test": True},
                execute=partial(execute_trial, metric_reader=reader),
            )
        run = self.latest_run()
        status = json.loads((run / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "crashed")
        self.assertNotEqual(status["state"], "completed")
        self.assertEqual(status["error"], "KeyError: 'latency'")
        self.assertIsNone(status["verdict"])
        self.assertFalse((run / "evaluation.json").exists())
        events = [
            json.loads(line)
            for line in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual([event["phase"] for event in events][-1], "crashed")
        self.assertNotIn("complete", [event["phase"] for event in events])

    def test_reader_violating_the_metric_contract_keeps_the_evaluation(self):
        # 0.0 is outside the finite-positive contract; before validation it reached
        # _summary and raised ZeroDivisionError inside the termination path.
        def reader(document, key):
            return 0.0

        path = run_with_adapters(
            self.spec,
            {"backend": "cpu", "test": True},
            execute=partial(execute_trial, metric_reader=reader),
        )
        result = json.loads((path / "evaluation.json").read_text(encoding="utf-8"))
        self.assertEqual(result["verdict"], "INCONCLUSIVE")
        self.assertIsNone(result["baseline"])
        self.assertIsNone(result["candidate"])
        self.assertTrue(any("finite and positive" in reason for reason in result["reasons"]))
        status = json.loads((path / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "completed")
        trial = json.loads(
            (path / "baseline/trial-001/execution.json").read_text(encoding="utf-8")
        )
        self.assertIsNone(trial["metric"])
        self.assertIn("finite and positive", trial["metric_error"])

    def test_snapshot_failure_terminates_with_a_named_state_and_retained_error(self):
        # The second snapshot call fails inside the try block: the run records
        # "failed". Cleanup needs another snapshot, so it fails too. The original
        # error must survive that second failure rather than be replaced by it.
        calls = []

        def snapshot(path, exclude=None):
            calls.append(path)
            if len(calls) > 1:
                raise OSError("snapshot backend unavailable")
            return {"available": True, "snapshot_hash": "fixture", "path": str(path)}

        with self.assertRaises(OSError):
            run_with_adapters(
                replace(self.spec, repetitions=1),
                {"backend": "cpu", "test": True},
                snapshot=snapshot,
            )
        run = self.latest_run()
        status = json.loads((run / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "termination_failed")
        self.assertEqual(status["phase"], "termination")
        self.assertEqual(status["requested_state"], "failed")
        self.assertEqual(status["error"], "snapshot backend unavailable")
        self.assertIn("snapshot backend unavailable", status["termination_error"])
        self.assertFalse((run / "evaluation.json").exists())
        self.assertFalse((run / "report.html").exists())

    def test_failed_trial_metric_is_excluded_and_named(self):
        failure = (sys.executable, "-c", "import sys; sys.exit(7)")
        _, evaluation = self.run_spec(validation_command=failure)
        # A completed quality command that rejects its gate fails the run, but
        # both measurement trials completed, so both remain measured.
        self.assertEqual(evaluation["verdict"], "FAIL")
        self.assertEqual(evaluation["baseline"]["values"], [100.0, 100.0])
        self.assertEqual(evaluation["candidate"]["values"], [80.0, 80.0])
        self.assertEqual(evaluation["candidate"]["excluded_trials"], 0)

    def test_summary_ignores_a_timed_out_trial_metric(self):
        summary = _summary(
            [{"status": "completed", "metric": 10.0}, {"status": "timeout", "metric": 5.0}]
        )
        self.assertEqual(summary["values"], [10.0])
        self.assertEqual(summary["excluded_trials"], 1)
        spec = replace(self.spec, repetitions=2)
        result = evaluate(
            spec,
            [{"status": "completed", "metric": 10.0}, {"status": "timeout", "metric": 5.0}],
            [{"status": "completed", "metric": 8.0}, {"status": "completed", "metric": 8.0}],
            {"status": "completed"},
            {"verified": True},
        )
        # A timed-out trial's metric must not enter the baseline median.
        self.assertEqual(result["baseline"]["values"], [10.0])
        self.assertEqual(result["baseline"]["excluded_trials"], 1)
        self.assertTrue(any("excluded from the recorded measurements" in reason
                            for reason in result["reasons"]))


if __name__ == "__main__":
    unittest.main()


class TerminationTests(unittest.TestCase):
    """A failure in the termination path must still leave a truthful status."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "source.txt").write_text("initial source\n", encoding="utf-8")
        for args in (
            ("init", "--quiet"),
            ("add", "source.txt"),
            ("-c", "user.name=InferRSI test", "-c", "user.email=test@example.invalid",
             "-c", "commit.gpgsign=false", "commit", "--quiet", "-s", "-m", "fixture"),
        ):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.spec = RunSpec(
            repo=str(self.repo),
            baseline_command=benchmark(100),
            candidate_command=benchmark(80),
            repetitions=1,
            validation_command=(sys.executable, "-c", "print('ok')"),
            output_dir=str(self.root / "runs"),
            max_minutes=1,
        )

    def test_unexpected_termination_error_is_recorded_not_escaped(self):
        # Report generation fails with an error outside the documented
        # OSError/ValueError contract, after `completed` was already written.
        # That failure must be persisted as the terminal state instead of
        # escaping while `completed` remains the last recorded status.
        with patch("inferrsi.harness.runner.write_report",
                   side_effect=RuntimeError("report backend crashed")):
            with self.assertRaises(RuntimeError):
                run_with_adapters(self.spec, {"backend": "cpu", "test": True})
        run = sorted((self.root / "runs").iterdir())[-1]
        status = json.loads((run / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "termination_failed")
        self.assertEqual(status["phase"], "termination")
        self.assertEqual(status["requested_state"], "completed")
        self.assertIn("report backend crashed", status["termination_error"])

    def test_interruption_while_writing_the_report_is_recorded_as_termination(self):
        # Ctrl-C inside terminate() is outside the caller's own KeyboardInterrupt
        # handler. `completed` was already written, so the interruption must be
        # persisted as a termination failure rather than left looking finished.
        with patch("inferrsi.harness.runner.write_report", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_with_adapters(self.spec, {"backend": "cpu", "test": True})
        run = sorted((self.root / "runs").iterdir())[-1]
        status = json.loads((run / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "termination_failed")
        self.assertEqual(status["phase"], "termination")
        self.assertEqual(status["requested_state"], "completed")
        self.assertIn("KeyboardInterrupt", status["termination_error"])

    def test_interruption_during_final_snapshot_is_recorded_as_termination(self):
        # The final snapshot runs inside terminate(). Interrupting it must not
        # leave `running` as the last persisted state.
        calls = []

        def snapshot(path, exclude=None):
            calls.append(path)
            if len(calls) > 3:
                raise KeyboardInterrupt
            return {"available": True, "snapshot_hash": "fixture", "path": str(path)}

        with self.assertRaises(KeyboardInterrupt):
            run_with_adapters(self.spec, {"backend": "cpu", "test": True}, snapshot=snapshot)
        run = sorted((self.root / "runs").iterdir())[-1]
        status = json.loads((run / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "termination_failed")
        self.assertEqual(status["phase"], "termination")
        self.assertFalse((run / "evaluation.json").exists())
