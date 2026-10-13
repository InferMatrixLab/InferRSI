"""Current Qwen validation must agree with its frozen pre-cleanup implementation."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
