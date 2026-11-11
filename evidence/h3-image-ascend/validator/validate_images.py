"""Compare complete matched benchmark outputs using decoded RGB bytes."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def read_run(root):
    root = root.resolve()
    summary = json.loads((root / "summary.json").read_text())
    records = json.loads((root / "requests.json").read_text())
    if not summary["evidence"]["requests_complete"] or not all(r["complete"] for r in records):
        raise ValueError("Cannot validate an incomplete run")
    results = {}
    seen = set()
    for record in records:
        path = (root / record["image"]).resolve()
        if not path.is_relative_to(root) or path in seen:
            raise ValueError("Aliased or escaping output path")
        seen.add(path)
        with Image.open(path) as image:
            pixels = np.array(image.convert("RGB"))
        if hashlib.sha256(pixels.tobytes()).hexdigest() != record["rgb_sha256"]:
            raise ValueError("Image differs from its recorded pixels")
        key = (record["workload"], record["seed"], record["index"])
        if key in results:
            raise ValueError("Duplicate request identity")
        results[key] = (record, pixels)
    return results


def main(args):
    if args.reference.resolve() == args.candidate.resolve():
        raise ValueError("Reference and candidate must be independent run directories")
    reference = read_run(args.reference)
    candidate = read_run(args.candidate)
    if reference.keys() != candidate.keys():
        raise ValueError("Reference and candidate request coverage differs")
    checks = []
    for key, (row, actual) in candidate.items():
        expected_row, expected = reference[key]
        if row["request"] != expected_row["request"] or expected.shape != actual.shape:
            raise ValueError("Request or output dimensions differ")
        difference = actual.astype(np.int16) - expected.astype(np.int16)
        checks.append({"workload": key[0], "seed": key[1], "index": key[2],
                       "pixel_equal": bool(np.array_equal(actual, expected)),
                       "max_abs_difference": int(np.abs(difference).max()),
                       "different_channels": int(np.count_nonzero(difference))})
    passed = bool(checks) and all(c["pixel_equal"] for c in checks)
    result = {"verdict": "PASS" if passed else "FAIL", "scope": "same-device exact decoded RGB parity",
              "cross_hardware_reference_quality": "not verified", "checks": checks}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"verdict": result["verdict"], "compared": len(checks)}))
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(main(parser.parse_args()))
