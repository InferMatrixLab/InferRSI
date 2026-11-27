import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter


def run():
    from vllm_omni.diffusion.utils.image_output import extract_images_from_outputs
    from vllm_omni.entrypoints.omni import Omni
    from vllm_omni.inputs.data import OmniDiffusionSamplingParams

    protocol = json.loads(Path(__file__).with_name("protocol.json").read_text())
    root = Path("/results") / sys.argv[1]
    root.mkdir()
    sigmas = json.loads(Path("/model/model_index.json").read_text())["sample_sigmas"]
    if len(sigmas) != protocol["steps"]:
        raise ValueError("Checkpoint sigma count differs from the benchmark protocol")
    engine = Omni(model="/model", enforce_eager=True, init_timeout=600, stage_init_timeout=600)
    rows = []
    for seed in protocol["warmups"] + protocol["seeds"]:
        params = OmniDiffusionSamplingParams(
            height=protocol["height"],
            width=protocol["width"],
            seed=seed,
            true_cfg_scale=protocol["cfg"],
            guidance_scale=protocol["cfg"],
            num_inference_steps=len(sigmas),
            sigmas=sigmas,
        )
        started = perf_counter()
        outputs = engine.generate(
            {"prompt": "A small red sailboat on a blue lake at sunrise"},
            sampling_params_list=[params],
        )
        images = extract_images_from_outputs(outputs)
        img = images[0].convert("RGBA")
        raw = img.tobytes()
        seconds = perf_counter() - started
        if img.size != (protocol["width"], protocol["height"]):
            raise ValueError(f"Unexpected decoded size {img.size} for seed {seed}")
        img.save(root / f"{seed}.png")
        rows.append(
            dict(
                seed=seed,
                warmup=seed in protocol["warmups"],
                seconds=seconds,
                rgba_sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
        (root / "timings.json").write_text(json.dumps(rows, indent=2))
    print("All decoded outputs persisted", flush=True)
    engine.close()
    print("Engine closed", flush=True)


if __name__ == "__main__":
    run()
