"""Versioned field weights for the shared lexical Knowledge ranking."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

# Bump when the scoring or tie-breaking semantics change.
RANKING_VERSION = 1
_DEFAULT_WEIGHTS = MappingProxyType({
    "title": 5.0, "summary": 4.0, "tags": 4.0, "findings": 4.0,
    "applicability": 2.0, "body": 1.0,
})


@dataclass(frozen=True)
class RankingPolicy:
    """A named set of overrides, expanded once into immutable effective weights."""

    policy_id: str = "default"
    weights: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", self.policy_id
        ):
            raise ValueError("Ranking policy requires a nonempty identifier")
        if not isinstance(self.weights, Mapping) or self.weights.keys() - _DEFAULT_WEIGHTS.keys():
            raise ValueError("Unknown ranking weight field")
        effective = dict(_DEFAULT_WEIGHTS)
        for name, value in self.weights.items():
            if type(value) not in (float, int) or not 0 <= value <= sys.float_info.max:
                raise ValueError(f"Ranking weight for {name} must be finite and nonnegative")
            effective[name] = float(value) if value else 0.0
        object.__setattr__(self, "weights", MappingProxyType(effective))

    def configuration(self) -> dict:
        """Return the full effective rule, also suitable for service-mode receipts."""
        return {"id": self.policy_id, "version": RANKING_VERSION, "weights": dict(self.weights)}

    def receipt(self) -> dict:
        configuration = self.configuration()
        raw = json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {**configuration, "config_sha256": hashlib.sha256(raw).hexdigest()}


DEFAULT_RANKING_POLICY = RankingPolicy()

MANAGED_RANKING_POLICIES = MappingProxyType({
    "default": DEFAULT_RANKING_POLICY,
    "applicability": RankingPolicy("applicability", {"applicability": 3}),
})


def managed_ranking_policy(name: str) -> RankingPolicy:
    try:
        return MANAGED_RANKING_POLICIES[name]
    except KeyError:
        raise ValueError(
            f"Unknown frozen ranking policy {name!r}, use its original runtime"
        ) from None
