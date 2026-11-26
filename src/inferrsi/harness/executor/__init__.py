"""Execution request identity for callers of the Harness execution ports."""

import hashlib
from collections.abc import Mapping

from inferrsi.contracts import json_v1


def request_digest(spec: Mapping) -> str:
    """Return the D017 semantic identifier of a complete ExecutionSpec."""
    return "sha256:" + hashlib.sha256(json_v1.encode(spec)).hexdigest()
