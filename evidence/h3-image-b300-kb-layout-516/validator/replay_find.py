"""Repeat a fixed local Find workload against the two immutable KB worktrees."""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time


PINS = {"old": "a3e33851981f1ecdc8b73d7b62633cc598e5d5ae",
        "new": "c27a359d0ec5c11551b3d4c77ddfa3068cbf1c36"}
QUERIES = [
    ("exact_target", "MiniMax H3 Image 4K BF16 single B300 six steps hot image latency", None),
    ("vae", "MiniMax H3 B300 diffusion VAE tile decode batching overlap memory",
     "vllm_omni.cuda.diffusion.minimax_h3_vae_stacked_tiling"),
    ("qk", "MiniMax H3 B300 packed queries keys RMS normalization rotary embeddings fusion",
     "vllm_omni.cuda.diffusion.minimax_h3_qk_norm_rope"),
    ("conditioning", "diffusion T2I redundant conditioning across denoising steps BF16 prompt reuse",
     "vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i"),
    ("adaln", "MiniMax H3 denoising time modulation projections cache timestep schedule",
     "vllm_omni.cuda.diffusion.minimax_h3_adaln_schedule_cache"),
    ("benchmark", "inference benchmark design warm requests baseline latency quality control",
     "inference-benchmark-design"),
]


def find(root, query):
    env = dict(os.environ, PYTHONPATH=str(root / "src"), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-m", "inferrsi", "find", query, "--limit", "5", "--no-external", "--json"]
    start = time.perf_counter()
    raw = subprocess.check_output(cmd, cwd=root, env=env)
    elapsed = time.perf_counter() - start
    data = json.loads(raw)
    return [item["id"] for item in data["items"]], elapsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arm in PINS:
        parser.add_argument("--" + arm, type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    roots = {arm:getattr(args,arm).resolve() for arm in PINS}
    for arm, root in roots.items():
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        if actual != PINS[arm]:
            raise ValueError(f"Unexpected {arm} revision {actual}")
        find(root, "warmup inference benchmark")
    results = []
    for i, (name, query, target) in enumerate(QUERIES):
        row = {"query_id": name, "query": query, "reference_id": target}
        for repeat in range(4):
            order = ("old", "new") if (i + repeat) % 2 == 0 else ("new", "old")
            for arm in order:
                ids, elapsed = find(roots[arm], query)
                arm_result = row.setdefault(arm, {"top5":ids, "seconds":[]})
                if ids != arm_result["top5"]:
                    raise RuntimeError(f"Unstable ranking at {name} {arm}")
                arm_result["seconds"].append(elapsed)
        for arm in roots:
            data = row[arm]
            data["median_seconds"] = statistics.median(data["seconds"])
            data["reference_rank"] = data["top5"].index(target) + 1 if target in data["top5"] else None
        results.append(row)
    report = {"pins":PINS, "limit":5, "repeats_per_query_and_arm":4,
              "scope":"Exploratory fixed-query replay after independent discovery; references are navigation checks, not exhaustive relevance labels.",
              "timing":"Fresh Python process to full JSON on the same host; two warmups excluded; AB and BA twice per query.",
              "results":results}
    args.out.write_bytes((json.dumps(report, indent=2) + "\n").encode())


if __name__ == "__main__":
    main()
