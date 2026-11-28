#!/usr/bin/env python3
"""Normalize selected Splash byte-budget syntax without importing the engine.

Adapted from incoai/splash server/serve_options.py, revision
39a97385f8560cf8a93972cec9b0a963c9195250, lines 35-43 and 115-192.
Upstream is Apache-2.0; retain the owning skill's source license/notices.
Changes: standalone CLI/JSON result, selected option kinds, ValueError interface;
no source-module imports, allocator, file access, network, or model execution.
Example: python parse_budget.py --kind max-memory 2.5G
This checks syntax only, not model compatibility, store floors, or memory fit.
"""

import argparse
import json
import re
from decimal import Decimal

SIZE_UNITS = {
    unit + suffix: 1024**power
    for power, unit in enumerate(("K", "M", "G"), 1)
    for suffix in ("", "B", "IB")
}
SIZE_NUMBER = re.compile(r"\d+(\.\d+)?")
KINDS = ("max-memory", "ple-memory", "expert-memory", "sparse-kv-memory", "max-cache-disk")


def parse_budget(kind, value):
    """Return None for auto, 'off' for whole-load modes, or integer bytes."""
    if kind not in KINDS:
        raise ValueError("unsupported budget kind")
    normalized = value.strip().upper()
    if normalized == "AUTO":
        return None
    if normalized == "OFF" and kind in ("ple-memory", "expert-memory"):
        return "off"
    if value.strip() == "0" and kind == "max-cache-disk":
        return 0
    multiplier = 1
    for suffix in sorted(SIZE_UNITS, key=len, reverse=True):
        if normalized.endswith(suffix):
            normalized, multiplier = normalized[:-len(suffix)], SIZE_UNITS[suffix]
            break
    number = SIZE_NUMBER.fullmatch(normalized)
    size = 0
    if number and (multiplier > 1 or not number.group(1)):
        size = int(Decimal(normalized) * multiplier)
    if not 1 <= size <= 2**63 - 1:
        raise ValueError("use auto or positive bytes such as 28G or 2.5G; modes depend on kind")
    return size


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS, required=True)
    parser.add_argument("value", help="auto, positive byte size, or a kind-specific mode")
    args = parser.parse_args(argv)
    try:
        result = parse_budget(args.kind, args.value)
    except ValueError as error:
        parser.error(str(error))
    if result is None:
        mode = "auto"
    elif result == "off":
        mode = "whole"
    else:
        mode = "disabled" if result == 0 else "size"
    print(json.dumps({"kind": args.kind, "mode": mode,
                      "bytes": result if isinstance(result, int) else None,
                      "scope": "syntax-only; no fit or backend verification"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
