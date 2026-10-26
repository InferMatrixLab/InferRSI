# Allocation efficiency is distinct from prefix reuse

ID: `case.paged-kv-allocation`. Owner: `optimization-search-policy`.
Axis: caching/state management. Resource: Accelerator HBM capacity.
Source-derived candidate; local validation not_run. No local campaign evidence.

## Source observation

Kwon et al., [PagedAttention, arXiv:2309.06180v1](https://arxiv.org/html/2309.06180v1),
§§4.1–4.5, 7.1–7.3: logical blocks map to separately allocated physical KV blocks;
sharing and copy-on-write reduce duplication. §7.1 reports attention-kernel
overhead despite system-level gains. §7.2/Figure 18 finds large blocks degrade
Alpaca short-sequence performance. §7.3 reports small transfers reduce swapping
efficiency. These ablations support a capacity/overhead trade-off, not a claim
that paging makes every kernel faster or makes prefix lookup unnecessary.

## Proposed decision

Signal: live/reserved KV and allocation traces show wasted capacity limiting admission.
Prerequisites: allocator/block accounting and a supported paged-attention path.
Candidate: change allocation/block size or sharing independently of scheduler policy.
Invariants: reference counts, copy-on-write, cancellation and no reuse before all
consumers finish. Metrics: live/reserved bytes, fragmentation, admitted work,
kernel latency, preemption/recompute and service tails/goodput. Counter-indication:
spare memory with compute saturation may offer no capacity benefit. Additional
batch capacity is not permission to weaken latency gates. Tiering is a separate
candidate with transfer costs. Rollback: restore the original allocator settings
after draining owned requests; never reinterpret live blocks under a new layout.

Attribution and source version: [case record](paged-kv-allocation.json).
