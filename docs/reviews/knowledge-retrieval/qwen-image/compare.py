"""Validate all PNGs and summarize the four counterbalanced, single-device blocks."""

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    root = parser.parse_args().results
    protocol = json.loads(Path(__file__).with_name("protocol.json").read_text())
    seeds = protocol["seeds"]
    sizes = (protocol["width"], protocol["height"])
    blocks, pixels, exits = {}, {}, {}
    for label in ("A1", "B1", "B2", "A2"):
        exits[label] = int((root / f"{label}.exit").read_text())
        samples = json.loads((root / label / "timings.json").read_text())
        assert [r["seed"] for r in samples] == protocol["warmups"] + seeds
        for row in samples:
            seed = row["seed"]
            assert row["warmup"] == (seed in protocol["warmups"]) and row["seconds"] > 0
            with Image.open(root / label / f"{seed}.png") as image:
                image = image.convert("RGBA")
                assert image.size == sizes
                assert hashlib.sha256(image.tobytes()).hexdigest() == row["rgba_sha256"]
                if not row["warmup"]:
                    pixels[label, seed] = np.asarray(image)
        blocks[label] = samples

    pairs = []
    for left, right in (("A1", "B1"), ("A2", "B2")):
        for seed in seeds:
            a, b = pixels[left, seed], pixels[right, seed]
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
