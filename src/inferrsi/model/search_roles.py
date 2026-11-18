"""Trainable finite-edit Drafter, independent Policy and linear continuation Scorer.

The reference CPU model samples tokens from a frozen vocabulary of permitted edit
operators. It is not a language-model fine-tuner. Hosts may supply another role
implementation, but must preserve observed contexts, masks and behavior laws.
"""

from dataclasses import asdict, dataclass, replace
from math import exp, fsum, isfinite, log


def finite(value):
    if type(value) not in (float, int) or not isfinite(value):
        raise ValueError("Expected a finite numeric observation")
    return value


def dot(left, right):
    if len(left) != len(right) or not left:
        raise ValueError("Role feature dimension mismatch")
    return finite(fsum(finite(a) * finite(b) for a, b in zip(left, right)))


def distribution(weights, features, temperature=1.0, exploration=0.0):
    if finite(temperature) <= 0 or not 0 <= finite(exploration) < 1 or not features:
        raise ValueError("Invalid sampling law")
    logits = [dot(weights, row) / temperature for row in features]
    scale = max(logits)
    raw = [exp(value - scale) for value in logits]
    total = fsum(raw)
    soft = tuple(value / total for value in raw)
    probabilities = tuple((1 - exploration) * p + exploration / len(soft) for p in soft)
    if any(p <= 0 for p in probabilities):
        raise ValueError("Sampling law underflows; rescale model or increase exploration")
    return probabilities, soft


@dataclass(frozen=True)
class Snapshot:
    drafter: tuple[float, ...]
    policy: tuple[float, ...]
    scorer: tuple[float, ...]
    origin: str

    def __post_init__(self):
        for name in ("drafter", "policy", "scorer"):
            values = tuple(getattr(self, name))
            if not values:
                raise ValueError("Empty role parameters")
            for value in values:
                finite(value)
            object.__setattr__(self, name, values)
        if not self.origin:
            raise ValueError("Checkpoint provenance is required")

    def document(self):
        return {
            **asdict(self),
            "drafter": list(self.drafter),
            "policy": list(self.policy),
            "scorer": list(self.scorer),
        }


@dataclass(frozen=True)
class Choice:
    role: str
    options: tuple[str, ...]
    features: tuple[tuple[float, ...], ...]
    selected: int
    probabilities: tuple[float, ...]
    temperature: float
    exploration: float
    context: str
    sampled: bool = True

    def __post_init__(self):
        if (
            self.role not in ("drafter", "policy")
            or not self.context
            or len(set(self.options)) != len(self.options)
            or not 0 <= self.selected < len(self.options)
            or len(self.options) != len(self.features)
            or len(self.options) != len(self.probabilities)
            or abs(fsum(self.probabilities) - 1) > 1e-10
            or any(not 0 < finite(p) <= 1 for p in self.probabilities)
        ):
            raise ValueError("Invalid recorded role choice")


def choose(
    snapshot, role, options, features, *, rng, context, collect, temperature=1.0, exploration=0.0
):
    probabilities, _ = distribution(getattr(snapshot, role), features, temperature, exploration)
    if collect or role == "drafter":
        selected = rng.choices(range(len(options)), weights=probabilities, k=1)[0]
    else:
        selected = max(range(len(options)), key=lambda index: probabilities[index])
    return Choice(
        role,
        tuple(options),
        tuple(tuple(row) for row in features),
        selected,
        probabilities,
        temperature,
        exploration,
        context,
        sampled=collect or role == "drafter",
    )


def actor_gradient(weights, reference, choice, advantage, clip, kl_weight):
    """Gradient ascent for the clipped surrogate minus KL to a frozen reference."""
    probabilities, soft = distribution(
        weights, choice.features, choice.temperature, choice.exploration
    )
    refs, _ = distribution(reference, choice.features, choice.temperature, choice.exploration)
    ratio = finite(probabilities[choice.selected] / choice.probabilities[choice.selected])
    active = not ((advantage > 0 and ratio > 1 + clip) or (advantage < 0 and ratio < 1 - clip))
    means = [fsum(p * row[d] for p, row in zip(soft, choice.features)) for d in range(len(weights))]
    jacobian = [
        tuple(
            (1 - choice.exploration) * p * (row[d] - means[d]) / choice.temperature
            for d in range(len(weights))
        )
        for p, row in zip(soft, choice.features)
    ]
    return tuple(
        finite(
            (
                advantage / choice.probabilities[choice.selected] * jacobian[choice.selected][d]
                if active
                else 0
            )
            - kl_weight
            * fsum(
                jacobian[i][d] * (log(probabilities[i] / refs[i]) + 1)
                for i in range(len(probabilities))
            )
        )
        for d in range(len(weights))
    )


def update(
    snapshot,
    reference,
    actor_examples,
    value_examples,
    pair_examples=(),
    *,
    learning_rate,
    clip=0.2,
    kl_weight=0.01,
    pair_weight=1.0,
    epochs=1,
    groups=1,
):
    """Update actual parameters; forced trajectories belong only in value/pair examples.

    Actor examples are (Choice, whole-search advantage), value examples are
    (features, realized suffix return), pairs are (left features, right features,
    paid observed return difference). Missing targets are rejected, never imputed.
    """
    if (
        finite(learning_rate) <= 0
        or not 0 < finite(clip) < 1
        or finite(kl_weight) < 0
        or finite(pair_weight) < 0
        or type(epochs) is not int
        or epochs < 1
        or type(groups) is not int
        or groups < 1
    ):
        raise ValueError("Invalid frozen training settings")
    actors, values, pairs = tuple(actor_examples), tuple(value_examples), tuple(pair_examples)
    for choice, advantage in actors:
        finite(advantage)
        if not choice.sampled:
            raise ValueError("Deterministic actions cannot enter the actor objective")
        replay, _ = distribution(
            getattr(snapshot, choice.role), choice.features, choice.temperature, choice.exploration
        )
        if any(abs(a - b) > 1e-10 for a, b in zip(replay, choice.probabilities)):
            raise ValueError("Behavior probabilities do not match the frozen checkpoint")
    current = snapshot
    for _ in range(epochs):
        changed = {}
        for role in ("drafter", "policy"):
            weights = getattr(current, role)
            gradients = [
                actor_gradient(
                    weights, getattr(reference, role), choice, advantage, clip, kl_weight
                )
                for choice, advantage in actors
                if choice.role == role
            ]
            changed[role] = tuple(
                finite(w + learning_rate * fsum(g[d] for g in gradients) / groups)
                for d, w in enumerate(weights)
            )
        weights = current.scorer
        gradient = [0.0] * len(weights)
        for features, target in values:
            error = dot(weights, features) - finite(target)
            for d in range(len(weights)):
                gradient[d] += 2 * error * features[d] / len(values)
        for left, right, target in pairs:
            delta = tuple(a - b for a, b in zip(left, right))
            error = dot(weights, delta) - finite(target)
            for d in range(len(weights)):
                gradient[d] += pair_weight * 2 * error * delta[d] / len(pairs)
        changed["scorer"] = tuple(finite(w - learning_rate * g) for w, g in zip(weights, gradient))
        current = replace(current, **changed)
    return current
