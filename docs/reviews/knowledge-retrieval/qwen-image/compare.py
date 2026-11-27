"""Validate all PNGs and summarize the four counterbalanced, single-device blocks."""

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median

from PIL import Image


def read_block(root, label, protocol):
    """Verify every persisted image against the timed RGBA digest."""
    samples = json.loads((root / label / "timings.json").read_text())
    if [r["seed"] for r in samples] != protocol["warmups"] + protocol["seeds"]:
        raise ValueError(f"{label}: incomplete or reordered requests")
    images = {}
    for row in samples:
        seed = row["seed"]
        if row["warmup"] != (seed in protocol["warmups"]) or not row["seconds"] > 0:
            raise ValueError(f"{label}/{seed}: invalid warm-up or duration")
        with Image.open(root / label / f"{seed}.png") as file:
            image = file.convert("RGBA")
        if image.size != (protocol["width"], protocol["height"]):
            raise ValueError(f"{label}/{seed}: unexpected image dimensions")
        if hashlib.sha256(image.tobytes()).hexdigest() != row["rgba_sha256"]:
            raise ValueError(f"{label}/{seed}: RGBA digest mismatch")
        if not row["warmup"]:
            images[seed] = image
    return samples, images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--verify-block", help="Verify one persisted block and exit")
    args = parser.parse_args()
    root = args.results
    protocol = json.loads(Path(__file__).with_name("protocol.json").read_text())
    if args.verify_block:
        read_block(root, args.verify_block, protocol)
        return

    import numpy as np
    from skimage.metrics import structural_similarity

    blocks, pixels, exits = {}, {}, {}
    for label in ("A1", "B1", "B2", "A2"):
        exits[label] = int((root / f"{label}.exit").read_text())
        blocks[label], images = read_block(root, label, protocol)
        pixels[label] = {seed: np.asarray(image) for seed, image in images.items()}

    pairs = []
    for left, right in (("A1", "B1"), ("A2", "B2")):
        for seed in protocol["seeds"]:
            a, b = pixels[left][seed], pixels[right][seed]
            mse = np.mean((a.astype(float) - b.astype(float)) ** 2)
            ssim = structural_similarity(a, b, data_range=255, channel_axis=-1)
            pairs.append(
                dict(
                    blocks=[left, right],
                    seed=seed,
                    exact=np.array_equal(a, b),
                    ssim=float(ssim),
                    psnr_db="infinity" if not mse else 10 * math.log10(255**2 / mse),
                )
            )
    summary = {}
    for arm in ("A", "B"):
        values = [
            row["seconds"]
            for key, rows in blocks.items()
            if key.startswith(arm)
            for row in rows
            if not row["warmup"]
        ]
        summary[arm] = dict(
            n=len(values),
            mean_s=mean(values),
            median_s=median(values),
            min_s=min(values),
            max_s=max(values),
        )
    ratio = summary["A"]["mean_s"] / summary["B"]["mean_s"]
    print(
        json.dumps(
            dict(
                warm=summary,
                latency_reduction_pct=100 * (1 - 1 / ratio),
                speedup=ratio,
                pairs=pairs,
                container_exit=exits,
                blocks=blocks,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
