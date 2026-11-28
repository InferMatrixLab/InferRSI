"""Check explicit operator-development decisions in a small JSON contract."""

import argparse
import json
from pathlib import Path


def validate(record):
    errors = []
    if not isinstance(record, dict):
        return ["contract must be a JSON object"]
    for key in ("schema", "reference"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            errors.append(f"{key} must be a nonempty string")
    schema = record.get("schema", "")
    if isinstance(schema, str) and ("::" not in schema or "->" not in schema):
        errors.append("schema must state namespace and return contract")
    for key in ("dtypes", "layouts", "shape_cases"):
        if not isinstance(record.get(key), list) or not record[key]:
            errors.append(f"{key} must be a nonempty list")
    for key in ("mutates_inputs", "requires_grad", "has_autograd", "compile_requested", "has_meta"):
        if not isinstance(record.get(key), bool):
            errors.append(f"{key} must be boolean")
    if record.get("requires_grad") is True and record.get("has_autograd") is not True:
        errors.append("gradient requirement has no autograd implementation plan")
    if record.get("compile_requested") is True and record.get("has_meta") is not True:
        errors.append("compile request has no Meta/fake implementation plan")
    if record.get("mutates_inputs") is True and isinstance(schema, str) and "!" not in schema:
        errors.append("mutation must be represented in schema alias annotations")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "contract", type=Path, help="JSON input; no source checkout or torch installation required"
    )
    args = parser.parse_args()
    try:
        record = json.loads(args.contract.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(json.dumps({"status": "FAIL", "errors": ["cannot read a valid JSON contract"]}))
        return 2
    errors = validate(record)
    print(
        json.dumps(
            {
                "status": "FAIL" if errors else "PASS",
                "scope": "declaration completeness only",
                "errors": errors,
            },
            indent=2,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
