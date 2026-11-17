"""Versioned delivery projection, independent of execution and AppsResultV1."""

import json
import math
from datetime import datetime, timezone

SCHEMA_ID = "inferrsi.campaign-delivery"
INDEX_ID = "inferrsi.delivery-artifacts"
FIELDS = {
    "schema_id",
    "schema_version",
    "export",
    "campaign",
    "sources",
    "execution",
    "completion",
    "outcome",
    "baseline",
    "selected_candidate",
    "final",
    "acceptance",
    "metrics",
    "checks",
    "rounds",
    "usage",
    "gaps",
    "artifacts_ref",
}


def encode(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def decode(raw):
    def constant(_):
        raise ValueError("Nonfinite JSON number")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(raw, parse_constant=constant, object_pairs_hook=pairs)
    encode(value)  # Also rejects overflowing float tokens and invalid Unicode.
    return value


def number(value):
    try:
        return value if type(value) in (int, float) and math.isfinite(value) else None
    except OverflowError:
        return None


def timestamp(value):
    if number(value) is not None:
        try:
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.isoformat()
        except ValueError:
            pass
    return None


def gap(result, code, affects, reason):
    entry = {"code": code, "affects": affects, "reason": reason}
    if entry not in result["gaps"]:
        result["gaps"].append(entry)


def empty_result(export_id, observed_at, version):
    return {
        "schema_id": SCHEMA_ID,
        "schema_version": 1,
        "export": {
            "id": export_id,
            "generated_at": timestamp(observed_at),
            "snapshot_at": timestamp(observed_at),
            "kind": "progress",
            "generator_version": version,
        },
        "campaign": {
            "id": None,
            "goal": None,
            "task_kind": None,
            "acceptance_basis": None,
            "plan_ref": None,
        },
        "sources": [],
        "execution": {},
        "completion": {"status": "incomplete", "reason": "Workflow facts are unavailable"},
        "outcome": {"kind": "undetermined", "reason": "Final improvement is not established"},
        "baseline": None,
        "selected_candidate": None,
        "final": None,
        "acceptance": {
            "status": "not_assessed",
            "verdict": None,
            "claim_id": None,
            "scope": None,
            "assessment_ref": None,
            "assessment_provenance": None,
            "delivery_accepted": False,
        },
        "metrics": None,
        "checks": None,
        "rounds": None,
        "usage": {
            key: {"value": None, "source": None, "coverage": "unknown"}
            for key in ("wall_seconds", "tokens", "device_seconds", "cost")
        },
        "gaps": [],
        "artifacts_ref": "artifacts.json",
    }


def validate_result(value):
    if not isinstance(value, dict) or not FIELDS <= value.keys():
        raise ValueError("Missing delivery contract fields")
    if (
        value["schema_id"] != SCHEMA_ID
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
    ):
        raise ValueError("Unsupported delivery schema or version")
    for key in ("export", "campaign", "execution", "completion", "outcome", "acceptance", "usage"):
        if not isinstance(value[key], dict):
            raise ValueError("Invalid delivery object field")
    for key in ("baseline", "selected_candidate", "final"):
        if value[key] is not None and not isinstance(value[key], dict):
            raise ValueError("Invalid optional delivery object")
    for key in ("sources", "gaps", "metrics", "checks", "rounds"):
        if value[key] is None and key not in ("sources", "gaps"):
            continue
        if not isinstance(value[key], list) or any(not isinstance(row, dict) for row in value[key]):
            raise ValueError("Invalid delivery collection")
    if value["completion"].get("status") not in ("completed", "incomplete"):
        raise ValueError("Invalid workflow completion")
    if value["outcome"].get("kind") not in (
        "improved",
        "baseline_retained",
        "no_valid_candidate",
        "undetermined",
    ):
        raise ValueError("Invalid selection outcome")
    acceptance = value["acceptance"]
    if (
        (acceptance.get("status") == "not_assessed" and acceptance.get("verdict") is not None)
        or (
            acceptance.get("status") == "assessed"
            and acceptance.get("verdict") not in ("PASS", "FAIL", "INCONCLUSIVE")
        )
        or acceptance.get("status") not in ("assessed", "not_assessed")
    ):
        raise ValueError("Invalid assessment semantics")
    if type(acceptance.get("delivery_accepted")) is not bool:
        raise ValueError("Invalid delivery acceptance flag")
    if acceptance["delivery_accepted"] and (
        acceptance["verdict"] != "PASS"
        or value["completion"]["status"] != "completed"
        or not value["final"]
        or value["final"].get("binding", {}).get("verified") is not True
        or (
            acceptance.get("assessment_provenance") is not None
            and acceptance["assessment_provenance"].get("verification") != "verified"
        )
    ):
        raise ValueError("Delivery acceptance requires a completed final with verified binding")
    for measure in value["usage"].values():
        if (
            not isinstance(measure, dict)
            or measure.get("coverage") not in ("complete", "partial", "unknown")
            or not {"value", "source"} <= measure.keys()
        ):
            raise ValueError("Invalid usage coverage")
    if value["export"].get("kind") not in ("progress", "final"):
        raise ValueError("Invalid snapshot kind")
    for key in ("generated_at", "snapshot_at"):
        if timestamp(value["export"].get(key)) is None:
            raise ValueError("Invalid export timestamp")
    if value["artifacts_ref"] != "artifacts.json":
        raise ValueError("Invalid artifact index reference")
    encode(value)
