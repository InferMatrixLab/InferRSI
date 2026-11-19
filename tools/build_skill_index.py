"""Compile offline catalog inputs from the registered skill library.

Run from a development installation with the skills extra. The explicit source
revision must contain the indexed inputs; Git handles checkout newline filters.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
from pathlib import Path

from inferrsi.knowledge import _source_snapshot
from inferrsi.knowledge.catalog import COMPILED, INPUTS
from inferrsi.knowledge.skill_catalog import _frontmatter, skill_records

PROJECT = Path(__file__).resolve().parents[1]
# The runtime reads these build products alongside the canonical owners.
LIBRARY = Path("src/inferrsi/knowledge/data/skill_library")
DESTINATION = LIBRARY / COMPILED
# How those inputs are named at the pinned source revision. After the explicit
# K02 re-pin this agrees with LIBRARY, the current checkout path.
PINNED_LIBRARY = Path(_source_snapshot.LIBRARY)
REPOSITORY = _source_snapshot.REPOSITORY
# Match the comparison tool: replacement refs and lazy promisor fetches must not
# change the bytes hashed for a pinned revision.
GIT_READ = ("git", "--no-replace-objects", "--no-lazy-fetch")


def _git(project: Path, *args: str) -> bytes:
    return subprocess.run(
        [*GIT_READ, "-C", str(project), *args], check=True, capture_output=True
    ).stdout


def _source_hashes(project: Path, revision: str, paths: set[str]) -> dict[str, str]:
    ordered = sorted(paths)
    requests = "".join(f"{revision}:{path}\n" for path in ordered).encode("utf-8")
    completed = subprocess.run(
        [*GIT_READ, "-C", str(project), "cat-file", "--batch"],
        input=requests, check=True, capture_output=True,
    )
    stream = io.BytesIO(completed.stdout)
    hashes = {}
    for path in ordered:
        _, kind, size = stream.readline().split()
        if kind != b"blob":
            raise ValueError(f"Skill source is not a Git blob: {path}")
        content = stream.read(int(size))
        if stream.read(1) != b"\n":
            raise ValueError(f"Invalid Git batch boundary for skill source: {path}")
        hashes[path] = hashlib.sha256(content).hexdigest()
    return hashes


def build_index(project: Path, source_revision: str) -> dict[str, str]:
    revision = _git(project, "rev-parse", "--verify", f"{source_revision}^{{commit}}")
    revision = revision.decode().strip()
    root = project / LIBRARY
    entries = _registry(root)
    inputs = source_inputs(root)
    prefixes = tuple(
        f"{PINNED_LIBRARY.as_posix()}/{item['path']}/" for item in entries.values()
    )
    tracked = _git(
        project, "ls-tree", "-r", "--name-only", revision, "--", str(PINNED_LIBRARY)
    )
    pinned_inputs = {
        path for path in tracked.decode().splitlines()
        if path.startswith(prefixes)
        or path == f"{PINNED_LIBRARY.as_posix()}/skill-index.json"
    }
    if inputs != pinned_inputs:
        raise ValueError("Skill input paths differ from the source revision; commit sources first")
    # Compare the whole tree diff and intersect locally: passing several hundred
    # paths on the command line exceeds the Windows process-argument limit.
    dirty = set(
        _git(project, "diff", "--name-only", revision).decode("utf-8").splitlines()
    )
    if dirty & inputs:
        raise ValueError("Skill inputs differ from the source revision; commit sources first")
    source_files = _source_hashes(project, revision, inputs)
    return render_index(root, revision, source_files)


def _registry(root: Path) -> dict:
    # The catalog validates IDs, paths and metadata before the generator uses them.
    skill_records(root)
    return json.loads((root / "skill-index.json").read_text(encoding="utf-8"))["skills"]


def source_inputs(root: Path) -> set[str]:
    """All registered bodies/resources plus the registry that assigns their scopes."""
    return {f"{PINNED_LIBRARY.as_posix()}/skill-index.json"} | {
        f"{PINNED_LIBRARY.as_posix()}/{path.relative_to(root).as_posix()}"
        for item in _registry(root).values()
        for path in (root / item["path"]).rglob("*") if path.is_file()
    }


def render_index(root: Path, revision: str, source_files: dict[str, str]) -> dict[str, str]:
    """Compile only the YAML header and Git fingerprints required by the base install."""
    owners = {}
    for name, registration in _registry(root).items():
        directory = registration["path"]
        prefix = f"{PINNED_LIBRARY.as_posix()}/{directory}/"
        with (root / directory / "SKILL.md").open("rb") as stream:
            header = _frontmatter(stream)
        owners[name] = {
            "header": header,
            "files": {p[len(prefix):]: digest for p, digest in sorted(source_files.items())
                      if p.startswith(prefix)},
        }
    snapshot = _source_snapshot.manifest(revision, source_files[_source_snapshot.REGISTRY])
    return {name: json.dumps(obj, ensure_ascii=False, indent=2) + "\n" for name, obj in (
        (_source_snapshot.MANIFEST, snapshot), (INPUTS, owners),
    )}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    outputs = build_index(PROJECT, args.source_revision)
    destination = PROJECT / DESTINATION
    existing = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*") if path.is_file()
    }
    stale = existing - outputs.keys()
    changed = [
        path for path, content in outputs.items()
        if not (destination / path).is_file()
        or (destination / path).read_bytes() != content.encode("utf-8")
    ]
    if args.check:
        if stale or changed:
            print("Skill index drift: " + ", ".join(sorted(stale | set(changed))))
            return 1
        print("Compiled catalog inputs match the registered skills")
        return 0
    if stale:
        raise ValueError("Remove obsolete generated files explicitly: " + ", ".join(sorted(stale)))
    for relative in changed:
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(outputs[relative], encoding="utf-8", newline="\n")
    print("Wrote compiled catalog inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
