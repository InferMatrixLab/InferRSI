"""Measure one checkout on one Ascend A2 NPU in a fresh Python process."""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from statistics import median


def worker_trace(engine, method):
    reply = engine.engine.collective_rpc(method, timeout=30)
    while isinstance(reply, (list, tuple)) and len(reply) == 1:
        reply = reply[0]
    if not isinstance(reply, dict):
        raise RuntimeError("Expected one diffusion worker sampling trace")
    return reply


def measure(source, checkpoint, output):
    workload_bytes = Path(__file__).with_name("workload.json").read_bytes()
    workload = json.loads(workload_bytes)
    model_bytes = (checkpoint / "model_index.json").read_bytes()
    model = json.loads(model_bytes)
    sigmas = workload["sample_sigmas"]
    if (model.get("_class_name") != "QwenImage21Pipeline"
            or len(sigmas) != 8 or model.get("sample_sigmas") != sigmas):
        raise ValueError("The checkpoint must contain the frozen native Turbo sampling grid")

    # Spawned engine processes must resolve the same checkout as this process.
    sys.path.insert(0, str(source))
    old_path = os.environ.get("PYTHONPATH")
    import_paths = [str(source), str(Path(__file__).resolve().parent)]
    if old_path:
        import_paths.append(old_path)
    os.environ["PYTHONPATH"] = os.pathsep.join(import_paths)
    os.environ["HF_HUB_OFFLINE"] = "1"
    import torch
    import vllm_omni
    from vllm_omni.diffusion.utils.image_output import extract_images_from_outputs
    from vllm_omni.entrypoints.omni import Omni
    from vllm_omni.inputs.data import OmniDiffusionSamplingParams
    from vllm_omni.platforms import current_omni_platform

    for module in (vllm_omni, sys.modules[Omni.__module__],
                   sys.modules[extract_images_from_outputs.__module__]):
        if not Path(module.__file__).resolve().is_relative_to(source / "vllm_omni"):
            raise RuntimeError("The measurement process imported a different vLLM-Omni checkout")
    if current_omni_platform.device_type != "npu" or torch.npu.device_count() != 1:
        raise RuntimeError("Expose exactly one Ascend A2 NPU to the measurement process")
    device = current_omni_platform.get_device_name(0)
    if "910B" not in device.upper():
        raise RuntimeError(f"Expected an Ascend A2 (910B) NPU, detected {device}")

    output.mkdir(parents=True, exist_ok=True)
    if (output / "result.json").exists() or any(output.glob("seed-*.png")):
        raise FileExistsError("Use a fresh output directory for every measurement")
    warmup_ms, latencies_ms = [], []
    sampling_grid = {}
    engine = Omni(
        model=str(checkpoint), dtype="bfloat16", tensor_parallel_size=1, enforce_eager=True,
        worker_extension_cls="sampling_trace.SamplingTraceExtension",
    )
    try:
        for group in ("warmups", "requests"):
            for case in workload[group]:
                params = OmniDiffusionSamplingParams(
                    width=workload["width"], height=workload["height"], seed=case["seed"],
                    true_cfg_scale=1.0, num_outputs_per_prompt=1,
                    sigmas=list(sigmas),
                )
                prompt = {"prompt": case["prompt"], "modalities": ["image"]}
                trace_started = worker_trace(engine, "begin_qwen_e2e_trace")
                if trace_started.get("sampling_trace_started") is not True:
                    raise RuntimeError("The diffusion worker did not start the sampling trace")
                start = time.perf_counter_ns()
                outputs = engine.generate(prompt, sampling_params_list=[params], use_tqdm=False)
                images = extract_images_from_outputs(outputs)
                if len(images) != 1:
                    raise ValueError("Expected exactly one decoded image")
                image = images[0]
                image.load()
                elapsed = (time.perf_counter_ns() - start) / 1e6
                sampling_grid[str(case["seed"])] = worker_trace(engine, "end_qwen_e2e_trace")
                if image.size != (workload["width"], workload["height"]) or image.mode != "RGBA":
                    raise ValueError(
                        f"Unexpected image for seed {case['seed']}: {image.size}, {image.mode}"
                    )
                if group == "warmups":
                    warmup_ms.append(elapsed)
                else:
                    latencies_ms.append(elapsed)
                    image.save(output / f"seed-{case['seed']}.png")
    finally:
        engine.close()
    result = {
        "device": device, "workload_sha256": hashlib.sha256(workload_bytes).hexdigest(),
        "model_index_sha256": hashlib.sha256(model_bytes).hexdigest(), "sample_sigmas": sigmas,
        "seeds": [case["seed"] for case in workload["requests"]],
        "sampling_grid": sampling_grid,
        "warmup_ms": warmup_ms, "latencies_ms": latencies_ms, "median_ms": median(latencies_ms),
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "checkpoint", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    measure(args.source.resolve(), args.checkpoint.resolve(), args.output.resolve())
    # The pinned Ascend runtime can abort during interpreter teardown after engine.close().
    # Only use this exit once all work, engine cleanup and file writes have succeeded.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
