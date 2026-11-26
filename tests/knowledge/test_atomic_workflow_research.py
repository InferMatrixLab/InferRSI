"""Replay the seven shared research resources read from the installed v0.3.4 wheel."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration
from inferrsi.knowledge.atomic_reader import AtomicReader, AtomPin, AtomUse
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import RELEASE, allow

COLLECTION = "inference-engine-research"
PREFIX = f"src/inferrsi/knowledge/data/skill_library/workflows/research/{COLLECTION}/"
ATOMS = Path(__file__).resolve().parents[2] / "src/inferrsi/knowledge/atoms"
PACKAGE_REVISION = "sha256:d2219d7cf339c87caac81db8a19b168eeb178f06174973b58a39facc34b4a39b"
# Independent SHA-256 values from the old rsi_evidence package's material receipts.
RELEASED = {
    "SKILL.md": "a94102df1790f51d673f2dfe4b047fa6a70b2ead2a12b1a73393ea3765984b6a",
    "references/cross-repository-mechanisms.md":
        "8eb1b8dd4807cf06df9f6fb1bf88aff9ad6112c408e377631ceada32bc56307a",
    "references/import.md": "c8a57db94768cc6cd4193932def75ba67ec453e56ee0e54f176fb82f1af53091",
    "references/model-aware-preparation.md":
        "1b117e8f3a35c25dbffc4f7d43bcef1410b2b3f51e98d53933ef3348fb3b070d",
    "references/overview.md": "4e39954ec5cc7ebfe5de1b1041762f75c5c3d381265e3711fd43ee2a7ac3d688",
    "references/repository-source-scope.md":
        "918e8358b7ef6caa2eb0dea56438c117f0737688d49d06d288ef5bd0cf668b2b",
    "references/source-manifest.json":
        "0ce1678803d1ede6b485fb6b4b1c88aba909056ee6e3b5af691899ceb2056240",
}


@pytest.fixture(scope="module")
def research_installation(tmp_path_factory):
    root = tmp_path_factory.mktemp("workflow-research")
    authors = make_author_root(root)
    release = root / "release"
    shutil.copytree(RELEASE_ROOT, release)
    refs = {}
    for original, digest in RELEASED.items():
        guide = original == "SKILL.md"
        suffix = "original" if guide else Path(original).stem
        identity = f"{COLLECTION}.{suffix}"
        descriptor = identity + ".json"
        local = Path("workflows", COLLECTION, "guide.md" if guide else original)
        raw = (ATOMS / local).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        shutil.copyfile(ATOMS / descriptor, authors / "atoms" / descriptor)
        for path in (authors / "atoms" / local, release / (PREFIX + original)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        refs["package:" + identity] = (original, raw)

    target = root / "installed"
    revision = build_generation(authors, target, source_roots={RELEASE: release}, permits=allow)
    installed = InstalledGeneration(target, expected=revision)
    uses = [AtomUse(AtomPin(ref, installed.catalog[ref]["revision"]), (ref,)) for ref in refs]
    return installed, refs, uses


def test_shared_material_preserves_original_names_bytes_and_evidence_scope(research_installation):
    installed, refs, uses = research_installation
    assert COLLECTION not in installed.skills
    assert f"package:{COLLECTION}" not in installed.catalog
    assert f"checkout:{COLLECTION}" not in installed.catalog
    result = AtomicReader(installed, permits=allow).read_group(
        uses, max_bytes=57_304, context={}, operations=("retain", "redistribute"),
    )
    assert result.receipt["status"] == "delivered" and result.receipt["body_bytes"] == 57_304
    assert [entry["ref"] for entry in result.receipt["delivered"]] == list(refs)
    manifest_name = "references/source-manifest.json"
    guide = refs[f"package:{COLLECTION}.original"][1]
    limits = (
        "The repository and framework owners retain their pinned provenance and source evidence.",
        "The collection is a portable candidate; actual GPU, native distributed and quality "
        "validation requires the target environment.",
        "No new engine or measured speedup is included.",
    )
    assert " ".join(limits).encode() in guide
    sources = {}
    for use, item, body in zip(uses, result.receipt["delivered"], result.bodies, strict=True):
        original, expected = refs[use.pin.ref]
        assert item["revision"] == use.pin.revision and body == expected
        assert item["layer"] == "L3" and item["source_range_verification"] == "verified_at_build"
        assert item["source"]["commit"] == RELEASE and item["source_byte_range"] == [0, len(body)]
        assert item["source_path"] == item["source"]["path"] == PREFIX + original
        assert item["sha256"] == item["source"]["sha256"] == RELEASED[original]
        _, bundle = installed.read_resolved(use.pin.ref, revision=use.pin.revision)
        metadata = bundle.metadata
        assert metadata["atom"]["license"] == "Apache-2.0"
        assert metadata["origin"] == ["external"]
        assert tuple(metadata["limitations"]) == limits
        assert metadata["state"] == "candidate" and metadata["empirical_validation"] == "not_run"
        assert metadata["attribution"] == [{
            "type": "git", "repo": "https://github.com/InferMatrixLab/InferRSI", "commit": RELEASE,
            "path": PREFIX + manifest_name, "sha256": RELEASED[manifest_name],
        }]
        sources[original] = body
    manifest = json.loads(sources[manifest_name])
    assert b"license: Apache-2.0" in sources["SKILL.md"]
    assert len(manifest["sources"]) == 5
    assert all(not row["locally_verified"] for row in manifest["sources"])
    vllm_omni, = (row for row in manifest["sources"] if row["skill"] == "vllm-omni")
    supplement, = vllm_omni["supplements"]
    assert not supplement["locally_verified"]
    assert "Abort acknowledgment/cleanup supplement only" in supplement["scope"]


def test_short_budget_denied_member_or_stale_pin_refuses_whole_group(research_installation):
    installed, _, uses = research_installation
    reader = AtomicReader(installed, permits=allow)
    short = reader.read_group(uses, max_bytes=57_303, context={})
    assert short.bodies == ()
    assert short.receipt == {
        "status": "over_budget", "body_bytes": 0, "delivered": [], "required_bytes": 57_304,
    }
    for index, use in enumerate(uses):
        def permits(pin, action, denied_pin=use.pin):
            return pin != denied_pin or action != "retain"

        denied = AtomicReader(installed, permits=permits).read_group(
            uses, max_bytes=57_304, context={}, operations=("retain",),
        )
        assert denied.bodies == ()
        assert denied.receipt == {"status": "permission_denied", "body_bytes": 0, "delivered": []}
        wrong = AtomUse(AtomPin(use.pin.ref, PACKAGE_REVISION), use.path)
        replaced = [*uses[:index], wrong, *uses[index + 1:]]
        stale = reader.read_group(replaced, max_bytes=57_304, context={})
        assert stale.bodies == ()
        assert stale.receipt == {"status": "unavailable_revision", "body_bytes": 0, "delivered": []}
