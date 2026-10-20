---
name: ascendc-tiling-design
description: 'Design tiling for a custom AscendC operator: normalize the shape first (axis-collapse or flatten), answer the fullload-vs-split question for UB, apply the universal four-element template (multi-core split, UB split, buffer plan, branch matrix), and route per operator class (reduction, broadcast, elementwise, matmul, conversion) using algorithm-selection and chip-generation tables (DAV_2201 vs DAV_3510). Use when writing or restructuring an AscendC operator''s tiling logic, before running any performance tuning campaign.

  '
---

# AscendC Tiling Design

Status: candidate. Source-grounded from awesome-ascend-skills
`ascendc-tiling-design` (SKILL.md + 23 reference docs) @ 75ec89c, mirrored from
cann/cannbot-skills @ ac5bbd2b (license UNKNOWN — verify before production use).
This is a distillation of the routing intelligence; the source references carry
the full per-pattern detail. Sample values are DAV_2201/FP32 illustrations —
re-evaluate per target chip.

## SearchSpace mapping

Accelerator row → Optimize cell.

Second-level targets: operator tiling, UB buffer planning, multi-core split,
reduction algorithm selection, broadcast primitive selection.

Companion skills: `ascend-operator-tuning` (the tuning campaign that runs after
the design), `ascend-operator-profiling` (measure the result), `kernel-writing-guide`
(when to write vs reuse).

---

## Universal four-element template

Every operator class completes the same four design elements, each with an
explicit output checklist:

1. **Multi-core split** — which dimension is split, work per AI Core, core
   count. Principles: load balance; data locality; moderate granularity
   ("tile neither too small — scheduling overhead dominates — nor too large —
   parallelism drops").
   Deliverable: split dimension + per-core task size + core count.
2. **UB split** — data volume per pass, whether chunking is needed, chunk-size
   formula. UB capacity: DAV_2201 192 KB, DAV_3510 248 KB.
   Deliverable: per-pass volume + chunk formula.
3. **Buffer plan** — inQueue/outQueue/tmpBuf/workBuf list, size formula per
   buffer, total UB usage, double-buffer decision.
   Deliverable: buffer table with formulas and total.
4. **Branch matrix** — dtype (FP32/FP16/BF16/INT8), big/small shapes, 32 B
   aligned vs unaligned, boundary values.
   Deliverable: branch condition + per-branch strategy + edge tests.

## Cross-class rules

1. **Normalize the shape before any tiling.** Reduction: mark dims A (kept) /
   R (reduced), drop size-1 contiguous dims, merge adjacent same-mark dims.
   Broadcast: pad dims left with 1, flag bitmap (dim==1 → broadcast), merge
   adjacent same-flag axes, broadcast axes get stride 0. Elementwise: all
   shapes identical → flatten to 1 D. Conversion: collapse to `[C, N]`.
2. **Fullload-vs-split is one question everywhere**: does the working set,
   including all intermediate buffers, fit UB? Yes → load once, reuse in UB,
   single pass. No → chunk + cross-chunk merge. Thresholds are
   operator-specific (per-operator intermediate buffers differ); there is no
   universal constant.
3. **Valid-vs-aligned length discipline**: lengths passed to compute APIs and
   copy blockLen use the **valid** length; UB offsets and buffer sizes use the
   **aligned** length. Same table appears verbatim in the reduction and matmul
   references.
4. **Solve tile size by direct formula, then constrain and take min**:
   `min(UB capacity, axis limit, core-balance)` — explicitly no binary search.
   API/hardware caps fold in as additional `min()` terms: `repeatTimes ≤ 255`,
   32 B dataBlock, 256 B Compare alignment (float: ×64 elements), K padded to
   multiple of 64 (mxfp8), vector register width 256 B.
5. **Core-utilization fallback**: if tiles < cores, shrink the UB tile (or
   flatten more axes) rather than leave cores idle. Floor: ≥ 4 KB data per
   core (`MIN_TILING_BITS = 32768` bits); elementwise per-core count aligned
   to 512.
6. **Chip generation is a first-class routing axis** — check the arch before
   choosing any broadcast/copy primitive:

   | | DAV_2201 | DAV_3510 |
   |---|---|---|
   | UB | 192 KB | 248 KB |
   | Broadcast | UB static only (rank 1-2 D, axis 0/1, compile-time) | UB dynamic (rank 1-9, any axis, runtime) + NDDMA (GM→UB) |
   | NDDMA | unavailable | available, ≤ 5 axes (more → loop) |
   | Known gaps | `Select` has no int32 dst (store index as float, Cast at output) | — |
   | Non-contiguous multi-axis copy | DataCopyPad strides or per-slice loop | NDDMA |

7. **Cross-core reduction** = two-phase partial + `SyncAll()` + workspace
   merge; workspace = `coreNum × CeilAlign(per-core output, 256 B)`, ×K for
   K outputs. Workspace slots 64 B-aligned to avoid bank conflicts.
8. **Precision playbook**: FP16/BF16 accumulating ops → FP32 intermediates;
   long FP sums → dichotomy addition; streaming mean/var → Welford;
   first-extremum semantics via LE-inverted Compare.

---

## Reduction routing

After axis-collapse, classify by what remains:

| Situation | Mode | API |
|---|---|---|
| Single axis, A0 = 1 (contiguous R rows) | AR | Level-2 Reduce API |
| Single axis, A0 > 1 ([R, A0] blocks) | ARA | `Pattern::Reduce::RA` |
| Multi-axis (ARAR…) | shape transform; each R level re-runs the AR/ARA test | per level |
| axis = 0 | folds to ARA | |
| All axes reduced | folds to AR | |

Load-mode decision:

| Mode | Fullload when | Split fallback | Cross-chunk merge |
|---|---|---|---|
| AR | ≥ 1 whole row fits UB | ColSplit (chunk along R) | scalar: Max→ternary, Sum→`+=` |
| ARA | all `R × tileA0Len` (32 B-aligned) fits UB | RowSplit (chunk rows) | elementwise Max/Add on chunk results |

Fullload wins when multi-pass intermediate reuse avoids GM re-reads; split
re-reads per pass.

Algorithm selection:

| Condition | Algorithm | Why |
|---|---|---|
| Fullload | direct sequential | data resident in UB |
| Fullload + two dependent reductions | TwoPass | pass 2 reuses pass 1 result |
| Split-load + two dependent reductions | Welford online | single pass, saves one IO round |
| Split-load + accumulating drift | Welford + group merge every 8 chunks | bounds drift |
| R too big for one core, A too small to parallelize | Group Reduce | R split across cores |
| Sum precision-critical | Dichotomy addition | similar-magnitude adds first; Sum only — Max/Min unaffected |
| Split-load + index tracking | shard merge + per-slice index offset | ArgMaxV1 returns slice-local index |

Key formulas (FP32 / DAV_2201 samples):
- ARA: `a0TileBase = 64` (vector reg 256 B / typeSize);
  `R_max = (UB_SIZE − (2×a0TileBase×4 + tmpBuf)) / (2×a0TileBase×4)`, capped
  `min(R_max, 255)` by the `repeatTimes ≤ 255` API limit (formula ≈ 375 →
  effective 255). RowSplit uses single-buffer overhead, so its formula differs.
- Multi-output UB equation: `tileSize × (T_in×2 + T_acc) + A_aligned × T_acc ×
  (K+3) ≤ UB_SIZE` (solve tileSize; ArgMax stores index as float, K=2).
- Index tracking: Compare count needs **256 B** alignment, not 32 B; LE-inverted
  Compare + `VSEL_TENSOR_SCALAR_MODE` = 3 instructions/loop, one buffer saved,
  no pre-fill of pad region.

## Broadcast routing

Selection after axis-collapse (multi-dim):

| Priority | Condition | Choice |
|---|---|---|
| 1 | User forced NDDMA / UB-BRC | obey |
| 2 | NLast (tail axis not broadcast) and tail ≥ dcache/2 | UB dynamic broadcast |
| 3 | dtype INT8/FP16/BF16 and tail 32 B-aligned | UB dynamic broadcast |
| 4 | else | NDDMA |

Rationale: a large non-broadcast tail makes NDDMA re-reads thrash dcache.
UB-internal broadcast of intermediates → dynamic API (rank 1-9).

Method comparison:

| | UB static (2201) | UB dynamic (3510) | NDDMA (3510) |
|---|---|---|---|
| Rank / axis | 1-2 D, axis 0/1, compile-time | 1-9, any axis, runtime | GM→UB stage |
| Alignment | judged on **original shape dims × sizeof(T)**, not the post-copy aligned values | none | hardware strides |
| UB cost | src + dst + tmp | src + dst | dst only |
| Fallback | move-instruction recipes (dummy-fill Copy srcStride=0 + GatherMask trim; per-row Duplicate for M ≤ 2) | — | > 5 dims → loop |

Common tiling: `maxElemNum = (ubSize − extraSize)×8 / (bufferNum × maxDtypeBits)`,
floored to `256×8/minDtypeBits`; UB split scans innermost→outer for the first
non-fitting axis; alignment 128 B (1 D) / 256 B (multi-dim). Scalar inputs
(1 D after collapse) → prefer TensorScalar APIs (Adds/Muls) over
Duplicate+vector — saves a buffer and an op.

## Elementwise routing

Gate: all in/out shapes identical → 1 D linear; else route to Broadcast.
Dtype×op branch: Add/Sub-dominated FP16/BF16 chains whose spec does not
declare "inputs of similar magnitude" → precision-up path (Cast→FP32→compute→
Cast, extra K FP32 buffers); mul/div coverage not yet written in source —
same-dtype direct path applies. Rules: ≥ 4 KB per core; per-core element count
aligned to 512; UB blocks 256 B-aligned; first/tail blocks get separate loop
and tail counts (4 tiling params).

## MatMul routing (mxfp8 + eltwise fusion only)

Scope: mxfp8 quantized matmul with Div/Mul/Add/Relu/Cast fusion, Ascend950
hardware; fp16/bf16 matmul and BatchMatMul were unwritten at snapshot.

- Multi-core: split **M×N only** — K iterates inside the core, never split
  across cores; snake scheduling via BlockScheduler;
  `usedCoreNum = CeilDiv(M, singleCoreM) × CeilDiv(N, singleCoreN)` —
  dynamically computed, hard-coding banned.
- The matmul region is fixed Tensor-API pattern (`[PATTERN]`, business edits
  forbidden; fusion operators use static-offset UB allocation, **TPipe UB
  management is forbidden**). The design work is the AIV **Epilogue**.
- ODD-M: pad M to even in the UB/L0C view; MMAD keeps original M; epilogue
  writes valid rows only. ODD-N: UB row stride 32 B-aligned
  (`AlignUp(curN, 8)`); epilogue writes valid columns via DataCopyPad; GM
  offset corrected by `GetSubBlockIdx() × halfM × N`.
- mxfp8 requires host-side K padding to a multiple of 64.
- Before using any API, build a per-API semantic verification table:
  `correct use = (layout ∈ API support) AND (constraints met) AND (no better
  choice)`.
- `DataCopyExtParams`: GM-side unit = **bytes**, UB-side unit = **dataBlock
  (32 B)** — never mix.
- Re-evaluate all `[SAMPLE]` constants per chip: UB size, dtype aliases,
  stageNum, alignment elements, naming, batch=1 and RowMajor assumptions.

## Conversion routing (small-channel transpose only)

Model `[C, N] → [N, C]`, C small (screen C ≤ 16). Anti-patterns: generic
transpose high-level API (fixed overhead); GetValue/SetValue scalar loops
(throughput); per-pixel DMA (blockLen too small, DMA setup dominates).
Tiling: `tileNA = AlignUp(tileN, 32)`; `repeats = tileNA/16 ≤ 255 →
tileNA ≤ 4080`; UB budget `tileNA × (16C + 32)`; trade big-tile vs
enough-tiles-to-fill-cores; `blockDim = min(coreNum, totalTiles)`; offset
table built on aligned tileNA, DMA'd once to a TBuf, regenerated when C
changes.

---

## Known limitations (from source)

- Coverage holes: Random / Convolution / NN classes planned but unwritten;
  matmul is mxfp8-only; conversion is small-channel-transpose-only; elementwise
  precision-up covers Add/Sub chains only.
- AR fullload thresholds are stated in prose, without a formula (ARA has
  explicit R_max).
- Design heuristics and formulas only — no on-device benchmarks anywhere in
  the source; recommended patterns are not perf-tested evidence.
- External references (`ascendc-direct-invoke-template`,
  `ascendc-api-best-practices`, `npu-arch` for UB sizes) were links, not
  verified in this snapshot.
- Chip constants (192/248 KB, 256 B vector reg, Select int32 gap) bind to
  DAV_2201/DAV_3510; transfer to other Ascend generations is unaddressed.
