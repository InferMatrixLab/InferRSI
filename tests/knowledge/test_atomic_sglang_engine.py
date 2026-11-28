import json
import shutil

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_composition import AtomPin, AtomUse
from inferrsi.knowledge.atomic_generation import InstalledGeneration, filesystem_root
from inferrsi.knowledge.atomic_reader import AtomicReader
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

NAME = "audit-sglang-diffusion-lifetimes"
REF = f"checkout:{NAME}"
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"
FIXTURE = json.loads((FIXTURES / "sglang-engine-v0.3.4.json").read_text(encoding="utf-8"))


def check_installed(installed, originals):
    old = FIXTURE["old_checkout"]
    entrypoint = old["entrypoint"]
    guide = originals[entrypoint]
    current = installed.catalog[REF]["revision"]
    _, bundle = installed.read_resolved(REF, revision=current)
    assert bundle.dependencies == old["dependencies"] == {}
    assert bundle.metadata["state"] == "candidate"
    assert bundle.metadata["empirical_validation"] == "not_run"
    assert NAME not in installed.skills
    assert "checkout:sglang" not in installed.catalog

    layers, receipts = {}, {}
    for level in ("L0", "L1", "L2", "L3"):
        first = select(installed, REF, level, sum(map(len, originals.values())), revision=current)
        assert first.receipt["status"] == "delivered"
        budget = sum(map(len, first.bodies))
        assert first.receipt["body_bytes"] == budget
        exact = select(installed, REF, level, budget, revision=current)
        assert exact == first
        short = select(installed, REF, level, budget - 1, revision=current)
        assert_empty(short, "over_budget")
        assert short.receipt["required_bytes"] == budget
        stale = select(installed, REF, level, budget, revision=old["revision"])
        assert_empty(stale, "unavailable_revision")
        refusals = {}
        for receipt, body in zip(exact.receipt["delivered"], exact.bodies, strict=True):
            denied_ref = receipt["ref"]
            denied = select(
                installed, REF, level, budget, revision=current,
                permits=lambda pin, operation: pin.ref != denied_ref,
            )
            assert_empty(denied, "permission_denied")
            refusals[denied_ref] = denied.receipt
            logical = receipt["source_path"].removeprefix(LIBRARY)
            start, stop = receipt["source_byte_range"]
            assert body == originals[logical][start:stop]
            assert receipt["source_sha256"] == digest(body)
            assert receipt["source_range_verification"] == "verified_at_build"
            assert receipt["source"]["commit"] == FIXTURE["release_commit"]
        layers[level] = exact
        receipts[level] = {
            "delivered": exact.receipt, "short": short.receipt,
            "stale": stale.receipt, "denied": refusals,
        }

    (navigation,) = layers["L0"].bodies
    (decision,) = layers["L1"].bodies
    assert guide.startswith(navigation)
    _, fields = _skill_search_source(decision.decode())
    source = DecisionSource(REF, old["revision"], "skill", entrypoint, entrypoint, fields)
    card = source.project()["card"]
    assert card["status"] == old["status"]
    assert card["missing_fields"] == old["missing_fields"]
    serialized = canonical(card)
    assert (len(serialized), digest(serialized)) == (old["card_bytes"], old["card_sha256"])
    assert layers["L2"].bodies[0] == decision
    assert b"".join(layers["L2"].bodies) == guide
    paths = [row["source_path"].removeprefix(LIBRARY) for row in layers["L3"].receipt["delivered"]]
    assert paths == old["required_resources"]
    assert layers["L3"].bodies == tuple(originals[path] for path in paths)
    assert bundle.content == {path: originals[path] for path in paths}

    private = {path: row for path, row in FIXTURE["files"].items() if path not in paths}
    uses = tuple(
        AtomUse(AtomPin(row["ref"], installed.catalog[row["ref"]]["revision"]), (row["ref"],))
        for row in private.values()
    )
    budget = sum(row["bytes"] for row in private.values())
    reader = AtomicReader(installed, permits=allow)
    group = reader.read_group(uses, max_bytes=budget, context={})
    assert group.receipt["status"] == "delivered"
    assert group.receipt["body_bytes"] == budget
    source_paths = [LIBRARY + path for path in private]
    assert [item["source_path"] for item in group.receipt["delivered"]] == source_paths
    assert group.bodies == tuple(originals[path] for path in private)
    for receipt, body in zip(group.receipt["delivered"], group.bodies, strict=True):
        assert receipt["source"]["commit"] == FIXTURE["release_commit"]
        assert receipt["source_byte_range"] == [0, len(body)]
        assert receipt["source_sha256"] == digest(body)
        assert receipt["source_range_verification"] == "verified_at_build"
    short = reader.read_group(uses, max_bytes=budget - 1, context={})
    assert_empty(short, "over_budget")
    denied_ref = uses[-1].pin.ref
    denying_reader = AtomicReader(installed, permits=lambda pin, operation: pin.ref != denied_ref)
    denied = denying_reader.read_group(uses, max_bytes=budget, context={})
    assert_empty(denied, "permission_denied")
    stale_uses = uses[:-1] + (AtomUse(AtomPin(denied_ref, old["revision"]), (denied_ref,)),)
    stale = reader.read_group(stale_uses, max_bytes=budget, context={})
    assert_empty(stale, "unavailable_revision")
    receipts["package_only"] = {
        "delivered": group.receipt,
        "short": short.receipt,
        "stale": stale.receipt,
        "denied": denied.receipt,
    }
    return receipts


def test_installed_sglang_preserves_checkout_and_original_package_resources(tmp_path):
    root = filesystem_root(tmp_path)
    author = make_author_root(root)
    pinned = root / "sglang-release"
    shutil.copytree(RELEASE_ROOT, pinned)
    originals = {}
    for logical, record in FIXTURE["files"].items():
        body = (ATOMS / record["body"]).read_bytes()
        assert len(body) == record["bytes"]
        assert digest(body) == record["sha256"]
        originals[logical] = body
        source = pinned / LIBRARY / logical
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(body)
        target = author / "atoms" / record["body"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        shutil.copyfile(ATOMS / record["descriptor"], author / "atoms" / record["descriptor"])

    filename = f"{NAME}.json"
    shutil.copyfile(ATOMS.parent / "compositions" / filename, author / "compositions" / filename)
    installed_root = root / "installed-sglang"
    seal = build_generation(
        author, installed_root, permits=allow, source_roots={FIXTURE["release_commit"]: pinned},
    )
    check_installed(InstalledGeneration(installed_root, expected=seal), originals)
