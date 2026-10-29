"""Opt-in raw-Git selected checkout closure; not the whole-library audit snapshot.

Closure follows KnowledgeReader: every selected-directory resource and each
metadata-declared reference. Markdown navigation links are not dependencies.
The index is explicitly projected, never represented as an original Git blob.
"""

import hashlib
import json
import posixpath
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath

from inferrsi.catalog import BACKENDS
from inferrsi.knowledge_operations import KnowledgeReader, safe_path
from inferrsi.skill_catalog import _skill_name, _unique_fields, skill_metadata

GIT_READ = ("git", "--no-replace-objects", "--no-lazy-fetch")


def _path(value: str) -> str:
    safe_path(value)
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("Noncanonical Unicode snapshot path")
    # Reject filesystem aliases even when preparation happens on Linux.
    for part in value.split("/"):
        if part.endswith((".", " ")) or part.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }:
            raise ValueError(f"Aliased snapshot path: {value}")
    return value


def selected_snapshot(repo: Path, revision: str, skill_root: str, skill: str,
                      destination: Path, *, bundle_revision: str | None = None) -> dict:
    """Materialize a selected closure into a new destination, returning provenance.

    No checkout/filter execution, chmod, provider call, or network fetch is used.
    All selected Git entries must be ordinary non-executable blobs, including
    files the reader considers incidental. Failure publishes no destination.
    """
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Selected snapshot requires a full immutable Git commit SHA")
    _path(skill_root)
    _skill_name(skill)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Selected snapshot destination must not exist")
    version = subprocess.check_output(["git", "--version"], cwd=repo, text=True)
    match = re.match(r"git version (\d+)\.(\d+)", version)
    if match is None or tuple(map(int, match.groups())) < (2, 45):
        raise ValueError("Selected snapshot requires Git >= 2.45 for --no-lazy-fetch")
    if subprocess.check_output([*GIT_READ, "cat-file", "-t", revision],
                               cwd=repo).strip() != b"commit":
        raise ValueError("Selected snapshot revision must identify a Git commit")
    inventory = {}
    aliases = {}
    for entry in subprocess.check_output(
        [*GIT_READ, "ls-tree", "-rz", revision, "--", skill_root], cwd=repo,
    ).split(b"\0"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        mode, kind, digest = header.decode("ascii").split()
        path = _path(name.decode("utf-8"))
        if not path.startswith(skill_root + "/"):
            raise ValueError("Snapshot entry escapes skill root")
        parts = path.split("/")
        for end in range(1, len(parts) + 1):
            component = "/".join(parts[:end])
            key = component.casefold()
            if key in aliases and aliases[key] != component:
                raise ValueError("Aliased snapshot entries")
            aliases[key] = component
        inventory[path] = (mode, kind, digest)

    provenance = {}

    def read(path):
        if path not in inventory:
            raise ValueError(f"Missing selected snapshot resource: {path}")
        mode, kind, digest = inventory[path]
        if mode != "100644" or kind != "blob":
            raise ValueError(f"Selected executable, symlink or submodule is unsupported: {path}")
        data = subprocess.check_output([*GIT_READ, "cat-file", "blob", digest], cwd=repo)
        provenance[path] = {"mode": mode, "git_blob": digest,
                            "sha256": hashlib.sha256(data).hexdigest()}
        return data

    index_path = skill_root + "/skill-index.json"
    projection = None
    if index_path in inventory:
        original = read(index_path)
        index = json.loads(original, object_pairs_hook=_unique_fields)
        if (not isinstance(index, dict) or type(index.get("schema_version")) is not int
                or index["schema_version"] != 1 or not isinstance(index.get("skills"), dict)):
            raise ValueError("Invalid skill index")
        paths = set()
        for name, item in index["skills"].items():
            _skill_name(name)
            if (not isinstance(item, dict) or not isinstance(item.get("path"), str)
                    or item.get("backend") not in (*BACKENDS, "common")):
                raise ValueError("Invalid skill index entry")
            path = _path(item["path"])
            if PurePosixPath(path).name != name or path.casefold() in paths:
                raise ValueError("Duplicate or aliased skill index path")
            paths.add(path.casefold())
        if skill not in index["skills"]:
            raise ValueError(f"Unknown skill: {skill}")
        relative = index["skills"][skill]["path"]
        projection = json.dumps({**index, "skills": {skill: index["skills"][skill]}},
                                sort_keys=True).encode()
    else:
        relative = skill
    prefix = skill_root + "/" + relative
    selected = {path for path in inventory if path.startswith(prefix + "/")}
    if prefix + "/SKILL.md" not in selected:
        raise ValueError(f"Missing selected SKILL.md: {skill}")
    # Stage only in our own fresh directory; never follow caller-created children.
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="selected-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "snapshot"
        root = staging / skill_root

        def write(path, data):
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        for path in sorted(selected):
            write(path, read(path))
        if projection is not None:
            write(index_path, projection)
        metadata = skill_metadata(root, skill)
        for reference in metadata.get("references", []):
            if not reference or "\\" in reference or ":" in reference or reference.startswith("/"):
                raise ValueError("Reference must use a relative POSIX path")
            path = posixpath.normpath(prefix + "/" + reference)
            _path(path)
            if not path.startswith(skill_root + "/"):
                raise ValueError("Reference escapes skills root")
            if projection is not None and path == index_path:
                raise ValueError("Declared reference conflicts with projected index")
            # Missing leaf behind a symlink/submodule is rejected, never traversed.
            write(path, read(path))
        bundle = KnowledgeReader(skill_root=root).read("checkout:" + skill,
                                                       revision=bundle_revision)
        staging.rename(destination)
    return {"root": destination / skill_root, "git_revision": revision,
            "skill": skill, "bundle_revision": bundle.revision,
            "entries": dict(sorted(provenance.items())),
            "projected_index": None if projection is None else {
                "path": index_path, "source_git_blob": provenance[index_path]["git_blob"],
                "sha256": hashlib.sha256(projection).hexdigest(),
                "transformation": "existing skill index restricted to selected identity"},
            "closure_semantics": "selected directory plus metadata.references; navigation excluded"}
