from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
# GitHub limits a label description to 100 characters.
MAX_DESCRIPTION = 100
NAME = re.compile(r"([a-z][a-z0-9-]*):([A-Za-z0-9][A-Za-z0-9._-]*)")

ADVICE = (
    "Change .github/labels.json in a PR first, then apply the change to the repository. "
    "See Labels in docs/agent-collaboration.md."
)


def manifest_problems(manifest: list[dict]) -> list[str]:
    problems = []
    for entry in manifest:
        name = entry.get("name")
        if set(entry) != {"name", "group", "description"}:
            problems.append(f"{name}: expected exactly name, group and description")
            continue
        match = NAME.fullmatch(name) if isinstance(name, str) else None
        if match is None or match.group(1) != entry["group"]:
            problems.append(f"{name}: name must have the form <group>:<value> for its group")
        description = entry["description"]
        if not isinstance(description, str) or not 0 < len(description) <= MAX_DESCRIPTION:
            problems.append(f"{name}: description must have 1-{MAX_DESCRIPTION} characters")
    names = [entry.get("name") for entry in manifest]
    problems += [f"{name}: listed more than once"
                 for name in sorted({name for name in names if names.count(name) > 1}, key=str)]
    return problems


def external_problems(external: list[dict], manifest: list[dict]) -> list[str]:
    problems = []
    names = []
    for entry in external:
        name = entry.get("name")
        if set(entry) != {"name", "owner"}:
            problems.append(f"{name}: expected exactly name and owner")
            continue
        # Only a usable name joins the duplicate and overlap comparisons below.
        if isinstance(name, str) and name:
            names.append(name)
        else:
            problems.append(f"{name}: name must be a nonempty string")
        if not isinstance(entry["owner"], str) or not entry["owner"].strip():
            problems.append(f"{name}: owner must name the app that applies it")
    problems += [f"{name}: listed more than once"
                 for name in sorted({n for n in names if names.count(n) > 1})]
    listed = {e["name"] for e in manifest if isinstance(e.get("name"), str)}
    problems += [f"{name}: external labels cannot also be in labels.json"
                 for name in sorted(set(names) & listed)]
    return problems


def _names(value, source: str) -> list[str]:
    # GitHub accepts a list of names or one comma-separated string in templates.
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError(f"{source}: labels must be a list of names or a comma-separated string")


def referenced_labels(root: Path) -> dict[str, list[str]]:
    references = {}
    for path in sorted((root / ".github/ISSUE_TEMPLATE").iterdir()):
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".md":
            lines = text.splitlines()
            # Markdown templates carry their settings in leading front matter.
            if not lines or lines[0] != "---":
                raise ValueError(f"{path.name}: issue template lacks front matter")
            text = "\n".join(lines[1:lines.index("---", 1)])
        elif path.suffix not in (".yml", ".yaml"):
            continue
        names = _names((yaml.safe_load(text) or {}).get("labels"), path.name)
        if names:
            references[path.relative_to(root).as_posix()] = names
    for path in sorted((root / "tools").glob("skill_eval_*_config.json")):
        config = json.loads(path.read_text(encoding="utf-8"))
        if "label" in config:
            references[path.relative_to(root).as_posix()] = [config["label"]]
    return references


def drift(manifest: list[dict], repository: list[dict],
          references: dict[str, list[str]], external: set[str]) -> list[str]:
    expected = {entry["name"]: entry["description"] for entry in manifest}
    # The labels API returns null for a label without a description.
    actual = {label["name"]: label["description"] or "" for label in repository}
    problems = [f"{name}: in labels.json, missing from the repository"
                for name in sorted(expected.keys() - actual.keys())]
    problems += [f"{name}: in the repository, missing from labels.json"
                 for name in sorted(actual.keys() - expected.keys() - external)]
    problems += [f"{name}: repository description differs from labels.json"
                 for name in sorted(expected.keys() & actual.keys())
                 if expected[name] != actual[name]]
    problems += [f"{name}: referenced by {source}, missing from labels.json"
                 for source, names in references.items() for name in names
                 if name not in expected]
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report label drift without changing labels.")
    parser.add_argument("repository_labels", type=Path,
                        help="JSON lines holding each repository label's name and description")
    args = parser.parse_args(argv)
    manifest = json.loads((ROOT / ".github/labels.json").read_text(encoding="utf-8"))
    external = json.loads((ROOT / ".github/external-labels.json").read_text(encoding="utf-8"))
    repository = [json.loads(line) for line in
                  args.repository_labels.read_text(encoding="utf-8").splitlines() if line.strip()]
    problems = manifest_problems(manifest) + external_problems(external, manifest)
    if not problems:
        problems = drift(manifest, repository, referenced_labels(ROOT),
                         {entry["name"] for entry in external})
    # Each printed line starts with "label drift" so a label name cannot form a workflow command.
    for problem in problems:
        print(f"label drift: {problem}")
    if problems:
        print(ADVICE)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
