# SPDX-License-Identifier: Apache-2.0
"""Check and pair-time a self-contained Qwen 2.1 denoising candidate."""

import argparse
import hashlib
import importlib.util
import inspect
import json
import math
import os
import shutil
import statistics
import sys
import time
import traceback
from pathlib import Path


class OutputValidationError(ValueError):
    """An explicit task output/input contract check rejected this implementation."""


class CandidateContractError(ValueError):
    """The candidate could not satisfy the Python entry contract before execution."""


def candidate_function(path):
    # Compile independently so only syntax errors in the submitted file are
    # attributed to the candidate, not failures importing its runtime dependencies.
    try:
        compile(path.read_bytes(), str(path), "exec")
    except SyntaxError as exc:
        raise CandidateContractError(str(exc)) from exc
    function = getattr(load(path, "submitted_candidate"), "compute", None)
    if not callable(function):
        raise CandidateContractError("Candidate must define callable compute")
    try:
        inspect.signature(function).bind(*(None,) * 6, config={})
    except TypeError as exc:
        raise CandidateContractError("compute does not accept the task arguments") from exc
    return function


class EngineImportGuard:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in {"vllm", "vllm_omni", "diffusers", "transformers"}:
            raise ModuleNotFoundError(f"The standalone task blocks engine import {fullname}")
        return None


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tensors(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from tensors(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from tensors(item)
    else:
        yield value


def run(args, output, record):
    # This guard is also active while importing PyTorch and torch_npu.
    sys.meta_path.insert(0, EngineImportGuard())
    import torch

    if args.device == "npu":
        visible = os.environ.get("ASCEND_RT_VISIBLE_DEVICES", "").split(",")
        if len(visible) != 1 or not visible[0].strip().isdigit():
            raise ValueError("Run inside one caller-owned NPU allocation, e.g. npu run --gpus 1")
        import torch_npu

        torch.npu.set_device(0)
        torch.npu.matmul.allow_hf32 = False
        synchronize = torch.npu.synchronize
        device = "npu:0"
        record["runtime"] = {
            "torch": torch.__version__,
            "torch_npu": torch_npu.__version__,
            "device": torch.npu.get_device_name(0),
            "hf32": False,
        }
    else:
        if not args.check_only:
            raise ValueError("CPU is supported for --check-only mathematical checks")

        def synchronize():
            pass

        device = "cpu"
        record["runtime"] = {"torch": torch.__version__, "device": "cpu"}
    torch.set_num_threads(args.cpu_threads)
    source = output / "snapshot"
    workload = load(source / "workload.py", "task_workload")
    reference = load(source / "reference.py", "independent_reference").compute
    baseline = load(source / "baseline.py", "trusted_baseline").compute
    functions = {"baseline": baseline}
    dtype = torch.bfloat16 if args.device == "npu" else torch.float32
    task = json.loads((source / "task.json").read_text(encoding="utf-8"))
    tolerance = task["tolerance"]
    selected = [case for case in task["cases"] if not args.case or case["id"] in args.case]
    if not selected or args.case and set(args.case) - {c["id"] for c in selected}:
        raise ValueError("Unknown or empty case selection")
    record["selected_cases"] = [c["id"] for c in selected]
    record["score_scope"] = "selected_cases" if args.case else "complete_task"
    record["phase"] = "candidate_import"
    record["round_consumed"] = True
    functions["candidate"] = candidate_function(source / "candidate.py")

    def invoke(label, inputs, params, config, expected, phase, pair=None, sample=None):
        record["phase"] = label + "_" + phase
        original = [
            (value, value.detach().cpu().clone(), value.stride(), value.device)
            for value in tensors((inputs, params))
        ]
        synchronize()
        started = time.perf_counter_ns()
        result = functions[label](*inputs, params, config=config)
        synchronize()
        elapsed = (time.perf_counter_ns() - started) / 1e6
        shape = (inputs[3].numel() - 1, *inputs[0].shape)
        if (
            not isinstance(result, torch.Tensor)
            or tuple(result.shape) != shape
            or result.dtype != inputs[0].dtype
            or result.device != inputs[0].device
        ):
            raise OutputValidationError("Wrong trajectory shape, dtype or device")
        for value, previous, stride, device_before in original:
            if (
                value.dtype != previous.dtype
                or value.device != device_before
                or value.stride() != stride
                or not torch.equal(value.cpu(), previous)
            ):
                raise OutputValidationError("Inputs or parameters were mutated")
        if result.untyped_storage().data_ptr() in {
            value.untyped_storage().data_ptr() for value, *_ in original
        }:
            raise OutputValidationError(
                "Output must own storage independent of the read-only inputs")
        actual = result.detach().float().cpu()
        errors = actual - expected
        rms = errors.flatten(1).square().mean(1).sqrt()
        scale = expected.flatten(1).square().mean(1).sqrt().clamp_min(1e-12)
        nrmse = (rms / scale).tolist()
        valid = (
            bool(torch.isfinite(actual).all())
            and torch.allclose(actual, expected, rtol=tolerance["rtol"], atol=tolerance["atol"])
            and max(nrmse) <= tolerance["max_nrmse"]
        )
        record["calls"].append(
            {
                "case": config["id"],
                "label": label,
                "phase": phase,
                "pair": pair,
                "sample": sample,
                "elapsed_ms": elapsed,
                "step_nrmse": nrmse,
                "max_abs_error": errors.abs().max().item(),
                "correctness": "PASS" if valid else "FAIL",
            }
        )
        result.zero_()
        if not valid:
            raise OutputValidationError(
                f"Trajectory failed numerical checks, per-step NRMSE={nrmse}")
        return elapsed

    preparation = 0.0
    with torch.inference_mode():
        for index, entry in enumerate(selected):
            config = {**task["defaults"], **entry}
            params = workload.parameters(config, 1701 + index, device, dtype)
            separate_params = {
                label: workload.map_tensors(params, lambda t: t.clone()) for label in functions
            }
            cpu_params = workload.map_tensors(
                params, lambda t: t.cpu().float() if t.is_floating_point() else t.cpu()
            )
            samples = {label: [] for label in functions}
            count = (
                1
                + args.warmups
                + (args.pairs * args.samples if entry["measured"] and not args.check_only else 0)
            )
            for request in range(count):
                record["phase"] = "input_reference_preparation"
                started = time.perf_counter()
                inputs = workload.inputs(config, 9001 + index * 1000 + request, device, dtype)
                cpu_inputs = workload.map_tensors(inputs, lambda t: t.cpu())
                expected = reference(*cpu_inputs, cpu_params, config=config)
                preparation += time.perf_counter() - started
                measured = request > args.warmups
                phase = "measurement" if measured else "correctness" if request == 0 else "warmup"
                sample_index = request - args.warmups - 1
                pair = sample_index // args.samples if measured else None
                order = (
                    ("candidate", "baseline")
                    if measured and pair % 2
                    else ("baseline", "candidate")
                )
                for label in order:
                    owned_inputs = workload.map_tensors(inputs, lambda t: t.clone())
                    elapsed = invoke(
                        label,
                        owned_inputs,
                        separate_params[label],
                        config,
                        expected,
                        phase,
                        pair,
                        sample_index if measured else None,
                    )
                    if measured:
                        samples[label].append(elapsed)
            # Keep the exact same parameter dictionary and storage addresses.
            # An immediately repeated call must observe an in-place weight update.
            for label in functions:
                separate_params[label]["image_out"].neg_()
            cpu_params["image_out"].neg_()
            expected = reference(*cpu_inputs, cpu_params, config=config)
            for label in functions:
                invoke(
                    label,
                    workload.map_tensors(inputs, lambda t: t.clone()),
                    separate_params[label],
                    config,
                    expected,
                    "weight_update",
                )
            if samples["baseline"]:
                medians = {label: statistics.median(values) for label, values in samples.items()}
                record["cases"].append(
                    {
                        "id": config["id"],
                        "samples_ms": samples,
                        "baseline_median_ms": medians["baseline"],
                        "candidate_median_ms": medians["candidate"],
                        "speedup": medians["baseline"] / medians["candidate"],
                    }
                )
    record["preparation_seconds"] = preparation
    record["engine_import_guard"] = "active throughout evaluation"
    record["forbidden_modules_loaded"] = [
        name
        for name in sys.modules
        if name.split(".", 1)[0] in {"vllm", "vllm_omni", "diffusers", "transformers"}
    ]
    if record["forbidden_modules_loaded"]:
        raise ValueError("An engine module was already loaded")
    record.update(status="completed", correctness="PASS", phase="completed")
    if record["cases"]:
        record["speedup"] = math.exp(
            statistics.mean(math.log(c["speedup"]) for c in record["cases"])
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("npu", "cpu"), default="npu")
    parser.add_argument("--pairs", type=int, required=True)
    parser.add_argument("--samples", type=int, required=True, help="Samples per paired block")
    parser.add_argument("--warmups", type=int, required=True)
    parser.add_argument("--cpu-threads", type=int, default=8)
    parser.add_argument("--case", action="append")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.pairs < 1 or args.samples < 1 or args.warmups < 0 or args.cpu_threads < 1:
        parser.error("pairs, samples and threads must be positive; warmups must be nonnegative")
    if not args.candidate.is_file():
        parser.error("candidate must be a self-contained Python file")
    if args.output_dir.exists():
        parser.error("output-dir must be new")
    output = args.output_dir.resolve()
    source = output / "snapshot"
    source.mkdir(parents=True)
    root = Path(__file__).resolve().parent
    for name in (
        "baseline.py",
        "reference.py",
        "workload.py",
        "task.json",
        "TASK.md",
        "benchmark.py",
        "LICENSE",
        "NOTICE.md",
    ):
        shutil.copyfile(root / name, source / name)
    shutil.copyfile(args.candidate, source / "candidate.py")
    identity = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    (output / "identity.json").write_text(json.dumps(identity, indent=2), encoding="utf-8")
    record = {
        "status": "infrastructure_failure",
        "correctness": "INCONCLUSIVE",
        "round_consumed": False,
        "phase": "setup",
        "calls": [],
        "cases": [],
        "speedup": None,
        "protocol": {
            "pairs": args.pairs,
            "samples": args.samples,
            "warmups": args.warmups,
            "check_only": args.check_only,
        },
    }
    started = time.perf_counter()
    try:
        run(args, output, record)
        if any(
            hashlib.sha256((source / name).read_bytes()).hexdigest() != digest
            for name, digest in identity.items()
        ):
            raise ValueError("Frozen source changed during evaluation")
    except Exception as error:
        candidate_failure = (isinstance(error, (OutputValidationError, CandidateContractError))
                             and record["phase"].startswith("candidate_"))
        record.update(
            status="candidate_failure" if candidate_failure else "infrastructure_failure",
            correctness="FAIL" if candidate_failure else "INCONCLUSIVE",
            error=str(error),
            speedup=None,
        )
        (output / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
    record["elapsed_seconds"] = time.perf_counter() - started
    (output / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(
        json.dumps({key: record.get(key) for key in ("status", "correctness", "speedup", "error")})
    )
    return (
        0
        if record["status"] == "completed"
        else 2
        if record["status"] == "candidate_failure"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
