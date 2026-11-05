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
    padded_x = x if x.shape[0] == max_tokens else F.pad(x, (0, 0, 0, max_tokens - x.shape[0]))
    all_x = torch.empty((2 * max_tokens, hidden), dtype=x.dtype, device=x.device)
    dist.all_gather_into_tensor(all_x, padded_x.contiguous(), group=group)
    # Router is replicated. Recompute it after gathering tokens to remove a
    # second collective while preserving FP32 routing arithmetic.
    all_logits = F.linear(all_x.float(), params["router_weight"], params["router_bias"])
    selected_logits, selected_experts = all_logits.topk(config["top_k"], dim=-1, sorted=True)
    probabilities = selected_logits.softmax(dim=-1)
    # Padded slots have zero weight in the final routed contribution.
    for source_rank, count in enumerate(config["rank_tokens"]):
        if count < max_tokens:
            probabilities[source_rank * max_tokens + count:(source_rank + 1) * max_tokens] = 0
    import torch_npu
    # Native dropless dispatch provides both the grouped input and inverse map.
    expert_x, inverse_map, groups, _ = torch_npu.npu_moe_init_routing_v2(
        all_x, selected_experts.to(torch.int32),
        active_num=2 * max_tokens * config["top_k"], expert_num=8,
        drop_pad_mode=0, expert_tokens_num_type=0,
        expert_tokens_num_flag=True, quant_mode=-1,
        active_expert_range=[rank * 4, rank * 4 + 4], row_idx_type=0,
    )
    # Test the runtime's prefix-group support with static dispatch capacity.
    # Group boundaries remain device tensors and contain every local route.
    projected = torch_npu.npu_grouped_matmul(
        [expert_x], [params["expert_gate_up"].transpose(1, 2)],
        group_list=groups, split_item=3, group_type=0,
        group_list_type=0, output_dtype=x.dtype,
    )[0]
    activated = torch_npu.npu_swiglu(projected, dim=-1)
    values = torch_npu.npu_grouped_matmul(
        [activated], [params["expert_down"].transpose(1, 2)],
        group_list=groups, split_item=3, group_type=0,
        group_list_type=0, output_dtype=x.dtype,
    )[0]
    # Kernels may leave inactive capacity uninitialized. Clear it before
    # finalize, including the fully empty-local-expert case.
    inactive = torch.arange(values.shape[0], device=x.device) >= groups[-1]
    full_values = values.masked_fill(inactive.unsqueeze(-1), 0).float()
    local_probabilities = probabilities * (inverse_map.view_as(probabilities) >= 0)
    local_contribution = torch_npu.npu_moe_finalize_routing(
        full_values, None, None, None, local_probabilities,
        inverse_map.clamp_min(0), None, drop_pad_mode=2,
    )
    local_routed = torch.empty((max_tokens, hidden), dtype=torch.float32, device=x.device)
    routed_work = dist.reduce_scatter_tensor(
        local_routed, local_contribution, group=group, async_op=True
    )
    shared = _mlp(x, params["shared_gate_up"], params["shared_down"])
    routed_work.wait()
    return (local_routed[:x.shape[0]] + shared.float()).to(dtype=x.dtype)
