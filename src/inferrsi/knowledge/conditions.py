"""Declared applicability shared by local knowledge navigation and catalog decisions."""

import re

CONDITION_FIELDS = (
    "backend",
    "hardware",
    "os",
    "model",
    "phase",
    "engine",
    "engine_version",
    "dependency_version",
    "dtype",
    "workload",
    "quality",
    "measurement",
)
APPLICABILITY_VERDICTS = ("match", "analogue", "unknown", "conflict")


def project_conditions(declared, *, backend=None, backend_locator="backend"):
    """Project the documented fields and retain the source of a discovered backend."""
    conditions = ({k: v for k, v in declared.items() if k in CONDITION_FIELDS}
                  if isinstance(declared, dict) else {})
    locators = {}
    if not conditions.get("backend") and backend:
        conditions["backend"] = backend
        locators["backend"] = backend_locator
    return conditions, locators


def _comparable_value(field, value):
    if not isinstance(value, str) or value.casefold() in {
        "unknown", "unspecified", "common", "any", "none"
    }:
        return False
    if field in ("engine_version", "dependency_version"):
        # Compare literal releases only. Wildcards, ranges and floating labels
        # require interpretation that an equality comparison cannot supply.
        return bool(re.fullmatch(
            r"v?\d+(?:\.\d+)*(?:[.-]?(?:a|b|alpha|beta|rc|post|dev)\.?\d+)?"
            r"(?:\+[a-z0-9]+(?:[.-][a-z0-9]+)*)?", value, re.IGNORECASE
        ))
    return bool(re.fullmatch(r"[\w.+:/-]+", value))


def compare_conditions(declared, task, *, purpose="conclusion", locators=None):
    """Exact scalar/list membership only. Prose, ranges and missing values stay unknown.

    A method can transfer as an analogy, but a mismatched bounded conclusion
    cannot. This verdict never modifies the source's validation state.
    """
    if purpose not in ("conclusion", "method"):
        raise ValueError("purpose must be conclusion or method")
    if not isinstance(task, dict) or set(task) - set(CONDITION_FIELDS):
        raise ValueError("conditions must use the documented condition fields")
    source = declared if isinstance(declared, dict) else {}
    comparisons = []
    for field, actual in task.items():
        expected = source.get(field)
        values = expected if isinstance(expected, list) else [expected]
        # Whitespace prose is not an enumerated condition. Versions must be exact;
        # source commits are deliberately not interpreted as engine versions.
        comparable = bool(values) and all(_comparable_value(field, v) for v in [actual, *values])
        result = (
            ("match" if actual.casefold() in [v.casefold() for v in values] else "conflict")
            if comparable
            else "unknown"
        )
        comparisons.append(
            {
                "field": field,
                "task": actual,
                "source": expected,
                "result": result,
                "locator": (locators or {}).get(field, f"applicability.{field}"),
            }
        )
    states = {c["result"] for c in comparisons}
    verdict = (
        ("analogue" if purpose == "method" else "conflict")
        if "conflict" in states
        else ("match" if states == {"match"} else "unknown")
    )
    return {
        "verdict": verdict,
        "purpose": purpose,
        "comparisons": comparisons,
        "missing": [c["field"] for c in comparisons if c["result"] == "unknown"],
        "scope": "declared fields only; prose and unrequested conditions require source review",
        "next_step": (
            "Validate the method on a minimal target workload before transfer."
            if verdict == "analogue"
            else "Check original bounds and task-required validation before using a claim."
        ),
    }
