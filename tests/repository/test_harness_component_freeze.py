"""Check the immutable pre-migration evidence without requiring the historical wheel."""

import hashlib
import json
import zipfile
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/optimization-session/component-freeze"


def test_frozen_inputs_and_plan_contracts():
    manifest = json.loads((FIXTURES / "manifest.json").read_bytes())
    fingerprint = json.loads((FIXTURES / manifest["runtime_sources"]).read_bytes())
    assert set(manifest["samples"]) == {path.name for path in FIXTURES.glob("*.zip")}
    for name, digest in manifest["samples"].items():
        archive = FIXTURES / name
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest, name
        with zipfile.ZipFile(archive) as packed:
            if name == "cleanup-proofs.zip":
                assert set(packed.namelist()) == set(manifest["cleanup_proofs"])
                for member, expected in manifest["cleanup_proofs"].items():
                    assert hashlib.sha256(packed.read(member)).hexdigest() == expected, member
            else:
                plan = json.loads(packed.read("plan.json"))
                if name.startswith("ordinary-"):
                    assert plan["runtime_identity"] == fingerprint
                else:
                    assert plan["schema_version"] == 3
                    assert plan["runtime_version"] == manifest["runtime_version"]


def test_cleanup_proofs_distinguish_attempt_and_service_identity():
    with zipfile.ZipFile(FIXTURES / "service-cleanup-pending.zip") as session:
        state = json.loads(session.read("state.json"))
        pending = state["pending"]
        checkpoint = json.loads(session.read(pending["path"] + "/execution/execution.json"))[
            "checkpoint"
        ]
        assert checkpoint["assessment"]["verdict"] == "FAIL" and checkpoint["quality_score"] is None
        assert pending["path"] + "/observation.json" not in session.namelist()
    with zipfile.ZipFile(FIXTURES / "cleanup-proofs.zip") as proofs:
        original = json.loads(proofs.read("cleanup.json"))
        foreign = json.loads(proofs.read("wrong-attempt.json"))
        mismatched = json.loads(proofs.read("wrong-owner.json"))
    assert original["attempt_id"] == mismatched["attempt_id"] == pending["attempt_id"]
    assert foreign["attempt_id"] in {attempt["attempt_id"] for attempt in state["attempts"]}
    assert foreign["attempt_id"] != pending["attempt_id"]
    assert original["services"] != foreign["services"] == mismatched["services"]
