"""PNG comparison for new campaigns with explicitly supplied quality gates.

Image dependencies are imported only when a comparison is requested. Historical
validators in examples remain frozen and do not import this implementation.
"""

import math
from dataclasses import dataclass

from ...infra.artifacts import sha256


@dataclass(frozen=True)
class ImageQualityGate:
    width: int
    height: int
    min_ssim: float
    min_psnr_db: float
    require_pixel_identity: bool = False
    mode: str = "RGBA"

    def __post_init__(self):
        if any(
            isinstance(v, bool) or not isinstance(v, int) or v <= 0
            for v in (self.width, self.height)
        ) or self.mode not in ("RGB", "RGBA"):
            raise ValueError("Positive image dimensions and RGB/RGBA mode are required")
        if not math.isfinite(self.min_ssim) or not 0 <= self.min_ssim <= 1:
            raise ValueError("min_ssim must be finite and within [0, 1]")
        if not math.isfinite(self.min_psnr_db) or self.min_psnr_db < 0:
            raise ValueError("min_psnr_db must be finite and nonnegative")


def compare_images(candidate: dict, reference: dict, gate: ImageQualityGate) -> dict:
    import numpy as np
    from PIL import Image
    from skimage.metrics import structural_similarity

    arrays = []
    for entry in (reference, candidate):
        if sha256(entry["path"]) != entry["sha256"]:
            raise ValueError("PNG hash mismatch")
        with Image.open(entry["path"]) as image:
            image.load()
            if (
                image.format != "PNG"
                or image.size != (gate.width, gate.height)
                or image.mode != gate.mode
            ):
                raise ValueError("Image does not match the frozen dimensions/format/mode")
            arrays.append(np.asarray(image).copy())
    left, right = arrays
    planes = [("rgb", left[:, :, :3], right[:, :, :3])]
    if gate.mode == "RGBA":
        planes.append(("alpha", left[:, :, 3], right[:, :, 3]))
    channels = []
    for name, a, b in planes:
        difference = a.astype(np.float64) - b.astype(np.float64)
        mse = float(np.mean(difference**2))
        psnr = math.inf if mse == 0 else 10 * math.log10(255**2 / mse)
        ssim = float(
            structural_similarity(
                a,
                b,
                channel_axis=2 if name == "rgb" else None,
                data_range=255,
            )
        )
        identical = bool(np.array_equal(a, b))
        channels.append(
            {
                "channel": name,
                "ssim": ssim,
                "psnr_db": "inf" if mse == 0 else psnr,
                "pixel_identical": identical,
                "max_abs_diff": float(np.abs(difference).max()),
                "passed": (
                    ssim >= gate.min_ssim
                    and psnr >= gate.min_psnr_db
                    and (not gate.require_pixel_identity or identical)
                ),
            }
        )
    return {
        "verdict": "PASS" if all(c["passed"] for c in channels) else "FAIL",
        "channels": channels,
        "pixel_identical": all(c["pixel_identical"] for c in channels),
    }
