"""Generate knowledge abstracts for the categorized, packaged skill library.

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

from inferrsi.skill_catalog import skill_metadata, skill_records

PROJECT = Path(__file__).resolve().parents[1]
LIBRARY = Path("src/inferrsi/data/skill_library")
DESTINATION = Path("src/inferrsi/data/repo_packs/inferrsi/knowledge")
REPOSITORY = "https://github.com/InferMatrixLab/InferRSI"


def _git(project: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(project), *args], check=True, capture_output=True
    ).stdout


def _source_hashes(project: Path, revision: str, paths: set[str]) -> dict[str, str]:
    ordered = sorted(paths)
    requests = "".join(f"{revision}:{path}\n" for path in ordered).encode("utf-8")
    completed = subprocess.run(
        ["git", "-C", str(project), "cat-file", "--batch"],
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
    prefixes = tuple(f"{LIBRARY.as_posix()}/{item['path']}/" for item in entries.values())
    tracked = _git(project, "ls-tree", "-r", "--name-only", revision, "--", str(LIBRARY))
    pinned_inputs = {
        path for path in tracked.decode().splitlines()
        if path.startswith(prefixes) or path == f"{LIBRARY.as_posix()}/skill-index.json"
    }
    if inputs != pinned_inputs:
        raise ValueError("Skill input paths differ from the source revision; commit sources first")
    if _git(project, "diff", "--name-only", revision, "--", *sorted(inputs)):
        raise ValueError("Skill inputs differ from the source revision; commit sources first")
    source_files = _source_hashes(project, revision, inputs)
    return render_index(root, revision, source_files)


def _registry(root: Path) -> dict:
    # The catalog validates IDs, paths and metadata before the generator uses them.
    skill_records(root)
    return json.loads((root / "skill-index.json").read_text(encoding="utf-8"))["skills"]


def source_inputs(root: Path) -> set[str]:
    """All registered bodies/resources plus the registry that assigns their scopes."""
    return {f"{LIBRARY.as_posix()}/skill-index.json"} | {
        f"{LIBRARY.as_posix()}/{path.relative_to(root).as_posix()}"
        for item in _registry(root).values()
        for path in (root / item["path"]).rglob("*") if path.is_file()
    }


def render_index(
    root: Path, revision: str | dict[str, str], source_files: dict[str, str]
) -> dict[str, str]:
    """Render the projection without requiring historical Git objects."""
    outputs = {}
    links = []
    entries = _registry(root)
    for selected in skill_records(root):
        name = selected["name"]
        source_revision = revision[name] if isinstance(revision, dict) else revision
        metadata = skill_metadata(root, name)
        backend = entries[name]["backend"]
        directory = f"{LIBRARY.as_posix()}/{entries[name]['path']}"
        hashes = {
            path: digest for path, digest in sorted(source_files.items())
            if path.startswith(f"{directory}/")
            or path == f"{LIBRARY.as_posix()}/skill-index.json"
        }
        paths = list(hashes)
        entry = f"{directory}/SKILL.md"
        state = metadata.get("status", "unspecified")
        record = {
            "schema_version": 1,
            "id": f"inferrsi.{backend}.skills.{name.replace('-', '_')}",
            "title": name,
            "repo": "inferrsi",
            "tier": "contribution",
            "backend": backend,
            "component": "skills",
            "scenario": "skills.discovery",
            "status": "imported",
            "summary": metadata["description"],
            "tags": metadata.get("tags", []),
            "origin": metadata.get("origin", ["unknown"]),
            "sources": [{
                "type": "git",
                "url": f"{REPOSITORY}/blob/{source_revision}/{entry}",
                "commit": source_revision,
                "paths": paths,
                "content_sha256": hashes[entry],
            }],
            "index_type": "packaged-skill",
            "skill_documents": {
                "original": f"data/skill_library/{entries[name]['path']}/SKILL.md",
            },
            "checkout_ref": f"checkout:{name}",
            "source_files": hashes,
            "skill_metadata": metadata,
            "applicability": metadata.get("applicability", {}),
            "recommendations": [
                "Read the pinned SKILL.md and its prerequisites before choosing this procedure.",
                "Read the packaged references and owner-local cases alongside the procedure.",
            ],
            "limitations": [
                "This generated abstract points to the complete packaged skill; "
                "external evidence and upstream repositories remain source links.",
                "The imported status describes this index, not the original skill; "
                f"its declared status is {state}.",
                "Reading or indexing does not authorize execution, validate efficacy, "
                "promote a candidate or grant a license.",
                "The backend categorizes the procedure's hardware dependency; it does not "
                "certify compatibility, and skills.discovery is a discovery scenario.",
                *metadata.get("limitations", []),
            ],
            "verification": {"locally_verified": False, "evidence_level": "guidance"},
        }
        relative = f"{backend}/skills/{name}.json"
        outputs[relative] = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        links.append(f"| [{name}]({relative}) | {backend} | {state} |")
    outputs["README.md"] = "\n".join([
        "# InferRSI skill discovery index", "",
        f"Generated abstracts for all {len(entries)} registered skills in `data/skill_library/`.",
        "Their complete procedures, references and cases ship in the same package.",
        "`skill-index.json` maps stable skill IDs to categorized directories. The",
        "reference and searchspace matrices",
        "remain the maintained knowledge views. Do not edit generated files by hand.", "",
        "Index status `imported` and `locally_verified: false` describe these discovery",
        "records. Original status, provenance, license declarations and limitations",
        "are preserved under `skill_metadata`; absent fields remain absent. Unknown",
        "licenses remain unknown. Indexing grants no execution permission or validation.", "",
        "These are knowledge abstracts (`--kind knowledge`), with namespaced package",
        "IDs distinct from explicitly selected `checkout_ref` skills. Ascend/CUDA",
        "procedures use their corresponding backend; shared methods use `common`.", "",
        "Each record retains its own source snapshot in `sources`; unchanged skills",
        "can keep their existing provenance when another skill is updated.", "",
        "```bash",
        "inferrsi knowledge search 'profiling' --repo-type inferrsi --limit 50",
        "inferrsi collect --repo-type inferrsi --kind knowledge --limit 50 --material",
        "```", "",
        "After committing changes to skill bodies, resources or the registry, regenerate from a",
        "development installation with the skills extra. The source revision must",
        "contain the current input paths and bytes (Git checkout filters are respected).",
        "`source_files` hashes identify the canonical Git bytes, not a validation result.", "",
        "```bash",
        "python tools/build_skill_index.py --source-revision <committed-source-revision>",
        "# Update or check one skill without repinning unrelated records:",
        "python tools/build_skill_index.py --source-revision <committed-source-revision> "
        "--skill <skill-name>",
        "python tools/build_skill_index.py --source-revision <committed-source-revision> "
        "--skill <skill-name> --check",
        "```", "",
        "`--check` detects missing, stale and unexpected generated records without writing.",
        "With `--skill`, only that record and the shared navigation are updated/checked.",
        "References and cases ship with their owning skill, not as duplicate knowledge abstracts.",
        "",
        "| Skill | Backend | Original declared status |", "| --- | --- | --- |", *links, "",
    ])
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--skill", help="Update/check only this registered skill and navigation")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    outputs = build_index(PROJECT, args.source_revision)
    destination = PROJECT / DESTINATION
    existing = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*") if path.is_file()
    }
    stale = existing - outputs.keys()
    if args.skill is not None:
        entry = _registry(PROJECT / LIBRARY).get(args.skill)
        if entry is None:
            parser.error(f"Unknown registered skill: {args.skill}")
        selected = f"{entry['backend']}/skills/{args.skill}.json"
        outputs = {path: outputs[path] for path in (selected, "README.md")}
        stale = {path for path in stale if path.endswith(f"/skills/{args.skill}.json")}
    changed = [
        path for path, content in outputs.items()
        if not (destination / path).is_file()
        or (destination / path).read_text(encoding="utf-8") != content
    ]
    if args.check:
        if stale or changed:
            print("Skill index drift: " + ", ".join(sorted(stale | set(changed))))
            return 1
        print(f"Skill index is current: {len(outputs) - 1} metadata records")
        return 0
    if stale:
        raise ValueError("Remove obsolete generated files explicitly: " + ", ".join(sorted(stale)))
    for relative in changed:
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(outputs[relative], encoding="utf-8", newline="\n")
    print(f"Generated {len(outputs) - 1} skill metadata records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
