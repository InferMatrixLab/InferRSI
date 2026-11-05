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
    # The router is replicated: recompute the small FP32 projection after
    # gathering BF16 activations and avoid a separate logits collective.
    all_logits = F.linear(all_x.float(), params["router_weight"], params["router_bias"])
    selected_logits, selected_experts = all_logits.topk(config["top_k"], dim=-1, sorted=True)
    probabilities = selected_logits.softmax(dim=-1)
    # Padded slots have zero weight and never perform an expert MLP.
    for source_rank, count in enumerate(config["rank_tokens"]):
        if count < max_tokens:
            probabilities[source_rank * max_tokens + count:(source_rank + 1) * max_tokens] = 0
    local_contribution = torch.zeros((2 * max_tokens, hidden), dtype=torch.float32, device=x.device)
    import torch_npu
    # Native dropless routing produces expert-sorted rows and a row-major
    # inverse mapping. Only this rank's expert range is processed here.
    expanded_x, row_map, group_counts, _ = torch_npu.npu_moe_init_routing_v2(
        all_x, selected_experts.to(torch.int32), expert_num=8,
        active_expert_range=[rank * 4, rank * 4 + 4],
        expert_tokens_num_type=1, expert_tokens_num_flag=True,
        drop_pad_mode=0, quant_mode=-1, row_idx_type=0
    )
    routed_count = int(group_counts.sum().item())
    if routed_count:
        projected = torch_npu.npu_grouped_matmul(
            [expanded_x[:routed_count]], [params["expert_gate_up"].transpose(1, 2)],
            group_list=group_counts, split_item=3, group_type=0, group_list_type=1
        )[0]
        activated = torch_npu.npu_swiglu(projected, dim=-1)
        values = torch_npu.npu_grouped_matmul(
            [activated], [params["expert_down"].transpose(1, 2)],
            group_list=group_counts, split_item=3, group_type=0, group_list_type=1
        )[0]
        # Finalize in FP32. Map non-local slots to an explicitly zero padded
        # row, so the dropless row-major finalize never sees negative indices.
        padded_values = F.pad(values.float(), (0, 0, 0, 2 * max_tokens * config["top_k"] - routed_count))
        safe_map = torch.where(row_map >= 0, row_map, routed_count)
        local_contribution = torch_npu.npu_moe_finalize_routing(
            padded_values, None, None, None, probabilities,
            safe_map, None, drop_pad_mode=2
        )
    local_routed = torch.empty((max_tokens, hidden), dtype=torch.float32, device=x.device)
    dist.reduce_scatter_tensor(local_routed, local_contribution, group=group)
    shared = _mlp(x, params["shared_gate_up"], params["shared_down"])
    return (local_routed[:x.shape[0]] + shared.float()).to(dtype=x.dtype)
