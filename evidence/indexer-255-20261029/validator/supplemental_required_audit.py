"""Supplemental post-run audit of saved retrieval results, not a frozen validator.

Portable adaptation of the independent audit used after the first timing run.
Inputs are saved case-result JSON arrays, optionally gzip compressed. This checks
all emitted contexts, not whether missing relevant items should have been found.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path


def read_cases(path: Path) -> list[dict]:
    """Load a raw case-result array without changing its semantics."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def audit(root: Path, arm: str, inputs: list[Path]) -> dict:
    sys.path.insert(0, str(root.resolve() / "src"))
    from inferrsi._skill_selection import indexed_skill
    from inferrsi.knowledge_operations import KnowledgeReader

    reader = KnowledgeReader()
    audits = []
    for input_path in inputs:
        for row in read_cases(input_path):
            for context in row["result"]["contexts"]:
                bundle = reader.read(context["ref"], revision=context["revision"])
                view = next(
                    item for item in row["result"]["items"]
                    if item["ref"] == context["ref"]
                )
                _, required, _ = indexed_skill(
                    reader.records()[view["id"]], view, bundle.content,
                )
                emitted = {resource["path"]: resource for resource in context["resources"]}
                missing = sorted(set(required) - emitted.keys())
                bad = [
                    path for path, resource in emitted.items()
                    if resource["content"].encode() != bundle.content[path]
                    or resource["sha256"] != hashlib.sha256(bundle.content[path]).hexdigest()
                ]
                revision_match = bundle.revision == context["revision"]
                audits.append({
                    "case": row["id"],
                    "ref": context["ref"],
                    "required": required,
                    "missing": missing,
                    "bad_bytes_or_hash": bad,
                    "revision_match": revision_match,
                    "passed": not missing and not bad and revision_match,
                })
    return {
        "arm": arm,
        "scope": (
            "all emitted contexts in supplied saved case results; absent relevant "
            "retrieval is not counted as delivery success"
        ),
        "checks": audits,
        "passed": all(check["passed"] for check in audits),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--inputs", required=True, nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.root, args.arm, args.inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(args.arm, len(result["checks"]), result["passed"])


if __name__ == "__main__":
    main()
