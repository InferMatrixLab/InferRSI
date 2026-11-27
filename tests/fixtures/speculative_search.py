"""Synthetic observations and identities; no model, hardware or billing evidence."""

from dataclasses import replace
from hashlib import sha256

from inferrsi.contracts.claim import Verdict
from inferrsi.harness.manager.search import search_tree as tree


def digest(text):
    return sha256(text.encode()).hexdigest()


def contract(**changes):
    return replace(tree.Contract(
        "search", tree.Context("contract", "plan", "grader", "cpu-fixture", "development",
                               "original-baseline", "quality-reference"),
        "improver-0", ("quality", "objective"), "objective", "maximize", 20, 5, 40,
    ), **changes)


def producer(snapshot="improver-0"):
    return tree.Producer(snapshot, "synthetic-producer-1", digest("context"), digest("history"))


def attempt(state, cid, check, *, dependencies=(), tag=None):
    node = tree.candidate(state, cid)
    tag = tag or str(len(state.attempts))
    return tree.Attempt(
        f"attempt-{tag}", f"execution-{tag}", f"reservation-{tag}", f"lease-{tag}",
        state.contract.search_id, cid, node.artifact_digest, check, state.contract.context,
        tuple(sorted(set(node.dependencies) | set(dependencies))),
    )


def receipt(binding, verdict=Verdict.PASS, objective=None):
    return tree.Receipt(binding, verdict, digest(f"receipt:{binding.attempt_id}"), objective)


def start(*, configuration=None, dependencies=(), root_dependencies=(), score=1):
    configuration = configuration or contract()
    root = tree.Candidate("root", digest("root"), None, producer(), root_dependencies)
    seed = tree.SearchState(configuration, "root", (root,), (), (), tuple(dependencies))
    receipts = tuple(receipt(attempt(seed, "root", check, tag=f"root-{check}"),
                             objective=score if check == configuration.objective_check else None)
                     for check in configuration.checks)
    return tree.initialize(configuration, root, receipts, dependencies=dependencies)


def add(state, cid, parent="root", *, dependencies=None, artifact_digest=None, snapshot=None):
    node = tree.Candidate(cid, artifact_digest or digest(cid), parent,
                          producer(snapshot or state.contract.improver_snapshot),
                          tree.candidate(state, parent).dependencies if dependencies is None
                          else dependencies)
    return tree.add_candidate(state, node, expected_revision=state.revision)


def observe(state, cid, check, verdict=Verdict.PASS, objective=None, *, dependencies=()):
    binding = attempt(state, cid, check, dependencies=dependencies)
    state = tree.register_attempt(state, binding, expected_revision=state.revision)
    return tree.record_receipt(state, receipt(binding, verdict, objective),
                               expected_revision=state.revision)


def complete(state, cid, score):
    state = observe(state, cid, "quality")
    return observe(state, cid, "objective", objective=score)
