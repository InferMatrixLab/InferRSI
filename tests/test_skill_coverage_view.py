"""The reverse coverage view stays reconciled with the registry it indexes."""

import hashlib
import json
from pathlib import Path

from tools import build_skill_coverage as coverage

PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / coverage.OUTPUT
LIBRARY = PROJECT / coverage.LIBRARY


def _registry():
    return json.loads((PROJECT / coverage.INDEX).read_text(encoding="utf-8"))["skills"]


def test_view_lists_every_registered_skill_exactly_once():
    registry = _registry()
    rows, unregistered, documents, dead, _ = coverage.collect(PROJECT)
    assert [row["id"] for row in rows] == sorted(registry)
    assert len({row["id"] for row in rows}) == len(rows)
    # Unregistered documents are listed separately and never enter the count.
    assert not set(unregistered) & set(registry)
    assert len(rows) + len(unregistered) == documents
    assert dead == []


def test_view_rows_copy_owner_state_without_promotion():
    registry = _registry()
    rows, _, _, _, _ = coverage.collect(PROJECT)
    for row in rows:
        assert row["task"]
        if not row["sidecar"]:
            # No sidecar means no owner state to copy; it must stay unknown.
            assert row["status"] == "unknown"
            assert row["validation"] == "unknown"
            continue
        sidecar = json.loads(
            (LIBRARY / registry[row["id"]]["path"] / "metadata.json").read_text(encoding="utf-8")
        )
        # The projection equals its owner, including a state other than not_run.
        assert row["status"] == sidecar.get("status", "unknown")
        assert row["validation"] == sidecar.get("empirical_validation", "unknown")


def test_non_default_owner_state_is_projected_not_downgraded():
    """A sidecar may record a validation state other than not_run."""
    registry = _registry()
    rows, _, _, _, _ = coverage.collect(PROJECT)
    by_id = {row["id"]: row for row in rows}
    non_default = {}
    for name, entry in registry.items():
        sidecar = LIBRARY / entry["path"] / "metadata.json"
        if not sidecar.is_file():
            continue
        validation = json.loads(sidecar.read_text(encoding="utf-8")).get("empirical_validation")
        if validation not in (None, "not_run"):
            non_default[name] = validation
    assert non_default, "expected at least one non-not_run sidecar at this revision"
    for name, validation in non_default.items():
        assert by_id[name]["validation"] == validation


def test_layer_stages_are_unioned_not_repeated():
    rows, _, _, _, _ = coverage.collect(PROJECT)
    for row in rows:
        for stages, _ in row["layers"].values():
            assert len(stages) == len(set(stages))


def test_supplementary_resource_tables_count_as_recorded_guidance():
    rows, _, _, _, _ = coverage.collect(PROJECT)
    by_id = {row["id"]: row for row in rows}
    # These are mapped by a supplementary Resource table, not a numbered layer.
    for name in ("reason-hopper-kernels", "generation-cache-lifecycle"):
        assert name in by_id, f"{name} is not registered at this revision"
        assert by_id[name]["layers"], f"{name} lost its supplementary mapping"
        assert coverage.guidance_only(by_id[name])
        assert "no-SearchSpace-layer" not in coverage.gaps(by_id[name])


def test_input_digest_is_checkout_location_independent(tmp_path):
    source = tmp_path / "a"
    copy = tmp_path / "b"
    for root in (source, copy):
        (root / "docs").mkdir(parents=True)
        (root / "docs" / "x.md").write_text("same bytes\n", encoding="utf-8")
    left = coverage.input_digest(source, [source / "docs" / "x.md"])
    right = coverage.input_digest(copy, [copy / "docs" / "x.md"])
    assert left == right


def test_input_digest_orders_by_relative_path_not_by_path_object(tmp_path):
    """Path objects sort case-folded on Windows and case-sensitively on POSIX.

    The expected digest is built here from the documented contract — relative
    POSIX path, a NUL separator, then the SHA-256 of the bytes, in sorted path
    order — rather than by calling the function twice. Comparing two calls
    would pass on either host even with the old `sorted(paths)`, because the
    two inputs collapse to whichever order that host happens to produce.
    """
    root = tmp_path / "repo"
    skill = root / "x" / "SKILL.md"
    sidecar = root / "x" / "metadata.json"
    skill.parent.mkdir(parents=True)
    # newline="" keeps the bytes identical on a CRLF-translating platform.
    skill.write_text("{}\n", encoding="utf-8", newline="")
    sidecar.write_text("{}\n", encoding="utf-8", newline="")

    body = hashlib.sha256(b"{}\n").digest()
    expected = hashlib.sha256()
    for relative in ("x/SKILL.md", "x/metadata.json"):
        expected.update(relative.encode("utf-8"))
        expected.update(b"\0")
        expected.update(body)

    assert "SKILL.md" < "metadata.json"  # relativePOSIX order, both platforms
    assert coverage.input_digest(root, [skill, sidecar]) == expected.hexdigest()
    assert coverage.input_digest(root, [sidecar, skill]) == expected.hexdigest()


def test_regeneration_is_byte_identical():
    first = coverage.collect(PROJECT)
    second = coverage.collect(PROJECT)
    assert first[-1] == second[-1], "input digest is not stable"
    assert coverage.render(*first) == coverage.render(*second)


def test_committed_view_matches_its_sources():
    rendered = coverage.render(*coverage.collect(PROJECT))
    assert OUTPUT.read_text(encoding="utf-8") == rendered, (
        "docs/skill-coverage.md is stale; rerun tools/build_skill_coverage.py"
    )


def test_absent_and_empty_applicability_are_both_unknown_but_distinct_from_na():
    """Absent, empty and not-applicable are three states, not one blank cell."""
    assert coverage.conditions({}) == {
        "scope": None, "not_applicable": [], "dimensions": 0,
    }
    assert coverage.conditions({"applicability": {}})["dimensions"] == 0
    na = coverage.conditions({
        "applicability": {"scope": "x", "hardware": coverage.NOT_APPLICABLE},
    })
    assert na["scope"] == "x"
    assert na["not_applicable"] == ["hardware"]
    assert coverage.conditions({
        "applicability": {"hardware": [coverage.NOT_APPLICABLE]},
    })["not_applicable"] == ["hardware"]


def test_gaps_separate_unknown_applicability_from_a_declared_statement():
    base = {"layers": {}, "rm": [], "sidecar": True, "eval": [],
            "conditions": coverage.conditions({"applicability": {"scope": "x"}})}
    assert "no-applicability" not in coverage.gaps(base)
    # A not-applicable-only declaration is a statement, not a missing field.
    stated = dict(base, conditions=coverage.conditions({
        "applicability": {"hardware": coverage.NOT_APPLICABLE},
    }))
    assert "no-applicability" not in coverage.gaps(stated)
    blank = dict(base, conditions=coverage.conditions({"applicability": {}}))
    assert "no-applicability" in coverage.gaps(blank)
    absent = dict(base, conditions=coverage.conditions({}))
    assert "no-applicability" in coverage.gaps(absent)


def test_declared_workflow_conditions_reach_the_rows():
    """The five workflow sidecars expose typed conditions, not only a scope."""
    rows, _, _, _, _ = coverage.collect(PROJECT)
    by_id = {row["id"]: row for row in rows}
    for name in (
        "cite-check-downstream-pr", "claim-contract", "competitor-scan",
        "draft-acceptance-issue", "rsi-evidence", "npu-skill-factory",
    ):
        assert name in by_id, f"{name} is not registered at this revision"
        row = by_id[name]
        assert row["conditions"]["scope"], f"{name} lost its declared scope"
        assert row["typed_conditions"] == [
            "failure_modes", "input_contract", "produced_artifact", "refusal_point",
        ], f"{name} does not carry the workflow shape"
        assert row["advice"], f"{name} declares no recommendations"
        assert "no-applicability" not in coverage.gaps(row)


def test_rendered_view_shows_the_collected_contract_and_advice_summary():
    """The Markdown projection must consume what collect() gathers per row."""
    rows, _, _, _, _ = coverage.collect(PROJECT)
    rendered = coverage.render(rows, [], 0, [], "digest")
    workflow = next(row for row in rows if row["id"] == "claim-contract")
    line = next(
        text for text in rendered.splitlines() if "workflows/claim-contract/SKILL.md" in text
    )
    assert "failure_modes, input_contract, produced_artifact, refusal_point" in line
    assert f"{workflow['advice']} advice" in line
    # A skill without these fields keeps one empty marker, not a blank cell.
    silent = next(row for row in rows if not row["typed_conditions"] and row["advice"] is None)
    silent_line = next(
        text for text in rendered.splitlines()
        if f"skill_library/{silent['path']}/SKILL.md" in text
    )
    assert "| — |" in silent_line


def test_na_only_declaration_keeps_its_marker_without_a_scope():
    """An N/A dimension is a statement even when no scope is named."""
    rows = [{
        "id": "probe", "path": "methods/probe", "backend": "common",
        "category": "methods", "task": "probe", "status": "candidate",
        "validation": "not_run", "readsets": 0, "sidecar": True,
        "conditions": coverage.conditions({"applicability": {"hardware": "not-applicable"}}),
        "typed_conditions": [], "advice": 0, "layers": {}, "other_ss": [],
        "rm": [], "eval": [],
    }]
    rendered = coverage.render(rows, [], 0, [], "digest")
    line = next(text for text in rendered.splitlines() if "methods/probe/SKILL.md" in text)
    assert "N/A: hardware" in line
    assert "— (declared, no scope)" in line
    assert "0 advice" in line


def test_list_valued_scope_is_rendered_not_treated_as_missing(tmp_path):
    """The catalog accepts a string list for scope; the view must show it."""
    library = tmp_path / coverage.LIBRARY
    skill = library / "methods" / "probe"
    skill.mkdir(parents=True)
    (library / "skill-index.json").write_text(json.dumps({
        "schema_version": 1,
        "skills": {"probe": {"path": "methods/probe", "backend": "common"}},
    }), encoding="utf-8")
    (skill / "SKILL.md").write_text(
        "---\nname: probe\ndescription: probe\n---\nBody\n", encoding="utf-8"
    )
    (skill / "metadata.json").write_text(
        json.dumps({"applicability": {"scope": ["serving", "kv-cache"]}}), encoding="utf-8"
    )
    for matrix in (coverage.SEARCHSPACE, coverage.REFERENCE):
        (tmp_path / matrix).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / matrix).write_text("", encoding="utf-8")
    collected = coverage.collect(tmp_path)
    line = next(
        text for text in coverage.render(*collected).splitlines()
        if "methods/probe/SKILL.md" in text
    )
    assert "serving; kv-cache" in line
    assert "no scope" not in line


def test_applicability_is_descriptive_and_never_promotes_validation():
    """Filling conditions must not raise locally_verified or change declared state."""
    from inferrsi.skill_catalog import skill_metadata

    rows, _, _, _, _ = coverage.collect(PROJECT)
    described = [row for row in rows if row["typed_conditions"]]
    assert described, "expected at least one workflow sidecar at this revision"
    for row in described:
        metadata = skill_metadata(LIBRARY, row["id"])
        assert metadata.get("verification", {}).get("locally_verified", False) is False
        assert row["validation"] == metadata.get("empirical_validation", "unknown")


def test_recommendations_default_only_when_the_sidecar_is_silent():
    from tools import build_skill_index as index_builder

    assert index_builder.recommendations({}) == index_builder.DEFAULT_RECOMMENDATIONS
    # An explicit empty list is a statement, so it must not fall back.
    assert index_builder.recommendations({"recommendations": []}) == []
    own = ["Read the acceptance issue first."]
    assert index_builder.recommendations({"recommendations": own}) == own
