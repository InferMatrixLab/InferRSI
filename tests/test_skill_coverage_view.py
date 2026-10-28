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
