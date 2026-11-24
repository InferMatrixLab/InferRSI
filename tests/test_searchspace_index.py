"""SearchSpace coordinates preserve canonical owner identity and authority."""

import json
import shutil
import sys
from pathlib import Path

import pytest

from inferrsi.knowledge._knowledge_errors import MissingSkillsExtra
from inferrsi.knowledge.knowledge_find import find, load_corpus
from inferrsi.knowledge.searchspace_index import (
    CATALOG,
    INDEX,
    LIBRARY,
    MATRIX,
    SearchspaceSourceMismatch,
    StaleSearchspaceIndex,
    load_searchspace_index,
)
from tools.build_skill_coverage import render_coordinate_index

PROJECT = Path(__file__).resolve().parents[1]
GRAPH = "ascend-graph-mode"
LLAMA = "audit-llama-runtime-state"
HUSKY = "husky"
REASON = "The owner records a resource exclusion for this test."


def _read_json(path):
    return json.loads(path.read_bytes())


def _registered_path(root, name):
    return _read_json(root / CATALOG)["skills"][name]["path"] + "/SKILL.md"


def _entry(index, root, name):
    return index.entry(skill_root=root / LIBRARY, skill_id=name, path=_registered_path(root, name))


def _generate(root):
    artifact = render_coordinate_index(root).encode("utf-8")
    (root / INDEX).write_bytes(artifact)
    return artifact


@pytest.fixture(scope="module")
def real_index():
    return load_searchspace_index(PROJECT)


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout"
    (root / MATRIX).parent.mkdir(parents=True)
    shutil.copyfile(PROJECT / MATRIX, root / MATRIX)
    registry = _read_json(PROJECT / CATALOG)
    registry["skills"] = {name: registry["skills"][name] for name in (GRAPH, LLAMA, HUSKY)}
    for owner in registry["skills"].values():
        path = LIBRARY / owner["path"] / "SKILL.md"
        (root / path).parent.mkdir(parents=True)
        shutil.copyfile(PROJECT / path, root / path)
    (root / CATALOG).write_text(json.dumps(registry), encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "name,positive,negative",
    [
        (GRAPH, (("Accelerator", "Configure"), ("SSD", "Diagnose")), (("SSD", "Configure"),)),
        ("audit-h3-runtime-residency", (("RAM/Host", "Observe"), ("SSD", "Configure")),
         (("SSD", "Observe"), ("Accelerator", "Configure"))),
        (LLAMA, (("Accelerator", "Diagnose"), ("RAM/Host", "Verify")),
         (("SSD", "Optimize"), ("OS", "Optimize"))),
        ("audit-afd-p2p-exchanges", (("Accelerator", "Verify"),), (("Network", "Verify"),)),
    ],
)
def test_real_matrix_coordinates_never_cross_resource_rows(real_index, name, positive, negative):
    entry = _entry(real_index, PROJECT, name)
    assert entry.state == "covered"
    assert all(entry.matches(*pair) for pair in positive)
    assert not any(entry.matches(*pair) for pair in negative)


@pytest.mark.parametrize(
    "name,state",
    [("reason-hopper-kernels", "supplementary"), ("husky", "unknown"),
     ("audit-fixed-workload-claim", "not-applicable")],
)
def test_noncovered_owners_keep_their_distinct_states(real_index, name, state):
    entry = _entry(real_index, PROJECT, name)
    assert entry.state == state
    assert entry.coordinates == set()
    assert bool(entry.exclusion_reason) == (state == "not-applicable")


def test_lookup_requires_root_and_registered_path(real_index, tmp_path):
    path = _registered_path(PROJECT, GRAPH)
    other_root = tmp_path / "other-kb" / "skill_library"
    (other_root / path).parent.mkdir(parents=True)
    shutil.copyfile(PROJECT / LIBRARY / path, other_root / path)
    with pytest.raises(SearchspaceSourceMismatch):
        real_index.entry(skill_root=other_root, skill_id=GRAPH, path=path)
    with pytest.raises(SearchspaceSourceMismatch):
        real_index.entry(skill_root=PROJECT / LIBRARY, skill_id=GRAPH, path=f"other/{path}")


def test_only_canonical_candidate_entries_contribute_coordinates(checkout):
    path = f"../{LIBRARY.as_posix()}/{_registered_path(checkout, LLAMA)}"
    graph = f"../{LIBRARY.as_posix()}/{_registered_path(checkout, GRAPH)}"
    fake = f"../other/{LIBRARY.as_posix()}/{_registered_path(checkout, LLAMA)}"
    # The identically named target really exists, but outside the registry's source.
    alternative = (checkout / "docs" / fake).resolve()
    alternative.parent.mkdir(parents=True)
    shutil.copyfile(checkout / LIBRARY / _registered_path(checkout, LLAMA), alternative)
    row = (
        f"| **Observe / Profile** | `{LLAMA}` | [{GRAPH}]({graph}) (see [{LLAMA}]({path})); "
        f"[owner map]({path}); [{LLAMA}]({path}#choose-the-scope); [{LLAMA}]({fake}) "
        f"| `{LLAMA}` | [{LLAMA}]({path}) | — |"
    )
    matrix = checkout / MATRIX
    matrix.write_text(matrix.read_text(encoding="utf-8").replace(
        "|---|---|---|---|---|---|", f"|---|---|---|---|---|---|\n{row}", 1,
    ), encoding="utf-8")
    _generate(checkout)
    index = load_searchspace_index(checkout)
    for stage in ("Observe", "Profile"):
        assert _entry(index, checkout, GRAPH).matches("Accelerator", stage)
        assert not _entry(index, checkout, LLAMA).matches("Accelerator", stage)


@pytest.mark.parametrize("changed", (MATRIX, CATALOG))
def test_index_rejects_stale_matrix_or_registry(checkout, changed):
    artifact = _generate(checkout)
    path = checkout / changed
    if changed == CATALOG:
        registry = _read_json(path)
        registry["skills"][GRAPH]["backend"] = "common"
        path.write_text(json.dumps(registry), encoding="utf-8")
    else:
        path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(StaleSearchspaceIndex):
        load_searchspace_index(checkout)
    assert (checkout / INDEX).read_bytes() == artifact


def test_index_rejects_an_artifact_declaring_another_source(checkout):
    _generate(checkout)
    artifact = _read_json(checkout / INDEX)
    artifact["source"]["catalog_path"] = "other/skill-index.json"
    (checkout / INDEX).write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(SearchspaceSourceMismatch):
        load_searchspace_index(checkout)


def test_verified_sources_do_not_hide_a_wrong_generated_skill_path(checkout):
    artifact = json.loads(_generate(checkout))
    artifact["skills"][GRAPH]["path"] = f"other/{GRAPH}/SKILL.md"
    (checkout / INDEX).write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(StaleSearchspaceIndex, match="path disagrees"):
        load_searchspace_index(checkout)


@pytest.mark.parametrize("tamper", ("coordinate", "state"))
def test_verified_sources_do_not_hide_forged_coordinates_or_state(checkout, tamper):
    artifact = json.loads(_generate(checkout))
    row = artifact["skills"][GRAPH]
    if tamper == "coordinate":
        row["coordinates"].append(["SSD", "Configure"])
    else:
        row.update(state="unknown", coordinates=[])
    (checkout / INDEX).write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(StaleSearchspaceIndex, match="entries disagree with canonical sources"):
        load_searchspace_index(checkout)


def test_index_reports_missing_pyyaml_and_regular_find_still_works(checkout, monkeypatch):
    _generate(checkout)
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.delenv("INFERRSI_LAUNCHER", raising=False)
    with pytest.raises(MissingSkillsExtra, match=r"pip install '<inferrsi-checkout>\[skills\]'"):
        load_searchspace_index(checkout)

    result = find("weight-loading-optimization", load_corpus(), limit=1)
    assert result["items"][0]["id"] == "weight-loading-optimization"
    assert "unreadable" not in result["items"][0]


def test_foreign_supplementary_link_cannot_change_a_registered_skill_state(checkout):
    target = f"../other/{LIBRARY.as_posix()}/{_registered_path(checkout, HUSKY)}"
    matrix = checkout / MATRIX
    matrix.write_bytes(matrix.read_bytes() + (
        "\n## Test guidance\n\n"
        "| Resource | Stage | Owner |\n"
        "|---|---|---|\n"
        f"| Accelerator | Verify | [{HUSKY}]({target}) |\n"
    ).encode("utf-8"))
    _generate(checkout)
    foreign = (checkout / "docs" / target).resolve()
    foreign.parent.mkdir(parents=True)
    shutil.copyfile(checkout / LIBRARY / _registered_path(checkout, HUSKY), foreign)
    assert _entry(load_searchspace_index(checkout), checkout, HUSKY).state == "unknown"


@pytest.mark.parametrize("legacy_sidecar", (False, True))
def test_exclusion_metadata_alone_stales_the_index_and_yields_conflict(checkout, legacy_sidecar):
    path = checkout / LIBRARY / _registered_path(checkout, GRAPH)
    if legacy_sidecar:
        path.write_bytes(f"---\nname: {GRAPH}\ndescription: Legacy Skill\n---\n".encode())
        path.with_name("metadata.json").write_text("{}", encoding="utf-8")
    _generate(checkout)
    old = load_searchspace_index(checkout)
    old_fingerprints = _read_json(checkout / INDEX)["source"]
    assert _entry(old, checkout, GRAPH).matches("Accelerator", "Configure")

    if legacy_sidecar:
        path.with_name("metadata.json").write_text(
            json.dumps({"searchspace_not_applicable": REASON}), encoding="utf-8",
        )
    else:
        initial = path.read_bytes()
        exclusion = f'      "searchspace_not_applicable": "{REASON}",\n'.encode()
        path.write_bytes(initial.replace(b"    {\n", b"    {\n" + exclusion, 1))
    with pytest.raises(StaleSearchspaceIndex):
        load_searchspace_index(checkout)

    _generate(checkout)
    fingerprints = _read_json(checkout / INDEX)["source"]
    assert fingerprints["matrix_sha256"] == old_fingerprints["matrix_sha256"]
    assert fingerprints["catalog_sha256"] == old_fingerprints["catalog_sha256"]
    assert fingerprints["metadata_sha256"] != old_fingerprints["metadata_sha256"]
    entry = _entry(load_searchspace_index(checkout), checkout, GRAPH)
    assert entry.state == "conflict"
    assert entry.exclusion_reason == REASON
    assert not entry.matches("Accelerator", "Configure")
    assert entry.coordinates == set()


def test_generated_file_matches_canonical_sources():
    assert render_coordinate_index(PROJECT).encode("utf-8") == (PROJECT / INDEX).read_bytes()


def test_generation_is_checkout_location_independent(checkout, tmp_path):
    other = tmp_path / "another checkout"
    shutil.copytree(checkout, other)
    assert _generate(checkout) == _generate(other)
