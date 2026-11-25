"""Synthetic CPU control, not a Qwen benchmark or hardware evidence."""

import hashlib
import json
import os
import runpy
import shutil
import sys
import time
from pathlib import Path

from PIL import Image

from inferrsi.harness import candidates

started = time.time()
source, output = map(Path, sys.argv[1:3])
engine = runpy.run_path(str(source / "engine.py"))
loaded_file = Path(engine["__file__"])
loaded_sha = candidates.identity(loaded_file.parent, [loaded_file.name])
metric = engine["LATENCY"]
requests = []
for seed in range(42, 48):
    path = output.parent / f"seed-{seed}.png"
    shutil.copyfile(Path(__file__).with_name(path.name), path)
    with Image.open(path) as image:
        pixels = hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()
    requests.append({"seed": seed, "latency_ms": metric, "file": path.name,
                     "pixel_sha256": pixels})
output.write_text(json.dumps({
    "loaded_source_sha256": loaded_sha,
    "median_ms": metric, "correct": True, "requests": requests,
    "effective_scheduler": {"num_steps": 8, "timesteps": list(range(8)), "sigmas": [1, 0]},
    "process": {"id": str(os.getpid()), "finished_at": time.time(), "started_at": started},
    "environment_identity": "synthetic-not-a-device",
    "workload_sha256": hashlib.sha256(Path(__file__).with_name("workload.json").read_bytes())
        .hexdigest(),
}), encoding="utf-8")
