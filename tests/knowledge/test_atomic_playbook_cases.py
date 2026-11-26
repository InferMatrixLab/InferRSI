"""Replay released Playbook findings and Case resource names through the installed Reader."""

import json
import shutil
from pathlib import Path

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration
from inferrsi.knowledge.decision_cards import DecisionSource
from tests.knowledge.test_atomic_casebooks import (
    ATOMS,
    FIXTURES,
    RELEASE_COMMIT,
    assert_empty,
    canonical,
    digest,
    select,
)
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import allow

BASELINE = json.loads((FIXTURES / "playbook-domain-v0.3.4.json").read_bytes())
CASES = {ref: row for ref, row in BASELINE["refs"].items() if row["kind"] == "case"}
FINDINGS = [(ref, index) for ref, row in CASES.items() for index in range(len(row["findings"]))]
LIBRARY = Path("src/inferrsi/knowledge/data/skill_library")


@pytest.fixture(scope="module")
def generation(tmp_path_factory):
    root = tmp_path_factory.mktemp("playbook-cases")
    author = make_author_root(root)
    pinned = root / "released"
    shutil.copytree(RELEASE_ROOT, pinned)
    originals = {}
    for ref, row in CASES.items():
        name = ref.partition(":")[2]
        composition = json.loads((ATOMS.parent / "compositions" / (name + ".json")).read_bytes())
        bindings = composition["case_resources"]
        assert set(bindings) == set(row["case_aliases"])
        for alias, old_path in row["case_aliases"].items():
            filename = f"{name}.{bindings[alias]}.json"
            shutil.copyfile(ATOMS / filename, author / "atoms" / filename)
            desc = json.loads((ATOMS / filename).read_bytes())
            (resource,) = desc["content"].values()
            local = Path(resource["path"])
            raw = (ATOMS / local).read_bytes()
            assert {"bytes": len(raw), "sha256": digest(raw)} == BASELINE["files"][old_path]
            source = desc["metadata"]["sources"][0]
            assert (source["commit"], source["path"]) == (
                RELEASE_COMMIT,
                (LIBRARY / old_path).as_posix(),
            )
            for dest in (author / "atoms" / local, pinned / LIBRARY / old_path):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
            originals[old_path] = raw
        shutil.copyfile(
            ATOMS.parent / "compositions" / (name + ".json"),
            author / "compositions" / (name + ".json"),
        )
    assert len(originals) == 7
    target = root / "installed"
    revision = build_generation(
        author, target, permits=allow, source_roots={RELEASE_COMMIT: pinned}
    )
    return InstalledGeneration(target, expected=revision), originals


def verify_group(installed, ref, layer, result, **selection):
    assert result.receipt["status"] == "delivered"
    size = sum(map(len, result.bodies))
    assert result.receipt["body_bytes"] == size
    assert select(installed, ref, layer, size, **selection) == result
    short = select(installed, ref, layer, size - 1, **selection)
    assert_empty(short, "over_budget")
    assert short.receipt["required_bytes"] == size
    for excluded in [ref, *(item["ref"] for item in result.receipt["delivered"])]:
        denied = select(
            installed, ref, layer, size, permits=lambda pin, op: pin.ref != excluded, **selection
        )
        assert_empty(denied, "permission_denied")
    stale = select(installed, ref, layer, size, revision=CASES[ref]["revision"], **selection)
    assert_empty(stale, "unavailable_revision")


@pytest.mark.parametrize("ref", sorted(CASES))
def test_pinned_case_aliases_permissions_and_original_procedures(generation, ref):
    installed, originals = generation
    row = CASES[ref]
    content = {alias: originals[path] for alias, path in row["case_aliases"].items()}
    record = json.loads(content["case.json"])
    _, bundle = installed.read_resolved(ref, revision=installed.catalog[ref]["revision"])
    assert bundle.content == content and bundle.dependencies == {}
    assert bundle.metadata["entrypoint"] == record["content"]
    assert bundle.metadata["required_resources"] == row["required"]
    for key in (
        "backend",
        "origin",
        "state",
        "empirical_validation",
        "applicability",
        "limitations",
        "attribution",
    ):
        assert (key in bundle.metadata) == (key in record)
        if key in record:
            assert bundle.metadata[key] == record[key]
    assert bundle.metadata["sources"][1:] == record["sources"]

    attachments = [
        content[alias]
        for alias in row["required"]
        if alias != "case.json" and not alias.endswith(".json")
    ]
    for layer in ("L0", "L2", "L3"):
        result = select(installed, ref, layer, 100_000)
        verify_group(installed, ref, layer, result)
        for entry, body in zip(result.receipt["delivered"], result.bodies, strict=True):
            source = Path(entry["source_path"]).relative_to(LIBRARY).as_posix()
            lo, hi = entry["source_byte_range"]
            assert entry["source_range_verification"] == "verified_at_build"
            assert body == originals[source][lo:hi] and digest(body) == entry["source_sha256"]
        if layer == "L0":
            identity = json.loads(b"{" + result.bodies[0] + b"}")
            assert identity == {k: record[k] for k in ("id", "kind", "backend") if k in record}
        elif layer == "L2":
            assert json.loads(b"{" + result.bodies[0] + b"}") == {"content": record["content"]}
            assert json.loads(b"{" + result.bodies[1] + b"}") == {
                "required_resources": record["required_resources"]
            }
            assert result.bodies[2:] == tuple(attachments)
        else:
            assert result.bodies == (content["case.json"], *attachments)
    for selector in (None, "id:unknown", f"case.json#/findings/{len(row['findings'])}"):
        assert_empty(select(installed, ref, "L1", 100_000, finding=selector), "not_applicable")


@pytest.mark.parametrize(("ref", "index"), FINDINGS)
def test_installed_case_reconstructs_the_released_card_and_refuses_partial_groups(
    generation, ref, index
):
    installed, originals = generation
    row = CASES[ref]
    old = row["findings"][index]
    selector = old["selector"]
    result = select(installed, ref, "L1", 100_000, finding=selector)
    verify_group(installed, ref, "L1", result, finding=selector)
    assert result.receipt["selection"]["canonical_finding"] == selector
    raw = originals[row["case_aliases"]["case.json"]]
    fields = {}
    for item, body in zip(result.receipt["delivered"], result.bodies, strict=True):
        start, end = item["source_byte_range"]
        assert body == raw[start:end]
        assert item["source_range_verification"] == "verified_at_build"
        if [start, end] == [old["start_byte"], old["end_byte"]]:
            assert digest(body) == old["span_sha256"] and "findings" not in fields
            fields["findings"] = [{} for _ in range(index)] + [json.loads(body)]
        else:
            fragment = json.loads(b"{" + body + b"}")
            assert not fields.keys() & fragment.keys()
            fields.update(fragment)
    assert sorted(fields.keys() - {"findings"}) == sorted(set(old["declared"]) - {"finding"})
    source = DecisionSource(
        ref, row["revision"], "case", "case.json", Path(row["entry_source"]).name, fields
    )
    card = source.project(finding=selector)["card"]
    assert (card["status"], card["missing_fields"]) == (old["status"], old["missing_fields"])
    assert (len(canonical(card)), digest(canonical(card))) == (
        old["card_bytes"],
        old["card_sha256"],
    )
