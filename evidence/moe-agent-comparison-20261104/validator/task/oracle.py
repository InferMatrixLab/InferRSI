"""Independent, unsharded CPU FP32 oracle for the complete mathematical MoE.

No baseline/candidate, distributed collective, NPU fused operator, permutation
or combine implementation is reused. Input and weight generators are shared
only to define the problem data.
"""

from functools import lru_cache

import torch

from workload import _weight_key, cpu_input, cpu_parameters


@lru_cache(maxsize=12)
def _float_parameters(key):
    hidden, intermediate, weight_seed, variant, routing = key
    case = {
        "hidden": hidden, "intermediate": intermediate,
        "weight_seed": weight_seed, "weight_variant": variant,
        "routing": routing,
    }
    return {name: value.float() for name, value in cpu_parameters(case, range(8)).items()}


def _expert(x, w_gate_up, w_down):
    intermediate = w_down.shape[1]
    # Separate matmuls deliberately differ from the implementation's fused
    # projection, while representing exactly the same mathematical function.
    gate = x @ w_gate_up[:intermediate].T
    up = x @ w_gate_up[intermediate:].T
    activated = (gate / (1.0 + torch.exp(-gate))) * up
    return activated @ w_down.T


@torch.inference_mode()
def expected(case, seed, rank):
    return expected_from_input(case, cpu_input(case, rank, seed))


@torch.inference_mode()
def expected_from_input(case, x_cpu):
    """Evaluate supplied problem data without using any candidate routing."""
    if x_cpu.device.type != "cpu" or x_cpu.dtype != torch.bfloat16:
        raise ValueError("Oracle input must be CPU BF16 problem data")
    if x_cpu.ndim != 2 or x_cpu.shape[1] != int(case["hidden"]):
        raise ValueError("Oracle input shape does not match the case")
    x = x_cpu.float()
    if x.shape[0] == 0:
        return x
    params = _float_parameters(_weight_key(case))
    logits = x @ params["router_weight"].T + params["router_bias"]
    # Sorting is an independent selection implementation. Generated input
    # margins exclude top-k boundary ties.
    order = torch.argsort(logits, dim=1, descending=True)
    chosen = order[:, :int(case["top_k"])]
    chosen_logits = logits.gather(1, chosen)
    exponents = torch.exp(chosen_logits - chosen_logits.max(dim=1, keepdim=True).values)
    probabilities = exponents / exponents.sum(dim=1, keepdim=True)
    result = _expert(x, params["shared_gate_up"], params["shared_down"])
    for expert_id in range(8):
        # Weighted output is accumulated directly at the original token row;
        # no distributed packing/permutation logic is involved.
        rows, slots = torch.where(chosen == expert_id)
        if rows.numel() == 0:
            continue
        expert_values = _expert(
            x[rows], params["expert_gate_up"][expert_id], params["expert_down"][expert_id]
        )
        result[rows] += expert_values * probabilities[rows, slots, None]
    return result.contiguous()


def metrics(actual, expected_output):
    """Useful calibration diagnostics; verdict thresholds belong to task.json."""
    values = actual.detach().cpu().float()
    reference = expected_output.detach().cpu().float()
    if values.shape != reference.shape:
        return {"shape_match": False, "finite": False}
    if values.numel() == 0:
        return {"shape_match": True, "finite": True, "max_abs": 0.0, "nrmse": 0.0}
    error = values - reference
    reference_rms = torch.sqrt(torch.mean(reference.square())).item()
    return {
        "shape_match": True,
        "finite": bool(torch.isfinite(values).all()),
        "max_abs": float(error.abs().max()),
        "nrmse": float(torch.sqrt(torch.mean(error.square()))) / max(reference_rms, 1e-12),
        "reference_rms": reference_rms,
    }
