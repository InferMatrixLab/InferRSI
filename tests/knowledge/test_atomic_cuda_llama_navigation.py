"""Replay the v0.3.4 CUDA and llama.cpp checkouts and their caller-specific link scopes."""

import json
import shutil

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration, filesystem_root
from inferrsi.knowledge.catalog import _skill_search_source
from inferrsi.knowledge.decision_cards import DecisionSource
from tests.knowledge.test_atomic_casebooks import (
    ATOMS,
    FIXTURES,
    assert_empty,
    canonical,
    digest,
    select,
)
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import allow

RELEASE = json.loads((FIXTURES / "cuda-llama-navigation-v0.3.4.json").read_bytes())
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"


@pytest.fixture(scope="module")
def installed_owners(tmp_path_factory):
    root = filesystem_root(tmp_path_factory.mktemp("navigation-owners"))
    author = make_author_root(root)
    pinned = root / "release"
    shutil.copytree(RELEASE_ROOT, pinned)
    for ref, legacy in RELEASE["refs"].items():
        name = ref.removeprefix("checkout:") + ".json"
        spec = ATOMS.parent / "compositions" / name
        shutil.copyfile(spec, author / "compositions" / name)
        declaration = json.loads(spec.read_bytes())
        nodes = declaration["metadata"]["composition"]["nodes"]
        bindings = declaration["directory_resources"]
        assert bindings.keys() == legacy["resources"].keys()
        for path, node in bindings.items():
            name = nodes[node]["ref"].removeprefix("checkout:") + ".json"
            descriptor = ATOMS / name
            shutil.copyfile(descriptor, author / "atoms" / name)
            (resource,) = json.loads(descriptor.read_bytes())["content"].values()
            raw = (ATOMS / resource["path"]).read_bytes()
            assert digest(raw) == legacy["resources"][path]
            for dest in (pinned / (LIBRARY + path), author / "atoms" / resource["path"]):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
    target = root / "installed"
    generation = build_generation(
        author, target, permits=allow, source_roots={RELEASE["source_commit"]: pinned}
    )
    return InstalledGeneration(target, expected=generation)


@pytest.mark.parametrize("ref", RELEASE["refs"])
def test_checkout_selection_matches_released_caller(installed_owners, ref):
    reader = installed_owners
    legacy = RELEASE["refs"][ref]
    _, bundle = reader.read_resolved(ref, revision=reader.catalog[ref]["revision"])
    assert bundle.view()["resources"] == legacy["resources"]
    assert bundle.dependencies == {}
    metadata = {key: value for key, value in bundle.metadata.items() if key != "composition"}
    entry = legacy["entrypoint"]
    source = metadata["sources"][0]
    metadata["sources"] = metadata["sources"][1:]
    assert source["commit"] == RELEASE["source_commit"]
    assert source["path"] == LIBRARY + entry and source["sha256"] == legacy["resources"][entry]
    assert digest(canonical(metadata)) == legacy["metadata_sha256"]
    assert metadata["state"] == "candidate" and metadata["empirical_validation"] == "not_run"
    guide = bundle.content[entry]
    layers = {}
    for layer in ("L0", "L1", "L2", "L3"):
        selection = select(reader, ref, layer, sum(map(len, bundle.content.values())))
        size = sum(map(len, selection.bodies))
        assert (
            selection.receipt["status"] == "delivered" and selection.receipt["body_bytes"] == size
        )
        assert select(reader, ref, layer, size) == selection
        assert_empty(select(reader, ref, layer, size - 1), "over_budget")
        assert_empty(
            select(reader, ref, layer, size, revision=legacy["revision"]), "unavailable_revision"
        )
        for pin in (ref, *(item["ref"] for item in selection.receipt["delivered"])):
            assert_empty(
                select(reader, ref, layer, size, permits=lambda resource, op: resource.ref != pin),
                "permission_denied",
            )
        for item, body in zip(selection.receipt["delivered"], selection.bodies, strict=True):
            path = item["source_path"].removeprefix(LIBRARY)
            lo, hi = item["source_byte_range"]
            assert (
                item["source_path"] == LIBRARY + path
                and item["source"]["commit"] == RELEASE["source_commit"]
            )
            assert item["source_range_verification"] == "verified_at_build"
            assert body == bundle.content[path][lo:hi] and digest(body) == item["source_sha256"]
        layers[layer] = selection.bodies

    assert guide.startswith(layers["L0"][0]) and layers["L2"][0] == layers["L1"][0]
    assert b"".join(layers["L2"]) == guide
    assert layers["L3"] == tuple(bundle.content[p] for p in metadata["required_resources"])
    _, fields = _skill_search_source(layers["L1"][0].decode())
    card = DecisionSource(ref, legacy["revision"], "skill", entry, entry, fields).project()["card"]
    assert card["status"] == "partial" and card["missing_fields"] == legacy["missing_fields"]
    assert (
        len(canonical(card)) == legacy["card_bytes"]
        and digest(canonical(card)) == legacy["card_sha256"]
    )


@pytest.mark.parametrize("ref", RELEASE["refs"])
def test_checkout_guide_links_use_the_released_caller_scope(installed_owners, ref):
    legacy = RELEASE["refs"][ref]
    _, owner = installed_owners.read_resolved(
        ref, revision=installed_owners.catalog[ref]["revision"]
    )
    guide = owner.content[legacy["entrypoint"]]
    for href, link in legacy["links"].items():
        assert href.encode() in guide
        assert (link["path"] in owner.content) == link["source_can_read"]


def test_source_notes_preserve_each_upstreams_attribution_and_rights(installed_owners):
    reader = installed_owners
    llama_ref = "checkout:audit-llama-runtime-state.source-notes"
    cuda_ref = "checkout:diagnose-attention-bottlenecks.sources"
    _, llama = reader.read_resolved(llama_ref, revision=reader.catalog[llama_ref]["revision"])
    _, cuda = reader.read_resolved(cuda_ref, revision=reader.catalog[cuda_ref]["revision"])
    (credit,) = llama.metadata["attribution"]
    assert credit["commit"] == "707616feb5f379e99ff7442680a55b4a1704c7c9"
    assert len(credit["paths"]) == 19 and "LICENSE" in credit["paths"]
    assert llama.metadata["sources"][1:] == [{**credit, "revision_precision": "full"}]
    assert b"MIT, The ggml authors" in llama.content["source-notes.md"]
    assert (
        b"Third-party notices remain independently owned upstream"
        in llama.content["source-notes.md"]
    )

    assert cuda.metadata["attribution"] == []
    assert cuda.metadata["sources"][1:] == [
        {"type": "unknown", "note": "Legacy provenance remains in procedure/readsets"}
    ]
    readset = cuda.content["sources.md"]
    for evidence in (
        b"Tri Dao",
        b"Jay Shah",
        b"2205.14135v2",
        b"2307.08691v1",
        b"2407.08608v2",
        b"PDFs/text/rendered pages remain in a separate research cache",
        b"no upstream code license is assumed to cover the paper text",
    ):
        assert evidence in readset
