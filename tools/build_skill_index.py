"""Generate packaged discovery metadata; skills/ remains the content authority.

Run from a development installation with the skills extra. The explicit source
revision must contain the indexed inputs; Git handles checkout newline filters.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from inferrsi.skill_catalog import skill_metadata, skill_records

PROJECT = Path(__file__).resolve().parents[1]
DESTINATION = Path("src/inferrsi/data/repo_packs/inferrsi/knowledge")
REPOSITORY = "https://github.com/InferMatrixLab/InferRSI"


def _git(project: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(project), *args], check=True, capture_output=True
    ).stdout


def build_index(project: Path, source_revision: str) -> dict[str, str]:
    revision = _git(project, "rev-parse", "--verify", f"{source_revision}^{{commit}}")
    revision = revision.decode().strip()
    root = project / "skills"
    names = [record["name"] for record in skill_records(root)]
    inputs = {
        f"skills/{name}/{filename}"
        for name in names
        for filename in ("SKILL.md", "metadata.json")
        if (root / name / filename).is_file()
    }
    tracked = _git(project, "ls-tree", "-r", "--name-only", revision, "--", "skills")
    pinned_inputs = {
        path for path in tracked.decode().splitlines()
        if len(Path(path).parts) == 3 and Path(path).name in ("SKILL.md", "metadata.json")
    }
    if inputs != pinned_inputs:
        raise ValueError("Skill input paths differ from the source revision; commit sources first")
    if _git(project, "diff", "--name-only", revision, "--", *sorted(inputs)):
        raise ValueError("Skill inputs differ from the source revision; commit sources first")
    source_files = {
        path: hashlib.sha256(_git(project, "show", f"{revision}:{path}")).hexdigest()
        for path in sorted(inputs)
    }
    return render_index(root, revision, source_files)


def render_index(root: Path, revision: str, source_files: dict[str, str]) -> dict[str, str]:
    """Render the projection without requiring historical Git objects."""
    outputs = {}
    links = []
    for selected in skill_records(root):
        name = selected["name"]
        metadata = skill_metadata(root, name)
        hashes = {
            path: digest for path, digest in sorted(source_files.items())
            if path.startswith(f"skills/{name}/")
        }
        paths = list(hashes)
        entry = f"skills/{name}/SKILL.md"
        state = metadata.get("status", "unspecified")
        record = {
            "schema_version": 1,
            "id": f"inferrsi.common.skills.{name.replace('-', '_')}",
            "title": name,
            "repo": "inferrsi",
            "tier": "contribution",
            "backend": "common",
            "component": "skills",
            "scenario": "skills.discovery",
            "status": "imported",
            "summary": metadata["description"],
            "tags": metadata.get("tags", []),
            "origin": metadata.get("origin", ["unknown"]),
            "sources": [{
                "type": "git",
                "url": f"{REPOSITORY}/blob/{revision}/{entry}",
                "commit": revision,
                "paths": paths,
                "content_sha256": hashes[entry],
            }],
            "index_type": "skill-metadata-only",
            "checkout_ref": f"checkout:{name}",
            "source_files": hashes,
            "skill_metadata": metadata,
            "applicability": metadata.get("applicability", {}),
            "recommendations": [
                "Read the pinned SKILL.md and its prerequisites before choosing this procedure.",
                "Use a complete source checkout for declared references and owner-local cases.",
            ],
            "limitations": [
                "This generated abstract indexes metadata only; procedure and resource "
                "bodies remain in the source checkout.",
                "The imported status describes this index, not the original skill; "
                f"its declared status is {state}.",
                "Reading or indexing does not authorize execution, validate efficacy, "
                "promote a candidate or grant a license.",
                "The common backend and skills.discovery scenario describe discovery only, "
                "not runtime compatibility.",
                *metadata.get("limitations", []),
            ],
            "verification": {"locally_verified": False, "evidence_level": "guidance"},
        }
        relative = f"common/skills/{name}.json"
        outputs[relative] = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        links.append(f"| [{name}]({relative}) | {state} |")
    outputs["README.md"] = "\n".join([
        "# InferRSI skill discovery index", "",
        "Generated metadata for every root `skills/` entry. The source procedures,",
        "references and cases remain authoritative in the checkout; their bodies",
        "are not redistributed by this index. The reference and searchspace matrices",
        "remain the maintained knowledge views. Do not edit generated files by hand.", "",
        "Index status `imported` and `locally_verified: false` describe these discovery",
        "records. Original status, provenance, license declarations and limitations",
        "are preserved under `skill_metadata`; absent fields remain absent. Unknown",
        "licenses remain unknown. Indexing grants no execution permission or validation.", "",
        "These are knowledge abstracts (`--kind knowledge`), with namespaced package",
        "IDs distinct from their `checkout_ref` skills. `common` and `skills.discovery`",
        "describe the index, not hardware or task applicability.", "",
        f"Source snapshot: [{revision}]({REPOSITORY}/tree/{revision}/skills).", "",
        "```bash",
        "inferrsi knowledge search 'profiling' --repo-type inferrsi --limit 50",
        "inferrsi collect --repo-type inferrsi --kind knowledge --limit 50 --material",
        "```", "",
        "After committing changes to skill headers or sidecars, regenerate from a",
        "development installation with the skills extra. The source revision must",
        "contain the current input paths and bytes (Git checkout filters are respected).",
        "`source_files` hashes identify the canonical Git bytes, not a validation result.", "",
        "```bash",
        "python tools/build_skill_index.py --source-revision <committed-source-revision>",
        f"python tools/build_skill_index.py --source-revision {revision} --check",
        "```", "",
        "`--check` detects missing, stale and unexpected generated records without writing.",
        "References and cases remain source links; they are not separate packaged entries.", "",
        "| Skill | Original declared status |", "| --- | --- |", *links, "",
    ])
    return outputs


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
