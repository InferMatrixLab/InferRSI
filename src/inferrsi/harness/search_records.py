"""Explicit JSON encoding of immutable search controls, without executable payloads."""

from dataclasses import asdict

from inferrsi.contracts.claim import Verdict

from . import search_tree as tree


def encode(state):
    return asdict(state)


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
