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
    padded_x = F.pad(x, (0, 0, 0, max_tokens - x.shape[0]))
    all_x = torch.empty((2 * max_tokens, hidden), dtype=x.dtype, device=x.device)
    dist.all_gather_into_tensor(all_x, padded_x.contiguous(), group=group)
    # Router parameters are replicated, so recomputing the small router on the
    # gathered tokens avoids a separate FP32 logits collective.
    all_logits = F.linear(
        all_x.float(), params["router_weight"], params["router_bias"]
    )
    selected_logits, selected_experts = all_logits.topk(
        config["top_k"], dim=-1, sorted=True
    )
    probabilities = selected_logits.softmax(dim=-1)
    # Padded slots have zero weight and never perform an expert MLP.
    for source_rank, count in enumerate(config["rank_tokens"]):
        if count < max_tokens:
            probabilities[source_rank * max_tokens + count:(source_rank + 1) * max_tokens] = 0
    local_contribution = torch.zeros(
        (2 * max_tokens, hidden), dtype=torch.float32, device=x.device
    )
    flat_experts = selected_experts.reshape(-1)
    flat_probabilities = probabilities.reshape(-1)
    flat_token_ids = (
        torch.arange(selected_experts.shape[0], device=x.device)
        .unsqueeze(1)
        .expand(-1, config["top_k"])
        .reshape(-1)
    )
    local_mask = (
        (flat_experts >= rank * 4)
        & (flat_experts < (rank + 1) * 4)
        & (flat_probabilities > 0)
    )
    local_experts = flat_experts[local_mask] - rank * 4
    token_ids = flat_token_ids[local_mask]
    route_probabilities = flat_probabilities[local_mask]
    if local_experts.numel():
        assignment_prefix = F.one_hot(local_experts, num_classes=4).cumsum(0) - 1
        packed_rows = assignment_prefix.gather(
            1, local_experts.unsqueeze(1)
        ).squeeze(1)
        counts = torch.bincount(local_experts, minlength=4)
        max_expert_tokens = int(counts.max().item())
        expert_inputs = torch.zeros(
            (4, max_expert_tokens, hidden), dtype=x.dtype, device=x.device
        )
        expert_inputs[local_experts, packed_rows] = all_x.index_select(0, token_ids)
        projected = torch.bmm(
            expert_inputs, params["expert_gate_up"].transpose(1, 2)
        )
        if x.device.type == "npu":
            import torch_npu
            activated = torch_npu.npu_swiglu(projected, dim=-1)
        else:
            gate, up = projected.chunk(2, dim=-1)
            activated = F.silu(gate) * up
        expert_outputs = torch.bmm(
            activated, params["expert_down"].transpose(1, 2)
        )
        weighted = (
            expert_outputs[local_experts, packed_rows].float()
            * route_probabilities.unsqueeze(-1)
        )
        local_contribution.index_add_(0, token_ids, weighted)
    local_routed = torch.empty(
        (max_tokens, hidden), dtype=torch.float32, device=x.device
    )
    reduce_work = dist.reduce_scatter_tensor(
        local_routed, local_contribution, group=group, async_op=True
    )
    shared = _mlp(x, params["shared_gate_up"], params["shared_down"])
    reduce_work.wait()
    return (local_routed[:x.shape[0]] + shared.float()).to(dtype=x.dtype)
