"""Trusted two-rank correctness and full-forward timer, inside torchrun only."""

import argparse
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import statistics
import sys
import time
import traceback
from pathlib import Path


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "compute", None)):
        raise ValueError("Candidate must define compute(x, params, *, config, group)")
    return module.compute


def tensor_snapshot(tensor):
    # BF16 is represented as bytes without asking numpy to support its dtype.
    cpu = tensor.detach().cpu().contiguous()
    return {
        "shape": list(tensor.shape),
        "dtype": str(tensor.dtype),
        "device": str(tensor.device),
        "stride": list(tensor.stride()),
        "storage_offset": tensor.storage_offset(),
        "sha256": hashlib.sha256(cpu.view(torch.uint8).numpy().tobytes()).hexdigest(),
    }


def snapshots(item):
    return {
        "x": tensor_snapshot(item["x"]),
        "params": {k: tensor_snapshot(v) for k, v in item["params"].items()},
        "config": copy.deepcopy(item["config"]),
    }


def check_output(output, item, expected, before, tolerance):
    spec = before["x"]
    shape = (
        isinstance(output, torch.Tensor)
        and list(output.shape) == spec["shape"]
        and tuple(output.shape) == tuple(expected.shape)
    )
    identity = shape and str(output.dtype) == spec["dtype"] and str(output.device) == spec["device"]
    result = {
        "shape_dtype_device": bool(identity),
        "input_parameters_preserved": snapshots(item) == before,
    }
    if not identity:
        result.update(finite=False, values=False, nrmse=None, max_abs_error=None)
        return result
    actual = output.detach().float().cpu()
    finite = bool(torch.isfinite(actual).all())
    diff = actual - expected
    denom = max(float(expected.square().mean().sqrt()), 1e-12) if expected.numel() else 1.0
    nrmse = float(diff.square().mean().sqrt()) / denom if expected.numel() else 0.0
    result.update(
        finite=finite,
        values=finite
        and bool(torch.allclose(actual, expected, atol=tolerance["atol"], rtol=tolerance["rtol"])),
        nrmse=nrmse,
        nrmse_pass=math.isfinite(nrmse) and nrmse <= tolerance["nrmse"],
        max_abs_error=float(diff.abs().max()) if diff.numel() else 0.0,
    )
    return result


def valid(checks):
    return all(
        checks.get(k) is True
        for k in (
            "shape_dtype_device",
            "input_parameters_preserved",
            "finite",
            "values",
            "nrmse_pass",
        )
    )


def main():
    global torch
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    ROOT = args.run_dir.resolve()
    OUT = ROOT / "results"
    sys.path.insert(0, str(ROOT / "task"))
    rank = int(os.environ["RANK"])
    local_rank = int(os.environ["LOCAL_RANK"])
    record = {
        "rank": rank,
        "started_at_utc": stamp(),
        "completed": False,
        "correctness": "INCONCLUSIVE",
        "calls": [],
        "samples": [],
        "phase": "initializing",
    }
    path = OUT / f"rank-{rank}.json"
    write(path, record)
    initialized = False
    try:
        import torch
        import torch.distributed as dist
        import torch_npu
        from oracle import expected as oracle_expected
        from oracle import expected_from_input
        from torch_npu.npu.utils import get_cann_version
        from workload import build_case, cpu_input, load_cases, load_task, warm_input

        torch.set_num_threads(8)
        assert int(os.environ["WORLD_SIZE"]) == 2
        assert torch.npu.device_count() == 2
        assert rank in (0, 1) and local_rank in (0, 1) and rank == local_rank
        torch.npu.set_device(local_rank)
        torch.npu.matmul.allow_hf32 = False
        record["phase"] = "hccl_initialization"
        write(path, record)
        dist.init_process_group("hccl", timeout=dt.timedelta(seconds=150))
        initialized = True
        dist.barrier()
        torch.npu.synchronize()
        request = json.loads((ROOT / "request.json").read_text())
        task = load_task()
        cases = load_cases()
        tolerance = task["tolerance"]
        measure = task["measurement"]
        record["runtime"] = {
            "torch": torch.__version__,
            "torch_npu": torch_npu.__version__,
            "cann": str(get_cann_version()),
            "python": sys.version.split()[0],
            "device": torch.npu.get_device_name(local_rank),
            "logical_device": local_rank,
            "matmul_allow_hf32": bool(torch.npu.matmul.allow_hf32),
        }
        record["phase"] = "baseline_import"
        write(path, record)
        functions = {"baseline": load(ROOT / "task" / "baseline.py", "trusted_baseline")}
        record["phase"] = "candidate_import"
        write(path, record)
        functions["candidate"] = load(
            ROOT / "candidate" / "implementation.py", "evaluated_candidate"
        )

        parameter_bundles = {}
        configs = {}
        expected_cache = {}
        prepared_inputs = {}

        def prepare_case(case, case_index):
            """Prepare both sides before timing, including all expensive CPU work.

            Computing the oracle just before the first implementation of a pair
            creates an asymmetric idle gap. Neither side may pay that gap alone.
            """
            started = time.monotonic()
            record["phase"] = "trusted_case_preparation"
            record["active_case"] = case["id"]
            write(path, record)
            base_seed = 100000 + case_index * 10000
            seeds = [base_seed, base_seed + 1]
            timed_seeds = []
            if case["measured"]:
                seeds.extend(base_seed + 10 + i for i in range(measure["warmups"]))
                timed_seeds = [
                    base_seed + 100 + pair * 100 + sample
                    for pair in range(request["repetitions"])
                    for sample in range(measure["samples_per_pair"])
                ]
                seeds.extend(timed_seeds)
            # All margin checks, FP32 oracle GEMMs and host tensors are prepared
            # before either label's correctness/warmup/measurement starts.
            host_inputs = {(seed, "standard"): cpu_input(case, rank, seed) for seed in seeds}
            expected_cache.clear()
            expected_cache.update(
                {(seed, "standard"): oracle_expected(case, seed, rank) for seed in seeds}
            )
            warm_started = time.monotonic()
            warm_pairs = []
            for seed in timed_seeds:
                warmed = warm_input(case, rank, seed)
                warm_expected = expected_from_input(case, warmed)
                original, original_expected = (
                    host_inputs[(seed, "standard")],
                    expected_cache[(seed, "standard")],
                )
                if original.numel():
                    assert not torch.equal(original, warmed), (
                        "Shape warmup must use different input values"
                    )
                    assert not torch.allclose(
                        original_expected,
                        warm_expected,
                        atol=tolerance["atol"],
                        rtol=tolerance["rtol"],
                    ), "Shape warmup must have a different output"
                    input_delta = (warmed.float() - original.float()).square().mean(dim=1).sqrt()
                    output_delta = (warm_expected - original_expected).square().mean().sqrt()
                    output_scale = max(float(original_expected.square().mean().sqrt()), 1e-12)
                    difference_nrmse = float(output_delta) / output_scale
                    assert math.isfinite(difference_nrmse) and difference_nrmse > 0.1, (
                        "Shape warmup output must prevent replay"
                    )
                    warm_pairs.append(
                        {
                            "seed": seed,
                            "minimum_row_input_rms_difference": float(input_delta.min()),
                            "output_nrmse_difference": difference_nrmse,
                            "output_outside_tolerance": True,
                        }
                    )
                host_inputs[(seed, "shape_warmup")] = warmed
                expected_cache[(seed, "shape_warmup")] = warm_expected
            warm_preparation_seconds = time.monotonic() - warm_started
            prepared_inputs.clear()
            for label in ("baseline", "candidate"):
                bundle_key = (case["id"], label)
                item = build_case(case, rank, torch.device(f"npu:{local_rank}"), base_seed)
                if case["id"] == "weight-update":
                    previous = parameter_bundles[("unequal-top1", label)]
                    for name, value in item["params"].items():
                        previous[name].copy_(value)
                    item["params"] = previous
                parameter_bundles[bundle_key] = item["params"]
                configs[bundle_key] = copy.deepcopy(item["config"])
                for (seed, variant), host_input in host_inputs.items():
                    prepared_inputs[(seed, label, variant)] = host_input.to(
                        f"npu:{local_rank}", copy=True
                    )
            torch.npu.synchronize()
            record.setdefault("case_preparation", []).append(
                {
                    "case_id": case["id"],
                    "distinct_seeds": len(seeds),
                    "shape_warmup_inputs": len(timed_seeds),
                    "shape_warmup_preparation_seconds": warm_preparation_seconds,
                    "shape_warmup_pairs": warm_pairs,
                    "elapsed_seconds": time.monotonic() - started,
                }
            )
            write(path, record)

        def call(
            case, seed, label, phase, *, timed=False, pair=None, sample=None, variant="standard"
        ):
            record["phase"] = "trusted_pre_call_validation"
            record["active_case"] = case["id"]
            write(path, record)
            # Production model parameters stay stable across forward calls. The
            # two implementations own separate, identical parameter tensors.
            bundle_key = (case["id"], label)
            item = {
                "x": prepared_inputs[(seed, label, variant)],
                "params": parameter_bundles[bundle_key],
                "config": copy.deepcopy(configs[bundle_key]),
            }
            before = snapshots(item)
            expected = expected_cache[(seed, variant)]
            assert expected.device.type == "cpu" and expected.dtype == torch.float32
            # This barrier is outside the measured interval. synchronize completes
            # HCCL/device work before starting the full host-to-device call timer.
            record["phase"] = label + "_" + phase
            write(path, record)
            try:
                dist.barrier()
                torch.npu.synchronize()
            except BaseException:
                record["phase"] = "trusted_rank_alignment_failure"
                write(path, record)
                raise
            started = time.perf_counter_ns()
            with torch.inference_mode():
                output = functions[label](
                    item["x"], item["params"], config=item["config"], group=dist.group.WORLD
                )
            torch.npu.synchronize()
            local_ms = (time.perf_counter_ns() - started) / 1e6
            record["phase"] = "trusted_output_validation"
            write(path, record)
            checks = check_output(output, item, expected, before, tolerance)
            good = torch.tensor([int(valid(checks))], device=item["x"].device, dtype=torch.int32)
            dist.all_reduce(good, op=dist.ReduceOp.MIN)
            torch.npu.synchronize()
            call_record = {
                "case_id": case["id"],
                "seed": seed,
                "label": label,
                "phase": phase,
                "variant": variant,
                "pair": pair,
                "sample": sample,
                "checks": checks,
                "input_sha256": before["x"]["sha256"],
                "all_ranks_correct": bool(good.item()),
                "local_elapsed_ms": local_ms,
                "included_in_score": timed,
            }
            record["calls"].append(call_record)
            if not call_record["all_ranks_correct"]:
                record["correctness"] = "FAIL" if label == "candidate" else "INCONCLUSIVE"
                record["failure_kind"] = (
                    "candidate_invalid_output"
                    if label == "candidate"
                    else "baseline_invalid_output"
                )
                write(path, record)
                raise ValueError(f"{label} {case['id']} failed independent correctness")
            if timed:
                elapsed = torch.tensor([local_ms], device=item["x"].device, dtype=torch.float32)
                dist.all_reduce(elapsed, op=dist.ReduceOp.MAX)
                torch.npu.synchronize()
                slowest = float(elapsed.item())
                if not math.isfinite(slowest) or slowest <= 0:
                    raise ValueError("Invalid completed-forward time")
                record["samples"].append(
                    {
                        **{
                            k: call_record[k]
                            for k in ("case_id", "seed", "label", "pair", "sample", "input_sha256")
                        },
                        "local_elapsed_ms": local_ms,
                        "slowest_rank_elapsed_ms": slowest,
                    }
                )
            # Explicitly overwrite returned storage after verification. Retaining
            # an output object for replay cannot satisfy a later changed input.
            record["phase"] = "trusted_output_reset"
            write(path, record)
            with torch.inference_mode():
                output.zero_()
            torch.npu.synchronize()
            write(path, record)

        for case_index, case in enumerate(cases):
            prepare_case(case, case_index)
            # Each verification and timed input changes. Both implementations use
            # exactly the same inputs/weights, constructed independently.
            base_seed = 100000 + case_index * 10000
            for variant in range(2):
                for label in ("baseline", "candidate"):
                    call(case, base_seed + variant, label, "correctness")
            if not case["measured"]:
                continue
            for warmup in range(measure["warmups"]):
                for label in ("baseline", "candidate"):
                    call(case, base_seed + 10 + warmup, label, "warmup")
            for pair in range(request["repetitions"]):
                order = ("baseline", "candidate") if pair % 2 == 0 else ("candidate", "baseline")
                for sample in range(measure["samples_per_pair"]):
                    seed = base_seed + 100 + pair * 100 + sample
                    # Both implementations see their own shape-matched but
                    # numerically different input before either timed call. This
                    # pays dynamic operator preparation independently of whether
                    # the other implementation happens to use the same operators.
                    for label in order:
                        call(
                            case,
                            seed,
                            label,
                            "shape_warmup",
                            pair=pair,
                            sample=sample,
                            variant="shape_warmup",
                        )
                    for label in order:
                        call(case, seed, label, "measurement", timed=True, pair=pair, sample=sample)

        record["phase"] = "trusted_summary"
        write(path, record)
        result_cases = []
        for case in cases:
            if not case["measured"]:
                continue
            grouped = {
                label: [
                    s["slowest_rank_elapsed_ms"]
                    for s in record["samples"]
                    if s["case_id"] == case["id"] and s["label"] == label
                ]
                for label in ("baseline", "candidate")
            }
            expected_count = request["repetitions"] * measure["samples_per_pair"]
            assert all(len(values) == expected_count for values in grouped.values())
            b, c = (statistics.median(grouped[label]) for label in ("baseline", "candidate"))
            result_cases.append(
                {
                    "id": case["id"],
                    "baseline_median_ms": b,
                    "candidate_median_ms": c,
                    "speedup": b / c,
                    "samples_ms": grouped,
                }
            )
        speedup = math.exp(statistics.mean(math.log(c["speedup"]) for c in result_cases))
        record.update(
            completed=True,
            correctness="PASS",
            phase="completed",
            cases=result_cases,
            speedup=speedup,
            aggregation="geometric_mean_case_speedups",
            measurement_protocol="shape-matched-different-values-warmup-both-labels-before-paired-timing",
            shape_warmup_cost={
                label: {
                    "calls": sum(
                        c["phase"] == "shape_warmup" and c["label"] == label
                        for c in record["calls"]
                    ),
                    "local_forward_ms": sum(
                        c["local_elapsed_ms"]
                        for c in record["calls"]
                        if c["phase"] == "shape_warmup" and c["label"] == label
                    ),
                }
                for label in ("baseline", "candidate")
            },
            peak_allocated_bytes=int(torch.npu.max_memory_allocated(local_rank)),
        )
        if rank == 0:
            summary = {
                k: record[k]
                for k in (
                    "completed",
                    "correctness",
                    "cases",
                    "speedup",
                    "aggregation",
                    "measurement_protocol",
                )
            }
            summary["metrics"] = {
                "suite_latency_ms": sum(c["candidate_median_ms"] for c in result_cases)
            }
            write(OUT / "summary.json", summary)
            write(Path(os.environ["INFERRSI_RESULT_PATH"]), summary)
    except BaseException as error:
        record["error"] = repr(error)
        record["traceback"] = traceback.format_exc()
    finally:
        record["completed_at_utc"] = stamp()
        write(path, record)
        if initialized:
            # Fatal candidate exceptions can leave the peer in a collective.
            # torchrun plus the outer bounded driver owns full-job termination.
            try:
                dist.destroy_process_group()
            except BaseException:
                pass
    return 0 if record["completed"] else 2


if __name__ == "__main__":
    sys.exit(main())
