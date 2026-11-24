"""Explicit JSON encoding of immutable search controls, without executable payloads."""

from dataclasses import asdict

from inferrsi.contracts.claim import Verdict

from . import search_tree as tree


def encode(record):
    # Preserve existing wire identities for evaluators without an experiment binding.
    def retained(fields):
        return {k: v for k, v in fields if k != "experiment_identity" or v is not None}

    return asdict(record, dict_factory=retained)


def initial_conditions(record):
    """Reject legacy records whose actual starting evidence was never retained."""
    value = record.get("initial_conditions")
    if not isinstance(value, str) or not value:
        raise ValueError("Legacy search lacks initial evidence identity; start a fresh search")
    return value


def decode(raw):
    def dependencies(values):
        return tuple(tree.Dependency(**value) for value in values)

    def attempt(value):
        return tree.Attempt(
            **(
                value
                | {
                    "context": tree.Context(**value["context"]),
                    "dependencies": dependencies(value["dependencies"]),
                }
            )
        )

    contract = tree.Contract(
        **(raw["contract"] | {"context": tree.Context(**raw["contract"]["context"])})
    )
    nodes = tuple(
        tree.Candidate(
            **(
                value
                | {
                    "producer": tree.Producer(**value["producer"]),
                    "dependencies": dependencies(value["dependencies"]),
                }
            )
        )
        for value in raw["candidates"]
    )
    return tree.SearchState(
        contract,
        raw["root_id"],
        nodes,
        tuple(attempt(value) for value in raw["attempts"]),
        tuple(
            tree.Receipt(
                attempt(value["attempt"]),
                Verdict(value["verdict"]),
                value["evidence_digest"],
                value["objective"],
            )
            for value in raw["receipts"]
        ),
        dependencies(raw["dependencies"]),
        raw["revision"],
    )
