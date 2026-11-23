import json
import random
from dataclasses import asdict

import pytest

from inferrsi.apps.workflows.search_roles import (
    Snapshot,
    actor_gradient,
    choose,
    distribution,
    update,
)


def test_actor_gradient_matches_finite_difference_with_exploration_and_kl():
    model = Snapshot((0.2, -0.1), (0.3, -0.2), (0.0, 0.0), "initial")
    choice = choose(
        model,
        "policy",
        ("a", "b"),
        ((1.0, 0.0), (0.0, 1.0)),
        rng=random.Random(2),
        context="observed",
        collect=True,
        exploration=0.1,
    )
    reference = (0.0, 0.0)
    gradient = actor_gradient(model.policy, reference, choice, 2.0, 0.2, 0.1)
    from math import log

    def objective(weights):
        p, _ = distribution(weights, choice.features, exploration=0.1)
        q, _ = distribution(reference, choice.features, exploration=0.1)
        return 2 * p[choice.selected] / choice.probabilities[choice.selected] - 0.1 * sum(
            a * log(a / b) for a, b in zip(p, q)
        )

    for i in range(2):
        plus, minus = list(model.policy), list(model.policy)
        plus[i] += 1e-6
        minus[i] -= 1e-6
        assert gradient[i] == pytest.approx((objective(plus) - objective(minus)) / 2e-6)


def test_actual_updates_keep_policy_scorer_independent_and_reject_false_behavior():
    model = Snapshot((0.0, 0.0), (0.0, 0.0), (0.0, 0.0), "initial")
    choice = choose(
        model,
        "drafter",
        ("a", "b"),
        ((1.0, 0.0), (0.0, 1.0)),
        rng=random.Random(1),
        context="observed",
        collect=True,
    )
    trained = update(model, model, [(choice, 2.0)], [((1.0, 0.0), 4.0)], learning_rate=0.1)
    assert trained.drafter != model.drafter
    assert trained.scorer != model.scorer
    assert trained.policy == model.policy
    with pytest.raises(ValueError, match="Behavior"):
        update(trained, model, [(choice, 2.0)], [], learning_rate=0.1)
    with pytest.raises(ValueError, match="finite"):
        update(model, model, [], [((1.0, 0.0), None)], learning_rate=0.1)


def test_clipped_actor_does_not_reinforce_outside_positive_ratio_bound():
    model = Snapshot((0.0, 0.0), (0.0, 0.0), (0.0, 0.0), "initial")
    choice = choose(
        model,
        "policy",
        ("a", "b"),
        ((1.0, 0.0), (0.0, 1.0)),
        rng=random.Random(1),
        context="observed",
        collect=True,
    )
    weights = (10.0, -10.0) if choice.selected == 0 else (-10.0, 10.0)
    assert actor_gradient(weights, model.policy, choice, 1.0, 0.2, 0.0) == (0.0, 0.0)


def test_injected_roles_preserve_serialized_behavior_and_checkpoint_operations():
    model = Snapshot((0.2, -0.1), (0.3, -0.2), (0.5, -0.25), "initial")
    vectors = ((1.0, 0.0), (0.0, 1.0))
    options = dict(context="observed", collect=True, temperature=0.8, exploration=0.1)
    choice = model.choose("policy", ("a", "b"), vectors, rng=random.Random(7), **options)
    assert choice == choose(model, "policy", ("a", "b"), vectors,
                            rng=random.Random(7), **options)
    actors = [(json.loads(json.dumps(asdict(choice))), 2.0)]
    values = [(vectors[0], 4.0)]
    trained = model.train(model, actors, values, (), learning_rate=0.1)
    assert trained == update(model, model, [(choice, 2.0)], values, learning_rate=0.1)
    restored = model.restore(json.loads(json.dumps(trained.document())))
    assert restored == trained and restored != model
    assert model.predict((2.0, 4.0)) == 0.0
    assert restored.predict(vectors[0]) == trained.scorer[0]
