#!/usr/bin/env python3
"""Inspect installed lithos-metal software and optional tiny CPU contracts.

Run: python <SKILL_DIR>/scripts/inspect_contract.py --check-contract
Requires lithos-metal in the selected Python environment. No network, device,
model, subprocess, file writes or original checkout is used. Output omits paths.
This is an authored diagnostic around upstream contracts, not an upstream tool.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import inspect
import json


def inspect_software(expected_version: str, check_contract: bool) -> tuple[dict, bool]:
    report = {
        "scope": "installed software/API and optional basic CPU contracts",
        "backend_runtime_checked": False,
        "model_numerics_checked": False,
        "expected_version": expected_version,
        "checks": [],
    }
    try:
        version = importlib.metadata.version("lithos-metal")
    except importlib.metadata.PackageNotFoundError:
        report["checks"].append({"name": "distribution", "ok": False,
                                  "reason": "lithos-metal is not installed"})
        return report, False
    report["distribution_version"] = version
    try:
        import monolith
        from monolith.compiler import compile_program
        from monolith.core.step_state import StepStateLayout
        from monolith.generate import Session, load_session
        from monolith.runtime.prefix_cache import PrefixCache
    except ImportError as exc:
        report["checks"].append({"name": "imports", "ok": False,
                                  "reason": "missing package dependency",
                                  "exception_type": type(exc).__name__})
        return report, False
    report["module_version"] = monolith.__version__
    report["checks"].append({"name": "version_agreement",
                              "ok": version == monolith.__version__ == expected_version})
    report["api_parameters"] = {
        name: list(inspect.signature(obj).parameters)
        for name, obj in (
            ("Session", Session), ("Session.generate", Session.generate),
            ("load_session", load_session), ("compile_program", compile_program),
            ("StepStateLayout", StepStateLayout), ("PrefixCache", PrefixCache),
        )
    }
    report["optional_modules_discoverable"] = {
        name: importlib.util.find_spec(name) is not None
        for name in ("fastapi", "httpx", "transformers", "safetensors")
    }
    if check_contract:
        from monolith.compiler.barriers import place_barriers
        from monolith.runtime.program import KernelSpec, OpSpec, Program

        layout = StepStateLayout(t_max=4, gamma_max=3)
        decoded = layout.unpack(layout.pack({"anchor": -1, "pending_tokens": [11, 12]}))
        report["checks"].append({
            "name": "layout_roundtrip_and_alignment",
            "ok": decoded["anchor"] == -1 and decoded["pending_tokens"] == [11, 12, 0, 0]
            and layout.size % 16 == 0 and len(set(layout.offsets.values())) == len(layout.fields),
        })
        rejected = False
        try:
            StepStateLayout(t_max=2, gamma_max=2)
        except ValueError:
            rejected = True
        report["checks"].append({"name": "invalid_layout_rejected", "ok": rejected})
        program = Program(
            {"k": KernelSpec("", "k")}, {}, [
                OpSpec("k", [(0, "x", 0), (1, "a", 0)], (1, 1, 1), (32, 1, 1),
                       meta={"writes": [1]}),
                OpSpec("k", [(0, "a", 0), (1, "out", 0)], (1, 1, 1), (32, 1, 1),
                       meta={"writes": [1]}),
            ],
        )
        count = place_barriers(program)
        report["checks"].append({
            "name": "dependent_dispatch_barriers",
            "ok": count == 2 and all(op.barrier_before for op in program.ops),
        })
    return report, all(item["ok"] for item in report["checks"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", default="0.1.2")
    parser.add_argument("--check-contract", action="store_true",
                        help="Run tiny CPU layout and dependency assertions; never create a device")
    args = parser.parse_args()
    try:
        report, ok = inspect_software(args.expected_version, args.check_contract)
    except Exception as exc:
        # Exception messages may contain local paths; retain only the failure type.
        report, ok = {"scope": "software/CPU contract inspection", "ok": False,
                      "exception_type": type(exc).__name__,
                      "reason": "inspection failed; inspect the selected package privately"}, False
    report["ok"] = ok
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
