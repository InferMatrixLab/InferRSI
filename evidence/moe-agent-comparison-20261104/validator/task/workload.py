"""Trusted, CPU-created inputs and deterministic EP-local model parameters.

No device import/initialization occurs until build_case receives a device.
Candidate implementations may use only the tensors/config passed to compute;
regenerating other ranks' weights or using these generator seeds is prohibited.
"""

import json
import math
from functools import lru_cache
from pathlib import Path

import torch


TASK_FILE = Path(__file__).with_name("task.json")


def load_task():
    return json.loads(TASK_FILE.read_text(encoding="utf-8"))


def load_cases():
    return load_task()["cases"]


def _generator(seed):
    return torch.Generator(device="cpu").manual_seed(int(seed) % (2**63 - 1))


def _weight_key(case):
    return (
        int(case["hidden"]), int(case["intermediate"]),
        int(case["weight_seed"]), int(case.get("weight_variant", 0)),
        str(case["routing"]),
    )


@lru_cache(maxsize=12)
def _common_cpu_weights(key):
    hidden, intermediate, seed, variant, routing = key
    gen = _generator(seed + 1_000_003 * variant)
    router_weight = torch.randn(8, hidden, generator=gen) / math.sqrt(hidden)
    router_bias = torch.zeros(8, dtype=torch.float32)
    if routing == "skewed":
        router_bias[0], router_bias[1] = 3.0, 1.5
    elif routing == "empty-rank-experts":
        router_bias.fill_(-16.0)
        router_bias[0], router_bias[1] = 16.0, 15.0
    elif routing != "balanced":
        raise ValueError(f"Unknown routing distribution: {routing}")
    shared_gate_up = (
        torch.randn(2 * intermediate, hidden, generator=gen) / math.sqrt(hidden)
    ).to(torch.bfloat16)
    shared_down = (
        torch.randn(hidden, intermediate, generator=gen) / math.sqrt(intermediate)
    ).to(torch.bfloat16)
    return router_weight, router_bias, shared_gate_up, shared_down


@lru_cache(maxsize=96)
def _expert_cpu_weights(key, expert_id):
    hidden, intermediate, seed, variant, _ = key
    gen = _generator(seed + 1_000_003 * variant + 10_007 * (int(expert_id) + 1))
    gate_up = (
        torch.randn(2 * intermediate, hidden, generator=gen) / math.sqrt(hidden)
    ).to(torch.bfloat16)
    down = (
        torch.randn(hidden, intermediate, generator=gen) / math.sqrt(intermediate)
    ).to(torch.bfloat16)
    return gate_up, down


def cpu_parameters(case, expert_ids):
    """Fresh parameter containers; caller chooses only its owned expert IDs.

    Oracle may request all eight experts. The candidate never receives this
    function, the case record, seeds, or the global expert tensors as arguments.
    """
    key = _weight_key(case)
    router_weight, router_bias, shared_gate_up, shared_down = _common_cpu_weights(key)
    experts = [_expert_cpu_weights(key, expert_id) for expert_id in expert_ids]
    return {
        "router_weight": router_weight,
        "router_bias": router_bias,
        "expert_gate_up": torch.stack([weights[0] for weights in experts]),
        "expert_down": torch.stack([weights[1] for weights in experts]),
        "shared_gate_up": shared_gate_up,
        "shared_down": shared_down,
    }


def cpu_input(case, rank, seed):
    """Different rank and call seeds produce different, BF16 input tensors.

    Random test inputs near a router top-k boundary are regenerated outside
    measurement. This avoids making an essentially tied routing decision a
    numerical-precision contest between CPU and NPU FP32 matmul implementations.
    It does not precompute or provide candidate routing decisions.
    """
    count = int(case["rank_tokens"][rank])
    hidden = int(case["hidden"])
    gen = _generator(int(seed) + 97_409 * (rank + 1))
    x = (0.7 * torch.randn(count, hidden, generator=gen)).to(torch.bfloat16)
    if count == 0:
        return x
    router, bias, _, _ = _common_cpu_weights(_weight_key(case))
    for _ in range(16):
        logits = torch.nn.functional.linear(x.float(), router, bias)
        ordered = logits.sort(dim=-1, descending=True).values
        k = int(case["top_k"])
        bad = ordered[:, k - 1] - ordered[:, k] < 0.025
        n_bad = int(bad.sum())
        if not n_bad:
            return x.contiguous()
        x[bad] = (0.7 * torch.randn(n_bad, hidden, generator=gen)).to(torch.bfloat16)
    raise RuntimeError("Could not create unambiguous routing inputs")


@lru_cache(maxsize=12)
def _router_nullspace_projection(key):
    router, _, _, _ = _common_cpu_weights(key)
    # Solve rather than explicitly invert W W^T. The eight random router rows
    # are full rank; failure is an invalid workload, never a silent fallback.
    return torch.linalg.solve(router @ router.T, router)


def warm_input(case, rank, seed):
    """Different token values with the same per-token selected expert sets.

    The timed input is never reused as its warmup, nor merely permuted. A
    substantial independent perturbation in the router's nullspace preserves
    expert GEMM row counts while changing the expert/shared-expert computation.
    BF16 quantization slightly perturbs router logits, so every row is checked
    again after quantization. Rejected rows are resampled; there is no fallback
    to the original input or to smaller noise.
    """
    original = cpu_input(case, rank, seed)
    if original.shape[0] == 0:
        return original.clone()
    original_fp32 = original.float()
    router, bias, _, _ = _common_cpu_weights(_weight_key(case))
    projection = _router_nullspace_projection(_weight_key(case))
    top_k = int(case["top_k"])
    original_logits = torch.nn.functional.linear(original_fp32, router, bias)
    original_experts = original_logits.topk(top_k, dim=-1).indices.sort(dim=-1).values
    gen = _generator(int(seed) + 30_000_019 + 1_009_117 * (rank + 1))
    pending = torch.arange(original.shape[0])
    warmed = torch.empty_like(original)
    for _ in range(32):
        noise = 0.3 * torch.randn(pending.numel(), original.shape[1], generator=gen)
        noise = noise - (noise @ router.T) @ projection
        trial = (original_fp32[pending] + noise).to(torch.bfloat16)
        trial_fp32 = trial.float()
        logits = torch.nn.functional.linear(trial_fp32, router, bias)
        selected = logits.topk(top_k, dim=-1).indices.sort(dim=-1).values
        ordered = logits.sort(dim=-1, descending=True).values
        margin = ordered[:, top_k - 1] - ordered[:, top_k]
        row_rms_change = (trial_fp32 - original_fp32[pending]).square().mean(dim=-1).sqrt()
        accepted = (
            (selected == original_experts[pending]).all(dim=-1)
            & (margin >= 0.02)
            & (row_rms_change >= 0.15)
            & torch.isfinite(trial_fp32).all(dim=-1)
        )
        warmed[pending[accepted]] = trial[accepted]
        pending = pending[~accepted]
        if pending.numel() == 0:
            return warmed.contiguous()
    raise RuntimeError("Could not create distinct routing-shape-matched warm input")


def build_case(case, rank, device, seed):
    """Return local input, EP-local parameters and public structural config."""
    if rank not in (0, 1):
        raise ValueError("This task requires exactly two ranks")
    cpu_params = cpu_parameters(case, range(rank * 4, rank * 4 + 4))
    params = {name: tensor.to(device=device, copy=True) for name, tensor in cpu_params.items()}
    config = {
        "world_size": 2,
        "rank": rank,
        "num_experts": 8,
        "experts_per_rank": 4,
        "hidden": int(case["hidden"]),
        "intermediate": int(case["intermediate"]),
        "top_k": int(case["top_k"]),
        "rank_tokens": list(case["rank_tokens"]),
    }
    return {
        "x": cpu_input(case, rank, seed).to(device=device, copy=True),
        "params": params,
        "config": config,
    }
