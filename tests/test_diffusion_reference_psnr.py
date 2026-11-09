"""CPU regression for the known reference-PSNR ranking failure.

A blurred frame can score a higher PSNR than a sharp frame that was only
shifted. Laplacian variance ranks the same pair the other way. The sharp
sample is a fixed high-frequency pattern, not a picture, and a higher
variance is not a quality pass.

The dependency-free test always runs. A second test repeats the same pixels
with NumPy when that extra is installed. Standard CI installs only the dev
extra, so it executes the dependency-free test and skips the NumPy twin.
Skipping the twin is not a substitute for the ranking assertion.

On NumPy 1.26.4 the issue's seed-0 random fixture measured about 7.612 dB
for the shift and 11.008 dB for the blur. Those samples are not pinned:
NumPy's Generator stream is not a portability contract, and a theoretical
independent-pixel center near 7.75 dB is a different quantity.
"""

from __future__ import annotations

import math
import unittest

from inferrsi.model.validators.image import ImageQualityGate

HEIGHT = 64
WIDTH = 64
_QUALITY_FIELD_MARKERS = ("sharpness", "laplacian", "luma", "temporal")


def _pattern() -> list[list[int]]:
    """Fixed high-frequency bytes. No random generator."""
    return [
        [((x * 17) + (y * 31) + ((x * y) % 13)) % 256 for x in range(WIDTH)]
        for y in range(HEIGHT)
    ]


def _shift(image: list[list[int]], offset: int) -> list[list[int]]:
    return [row[-offset:] + row[:-offset] for row in image]


def _blur(image: list[list[int]], passes: int = 8) -> list[list[int]]:
    current = [[float(value) for value in row] for row in image]
    for _ in range(passes):
        nxt = [[0.0] * WIDTH for _ in range(HEIGHT)]
        for y in range(HEIGHT):
            for x in range(WIDTH):
                nxt[y][x] = (
                    current[y][x]
                    + current[(y + 1) % HEIGHT][x]
                    + current[(y - 1) % HEIGHT][x]
                    + current[y][(x + 1) % WIDTH]
                    + current[y][(x - 1) % WIDTH]
                ) / 5.0
        current = nxt
    return [[int(value) for value in row] for row in current]


def _psnr(left: list[list[int]], right: list[list[int]]) -> float:
    count = HEIGHT * WIDTH
    mse = sum(
        (left[y][x] - right[y][x]) ** 2
        for y in range(HEIGHT)
        for x in range(WIDTH)
    ) / count
    if mse == 0:
        return math.inf
    return 10 * math.log10((255**2) / mse)


def _laplacian_variance(image: list[list[int]]) -> float:
    """Edge-padded 4-neighbor Laplacian. Higher is not a quality verdict."""
    values: list[float] = []
    for y in range(HEIGHT):
        for x in range(WIDTH):
            center = image[y][x]
            north = image[max(y - 1, 0)][x]
            south = image[min(y + 1, HEIGHT - 1)][x]
            west = image[y][max(x - 1, 0)]
            east = image[y][min(x + 1, WIDTH - 1)]
            values.append(north + south + west + east - 4 * center)
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _assert_blur_outranks_shift(
    sharp: list[list[int]],
    shifted: list[list[int]],
    blurred: list[list[int]],
) -> None:
    shifted_psnr = _psnr(sharp, shifted)
    blurred_psnr = _psnr(sharp, blurred)
    detail = _laplacian_variance(sharp)
    # Ordering and a wide gap. Not a frozen campaign threshold.
    assert blurred_psnr - shifted_psnr > 2
    assert _laplacian_variance(shifted) / detail > 0.95
    assert _laplacian_variance(blurred) / detail < 0.05


class ReferencePsnrRankingTest(unittest.TestCase):
    def test_blur_can_outrank_a_sharp_shift_without_numpy(self) -> None:
        sharp = _pattern()
        _assert_blur_outranks_shift(sharp, _shift(sharp, 3), _blur(sharp))

    def test_numpy_cpu_agrees_when_installed(self) -> None:
        try:
            import numpy as np
        except ImportError:
            self.skipTest(
                "numpy is not installed; the dependency-free ranking test already ran"
            )
        sharp = np.asarray(_pattern(), dtype=np.uint8)
        shifted = np.roll(sharp, 3, axis=1)
        blurred = sharp.astype(np.float64).copy()
        for _ in range(8):
            blurred = (
                blurred
                + np.roll(blurred, 1, 0)
                + np.roll(blurred, -1, 0)
                + np.roll(blurred, 1, 1)
                + np.roll(blurred, -1, 1)
            ) / 5.0
        blurred = blurred.astype(np.uint8)
        _assert_blur_outranks_shift(
            sharp.tolist(),
            shifted.tolist(),
            blurred.tolist(),
        )

    def test_noise_can_raise_laplacian_variance_without_a_quality_field(self) -> None:
        smooth = [[0] * WIDTH for _ in range(HEIGHT)]
        noise = [
            [((x * 3) + (y * 5)) % 256 for x in range(WIDTH)]
            for y in range(HEIGHT)
        ]
        self.assertGreater(_laplacian_variance(noise), _laplacian_variance(smooth))
        names = set(ImageQualityGate.__dataclass_fields__)
        for marker in _QUALITY_FIELD_MARKERS:
            self.assertFalse(any(marker in name for name in names))


if __name__ == "__main__":
    unittest.main()
