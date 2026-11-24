"""Qwen2.1 Turbo validation adapter, artifact ownership, and frozen gate parity."""

import importlib.util
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.campaigns.test_qwen21_turbo_campaign import campaign, quality

ROOT = Path(__file__).resolve().parents[2]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = load_module(
    "qwen21_validation_adapter", ROOT / "examples/qwen21_turbo_validation_adapter.py"
)


def png_bytes(color):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    pixels = (b"\0" + bytes(color) * 1280) * 704
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1280, 704, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )


class ArtifactOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.manifest("reference")
        self.candidate = self.manifest("candidate")

    def manifest(self, name):
        directory = self.root / name
        directory.mkdir()
        artifacts = []
        protocol = campaign.protocol()
        for index, prompt in enumerate(protocol["prompts"]):
            path = directory / f"image-{index}.png"
            path.write_bytes(png_bytes((index * 50, 100, 150, 255)))
            artifacts.append(
                {
                    "id": prompt["id"],
                    "group": 1,
                    "path": str(path),
                    "sha256": campaign.artifacts.sha256(path),
                }
            )
        first = directory / "first.png"
        first.write_bytes(png_bytes((200, 100, 150, 255)))
        payload = {
            "status": "completed",
            "diagnostic": False,
            "source_integrity": {"verified": True},
            "protocol": protocol,
            "protocol_sha256": campaign.artifacts.digest(protocol),
            "protected_sources": {},
            "guard_hashes": {},
            "dependency_versions": {},
            "model_assets_sha256": "fixture",
            "parallel": {"tp": 1, "ulysses": 4},
            "groups_ms": [100],
            "artifacts": artifacts,
            "first_request": {
                "path": str(first),
                "sha256": campaign.artifacts.sha256(first),
                "seed": 10042,
            },
        }
        result = directory / "result.json"
        result.write_text(json.dumps(payload))
        return result

    def test_first_request_alone_cannot_pass_without_measured_outputs(self):
        candidate = json.loads(self.candidate.read_text())
        candidate.update(groups_ms=[], artifacts=[])
        self.candidate.write_text(json.dumps(candidate))
        with patch.object(quality, "compare_images") as compare:
            with self.assertRaisesRegex(ValueError, "Positive candidate measured group"):
                quality.validate(self.reference, self.candidate, (1, 4))
            compare.assert_not_called()

    def test_incomplete_measured_group_cannot_pass(self):
        candidate = json.loads(self.candidate.read_text())
        candidate["artifacts"].pop()
        self.candidate.write_text(json.dumps(candidate))
        with patch.object(quality, "compare_images") as compare:
            with self.assertRaisesRegex(ValueError, "Wrong artifact count"):
                quality.validate(self.reference, self.candidate, (1, 4))
            compare.assert_not_called()

    def test_reference_files_cannot_stand_in_for_candidate_outputs(self):
        reference = json.loads(self.reference.read_text())
        candidate = json.loads(self.candidate.read_text())
        candidate["artifacts"] = reference["artifacts"]
        candidate["first_request"] = reference["first_request"]
        self.candidate.write_text(json.dumps(candidate))
        with self.assertRaisesRegex(ValueError, "trial|reference|reused"):
            quality.validate(self.reference, self.candidate, (1, 4))

    def test_same_file_cannot_cover_multiple_groups(self):
        candidate = json.loads(self.candidate.read_text())
        candidate["groups_ms"].append(100)
        candidate["artifacts"] += [{**item, "group": 2} for item in candidate["artifacts"]]
        self.candidate.write_text(json.dumps(candidate))
        with self.assertRaisesRegex(ValueError, "reused|Reused"):
            quality.validate(self.reference, self.candidate, (1, 4))

    def test_symlink_to_reference_is_outside_trial(self):
        candidate = json.loads(self.candidate.read_text())
        image = Path(candidate["artifacts"][0]["path"])
        image.unlink()
        try:
            image.symlink_to(json.loads(self.reference.read_text())["artifacts"][0]["path"])
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "trial"):
            quality.validate(self.reference, self.candidate, (1, 4))

    def test_aggregate_cannot_reuse_a_manifest_for_two_trials(self):
        seen = set()
        with patch.object(
            quality, "compare_images", return_value={"verdict": "PASS"}
        ):
            quality.validate(self.reference, self.candidate, (1, 4), seen_paths=seen)
            with self.assertRaisesRegex(ValueError, "reused|Reused"):
                quality.validate(self.reference, self.candidate, (1, 4), seen_paths=seen)


class ValidationAdapterTests(unittest.TestCase):
    def test_nested_runner_result_resolves_original_run_without_changing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "run.lock.json").write_text(json.dumps({"repetitions": 5}))
            result = root / "validation/result.json"
            env = adapter.validation_environment(
                result, {"INFERRSI_RESULT_PATH": str(result), "CONTROL": "frozen"}
            )
            self.assertEqual(env["INFERRSI_RESULT_PATH"], str(result))
            self.assertEqual(Path(env["OMNIRSI_RESULT_PATH"]).parent, root)
            self.assertEqual(env["CONTROL"], "frozen")
            self.assertFalse((root / "v4-root-adapter.json").exists())

    def test_wrong_location_and_incomplete_cohort_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                adapter.validation_environment(root / "result.json", {})
            (root / "run.lock.json").write_text(json.dumps({"repetitions": 4}))
            with self.assertRaises(ValueError):
                adapter.validation_environment(root / "validation/result.json", {})


@pytest.mark.parametrize("change", ["identical", "rgb", "alpha"])
def test_quality_gate_matches_frozen_snapshot(tmp_path, change):
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")
    pytest.importorskip("skimage.metrics")
    legacy = ROOT / "tests/fixtures/legacy"
    helper = load_module("legacy_artifact_helper", legacy / "ltx25_b300.py")
    with patch.dict(sys.modules, {"ltx25_b300": helper}):
        frozen = load_module("frozen_quality", legacy / "qwen21_turbo_quality.py")
    current = load_module("current_quality", ROOT / "examples/qwen21_turbo_quality.py")
    pixels = np.full((704, 1280, 4), 128, dtype=np.uint8)
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    Image.fromarray(pixels).save(reference)
    if change == "rgb":
        pixels[:, :, :3] = 0
    elif change == "alpha":
        pixels[:, :, 3] = 0
    Image.fromarray(pixels).save(candidate)
    ref = {"path": str(reference), "sha256": helper.sha256(reference)}
    cand = {"path": str(candidate), "sha256": helper.sha256(candidate)}
    actual = current.compare_images(cand, ref)
    assert actual == frozen.compare_images(cand, ref)
    assert actual["verdict"] == ("PASS" if change == "identical" else "FAIL")
    assert current.lifecycle.digest({"images": [ref, cand]}) == helper.digest(
        {"images": [ref, cand]}
    )
    output = tmp_path / "current.json"
    original = tmp_path / "frozen.json"
    current.lifecycle.write_json(output, actual)
    helper.write_json(original, actual)
    assert output.read_bytes() == original.read_bytes()
