"""Artifact provenance failures must be rejected before image decoding."""

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tests.test_qwen21_turbo_campaign import campaign, quality


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
                    "sha256": campaign.lifecycle.sha256(path),
                }
            )
        first = directory / "first.png"
        first.write_bytes(png_bytes((200, 100, 150, 255)))
        payload = {
            "status": "completed",
            "diagnostic": False,
            "source_integrity": {"verified": True},
            "protocol": protocol,
            "protocol_sha256": campaign.lifecycle.digest(protocol),
            "protected_sources": {},
            "guard_hashes": {},
            "dependency_versions": {},
            "model_assets_sha256": "fixture",
            "parallel": {"tp": 1, "ulysses": 4},
            "groups_ms": [100],
            "artifacts": artifacts,
            "first_request": {
                "path": str(first),
                "sha256": campaign.lifecycle.sha256(first),
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
        with unittest.mock.patch.object(quality, "compare_images") as compare:
            with self.assertRaisesRegex(ValueError, "Positive candidate measured group"):
                quality.validate(self.reference, self.candidate, (1, 4))
            compare.assert_not_called()

    def test_incomplete_measured_group_cannot_pass(self):
        candidate = json.loads(self.candidate.read_text())
        candidate["artifacts"].pop()
        self.candidate.write_text(json.dumps(candidate))
        with unittest.mock.patch.object(quality, "compare_images") as compare:
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
        with unittest.mock.patch.object(
            quality, "compare_images", return_value={"verdict": "PASS"}
        ):
            quality.validate(self.reference, self.candidate, (1, 4), seen_paths=seen)
            with self.assertRaisesRegex(ValueError, "reused|Reused"):
                quality.validate(self.reference, self.candidate, (1, 4), seen_paths=seen)
