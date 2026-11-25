"""Offline security tests for the historical report-only bridge."""
import copy
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools import skill_eval_retained as bridge


def zipped(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return stream.getvalue()


class RetainedArchiveTests(unittest.TestCase):
    def test_archive_reads_only_data(self):
        raw = b"raise RuntimeError('never execute artifact code')"
        self.assertEqual(bridge._archive(zipped({"validator/verify.py": raw})),
                         {"validator/verify.py": raw})

    def test_unsafe_names(self):
        for name in ("../escape", "/absolute", "a\\b", "a//b", "a/./b", "a/../b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                bridge._archive(zipped({name: b"x"}))

    def test_symlink_and_special(self):
        for mode in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as archive:
                item = zipfile.ZipInfo("entry")
                item.external_attr = (mode | 0o600) << 16
                archive.writestr(item, "target")
            with self.assertRaises(ValueError):
                bridge._archive(stream.getvalue())

    def test_duplicate_and_oversize(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("one", "first")
            archive.writestr("one", "second")
        with self.assertRaises(ValueError):
            bridge._archive(stream.getvalue())
        with patch.object(bridge, "MAX_BYTES", 1), self.assertRaises(ValueError):
            bridge._archive(zipped({"one": b"xx"}))


class HistoricalGitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "--quiet")
        (self.repo / "tools").mkdir()
        (self.repo / "src").mkdir()
        (self.repo / "src/empty.py").write_text("")
        self.adapter = b"# trusted historical adapter\n"
        (self.repo / "tools/skill_eval_pr.py").write_bytes(self.adapter)
        (self.repo / "tools/skill_eval_pr_cases.json").write_text("{}")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "historical main")
        self.old = self.git("rev-parse", "HEAD")
        (self.repo / "src/empty.py").write_text("# new controller bytes\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "current main")
        self.current = self.git("rev-parse", "HEAD")
        self.plan = {"adapter_sha256": bridge._hash(self.adapter),
                     "mapping_sha256": bridge._hash(b"{}")}

    def git(self, *args):
        return subprocess.check_output(["git", "-c", "user.name=Offline Fixture", "-c",
             "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", *args],
             cwd=self.repo, text=True).strip()

    def test_historical_bytes_not_current_controller(self):
        dest = self.root / "code"
        dest.mkdir()
        bridge._trusted_code(self.repo, self.old, self.current, self.plan, dest)
        self.assertEqual((dest / "src/empty.py").read_bytes(), b"")
        self.assertEqual((dest / "tools/skill_eval_pr.py").read_bytes(), self.adapter)

    def test_invalid_revision_and_blob_bindings(self):
        for field in ("adapter_sha256", "mapping_sha256"):
            changed = {**self.plan, field: "0" * 64}
            with self.subTest(field=field), self.assertRaises(ValueError):
                bridge._trusted_code(self.repo, self.old, self.current, changed, self.root / field)
        with self.assertRaises(ValueError):
            bridge._trusted_code(self.repo, "--help", self.current, self.plan, self.root / "bad")
        with self.assertRaises(ValueError):
            bridge._trusted_code(self.repo, self.old, self.old, self.plan, self.root / "bad")

    def test_nonancestor_rejected(self):
        self.git("checkout", "--quiet", "--orphan", "untrusted")
        self.git("commit", "--quiet", "-m", "unrelated")
        unrelated = self.git("rev-parse", "HEAD")
        self.git("checkout", "--quiet", self.current)
        with self.assertRaises(ValueError):
            bridge._trusted_code(self.repo, unrelated, self.current, self.plan, self.root / "bad")


class ReportOnlyTests(unittest.TestCase):
    def test_clean_environment_no_provider_execute_network_or_artifact_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code, data, home = (root / n for n in ("code", "data", "home"))
            for directory in (code / "tools", code / "src", data, home):
                directory.mkdir(parents=True)
            (code / "tools/__init__.py").write_text("")
            (code / "tools/skill_eval_compare.py").write_text("")
            (data / "results.zip").write_bytes(zipped({}))
            (data / "sitecustomize.py").write_text("raise AssertionError('artifact import')")
            (code / "tools/skill_eval_pr.py").write_text('''
import os, socket, subprocess, sys
from tools import skill_eval_compare as compare
def import_results(raw, output):
    assert set(os.environ) <= {"HOME", "LANG", "LC_ALL", "LC_CTYPE"}
    assert not any(str(output) == p for p in sys.path)
def reports(output):
    for call in (lambda: execute(None), lambda: compare.provider_client(None),
                 lambda: subprocess.run([sys.executable, "-c", "pass"]),
                 lambda: socket.socket()):
        try:
            call()
        except RuntimeError:
            continue
        raise AssertionError("report-only restriction bypassed")
    return [{"verified": True}]
''')
            with patch.dict(os.environ, {"GITHUB_TOKEN": "fake-secret",
                                         "ANTHROPIC_API_KEY": "fake-key",
                                         "PYTHONPATH": str(data), "HTTPS_PROXY": "fake-proxy"}):
                self.assertEqual(bridge._regrade(code, data, home), [{"verified": True}])


class FrozenInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.code, self.data = self.root / "code", self.root / "data"
        (self.code / "tools").mkdir(parents=True)
        self.data.mkdir()
        (self.code / "tools/controller.py").write_bytes(b"trusted")
        self.frozen = {"skill": "selected", "adapter": "audit", "exam": {"grader": "a" * 64},
            "arms": {"baseline": {"git_revision": "b" * 40},
                     "candidate": {"git_revision": "c" * 40}},
            "controllers": {"tools/controller.py": bridge._hash(b"trusted")},
            "files": {"plan/tasks.json": bridge._hash(b"[]"),
                      "plan/schema.json": bridge._hash(b"{}"),
                      "validator/verify.py": bridge._hash(b"raise RuntimeError('do not execute')")}}
        self.files = {"selected/plan/tasks.json": b"[]", "selected/plan/schema.json": b"{}",
                      "selected/validator/verify.py": b"raise RuntimeError('do not execute')"}
        self.plan = {"head": "c" * 40, "base": "b" * 40, "comparisons": [{"skill": "selected",
                     "exam": self.frozen["exam"]}]}
        self.freeze()

    def freeze(self):
        raw = json.dumps(self.frozen).encode()
        self.files["selected/plan/freeze.json"] = raw
        self.plan["comparisons"][0]["plan_sha256"] = bridge._hash(raw)
        self.files["pr-plan.json"] = json.dumps(self.plan).encode()

    def materialize(self):
        return bridge._materialize(self.files, self.plan, self.data, self.code)

    def test_hash_verified_python_remains_data(self):
        context = self.materialize()
        self.assertEqual(context["selected"]["tasks"], [])
        self.assertEqual((self.data / "selected/validator/verify.py").read_bytes(),
                         self.files["selected/validator/verify.py"])

    def test_mismatched_freeze_input_controller_and_arm(self):
        for kind in ("freeze", "input", "controller", "arm", "extra"):
            original_files, original_frozen = copy.deepcopy(self.files), copy.deepcopy(self.frozen)
            with self.subTest(kind=kind):
                if kind == "freeze":
                    self.files["selected/plan/freeze.json"] += b" "
                elif kind == "input":
                    self.files["selected/plan/tasks.json"] = b"[1]"
                elif kind == "extra":
                    self.files["selected/plan/extra.py"] = b"malicious"
                elif kind == "controller":
                    self.frozen["controllers"]["tools/controller.py"] = "0" * 64
                    self.freeze()
                else:
                    self.frozen["arms"]["baseline"]["git_revision"] = "d" * 40
                    self.freeze()
                with self.assertRaises(ValueError):
                    self.materialize()
            self.files, self.frozen = original_files, original_frozen
            self.freeze()

    def test_frozen_path_traversal(self):
        for field, name in (("files", "../../escape"), ("controllers", "../escape")):
            with self.subTest(field=field):
                self.frozen[field][name] = "0" * 64
                self.freeze()
                with self.assertRaises(ValueError):
                    self.materialize()
                del self.frozen[field][name]


class SourceAuthenticationTests(unittest.TestCase):
    def setUp(self):
        from tests.fixtures.skill_eval_pr_support import SimulatedGitHub
        self.plan = {"repository": "example/fixture", "pr": 7, "head": "b" * 40,
                     "base": "c" * 40, "version": "d" * 40, "comparisons": []}
        self.api = SimulatedGitHub(self.plan, zipped({}))
        self.api.run.update(event="pull_request_target", run_attempt=1,
            display_title="skill-eval plan or publish PR 7", head_sha=self.plan["head"])
        self.patches = [patch("tools.skill_eval_auto.retained_source", return_value=10),
                        patch.object(bridge, "_trusted_code"),
                        patch.object(bridge, "_materialize", return_value={}),
                        patch.object(bridge, "_regrade", return_value=[])]
        self.mocks = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def call(self):
        return bridge.retained_reports(self.api, 7, 10, trusted_repo=Path("."),
                                       renderer_revision="e" * 40, now=100)

    def test_authenticated_source_read_only_and_separate_renderer(self):
        result = self.call()
        self.assertEqual(result["plan"], self.plan)
        self.assertEqual(result["renderer_revision"], "e" * 40)
        self.assertEqual(self.api.writes, [])
        self.mocks[0].assert_called_once_with(self.api, self.plan)
        self.mocks[1].assert_called_once()

    def test_bad_source_identity_fails_before_verifier(self):
        fields = {"id": 11, "run_attempt": 2, "path": "untrusted.yml",
                  "event": "pull_request", "status": "in_progress", "display_title": "other",
                  "head_sha": "f" * 40,
                  "repository": {"id": 999, "full_name": "example/untrusted"}}
        for name, value in fields.items():
            old = self.api.run[name]
            self.api.run[name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.call()
            self.api.run[name] = old
        self.mocks[1].assert_not_called()
        self.assertEqual(self.api.writes, [])

    def test_stale_and_ledger_mismatch(self):
        self.api.current["head"] = "f" * 40
        with self.assertRaises(ValueError):
            self.call()
        self.api.current["head"] = self.plan["head"]
        for source in (None, 11):
            self.mocks[0].return_value = source
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.call()
        self.mocks[0].side_effect = ValueError("ambiguous ledger")
        with self.assertRaises(ValueError):
            self.call()
        self.mocks[1].assert_not_called()

    def test_expired_plan_and_results(self):
        for artifact in (self.api.plan_artifact, self.api.artifact):
            artifact["expired"] = True
            with self.assertRaises(ValueError):
                self.call()
            artifact["expired"] = False
        self.mocks[1].assert_not_called()

    def test_missing_source_plan(self):
        self.api.plan_artifact = None
        with self.assertRaises(ValueError):
            self.call()
        self.mocks[1].assert_not_called()


if __name__ == "__main__":
    unittest.main()
