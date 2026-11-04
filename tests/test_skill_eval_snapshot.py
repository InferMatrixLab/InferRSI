import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from inferrsi.knowledge_operations import KnowledgeReader
from tools.skill_eval_compare import snapshot
from tools.skill_eval_snapshot import selected_snapshot


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo).decode().strip()


def fixture(repo, *, indexed=True):
    git(repo, "init", "-q")
    root = repo / "library"
    directory = root / ("methods/selected" if indexed else "selected")
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: selected\ndescription: Synthetic test skill\n---\nRead resources.\n")
    (directory / "metadata.json").write_text(json.dumps({"references": ["../shared/ref.md"]}))
    (directory / "resource.bin").write_bytes(b"\x00\xff\r\n")
    (directory / "__pycache__").mkdir()
    (directory / "__pycache__/retained.pyc").write_bytes(b"incidental")
    shared = directory.parent / "shared"
    shared.mkdir()
    (shared / "ref.md").write_bytes(b"reference\r\n")
    unrelated = root / "unrelated"
    unrelated.mkdir()
    (unrelated / "run.sh").write_text("not executed\n")
    if indexed:
        (root / "skill-index.json").write_text(json.dumps({"schema_version": 1, "skills": {
            "selected": {"path": "methods/selected", "backend": "common"}}}))
    git(repo, "add", ".")
    git(repo, "update-index", "--chmod=+x", "library/unrelated/run.sh")
    return commit(repo), directory


def commit(repo):
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "-c", "core.hooksPath=/dev/null", "commit", "-qm", "synthetic fixture")
    return git(repo, "rev-parse", "HEAD")


class SelectedSnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_complete_closure_raw_bytes_and_original_guard(self):
        tmp_path = self.root
        for indexed in [True, False]:
            with self.subTest(indexed=indexed), tempfile.TemporaryDirectory() as temporary:
                tmp_path = Path(temporary)
                repo = tmp_path / "repo"
                repo.mkdir()
                revision, directory = fixture(repo, indexed=indexed)
                result = selected_snapshot(repo, revision, "library", "selected", tmp_path / "out")
                relative = directory.relative_to(repo).as_posix()
                assert result["entries"][relative + "/resource.bin"]["sha256"] == hashlib.sha256(
                    b"\x00\xff\r\n").hexdigest()
                incidental = tmp_path / "out" / relative / "__pycache__/retained.pyc"
                assert incidental.read_bytes() == b"incidental"
                bundle = KnowledgeReader(skill_root=result["root"]).read("checkout:selected")
                assert bundle.revision == result["bundle_revision"]
                assert any(data == b"reference\r\n" for data in bundle.content.values())
                assert all("unrelated" not in path for path in result["entries"])
                if indexed:
                    projected = result["projected_index"]
                    assert projected["source_git_blob"] == git(
                        repo, "rev-parse", revision + ":library/skill-index.json")
                    assert projected["sha256"] == hashlib.sha256(
                        (result["root"] / "skill-index.json").read_bytes()).hexdigest()
                with self.assertRaisesRegex(ValueError, "Executable"):
                    snapshot(repo, revision, "library", tmp_path / "all")

    def test_reject_executable_anywhere_in_closure(self):
        tmp_path = self.root
        for target in ["methods/selected/resource.bin", "methods/shared/ref.md",
                       "methods/selected/__pycache__/retained.pyc"]:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                tmp_path = Path(temporary)
                revision, _ = fixture(tmp_path)
                git(tmp_path, "update-index", "--chmod=+x", "library/" + target)
                revision = commit(tmp_path)
                with self.assertRaisesRegex(ValueError, "executable"):
                    selected_snapshot(tmp_path, revision, "library", "selected", tmp_path / "out")
                assert not (tmp_path / "out").exists()

    def test_bad_reference_fails_without_partial_output(self):
        tmp_path = self.root
        for reference in ["../../../escape", "../shared/missing", "/absolute",
                          "..\\shared\\ref.md", "../../skill-index.json"]:
            with self.subTest(reference=reference), tempfile.TemporaryDirectory() as temporary:
                tmp_path = Path(temporary)
                _, directory = fixture(tmp_path)
                (directory / "metadata.json").write_text(json.dumps({"references": [reference]}))
                git(tmp_path, "add", ".")
                revision = commit(tmp_path)
                with self.assertRaisesRegex(ValueError, ""):
                    selected_snapshot(tmp_path, revision, "library", "selected", tmp_path / "out")
                assert not (tmp_path / "out").exists()

    def test_symlink_and_submodule_rejected(self):
        tmp_path = self.root
        _, directory = fixture(tmp_path)
        target = directory / "link"
        target.symlink_to("resource.bin")
        git(tmp_path, "add", ".")
        revision = commit(tmp_path)
        with self.assertRaisesRegex(ValueError, "symlink"):
            selected_snapshot(tmp_path, revision, "library", "selected", tmp_path / "out")
        target.unlink()
        git(tmp_path, "add", "-u")
        git(tmp_path, "update-index", "--add", "--cacheinfo", "160000," + revision
            + ",library/methods/selected/submodule")
        revision = commit(tmp_path)
        with self.assertRaisesRegex(ValueError, "submodule"):
            selected_snapshot(tmp_path, revision, "library", "selected", tmp_path / "out")

    def test_index_traversal_alias_rejected(self):
        tmp_path = self.root
        for path in ['methods/../methods/selected', 'methods/selected.']:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                tmp_path = Path(temporary)
                fixture(tmp_path)
                (tmp_path / "library/skill-index.json").write_text(json.dumps({"schema_version": 1,
                    "skills": {"selected": {"path": path, "backend": "common"}}}))
                git(tmp_path, "add", ".")
                revision = commit(tmp_path)
                with self.assertRaisesRegex(ValueError, ""):
                    selected_snapshot(tmp_path, revision, "library", "selected", tmp_path / "out")

    def test_duplicate_index_fields_rejected(self):
        tmp_path = self.root
        fixture(tmp_path)
        (tmp_path / "library/skill-index.json").write_text(
            '{"schema_version":1,"skills":{},"skills":{}}')
        git(tmp_path, "add", ".")
        revision = commit(tmp_path)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            selected_snapshot(tmp_path, revision, "library", "selected", tmp_path / "out")

    def test_directory_case_alias_rejected(self):
        tmp_path = self.root
        _, directory = fixture(tmp_path)
        (directory / "Assets").mkdir()
        (directory / "assets").mkdir()
        (directory / "Assets/a").write_text("a")
        (directory / "assets/b").write_text("b")
        git(tmp_path, "add", ".")
        revision = commit(tmp_path)
        with self.assertRaisesRegex(ValueError, "Aliased"):
            selected_snapshot(tmp_path, revision, "library", "selected", tmp_path / "out")

    def test_revision_and_destination_guard(self):
        tmp_path = self.root
        revision, _ = fixture(tmp_path)
        with self.assertRaisesRegex(ValueError, "immutable"):
            selected_snapshot(tmp_path, "HEAD", "library", "selected", tmp_path / "out")
        with self.assertRaisesRegex(ValueError, "destination"):
            selected_snapshot(tmp_path, revision, "library", "selected", tmp_path)
        with self.assertRaisesRegex(ValueError, "Revision"):
            selected_snapshot(tmp_path, revision, "library", "selected", tmp_path / "out",
                              bundle_revision="sha256:" + "0" * 64)
        assert not (tmp_path / "out").exists()


if __name__ == "__main__":
    unittest.main()
