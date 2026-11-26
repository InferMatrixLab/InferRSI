"""Evidence path rules and directory creation are separate modules (#451 C2).

``inferrsi.contracts.evidence`` builds paths and never touches the filesystem.
``inferrsi.apps.storage.evidence_layout`` is the one place that calls ``mkdir``. Root
``inferrsi.evidence_paths`` is retired without an alias.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from inferrsi.apps.storage import evidence_layout
from inferrsi.apps.storage.evidence_layout import ensure_evidence_layout
from inferrsi.contracts import evidence
from inferrsi.contracts.evidence import (
    EVIDENCE_SEGMENTS,
    campaign_evidence_root,
    evidence_subpaths,
)

SRC = Path(__file__).resolve().parents[2] / "src"
ROOT = SRC / "inferrsi"
RETIRED = "inferrsi.evidence_paths"
# Path rules run first and must emit nothing; directory creation runs second under the
# same hook and must be seen, so a silent hook cannot make the first half pass.
AUDIT = """
import json, sys
from pathlib import Path
from inferrsi.apps.storage.evidence_layout import ensure_evidence_layout
from inferrsi.contracts.evidence import campaign_evidence_root, evidence_subpaths
IO_EVENTS = ("os.", "shutil.", "pathlib.", "tempfile.", "glob.", "subprocess.", "socket.")
seen = {"rules": [], "layout": []}
active = []
def hook(event, args):
    if active and (event == "open" or event.startswith(IO_EVENTS)):
        seen[active[0]].append(event)
sys.addaudithook(hook)
base = Path(sys.argv[1])
active[:] = ["rules"]
root = campaign_evidence_root(base, "demo")
paths = evidence_subpaths(root)
relative = evidence_subpaths(campaign_evidence_root(Path("."), "demo"))
active[:] = ["layout"]
made = ensure_evidence_layout(root)
active.clear()
print(json.dumps({
    "seen": seen, "same": made == paths,
    "relative": [path.as_posix() for path in relative.values()],
}))
"""


def _reference(root: Path) -> dict[str, Path]:
    """The body of the retired ``evidence_paths.ensure_evidence_layout``, verbatim."""
    paths = {name: root / name for name in EVIDENCE_SEGMENTS}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def _tree(base: Path) -> list[str]:
    return sorted(
        path.relative_to(base).as_posix() + ("/" if path.is_dir() else "")
        for path in base.rglob("*")
    )


def test_segments_and_subpaths_are_unchanged(tmp_path: Path) -> None:
    assert EVIDENCE_SEGMENTS == ("plan", "results", "patch", "validator")
    assert type(EVIDENCE_SEGMENTS) is tuple
    root = campaign_evidence_root(tmp_path, "demo-campaign")
    assert root == tmp_path / "evidence" / "demo-campaign"
    paths = evidence_subpaths(root)
    assert type(paths) is dict
    assert list(paths) == list(EVIDENCE_SEGMENTS)
    assert paths == {name: root / name for name in EVIDENCE_SEGMENTS}
    # Each call builds a new mapping; nothing is cached or shared.
    assert evidence_subpaths(root) is not paths


@pytest.mark.parametrize(
    "repo_root,campaign_id",
    [
        (Path("repo"), "demo"),
        (Path("."), "demo"),
        (Path("a/b"), "nested/campaign"),
        (Path("repo"), PurePosixPath("as/pathlike")),
        (PurePosixPath("/srv/repo"), "demo"),
        (PureWindowsPath("C:/repo"), "demo"),
        # No validation is added: an absolute campaign id still replaces the root.
        (PurePosixPath("repo"), "/absolute"),
    ],
    ids=str,
)
def test_path_rules_keep_relative_pure_and_pathlike_inputs(repo_root, campaign_id) -> None:
    expected = repo_root / "evidence" / campaign_id
    root = campaign_evidence_root(repo_root, campaign_id)
    assert root == expected and type(root) is type(expected)
    # A relative root stays relative: nothing is resolved against the working directory.
    assert root.is_absolute() == expected.is_absolute()
    paths = evidence_subpaths(root)
    assert paths == {name: expected / name for name in EVIDENCE_SEGMENTS}
    assert {type(path) for path in paths.values()} == {type(expected)}


def test_path_rules_add_no_coercion() -> None:
    # A string root was never coerced to a Path: the join itself raises, as before.
    with pytest.raises(TypeError):
        campaign_evidence_root("repo", "demo")
    with pytest.raises(TypeError):
        evidence_subpaths("evidence/demo")
    with pytest.raises(TypeError):
        campaign_evidence_root(Path("repo"), 7)
    with pytest.raises(TypeError):
        campaign_evidence_root(Path("repo"), None)
    # Directory creation fails at the same stage, before any mkdir.
    with pytest.raises(TypeError):
        ensure_evidence_layout("evidence/demo")


def test_path_rules_create_nothing(tmp_path: Path) -> None:
    root = campaign_evidence_root(tmp_path, "never-created")
    paths = evidence_subpaths(root)
    assert _tree(tmp_path) == []
    assert not root.exists() and not any(path.exists() for path in paths.values())


def test_path_rules_emit_no_filesystem_event_and_directory_creation_does(tmp_path: Path) -> None:
    environment = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run(
        [sys.executable, "-c", AUDIT, str(tmp_path)], capture_output=True, text=True,
        encoding="utf-8", env=environment, cwd=tmp_path, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["seen"]["rules"] == []
    # Positive control: the same hook saw the Apps half create directories.
    assert "os.mkdir" in payload["seen"]["layout"]
    assert payload["same"] is True
    assert payload["relative"] == [f"evidence/demo/{name}" for name in EVIDENCE_SEGMENTS]
    assert _tree(tmp_path) == ["evidence/", "evidence/demo/"] + sorted(
        f"evidence/demo/{name}/" for name in EVIDENCE_SEGMENTS
    )


def test_contracts_evidence_source_holds_no_call_and_no_io_import() -> None:
    tree = ast.parse((ROOT / "contracts" / "evidence.py").read_text(encoding="utf-8"))
    # Path joins only: with no call expression the module cannot mkdir, stat or open.
    assert [node for node in ast.walk(tree) if isinstance(node, ast.Call)] == []
    imports = [
        (node.module, [alias.name for alias in node.names])
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    assert imports == [("__future__", ["annotations"]), ("pathlib", ["Path"])]
    assert [node for node in ast.walk(tree) if isinstance(node, ast.Import)] == []
    assert sorted(name for name in vars(evidence) if not name.startswith("_")) == [
        "EVIDENCE_SEGMENTS", "Path", "annotations", "campaign_evidence_root", "evidence_subpaths",
    ]
    assert not hasattr(evidence, "ensure_evidence_layout")


def test_mkdir_lives_only_in_the_apps_module() -> None:
    def mkdir_calls(path: Path) -> list[ast.Call]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"mkdir", "makedirs"}
        ]

    for path in sorted((ROOT / "contracts").glob("*.py")):
        assert mkdir_calls(path) == [], path.name
    calls = mkdir_calls(ROOT / "apps" / "storage" / "evidence_layout.py")
    assert len(calls) == 1 and calls[0].args == []
    assert {key.arg: key.value.value for key in calls[0].keywords} == {
        "parents": True, "exist_ok": True,
    }
    # The Apps module reuses the canonical rule; it holds no second copy of the segments.
    assert evidence_layout.evidence_subpaths is evidence_subpaths
    assert not hasattr(evidence_layout, "EVIDENCE_SEGMENTS")


def test_ensure_layout_creates_exactly_four_directories_and_returns_the_map(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence" / "x"
    paths = ensure_evidence_layout(root)
    assert type(paths) is dict and list(paths) == list(EVIDENCE_SEGMENTS)
    assert paths == evidence_subpaths(root)
    assert all(path.is_dir() for path in paths.values())
    assert sorted(child.name for child in root.iterdir()) == sorted(EVIDENCE_SEGMENTS)
    # Missing parents are created; nothing else appears.
    assert _tree(tmp_path) == ["evidence/", "evidence/x/"] + sorted(
        f"evidence/x/{name}/" for name in EVIDENCE_SEGMENTS
    )


def test_ensure_layout_is_idempotent_and_keeps_existing_content(tmp_path: Path) -> None:
    root = tmp_path / "evidence" / "x"
    first = ensure_evidence_layout(root)
    (first["plan"] / "gates.md").write_text("frozen", encoding="utf-8")
    before = _tree(tmp_path)
    second = ensure_evidence_layout(root)
    assert second == first and second is not first
    assert _tree(tmp_path) == before
    assert (first["plan"] / "gates.md").read_text(encoding="utf-8") == "frozen"


def test_ensure_layout_keeps_a_relative_root_relative(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    paths = ensure_evidence_layout(Path("evidence") / "relative")
    assert paths == {name: Path("evidence") / "relative" / name for name in EVIDENCE_SEGMENTS}
    assert not any(path.is_absolute() for path in paths.values())
    assert all((tmp_path / path).is_dir() for path in paths.values())


@pytest.mark.parametrize("blocker", ["plan", "patch", "validator"])
def test_a_file_in_place_of_a_segment_fails_like_the_original_body(
    tmp_path: Path, blocker: str
) -> None:
    outcomes = []
    for label, function in (("reference", _reference), ("moved", ensure_evidence_layout)):
        root = tmp_path / label / "evidence" / "x"
        root.mkdir(parents=True)
        (root / blocker).write_text("not a directory", encoding="utf-8")
        with pytest.raises(OSError) as caught:
            function(root)
        outcomes.append((type(caught.value), caught.value.errno, _tree(tmp_path / label)))
        assert (root / blocker).read_text(encoding="utf-8") == "not a directory"
    assert outcomes[0] == outcomes[1]
    assert outcomes[1][0] is FileExistsError
    # Segments are created in order and a failure rolls nothing back.
    moved = tmp_path / "moved" / "evidence" / "x"
    created = [name for name in EVIDENCE_SEGMENTS if (moved / name).is_dir()]
    assert created == list(EVIDENCE_SEGMENTS[: EVIDENCE_SEGMENTS.index(blocker)])


def test_a_file_in_place_of_a_parent_fails_like_the_original_body(tmp_path: Path) -> None:
    outcomes = []
    for label, function in (("reference", _reference), ("moved", ensure_evidence_layout)):
        base = tmp_path / label
        base.mkdir()
        (base / "evidence").write_text("a file, not a directory", encoding="utf-8")
        with pytest.raises(OSError) as caught:
            function(base / "evidence" / "x")
        outcomes.append((type(caught.value), caught.value.errno, _tree(base)))
    # The exact OSError subclass is platform-specific; it is the same one as before.
    assert outcomes[0] == outcomes[1]
    assert outcomes[1][2] == ["evidence"]


def test_campaign_acceptance_template_lists_the_canonical_segments() -> None:
    # The acceptance form consumes the segment names. Its ``evidence_paths`` key is a
    # form field id, not the retired module path, and stays as it is.
    text = (SRC.parent / ".github" / "ISSUE_TEMPLATE" / "campaign-acceptance.yml").read_text(
        encoding="utf-8"
    )
    lines = [f"{name}: evidence/<campaign-id>/{name}/" for name in EVIDENCE_SEGMENTS]
    assert [line.strip() for line in text.splitlines() if line.strip() in lines] == lines
    assert ", ".join(f"`{name}/`" for name in EVIDENCE_SEGMENTS) in text
    assert "inferrsi." not in text


def test_retired_evidence_paths_module_has_no_alias() -> None:
    assert not (ROOT / "evidence_paths.py").exists()
    assert importlib.util.find_spec(RETIRED) is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(RETIRED)
    assert RETIRED not in sys.modules
    # A pickle that names a moved function by the retired module path no longer loads.
    for name in ("campaign_evidence_root", "evidence_subpaths", "ensure_evidence_layout"):
        with pytest.raises(ModuleNotFoundError):
            pickle.loads(f"c{RETIRED}\n{name}\n.".encode("ascii"))
    # New pickles name the canonical modules, and path values are plain data.
    assert b"inferrsi.contracts.evidence" in pickle.dumps(evidence_subpaths, protocol=0)
    assert pickle.loads(pickle.dumps(campaign_evidence_root)) is campaign_evidence_root
    assert b"inferrsi.apps.storage.evidence_layout" in pickle.dumps(
        ensure_evidence_layout, protocol=0
    )
    assert pickle.loads(pickle.dumps(ensure_evidence_layout)) is ensure_evidence_layout
    assert b"inferrsi" not in pickle.dumps(EVIDENCE_SEGMENTS, protocol=0)
    assert b"inferrsi" not in pickle.dumps(evidence_subpaths(Path("root")), protocol=0)
