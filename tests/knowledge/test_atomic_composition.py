import pytest

from inferrsi.knowledge.atomic_reader import AtomicReader
from tests.fixtures.atomic_composition import composition, node
from tests.knowledge.test_atomic_reader import Snapshots, allow, excerpt


def read(source, pin, layer, budget, **context):
    return AtomicReader(source, permits=allow).read_selection(
        pin.ref, revision=pin.revision, layer=layer, max_bytes=budget, context=context,
    )


def test_required_closure_deduplicates_multiple_paths_and_accounts_for_optional_groups():
    source = Snapshots()
    rule, steps, evidence = [source.add(excerpt(layer)) for layer in ("L1", "L2", "L3")]
    nodes = {"rule": node(rule), "steps": node(steps, "rule"), "evidence": node(evidence, "rule")}
    acceptance = {"layer": "L2", "required": ["rule", "steps"], "optional": ["evidence"]}
    pin = source.add(composition(nodes, {"acceptance": acceptance}))
    result = read(source, pin, "L2", 2383)
    assert result.receipt["body_bytes"] == sum(map(len, result.bodies)) == 2383
    records = result.receipt["delivered"]
    assert [r["ref"] for r in records] == [rule.ref, steps.ref]
    assert records[0]["paths"] == [["acceptance", "rule"], ["acceptance", "steps", "rule"]]
    assert result.receipt["omissions"] == [{"path": ["acceptance", "evidence"],
                                           "reason": "over_budget"}]
    assert source.reads.count(rule) == 1
    short = read(source, pin, "L2", 2382)
    assert (short.bodies, short.receipt["status"], short.receipt["required_bytes"]) == (
        (), "over_budget", 2383,
    )
    complete = read(source, pin, "L2", 4398)
    assert [r["bytes"] for r in complete.receipt["delivered"]] == [845, 1538, 2015]
    assert ["acceptance", "evidence", "rule"] in complete.receipt["delivered"][0]["paths"]


def test_query_and_layer_select_the_frozen_release_excerpts():
    source = Snapshots()
    nodes, routes = {}, {}
    for layer, query in (("L1", "acceptance criteria"), ("L2", "acceptance criteria"),
                         ("L3", "roofline example")):
        nodes[layer] = node(source.add(excerpt(layer)))
        routes[layer] = {"layer": layer, "required": [layer], "when": {"query": [query]}}
    pin = source.add(composition(nodes, routes))
    examples = [("L1", 845, "acceptance criteria"), ("L2", 1538, "acceptance criteria"),
                ("L3", 2015, "roofline example")]
    for layer, size, query in examples:
        assert read(source, pin, layer, size, query=query).receipt["body_bytes"] == size
        assert read(source, pin, layer, size - 1, query=query).receipt["status"] == "over_budget"
    assert read(source, pin, "L3", 9000, query="acceptance criteria").receipt["status"] == (
        "not_applicable"
    )


def test_each_selected_route_must_supply_its_declared_layer():
    source = Snapshots()
    nodes = {"rule": node(source.add(excerpt("L1"))), "asset": node(source.add(excerpt("L3")))}
    routes = {name: {"layer": "L1", "required": [name]} for name in nodes}
    pin = source.add(composition(nodes, routes))
    with pytest.raises(ValueError, match="supplying L1"):
        read(source, pin, "L1", 9000)


def test_only_applicable_supersession_changes_current_routes_and_history_stays_pinned():
    source = Snapshots()
    old = source.add(excerpt("L1"))
    revised = excerpt("L1")
    revised.metadata["id"] = "current-rule"
    new = source.add(revised)
    nodes = {"old": node(old), "new": node(new)}
    routes = {"X": {"layer": "L1", "required": ["old"], "when": {"query": ["current"]}}}
    original = source.add(composition(nodes, routes))
    routes["Y"] = {"layer": "L1", "required": ["new"], "when": {"engine": {"min": "0.5"}},
                   "supersedes": ["X"], "conflicts": ["X"]}
    current = source.add(composition(nodes, routes))
    for pin, engine, expected in [(current, "v0.4", old), (current, "v0.5", new),
                                  (original, "v0.5", old)]:
        result = read(source, pin, "L1", 3000, engine=engine, query="current")
        assert [r["ref"] for r in result.receipt["delivered"]] == [expected.ref]
    routes["Y"].pop("supersedes")
    conflicting = source.add(composition(nodes, routes))
    source.reads.clear()
    conflict = read(source, conflicting, "L1", 3000, engine="v0.5", query="current")
    assert conflict.receipt["status"] == "conflict" and not conflict.bodies
    assert source.reads == [conflicting]


@pytest.mark.parametrize("bad", ["cycle", "dangling", "supersedes cycle"])
def test_invalid_composition_fails_before_releasing_any_atom(bad):
    source = Snapshots()
    nodes = {"leaf": node(source.add(excerpt("L1")))}
    routes = {"selected": {"layer": "L1", "required": ["leaf"]}}
    if bad == "supersedes cycle":
        routes["selected"]["supersedes"] = ["selected"]
    else:
        nodes["leaf"]["requires"] = ["missing" if bad == "dangling" else "leaf"]
    pin = source.add(composition(nodes, routes))
    with pytest.raises(ValueError, match="Cycle|names declared"):
        read(source, pin, "L1", 1)
    assert source.reads == [pin]
