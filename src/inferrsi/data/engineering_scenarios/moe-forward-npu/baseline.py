"""EP=2 MoE + shared expert: AllGather/local experts/ReduceScatter baseline.

This is a self-contained, newly written implementation of the common
AllGather-based expert-parallel MoE workload architecture, not a copy of the
vLLM serving stack. It uses a fused gate/up projection and NPU SwiGLU.
"""

import torch
import torch.distributed as dist
import torch.nn.functional as F


def _mlp(x, gate_up, down):
    if x.shape[0] == 0:
        return x.new_empty((0, down.shape[0]))
    projected = F.linear(x, gate_up)
    if x.device.type == "npu":
        import torch_npu
        activated = torch_npu.npu_swiglu(projected, dim=-1)
    else:
        gate, up = projected.chunk(2, dim=-1)
        activated = F.silu(gate) * up
    return F.linear(activated, down)


def compute(x, params, *, config, group):
    world_size, rank = dist.get_world_size(group), dist.get_rank(group)
    if world_size != 2 or rank != config["rank"]:
        raise ValueError("Expected the configured two-rank process group")
    max_tokens = max(config["rank_tokens"])
    hidden = config["hidden"]
    logits = (
        F.linear(x.float(), params["router_weight"], params["router_bias"])
        if x.shape[0] else torch.empty((0, 8), dtype=torch.float32, device=x.device)
    )
    padded_x = F.pad(x, (0, 0, 0, max_tokens - x.shape[0]))
    padded_logits = F.pad(logits, (0, 0, 0, max_tokens - x.shape[0]))
    all_x = torch.empty((2 * max_tokens, hidden), dtype=x.dtype, device=x.device)
    all_logits = torch.empty((2 * max_tokens, 8), dtype=torch.float32, device=x.device)
    dist.all_gather_into_tensor(all_x, padded_x.contiguous(), group=group)
    dist.all_gather_into_tensor(all_logits, padded_logits.contiguous(), group=group)
    selected_logits, selected_experts = all_logits.topk(config["top_k"], dim=-1, sorted=True)
    probabilities = selected_logits.softmax(dim=-1)
    # Padded slots have zero weight and never perform an expert MLP.
    for source_rank, count in enumerate(config["rank_tokens"]):
        if count < max_tokens:
            probabilities[source_rank * max_tokens + count:(source_rank + 1) * max_tokens] = 0
    local_contribution = torch.zeros((2 * max_tokens, hidden), dtype=torch.float32, device=x.device)
    for local_expert in range(4):
        expert_id = rank * 4 + local_expert
        positions = torch.nonzero(
            (selected_experts == expert_id) & (probabilities > 0), as_tuple=False
        )
        if positions.shape[0] == 0:
            continue
        token_ids, slot_ids = positions[:, 0], positions[:, 1]
        values = _mlp(
            all_x.index_select(0, token_ids),
            params["expert_gate_up"][local_expert],
            params["expert_down"][local_expert],
        )
        weighted = values.float() * probabilities[token_ids, slot_ids].unsqueeze(-1)
        local_contribution.index_add_(0, token_ids, weighted)
    local_routed = torch.empty((max_tokens, hidden), dtype=torch.float32, device=x.device)
    dist.reduce_scatter_tensor(local_routed, local_contribution, group=group)
    shared = _mlp(x, params["shared_gate_up"], params["shared_down"])
    return (local_routed[:x.shape[0]] + shared.float()).to(dtype=x.dtype)
