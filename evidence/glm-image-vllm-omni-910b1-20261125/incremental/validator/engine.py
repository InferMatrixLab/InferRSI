"""Evaluate the native vLLM-Omni two-stage GLM-Image pipeline."""

import argparse
import hashlib
import json
import os
import statistics
import time
from pathlib import Path

WARMUP = ("A photograph of a yellow apple on a plate.", 107)
CASES = (
    ("A red ceramic teapot on a wooden table in soft window light, a still life photograph.", 42),
    ('A blue book cover with the word "MOON" in white, a crescent moon above a quiet lake.', 771),
)
SIZE = 512
STEPS = 20


def generate(engine, case):
    import numpy as np
    from vllm import SamplingParams
    from vllm_omni.inputs.data import OmniDiffusionSamplingParams
    from vllm_omni.model_executor.stage_input_processors.glm_image import compute_max_tokens

    caption, seed = case
    grid = {"target_h": SIZE, "target_w": SIZE}
    generation = {"num_inference_steps": STEPS, "guidance_scale": 1.5, "seed": seed}
    params = [
        SamplingParams(
            temperature=0.9, top_p=0.75, top_k=16512, seed=seed, detokenize=False,
            max_tokens=compute_max_tokens(SIZE, SIZE), stop_token_ids=[16385], extra_args=grid,
        ),
        OmniDiffusionSamplingParams(height=SIZE, width=SIZE, **generation),
    ]
    prompt = {"prompt": caption, "height": SIZE, "width": SIZE, "mm_processor_kwargs": grid, **generation}
    started = time.perf_counter()
    outputs = list(engine.generate([prompt], params, py_generator=True))
    elapsed = time.perf_counter() - started
    outputs = [out for out in outputs if out.final_output_type == "image"]
    if len(outputs) != 1 or len(outputs[0].images) != 1:
        raise ValueError("Expected one completed image")
    image = outputs[0].images[0].convert("RGB")
    pixels = np.asarray(image)
    contrast = float(pixels.std(axis=(0, 1)).max())
    if image.size != (SIZE, SIZE) or contrast == 0 or (seed != 771 and contrast <= 2):
        raise ValueError(f"Invalid native output for seed {seed}: {image.size}, contrast {contrast}")
    timing = getattr(outputs[0], "stage_durations", None) or {}
    row = {
        "seed": seed, "elapsed_s": elapsed,
        "sha256": hashlib.sha256(image.tobytes()).hexdigest(),
        "max_channel_std": contrast, "stage_durations": {k: float(v) for k, v in timing.items() if isinstance(v, (int, float))},
    }
    return image, row


def main():
    import vllm_omni
    from vllm_omni.entrypoints.omni import Omni

    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("quality", "measure"))
    parser.add_argument("source", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    if not Path(vllm_omni.__file__).resolve().is_relative_to(args.source.resolve()):
        raise RuntimeError("The imported vllm_omni is outside the declared source snapshot")
    engine = Omni(
        model=os.environ["GLM_IMAGE_MODEL"], deploy_config=str(Path(__file__).with_name("deploy.yaml")),
        stage_init_timeout=750, log_stats=True,
    )
    frozen = json.loads(Path(__file__).with_name("reference.json").read_text())
    rows = []
    comparisons = {}
    quality_images = {}
    control = None
    try:
        warmup_image, warmup = generate(engine, WARMUP)
        if warmup["sha256"] != frozen[str(warmup["seed"])]:
            raise ValueError("Warmup control differs from the independent stock baseline")
        if args.mode == "quality":
            quality_images[warmup["seed"]] = warmup_image
        for case in CASES:
            image, row = generate(engine, case)
            if row["sha256"] != frozen[str(row["seed"])]:
                raise ValueError(f"Seed {row['seed']} differs from the stock baseline: {row['sha256']}")
            if args.mode == "quality":
                quality_images[row["seed"]] = image
            rows.append(row)
            print(json.dumps(row), flush=True)
        if args.mode == "quality":
            other, control = generate(engine, (CASES[0][0], CASES[0][1] + 1))
            if control["sha256"] == rows[0]["sha256"]:
                raise ValueError("Changing the seed did not change the control image")
            quality_images[control["seed"]] = other
    finally:
        engine.close()
    quality = True
    if args.mode == "quality":
        import numpy as np
        from PIL import Image

        if args.result.parent.name not in {"quality-baseline", "quality-candidate"}:
            raise ValueError("Unknown InferRSI quality step")
        for seed, image in quality_images.items():
            name = f"image-{seed}.png"
            image.save(args.result.parent / name)
            if args.result.parent.name == "quality-candidate":
                with Image.open(args.result.parent.parent / "quality-baseline" / name) as reference:
                    delta = np.abs(np.asarray(image, dtype=np.int16) - np.asarray(reference.convert("RGB"), dtype=np.int16))
                comparisons[str(seed)] = {"max_channel_delta": int(delta.max()),
                                          "differing_pixels": int(np.any(delta != 0, axis=2).sum())}
                quality = quality and comparisons[str(seed)]["differing_pixels"] == 0
    args.result.write_text(json.dumps({
        "quality": quality, "comparisons": comparisons, "different_seed_control": control, "warmup_control": warmup, "latency_s": statistics.median(s["elapsed_s"] for s in rows), "images": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
