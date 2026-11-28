"""Preserve the released Husky package originals within their source boundary."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import PUBLIC_TASKS, InstalledGeneration
from inferrsi.knowledge.atomic_reader import AtomicReader, AtomPin, AtomUse
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import RELEASE, allow

ATOMS = Path(__file__).resolve().parents[2] / "src/inferrsi/knowledge/atoms"
SOURCE = "src/inferrsi/knowledge/data/skill_library/systems/engines/husky/"
IDENTITY_PREFIX = "engine-directory.husky"
TOTAL_BYTES = 22_586

# Original source paths, byte counts and digests from both v0.3.4 package receipts.
ORIGINALS = (
    ("", "SKILL.md", 9_820, "dcc95d498466d2591513cbe2845374fd415ea83286b59f2eb99e9d749e0113cd"),
    (".author-report", "references/author-report.md", 1_012,
     "4c1351ca42b2535a7c03c4da87706040650ef10d86eadcdb496e881a147fc0f7"),
    (".repo-provenance", "references/repo-provenance.md", 2_235,
     "37de912e2e2a36b44233560e6a8368b994428bff587ed4f04b1cb5fbaba0a9e7"),
    (".source-availability", "references/source-availability.json", 558,
     "d3523e53c89d4aee5bfaa17db84501aa4c4eddd59bcee486df5d48d3aa48173d"),
    (".troubleshooting", "references/troubleshooting.md", 1_922,
     "3948711437d25822d389dd857c72dc7fcc15727c9048d2e3eae3317d97aca6dd"),
    (".verification-protocol", "references/verification-protocol.md", 4_425,
     "83c5a966ed3f721b412b8d8417af8336c5a8c1e46044a888720936bf2f1deeab"),
    (".audit-evidence-card", "scripts/audit_evidence_card.py", 2_614,
     "291e62701ef7a37a5bfab963ea4e20abb94245bc015584223a101f18b1490895"),
)


@pytest.fixture(scope="module")
def husky_package_originals(tmp_path_factory):
    root = tmp_path_factory.mktemp("husky-originals")
    authors = make_author_root(root)
    release = root / "release"
    shutil.copytree(RELEASE_ROOT, release)
    for suffix, original, _, _ in ORIGINALS:
        descriptor = f"{IDENTITY_PREFIX}{suffix}.original.json"
        author = json.loads((ATOMS / descriptor).read_bytes())
        entrypoint = author["metadata"]["entrypoint"]
        relative = author["content"][entrypoint]["path"]
        raw = (ATOMS / relative).read_bytes()
        shutil.copyfile(ATOMS / descriptor, authors / "atoms" / descriptor)
        for path in (authors / "atoms" / relative, release / SOURCE / original):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

    target = root / "installed"
    generation = build_generation(authors, target, source_roots={RELEASE: release}, permits=allow)
    installed = InstalledGeneration(target, expected=generation)
    uses = []
    for suffix, *_ in ORIGINALS:
        ref = f"package:{IDENTITY_PREFIX}{suffix}.original"
        uses.append(AtomUse(AtomPin(ref, installed.catalog[ref]["revision"]), (ref,)))
    return installed, uses


def test_husky_package_originals_keep_checkout_unavailable(husky_package_originals):
    installed, uses = husky_package_originals
    result = AtomicReader(installed, permits=allow).read_group(
        uses, max_bytes=TOTAL_BYTES, context={}, operations=("retain", "redistribute"),
    )
    assert result.receipt["status"] == "delivered"
    assert result.receipt["body_bytes"] == TOTAL_BYTES
    for spec, use, body, receipt in zip(
        ORIGINALS, uses, result.bodies, result.receipt["delivered"], strict=True,
    ):
        _, original, length, digest = spec
        assert len(body) == length and hashlib.sha256(body).hexdigest() == digest
        assert receipt["ref"] == use.pin.ref and receipt["revision"] == use.pin.revision
        assert receipt["source_path"] == receipt["source"]["path"] == SOURCE + original
        assert receipt["source"]["commit"] == RELEASE
        assert receipt["source_byte_range"] == [0, length]
        assert receipt["sha256"] == receipt["source"]["sha256"] == digest
        assert receipt["layer"] == "L3"
        assert receipt["source_range_verification"] == "verified_at_build"
        _, bundle = installed.read_resolved(use.pin.ref, revision=use.pin.revision)
        assert bundle.metadata["atom"]["license"] == "Apache-2.0"
        assert bundle.metadata["state"] == "candidate"
        assert bundle.metadata["empirical_validation"] == "not_run"
        if original in {"SKILL.md", "references/author-report.md"}:
            assert "Sigil Wen" in bundle.metadata["attribution"]

    assert "checkout:husky" not in installed.catalog
    assert set(installed.skills) == PUBLIC_TASKS | {"analysis-example"}
    source_availability = json.loads(result.bodies[3])
    assert source_availability["source_license"] == "UNKNOWN"
    assert source_availability["immutable_document_revision"] is None
    assert source_availability["implementation_revision"] is None


def test_budget_permission_and_revision_apply_to_the_whole_group(husky_package_originals):
    installed, uses = husky_package_originals
    reader = AtomicReader(installed, permits=allow)
    short = reader.read_group(uses, max_bytes=TOTAL_BYTES - 1, context={})
    assert short.bodies == ()
    assert short.receipt == {
        "status": "over_budget", "body_bytes": 0, "delivered": [], "required_bytes": TOTAL_BYTES,
    }
    first, *rest = uses
    for operation in ("read", "retain", "redistribute"):
        restricted = AtomicReader(
            installed, permits=lambda pin, op: (pin, op) != (first.pin, operation),
        )
        denied = restricted.read_group(
            uses, max_bytes=TOTAL_BYTES, context={}, operations=(operation,),
        )
        assert denied.bodies == ()
        assert denied.receipt == {"status": "permission_denied", "body_bytes": 0, "delivered": []}

    stale = AtomUse(AtomPin(first.pin.ref, "sha256:" + "0" * 64), first.path)
    missing = reader.read_group([stale, *rest], max_bytes=TOTAL_BYTES, context={})
    assert missing.bodies == ()
    assert missing.receipt == {"status": "unavailable_revision", "body_bytes": 0, "delivered": []}
