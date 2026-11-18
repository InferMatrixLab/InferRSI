"""GVO data separation and metered group updates of frozen search roles."""

import math
import time
import uuid
from dataclasses import replace

from inferrsi.model.search_roles import Choice, finite, update

from .artifact_primitives import digest
from .search_records import decode


def choice_from_document(raw):
    return Choice(
        **(
            raw
            | {
                "options": tuple(raw["options"]),
                "features": tuple(tuple(row) for row in raw["features"]),
                "probabilities": tuple(raw["probabilities"]),
            }
        )
    )


def examples(records, *, expense_weight=0.0, elapsed_weight=0.0):
    records = tuple(records)
    if len(records) < 2:
        raise ValueError("GVO requires at least two independent complete searches")
    if finite(expense_weight) < 0 or finite(elapsed_weight) < 0:
        raise ValueError("Return penalties cannot be negative")
    identities, roots, contracts, snapshots, settings, adapters = (
        [],
        set(),
        set(),
        set(),
        set(),
        set(),
    )
    returns = []
    for record in records:
        if record["status"] != "complete" or record["pending"] is not None:
            raise ValueError("Incomplete searches cannot supply GVO returns")
        state = decode(record["tree"])
        identities.append(state.contract.search_id)
        roots.add(
            next(n.artifact_digest for n in state.candidates if n.candidate_id == state.root_id)
        )
        frozen = record["tree"]["contract"].copy()
        frozen.pop("search_id")
        contracts.add(digest(frozen))
        snapshots.add(record["snapshot"])
        settings.add(record["settings"])
        adapters.add(record["adapter"])
        returns.append(
            finite(
                record["gain"]
                - record["initial_gain"]
                - expense_weight * finite(record["spent_ms"]) / 1000
                - elapsed_weight * finite(record["elapsed_ms"]) / 1000
            )
        )
    if len(set(identities)) != len(identities) or any(
        len(values) != 1 for values in (roots, contracts, snapshots, settings, adapters)
    ):
        raise ValueError("Search group must have distinct IDs and identical starting conditions")
    if any(record["forced"] for record in records):
        raise ValueError("Forced continuations are Scorer-only, never actor group members")
    advantages = [
        finite(value - math.fsum(v for j, v in enumerate(returns) if j != i) / (len(returns) - 1))
        for i, value in enumerate(returns)
    ]
    actors, values = [], []
    for record, advantage in zip(records, advantages):
        values.extend(
            suffix_examples(record, expense_weight=expense_weight, elapsed_weight=elapsed_weight)
        )
        if not record["collect"]:
            raise ValueError("Deployment searches cannot supply on-policy actor data")
        for step in record["trace"]:
            if step["forced"]:
                raise ValueError("Forced action leaked into a natural trajectory")
            for raw in (step["choice"], *step["draft_choices"]):
                choice = choice_from_document(raw)
                if choice.sampled:
                    actors.append((choice, advantage))
    return actors, values, {"search_ids": identities, "returns": returns, "advantages": advantages}


def suffix_examples(record, *, expense_weight, elapsed_weight):
    if record["status"] != "complete" or record["pending"] is not None:
        raise ValueError("Suffix target requires a completed and settled search")
    end = record["started_at"] + record["elapsed_ms"] / 1000
    result = []
    for step in record["trace"]:
        future_cost = record["spent_ms"] - step["spent_before"]
        if future_cost < 0 or end < step["at"]:
            raise ValueError("Suffix accounting precedes its paid decision state")
        target = finite(
            record["gain"]
            - step["gain_before"]
            - expense_weight * future_cost / 1000
            - elapsed_weight * (end - step["at"])
        )
        result.append((tuple(step["features"]), target))
    return result


def train_group(
    control,
    campaign,
    records,
    snapshot,
    reference,
    *,
    cap_ms,
    learning_rate,
    expense_weight=0.0,
    elapsed_weight=0.0,
    scorer_continuations=(),
    scorer_pairs=(),
    pair_examples=(),
    **training,
):
    """One actual parameter update, durably checkpointed inside the campaign budget."""
    records = tuple(records)
    if any(record["snapshot"] != digest(snapshot.document()) for record in records):
        raise ValueError("Training checkpoint differs from collection checkpoint")
    doc = control.read(campaign)
    if doc["final_claim"] is not None:
        raise ValueError("Training is closed before final evaluation")
    if digest(doc["state"]["checkpoint"]) != digest(snapshot.document()):
        raise ValueError("Training checkpoint is no longer current")
    if any(
        op["category"] == "training" and op["status"] != "settled"
        for op in doc["operations"].values()
    ):
        raise ValueError("Unresolved training execution cannot be relaunched")
    for record in (*records, *scorer_continuations, *(r for pair in scorer_pairs for r in pair)):
        search_id = decode(record["tree"]).contract.search_id
        retained = doc["state"]["searches"].get(search_id)
        if retained is None or digest(retained) != digest(record):
            raise ValueError("Training requires the retained, settled search record")
    if pair_examples:
        raise ValueError("Unreceipted pair targets are unsupported; use paid suffix records")
    from .search_continuations import paired_targets

    pair_examples = tuple(
        paired_targets(pair, expense_weight=expense_weight, elapsed_weight=elapsed_weight)
        for pair in scorer_pairs
    )
    operation = "gvo-" + uuid.uuid4().hex
    control.claim(
        campaign,
        doc["revision"],
        operation,
        category="training",
        cap_ms=cap_ms,
        binding={
            "snapshot": digest(snapshot.document()),
            "reference": digest(reference.document()),
            "training": {
                "learning_rate": learning_rate,
                "expense_weight": expense_weight,
                "elapsed_weight": elapsed_weight,
                **training,
            },
            "searches": [decode(r["tree"]).contract.search_id for r in records],
        },
    )
    claim = control.launch(campaign, operation)
    started = time.monotonic()
    actors, values, summary = examples(
        records, expense_weight=expense_weight, elapsed_weight=elapsed_weight
    )
    for record in scorer_continuations:
        if not record["forced"]:
            raise ValueError("Additional Scorer trajectories must be explicitly marked forced")
        values.extend(
            suffix_examples(record, expense_weight=expense_weight, elapsed_weight=elapsed_weight)
        )
    trained = update(
        snapshot,
        reference,
        actors,
        values,
        pair_examples,
        learning_rate=learning_rate,
        groups=len(records),
        **training,
    )
    trained = replace(trained, origin=digest({"parent": snapshot.document(), "group": summary}))
    elapsed = max(1, math.ceil((time.monotonic() - started) * 1000))

    def checkpoint(state):
        state["checkpoint"] = trained.document()
        state.setdefault("training", []).append(
            {**summary, "operation": operation, "checkpoint": digest(trained.document())}
        )
        return state

    control.settle(
        campaign,
        operation,
        {**summary, "checkpoint": trained.document()},
        actual_ms=elapsed,
        cleanup_verified=True,
        transition=checkpoint,
    )
    if elapsed > cap_ms or time.time() >= claim["deadline"]:
        raise ValueError("Training exceeded its frozen budget")
    return trained
