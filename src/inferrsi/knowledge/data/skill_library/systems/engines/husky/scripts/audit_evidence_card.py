#!/usr/bin/env python3
"""Screen a supplied research card without authenticating claims or execution.

Original offline helper for this document-derived candidate. Reads one JSON
file, prints schema/identity gaps, performs no network/model/process operation.
Example: python audit_evidence_card.py --input card.json
"""

import argparse
import json
from pathlib import Path

IDENTITIES = ("engine_revision", "model_digest", "workload_digest", "output_digest", "backend")
CLASSES = {"author_report", "source_inspection", "runtime_run"}


def audit(card):
    if not isinstance(card, dict) or set(card) != {
        "schema_version", "claim", "evidence_class", "source_url", "identities",
        "raw_artifacts_available",
    }:
        raise ValueError("expected exactly the documented research-card fields")
    if type(card["schema_version"]) is not int or card["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    if not isinstance(card["claim"], str) or not card["claim"].strip():
        raise ValueError("claim must be nonempty text")
    if card["evidence_class"] not in CLASSES:
        raise ValueError("unknown evidence_class")
    if card["source_url"] != "https://husky.underdog.ai/":
        raise ValueError("source_url must identify the selected official document")
    identities = card["identities"]
    if not isinstance(identities, dict) or set(identities) != set(IDENTITIES):
        raise ValueError("identities must name every documented identity, using null for unknown")
    if any(value is not None and (not isinstance(value, str) or not value.strip())
           for value in identities.values()):
        raise ValueError("identity values must be nonempty text or null")
    if type(card["raw_artifacts_available"]) is not bool:
        raise ValueError("raw_artifacts_available must be a boolean")
    return {
        "schema_valid": True,
        "evidence_class": card["evidence_class"],
        "missing_identity": [key for key in IDENTITIES if identities[key] is None],
        "qualification": "not_adjudicated",
        "scope": "supplied metadata only; no artifact bytes or executions authenticated",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = audit(json.loads(args.input.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"invalid research card: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
