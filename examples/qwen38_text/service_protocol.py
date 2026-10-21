"""Frozen input contract for functional service validation, with no timing defaults."""

import hashlib
import json
import math
import re
from pathlib import Path

from .profiles import check_precision

SCOPE = "native_service_functional"
TIMEOUT_KEYS = {"startup", "request", "release", "poll", "shutdown", "socket"}
LIMIT_KEYS = {
    "max_context_tokens",
    "max_active_requests",
    "max_connections",
    "max_body_bytes",
    "max_response_bytes",
}
ERROR_IDS = {
    "invalid_json",
    "unknown_field",
    "sampling",
    "context_limit",
    "output_limit",
    "body_limit",
}


def read_protocol(path, model_id):
    content = Path(path).read_bytes()
    value = json.loads(content)
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("qualification_scope") != SCOPE
        or value.get("model_id") != model_id
    ):
        raise ValueError("Wrong service protocol identity")
    check_precision(value, model_id)
    for field, keys in (("timeouts", TIMEOUT_KEYS), ("limits", LIMIT_KEYS)):
        items = value.get(field)
        if not isinstance(items, dict) or set(items) != keys:
            raise ValueError("Service protocol must freeze every timeout and limit")
        for number in items.values():
            valid = type(number) is int if field == "limits" else type(number) in (int, float)
            if not valid or not math.isfinite(number) or number <= 0:
                raise ValueError("Service bounds must be positive finite numbers")
    limits = value["limits"]
    if (
        limits["max_active_requests"] < 2
        or limits["max_connections"] < limits["max_active_requests"] + 2
    ):
        raise ValueError("Service scope requires concurrency and reserved control connections")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) < 2:
        raise ValueError("Service scope requires multiple generation cases")
    seen = set()
    for case in cases + [value.get("lifecycle"), value.get("queued_case")]:
        if not isinstance(case, dict):
            raise ValueError("Service generation cases must be objects")
        prompt = case.get("prompt")
        if (
            not (
                isinstance(prompt, str)
                and prompt
                or isinstance(prompt, list)
                and prompt
                and all(type(token) is int and token >= 0 for token in prompt)
            )
            or type(case.get("max_tokens")) is not int
            or case["max_tokens"] <= 0
        ):
            raise ValueError("Invalid service generation request")
    for case in cases:
        name = case.get("id")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name) or name in seen:
            raise ValueError("Service case IDs must be unique safe identifiers")
        seen.add(name)
    concurrent = value.get("concurrent_case_ids")
    if (
        not isinstance(concurrent, list)
        or len(concurrent) < 2
        or len(concurrent) > limits["max_active_requests"]
        or any(not isinstance(name, str) or name not in seen for name in concurrent)
        or len(set(concurrent)) != len(concurrent)
    ):
        raise ValueError("Invalid concurrent case coverage")
    selected = {case["id"]: case for case in cases}
    if len({json.dumps(selected[name]["prompt"], sort_keys=True) for name in concurrent}) < 2:
        raise ValueError("Concurrent isolation requires distinct request inputs")
    for key in ("lifecycle", "queued_case"):
        name = value[key].get("id")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Lifecycle case IDs must be explicit safe identifiers")
    for key in ("eos_case_id", "survivor_case_id"):
        if not isinstance(value.get(key), str) or value[key] not in seen:
            raise ValueError("EOS and lifecycle survivor cases must be explicitly frozen")
    if value["lifecycle"]["max_tokens"] < 2:
        raise ValueError("Fault probe requires at least two model calls")
    return value, hashlib.sha256(content).hexdigest()
