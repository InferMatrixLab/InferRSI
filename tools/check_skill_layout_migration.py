"""Validate two materialized source trees. This filesystem-only check does not invoke Git."""

import argparse
import csv
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
LIBRARY = Path("src/inferrsi/knowledge/data/skill_library")
sys.path.insert(0, str(PROJECT / "src"))

from inferrsi.knowledge.knowledge_operations import KnowledgeReader, RevisionConflict  # noqa: E402
from inferrsi.knowledge.skill_catalog import skill_registrations  # noqa: E402


def verify_snapshot(checkout, rows, side):
    root = (checkout / LIBRARY).resolve()
    reader = KnowledgeReader(skill_root=root)
    locations = {
        name: ("skill", directory.relative_to(root).as_posix())
        for name, (directory, _) in skill_registrations(root).items()
    }
    locations.update({
        name: ("case", path.relative_to(root).as_posix()) for name, path in reader.cases().items()
    })
    expected = {
        row["stable_id"]: (row["kind"], row[f"{side}_path"])
        for row in rows if row[f"{side}_path"]
    }
    if locations != expected:
        mismatches = [name for name in locations.keys() | expected.keys()
                      if locations.get(name) != expected.get(name)]
        raise ValueError(f"{side}: identity or path disagreement: {sorted(mismatches)}")

    rejections = 0
    for row in rows:
        path = row[f"{side}_path"]
        if not path:
            continue
        ref = "checkout:" + row["stable_id"]
        revision = row[f"{side}_checkout_revision"]
        if revision == "unavailable_at_cutover":
            try:
                reader.read(ref)
            except ValueError as error:
                if "Document source requires URL and version or snapshot identity" in str(error):
                    continue
                raise
            raise ValueError(f"{side}: unexpectedly readable: {ref} at {path}")
        reader.read(ref, revision=revision)
        old = row["old_checkout_revision"]
        if side == "new" and old.startswith("sha256:") and old != revision:
            try:
                reader.read(ref, revision=old)
            except RevisionConflict:
                rejections += 1
            else:
                raise ValueError(f"Old revision silently resolved: {ref} at {row['old_path']}")
    return len(expected), rejections


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True,
                        help="pre-layout checkout corresponding to the migration manifest")
    parser.add_argument("--after", type=Path, default=PROJECT, help="cutover source checkout")
    args = parser.parse_args()
    with (PROJECT / "docs/skill-layout-migration.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len({row["stable_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate identities in migration manifest")
    before, _ = verify_snapshot(args.before, rows, "old")
    after, rejections = verify_snapshot(args.after, rows, "new")
    print(f"Verified {before} previous and {after} cutover entries; "
          f"{rejections} stale revisions rejected.")


if __name__ == "__main__":
    main()
