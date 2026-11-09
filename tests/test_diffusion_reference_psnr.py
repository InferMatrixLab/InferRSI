"""CPU regression for the known reference-PSNR ranking failure.

A blurred frame can score a higher PSNR than a sharp frame that was only
shifted. Laplacian variance ranks the same pair the other way. The sharp
input here is random high-frequency noise, so a higher variance is not a
quality pass. This test does not change ImageQualityGate thresholds and does
not score sharpness, luma, or frame difference as PASS/FAIL.
"""

from __future__ import annotations

import unittest

import numpy as np

from inferrsi.model.validators.image import ImageQualityGate


def _psnr(left: np.ndarray, right: np.ndarray) -> float:
    difference = left.astype(np.float64) - right.astype(np.float64)
    mse = float(np.mean(difference**2))
    if mse == 0:
        return float("inf")
    return float(10 * np.log10(255.0**2 / mse))


def _laplacian_variance(image: np.ndarray) -> float:
    """Variance of a 4-neighbor Laplacian. Higher is not a quality verdict."""
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)
    padded = np.pad(image.astype(np.float64), 1, mode="edge")
    response = np.zeros(image.shape, dtype=np.float64)
    for row in range(3):
        for column in range(3):
            response += kernel[row, column] * padded[
                row : row + image.shape[0], column : column + image.shape[1]
            ]
    return float(response.var())


def _box_blur(image: np.ndarray, passes: int = 8) -> np.ndarray:
    blurred = image.astype(np.float64).copy()
    for _ in range(passes):
        blurred = (
            blurred
            + np.roll(blurred, 1, 0)
            + np.roll(blurred, -1, 0)
            + np.roll(blurred, 1, 1)
            + np.roll(blurred, -1, 1)
        ) / 5.0
    return blurred.astype(np.uint8)


class ReferencePsnrRankingTest(unittest.TestCase):
    def test_blur_can_outrank_a_sharp_shift_on_psnr(self) -> None:
        generator = np.random.default_rng(0)
        sharp = generator.integers(0, 256, size=(128, 128), dtype=np.uint8)
        shifted = np.roll(sharp, 3, axis=1)
        blurred = _box_blur(sharp)

        shifted_psnr = _psnr(sharp, shifted)
        blurred_psnr = _psnr(sharp, blurred)
        sharp_detail = _laplacian_variance(sharp)
        self.assertGreater(blurred_psnr, shifted_psnr)
        self.assertAlmostEqual(shifted_psnr, 7.61, delta=0.05)
        self.assertAlmostEqual(blurred_psnr, 11.01, delta=0.05)
        self.assertAlmostEqual(_laplacian_variance(shifted) / sharp_detail, 1.0, places=3)
        self.assertLess(_laplacian_variance(blurred) / sharp_detail, 0.01)

    def test_high_frequency_noise_raises_laplacian_variance_without_a_pass(self) -> None:
        smooth = np.zeros((32, 32), dtype=np.uint8)
        noise = np.random.default_rng(1).integers(0, 256, size=smooth.shape, dtype=np.uint8)
        self.assertGreater(_laplacian_variance(noise), _laplacian_variance(smooth))
        # The production still-image gate has no sharpness field to turn this into PASS.
        self.assertEqual(
            [field.name for field in ImageQualityGate.__dataclass_fields__.values()],
            [
                "width",
                "height",
                "min_ssim",
                "min_psnr_db",
                "require_pixel_identity",
                "mode",
            ],
        )

    def test_identical_frame_is_not_a_new_quality_gate(self) -> None:
        frame = np.arange(16, dtype=np.uint8).reshape(4, 4)
        self.assertEqual(_psnr(frame, frame), float("inf"))
        self.assertEqual(_laplacian_variance(frame), _laplacian_variance(frame.copy()))


if __name__ == "__main__":
    unittest.main()
