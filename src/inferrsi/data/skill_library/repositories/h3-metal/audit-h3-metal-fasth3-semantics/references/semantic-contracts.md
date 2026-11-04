# FastH3 semantic contracts and falsifiers

All implementation claims below are scoped to the immutable
[h3-metal source](https://github.com/zuiho-kai/h3-metal/tree/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8).
Source implementation, comments about external FastVideo behavior, upstream
reported results, and local execution are different evidence classes. External
comments are not a newly verified FastVideo/config/weight readset.

## Effective parameters and ambient state

[`h3_generate`](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3.c#L893-L923)
copies and normalizes FastH3 parameters **before** parameter validation:

| Requested control | FastH3 parameter used | Important qualification |
| --- | --- | --- |
| steps | 4 | The separate fixed audio/video sigma arrays are not the original four-step schedule |
| dit_layers | 50 | Does not select a fully BF16 reference or disable other approximate paths |
| denoise_reuse / core_reuse | 1 / 1 | `H3_REUSE_STEPS` is parsed only for reuse greater than 1 |
| token_reduction | 0 | Later environment enable can still configure reduction |
| ssd_streaming | 0 | A requested FastH3+SSD command is not an SSD-memory experiment |
| ordered references | rejected when count is nonzero | FL2VA first/last-frame anchors are not the ordered Ref2VA list |

The layer default is [50](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3.h#L13-L19).
[`configure_token_reduction`](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit.c#L575-L670)
still recognizes nonempty/non-`0` `H3_TOKEN_REDUCTION`, its block range, early
range and scale. At forward time,
[`H3_DISABLE_TOKEN_REDUCTION` presence](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit.c#L2704-L2748)
suppresses entering reduction. Without that suppression, a reduced FastH3
sequence reaches the [unsupported full-sequence guard](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit.c#L2439-L2483).
Flag this conflict; do not infer universal successful execution or universal
failure merely from the normalized parameter.

[`h3_temporal`](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_host.c#L15-L46)
aligns to 5+17k frames. Requested 49 therefore becomes 56 with video latent_t17.
At an internal 768×448 canvas, the latent is 48×28 and patchified video grid is
17×14×24: 120 video tiles and top-k12. These are source-derived arithmetic,
not measured output, quality or timing. Record internal canvas separately from
resized output. The result reports
[decoded `frames.frames`](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3.c#L1864-L1877),
not an asserted trim to the originally requested count.

## Checkpoint identity and tensor transformations

Generation chooses
[`FastH3-4step/transformer` with FL2VA encoders/VAEs](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3.c#L979-L989).
DiT uses a [path substring](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit.c#L1984-L2005),
while AdaLN schedule uses
[`time_embedder.linear_1.weight` presence](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit_schedule.c#L304-L333).
A mixed-key checkpoint or renamed direct-loader directory needs its own audit;
the two detection predicates are not a universal format identifier.

The [loader mapping](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit.c#L249-L455)
handles block/refiner, norm, attention-out, MLP, time and modality projection
names. Its semantic work includes:

- **QKV:** 56 heads ×128 dimensions. For head h, source rows `h*128:(h+1)*128`
  from each Q/K/V tensor occupy destination rows `h*384:(h+1)*384` in Q,K,V
  order. A global `concat(Q,K,V)` has the same shape but wrong multi-head rows.
  A labeled two-head/two-row fixture must read
  `q0,q1,k0,k1,v0,v1,q2,q3,k2,k3,v2,v3`, not
  `q0,q1,q2,q3,k0,k1,k2,k3,v0,v1,v2,v3`.
- **FC1:** swap the two equal projection-row halves before quantization; this
  preserves the baseline SwiGLU gate/value convention. A tiny `[a,b,c,d]`
  fixture must become `[c,d,a,b]`. Matching shape/dtype does not catch no-swap.
- **F32 consumers:** mapped source weights are loaded BF16, then explicitly
  cast to F32 for the mapped `f1`/`f2` paths. Do not infer the checkpoint itself
  stores original-H3 F32 tensors just because the consumer is F32.

Within the selected
[int8 fused-MLP branch](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit.c#L2527-L2552),
the FC2 row-wise selector is `use_int8_row_fc2 || fasth3`. An unset row-FC2
request therefore does not prove grouped FC2 in FastH3. This is branch-dependent:
int8/fused capability, precision controls and retained weights still determine
which MLP path runs. It is not proof of unconditional int8 execution on a named
chip, nor a reason to call an unset flag the original numerical reference.

The bundled helper prints those fixed **label-only** counterexamples; it does
not convert weights or verify the numerical loader.

## Schedule, rounding and RoPE

[`h3_fasth3_schedule_build`](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_host.c#L167-L177)
uses video `[.99992,.97283,.92308,.8,0]` and audio
`[.99967,.89952,.75,.5,0]`. The
[row builder](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit_schedule.c#L60-L159)
indexes modality times and optional conditioning separately. Equal step counts
do not permit merging these rows.

The [FastH3 timestep branch](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit_schedule.c#L162-L243)
materializes F32 features as BF16 before BF16 linear, SiLU, linear and SiLU.
Block and final AdaLN projections use
[FastH3-specific names](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit_schedule.c#L334-L401).
Replacing these with an algebraically equivalent all-F32 MLP changes rounding
boundaries; no numerical equivalence is established by renaming keys.

[`prepare_rope`](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit.c#L1116-L1238)
generates omitted FastH3 inverse frequencies `10000^(-i/16)`, then derives tables
from packed coordinates/spatial scaling and casts to BF16. The constants come
from this implementation's architecture assumptions; no new external model
configuration or payload was inspected. Missing arbitrary buffers must not be
silently generalized into this special case.

## VSA tiles, top-k and fallback

[`prepare_vsa_tiles`](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit.c#L1313-L1418)
first merges contiguous same-kind segments before the target video, then splits
each merged prefix region into ≤64 rows. For target video, map local `(t,h,w)`
in the patchified grid to `((t//4)*ceil(H/4)+h//4)*ceil(W/4)+w//4`, offset by
the prefix tile count. Counting-sort grouping preserves row order within tiles.
Edges have real counts smaller than64, not artificial padded-token membership.

Top-k is `clamp(ceil((1.0-0.9)*video_tiles),1,video_tiles)` using **double**
arithmetic. This is one ceil, not two. At120 tiles, binary double produces12;
float32 subtraction/multiplication can produce13. No video tiles means zero.

The [coarse shaders](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_shaders.metal#L31-L213)
pool by actual row counts and exclude empty key tiles. Prefix query tiles see
all keys. Video query tiles see every prefix key plus top-k video keys; tied
scores prefer the lower tile index. Fine attention
[masks partial key tails and scatters rows back](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_shaders.metal#L4550-L4685).

Sparse availability is the actual
[fine-pipeline presence](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_gpu.m#L1642-L1695),
not merely the requested option or a chip label. Creation uses an
[M5-name/TensorOps compile predicate and optional compile fallback](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_gpu.m#L335-L405);
the fine pipeline is [conditionally registered](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_gpu.m#L437-L448).
Head dimension128, video range/top-k and device threadgroup-memory capacity are
additional native constraints. A caller-declared pipeline flag is not a probe.

The [dispatch](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_dit.c#L2421-L2483)
is sparse fine+coarse **once**, or dense fine followed by gated coarse **once**.
`H3_DISABLE_FASTH3_SPARSE` is presence-based, including empty string or `0`.
Disabling sparse fine neither removes the coarse branch nor selects base H3.
Full sequence is required. Precision and layout controls, including gate
projection, remain separate audit axes; fallback does not establish parity.
