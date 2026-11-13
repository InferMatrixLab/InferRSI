"""Pure ExecutionSpec encoding helpers shared by H ports and their callers.

This module has no RunStore or execution side effects. The digest covers the
complete canonical spec; storage implementations must use the same function.
"""

import hashlib
from collections.abc import Mapping

from inferrsi import _json_v1


def request_digest(spec: Mapping) -> str:
    """Return the D017 semantic identifier of a complete ExecutionSpec."""
    return "sha256:" + hashlib.sha256(_json_v1.encode(spec)).hexdigest()
