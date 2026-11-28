#!/usr/bin/env python3
"""Screen a redacted Maya family projection and supplied physical-pool estimates.

Python 3.10+, standard library only. Example:
  python audit_runtime_plan.py --plan plan.json
Reads one JSON file (at most 64 KiB); writes JSON only to stdout. No engine
imports, model reads, device probes, network, subprocesses or config changes.

Original helper, with bounded source-derived dispatch semantics informed by
mw00/project-maya 249f9a87d1a9d72bec2b684d704b0aa9296b1c9c,
tools/maya_quants.py:132-144. Source attribution: Copyright (c) 2026 Peasant
Smith / Project Maya contributors; Niko1221 / Strata contributors, MIT.
The retained full upstream notice is in ../references/notices.md.
This is not the upstream resolver or a production memory-budget implementation.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FAMILIES = {"glm", "deepseek", "minimax", "qwen"}
MAX_BYTES = (1 << 63) - 1
NAME = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
UNCHECKED = [
    "checkpoint bytes, geometry, quant layout and pack integrity",
    "caller-supplied allocation sizes, alias truth and peak completeness",
    "actual residency, allocation success, Windows commit and driver accounting",
    "native backend, compiler, device topology, tokenization and inference",
    "model quality, service behavior, performance and deployment licensing",
]


class InvalidPlan(ValueError):
    """Malformed or ambiguous input; do not guess a repair."""


def pairs_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidPlan("duplicate JSON object key")
        result[key] = value
    return result


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys():
        raise InvalidPlan("object or required fields missing")
    if set(value) - set(required) - set(optional):
        raise InvalidPlan("unknown object field")


def integer(value, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_BYTES:
        raise InvalidPlan("expected a bounded integer, not a boolean or float")
    return value


def identity(value):
    if not isinstance(value, str) or NAME.fullmatch(value) is None:
        raise InvalidPlan("allocation identity must be a short lowercase-hyphen label")
    return value


def dispatch(config):
    fields(config, ("exe", "installer", "args"))
    fields(config["installer"], (), ("family",))
    inst = config["installer"].get("family")
    if inst is not None and inst not in FAMILIES:
        raise InvalidPlan("unknown installer family")
    if not isinstance(config["exe"], str) or len(config["exe"]) > 4096:
        raise InvalidPlan("exe must be a bounded string; it is never executed")
    args = config["args"]
    if (
        not isinstance(args, list)
        or len(args) > 256
        or any(not isinstance(arg, str) or len(arg) > 4096 for arg in args)
    ):
        raise InvalidPlan("args must be a bounded list of strings")
    for flag in ("--pack", "--ple-gguf"):
        for index, arg in enumerate(args):
            if arg == flag and (
                index + 1 == len(args) or not args[index + 1] or args[index + 1].startswith("--")
            ):
                raise InvalidPlan("selected family marker has no value")
    exe = config["exe"].replace("\\", "/").rsplit("/", 1)[-1]
    executable_family = (
        "minimax"
        if exe.startswith("maya-mm3")
        else "deepseek"
        if exe.startswith(("maya-ds4", "strata-ds4"))
        else None
    )
    conflicts = []
    if inst and executable_family and inst != executable_family:
        conflicts.append("installer and model-specific executable disagree")
    ple = "--ple-gguf" in args[:-1]
    if ple and (inst in {"minimax", "deepseek", "glm"} or executable_family):
        conflicts.append("Qwen special-route marker conflicts with another explicit family")
    # Preserve the relevant upstream precedence: --pack is also legitimate MM3
    # input and Qwen's generated args contain BOTH --pack and --ple-gguf.
    if inst == "minimax" or executable_family == "minimax":
        family = "minimax"
    elif inst == "qwen" or ple:
        family = "qwen"
    elif inst == "deepseek" or "--pack" in args[:-1] or executable_family == "deepseek":
        family = "deepseek"
    else:
        family = "glm"
    default_only = family == "glm" and inst != "glm"
    return family, conflicts, default_only


def audit(plan):
    fields(plan, ("schema_version", "family", "format", "config", "memory"))
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise InvalidPlan("unsupported schema version")
    if plan["family"] not in FAMILIES or plan["format"] not in {"gguf", "exl3"}:
        raise InvalidPlan("unsupported declared family or selected format")
    family, conflicts, default_only = dispatch(plan["config"])
    if family != plan["family"]:
        conflicts.append("declared family differs from selected config-marker route")
    if plan["family"] == "qwen" and plan["format"] != "gguf":
        conflicts.append("the inspected Qwen setup route is GGUF, not EXL3")
    memory = plan["memory"]
    fields(memory, ("kind", "capacity_bytes", "reserve_bytes", "allocations", "aliases"))
    kind = memory["kind"]
    capacities, reserves = memory["capacity_bytes"], memory["reserve_bytes"]
    if not isinstance(capacities, dict) or not isinstance(reserves, dict) or not capacities:
        raise InvalidPlan("nonempty capacity and reserve objects required")
    pools = set(capacities)
    if pools != set(reserves):
        raise InvalidPlan("capacity and reserve pools must match exactly")
    if kind == "unified":
        if pools != {"unified"}:
            raise InvalidPlan("unified memory requires ONE shared physical pool")
    elif kind == "discrete":
        allowed = {"host"} | {f"device-{i}" for i in range(16)}
        if not pools <= allowed:
            raise InvalidPlan("discrete pools must be host or device-0 through device-15")
    else:
        raise InvalidPlan("memory kind must be unified or discrete")
    usage = {pool: 0 for pool in pools}
    for pool in pools:
        integer(capacities[pool])
        integer(reserves[pool])
        if reserves[pool] > capacities[pool]:
            raise InvalidPlan("reserve exceeds supplied capacity")
    allocations, aliases = memory["allocations"], memory["aliases"]
    if not isinstance(allocations, list) or not 1 <= len(allocations) <= 256:
        raise InvalidPlan("one to 256 explicit allocations required")
    if not isinstance(aliases, list) or len(aliases) > 256:
        raise InvalidPlan("aliases must be a list of at most 256 entries")
    ids = set()
    for allocation in allocations:
        fields(allocation, ("id", "pool", "bytes", "copies"))
        name = identity(allocation["id"])
        if name in ids:
            raise InvalidPlan("duplicate allocation identity")
        ids.add(name)
        pool = allocation["pool"]
        if not isinstance(pool, str) or pool not in pools:
            raise InvalidPlan("allocation refers to an undeclared physical pool")
        usage[pool] += integer(allocation["bytes"]) * integer(allocation["copies"], 1)
        integer(usage[pool])
    alias_ids = set()
    for alias in aliases:
        fields(alias, ("id", "allocation"))
        name, target = identity(alias["id"]), identity(alias["allocation"])
        if name in ids or name in alias_ids or target not in ids:
            raise InvalidPlan("alias must have a unique identity and target a real allocation")
        alias_ids.add(name)
    rows = []
    for pool in sorted(pools):
        remaining = capacities[pool] - reserves[pool] - usage[pool]
        rows.append(
            {
                "pool": pool,
                "estimated_live_bytes": usage[pool],
                "reserve_bytes": reserves[pool],
                "capacity_bytes": capacities[pool],
                "estimated_remaining_bytes": remaining,
            }
        )
        if remaining < 0:
            conflicts.append(
                f"estimated simultaneous allocations exceed {pool} capacity less reserve"
            )
    warnings = (
        ["upstream GLM fallback has no discriminating identity evidence"] if default_only else []
    )
    return {
        "status": "screening_conflict" if conflicts else "screened_ledger_only",
        "selected_marker_family": family,
        "declared_family": plan["family"],
        "format_label_only": plan["format"],
        "physical_pools": rows,
        "alias_count_not_extra_allocations": len(alias_ids),
        "warnings": warnings,
        "conflicts": conflicts,
        "native_verification": "not_run",
        "model_compatibility": "not_verified",
        "unchecked": UNCHECKED,
    }, bool(conflicts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan", required=True, type=Path, help="small redacted JSON planning projection"
    )
    args = parser.parse_args()
    try:
        if not args.plan.is_file():
            raise InvalidPlan("input must be a regular JSON planning file")
        with args.plan.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise InvalidPlan("planning input exceeds 64 KiB")
        plan = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs_without_duplicates)
        result, conflict = audit(plan)
    except InvalidPlan as error:
        result = {
            "status": "invalid_input",
            "reason": str(error),
            "native_verification": "not_run",
            "model_compatibility": "not_verified",
            "unchecked": UNCHECKED,
        }
        print(json.dumps(result, sort_keys=True, indent=2))
        return 2
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        # Do not print caller file paths, config values or decoder excerpts.
        result = {
            "status": "invalid_input",
            "reason": "unreadable or invalid bounded planning projection",
            "native_verification": "not_run",
            "model_compatibility": "not_verified",
            "unchecked": UNCHECKED,
        }
        print(json.dumps(result, sort_keys=True, indent=2))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 1 if conflict else 0


if __name__ == "__main__":
    raise SystemExit(main())
