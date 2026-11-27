"""Versioned field weights for the shared lexical Knowledge ranking."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
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

    @classmethod
    def from_configuration(cls, configuration: Mapping) -> RankingPolicy:
        """Rebuild a policy from a frozen configuration or receipt and verify it.

        The configuration must name every weight field, use the current scoring
        version and, when it carries ``config_sha256``, match its own digest.
        """
        if not isinstance(configuration, Mapping):
            raise ValueError("Ranking configuration must be a mapping")
        keys = set(configuration)
        if keys - {"config_sha256"} != {"id", "version", "weights"}:
            raise ValueError("Ranking configuration requires id, version and weights only")
        version = configuration["version"]
        if type(version) is not int or version != RANKING_VERSION:
            raise ValueError(
                f"Ranking configuration version {version!r} differs from {RANKING_VERSION}"
            )
        weights = configuration["weights"]
        if not isinstance(weights, Mapping) or set(weights) != set(_DEFAULT_WEIGHTS):
            raise ValueError("Ranking configuration must list every weight field")
        policy = cls(configuration["id"], dict(weights))
        if any(policy.weights[name] != weights[name] for name in weights):
            raise ValueError("Ranking configuration weights are not canonical")
        if "config_sha256" in configuration and (
            configuration["config_sha256"] != policy.receipt()["config_sha256"]
        ):
            raise ValueError("Ranking configuration digest does not match its weights")
        return policy


@dataclass(frozen=True)
class RankingSpace:
    """Caller-declared editable weights: inclusive bounds and a step per field.

    Fields absent from ``bounds`` are fixed at the default weight. Bounds belong
    to a frozen experiment plan; this module declares no default search range.
    Step membership is decided on the shortest decimal form of each value, so
    ``0.3`` lies on a ``0.1`` grid regardless of binary rounding.
    """

    bounds: Mapping[str, tuple[float, float, float]]

    def __post_init__(self) -> None:
        if not isinstance(self.bounds, Mapping) or not self.bounds:
            raise ValueError("Ranking space requires at least one editable weight field")
        if self.bounds.keys() - _DEFAULT_WEIGHTS.keys():
            raise ValueError("Unknown ranking weight field in ranking space")
        canonical = {}
        for name, bound in self.bounds.items():
            if not isinstance(bound, (tuple, list)) or len(bound) != 3 or any(
                type(value) not in (float, int) or not math.isfinite(value) for value in bound
            ):
                raise ValueError(f"Ranking space for {name} needs finite minimum, maximum and step")
            low, high, step = (float(value) for value in bound)
            if not 0 <= low <= high or step <= 0:
                raise ValueError(
                    f"Ranking space for {name} needs 0 <= minimum <= maximum, step > 0"
                )
            canonical[name] = (low + 0.0, high + 0.0, step)
        object.__setattr__(self, "bounds", MappingProxyType(dict(sorted(canonical.items()))))

    def document(self) -> dict:
        return {
            "version": RANKING_VERSION,
            "fixed": {k: v for k, v in _DEFAULT_WEIGHTS.items() if k not in self.bounds},
            "bounds": {k: list(v) for k, v in self.bounds.items()},
        }

    def digest(self) -> str:
        raw = json.dumps(self.document(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def check(self, policy: RankingPolicy) -> RankingPolicy:
        """Return ``policy`` if every weight lies inside this space, else raise."""
        if not isinstance(policy, RankingPolicy):
            raise ValueError("Ranking space checks a RankingPolicy")
        for name, value in policy.weights.items():
            if name not in self.bounds:
                if value != _DEFAULT_WEIGHTS[name]:
                    raise ValueError(f"Ranking weight for {name} is fixed in this space")
                continue
            low, high, step = self.bounds[name]
            steps = (_decimal(value) - _decimal(low)) / _decimal(step)
            if not low <= value <= high or steps != steps.to_integral_value():
                raise ValueError(
                    f"Ranking weight for {name} must lie on [{low}, {high}] in steps of {step}"
                )
        return policy


def _decimal(value: float) -> Decimal:
    return Decimal(repr(float(value)))


DEFAULT_RANKING_POLICY = RankingPolicy()

MANAGED_RANKING_POLICIES = MappingProxyType({
    "default": DEFAULT_RANKING_POLICY,
    "applicability": RankingPolicy("applicability", {"applicability": 3}),
})


def managed_ranking_policy(name: str | Mapping) -> RankingPolicy:
    """Resolve a registered policy name, or rebuild a candidate from its frozen configuration.

    A candidate cannot reuse a registered name, so a frozen name always means the
    installed registry entry and a frozen configuration always means itself.
    """
    if isinstance(name, Mapping):
        if isinstance(name.get("id"), str) and name["id"] in MANAGED_RANKING_POLICIES:
            raise ValueError(
                f"Candidate ranking policy cannot reuse the registered name {name['id']!r}"
            )
        return RankingPolicy.from_configuration(name)
    try:
        return MANAGED_RANKING_POLICIES[name]
    except (KeyError, TypeError):
        raise ValueError(
            f"Unknown frozen ranking policy {name!r}, use its original runtime"
        ) from None
