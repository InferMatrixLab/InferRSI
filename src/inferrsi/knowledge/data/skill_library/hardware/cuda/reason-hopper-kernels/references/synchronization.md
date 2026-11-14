# TMA, mbarrier and WGMMA ownership on Hopper

Read this when a kernel stalls, hangs, produces stale tiles, or proposes overlap.
This is a reasoning protocol, not compilable PTX. Source IDs and inspection limits
are in [sources](sources.md); the concrete SM90 anchors are **DG** and **C2139**.
The **PTX87** sections on mbarrier, WGMMA and asynchronous proxies qualify the
instruction semantics. No device execution was performed.

## Establish two lifetimes for every input stage

A stage needs a proof that its input is ready and a separate proof that all its
readers have finished. TMA issue, TMA completion, WGMMA issue and WGMMA completion
are different events. A warp rendezvous cannot substitute for async-engine
completion.

**Inspected DG behavior:** the SM90 mainloop allocates full and empty barriers per
stage; its producer waits for empty before copying A, B and their scale tiles.
Its consumer waits for full, reads scale values, fences/issues/commits WGMMA,
waits for the WGMMA batch, and only then arrives at empty. A separate scaled FP32
accumulation can proceed after releasing the input stage because those scale
values and MMA results are already in registers. This order explains which
live ranges can be shortened safely; it is not permission to release a stage
immediately after issuing MMA.

| Boundary | Proposed audit | Failure or misleading shortcut |
| --- | --- | --- |
| Initialization | Check barrier storage/alignment, expected participant counts and publication to all participating threads and async observers before first use. DG calls `fence_barrier_init` and then CTA/cluster synchronization. | A CTA barrier in divergent producer-only/consumer-only control flow can deadlock. Initialization in one lane is not publication by itself. |
| Empty → loading | Prove the previous readers released this particular slot and generation. Include all math warps and multicast peers that can still read it. | Reusing the slot because its numerical index wrapped ignores old readers. |
| Loading → full | Account for the transaction units of every attached asynchronous copy, including scales and padded-versus-transferred byte distinctions. Match expected arrivals to the real issuers. | mbarrier phase completion requires both arrival count and transaction count to finish. TMA transaction completion is not another ordinary software arrival. |
| Full → MMA | Establish copy completion and the required memory/proxy ordering for this producer and consumer path. Keep ordinary shared writes, TMA writes and WGMMA register ordering distinct. | A WGMMA register fence is not a universal shared-memory fence; copying a tcgen05 fence spelling into SM90 is invalid. |
| MMA → empty | Identify the committed WGMMA group that last reads the slot and the corresponding wait/drain point. A pipelined implementation may release an older stage while newer groups remain in flight if the mapping proves it safe. | `__syncwarp`, `__syncthreads` or source order alone does not complete WGMMA reads. Releasing the newest slot too early permits producer overwrite. |
| MMA → epilogue | Wait before ordinary operations read or overwrite pending accumulator registers. Preserve group-uniform execution and compiler operand constraints. | A correct input-stage release does not prove all output registers are ready. |
| Epilogue store → reuse/exit | For TMA stores, identify the bulk-group completion/read boundary and scratch lifetime. DG waits before overwriting output SMEM, publishes normal writes before TMA store and synchronizes participating math threads. | A GMEM-to-SMEM full barrier does not certify SMEM-to-GMEM store completion. |

**Proposed check:** make a small ownership ledger per stage with the slot,
generation, copy issuers/bytes, reader warpgroups, last consuming batch and
release event. Trace fill, steady state and drain separately. Include a short
K-loop, a non-multiple of stage count and reuse across persistent output tiles.
This can disprove an invalid schedule before profiling it.

## Track parity by stage generation

DG derives `slot = iteration % stages` and
`phase = (iteration / stages) & 1`; the producer waits on the corresponding empty
phase with its initial offset, while the consumer waits on the full phase. Its
iteration counter persists across scheduled work tiles. This is a **source
example**, not an initial-phase prescription for other barrier abstractions.

For a proposed three-slot trace, iterations 0/1/2 visit slots 0/1/2 in generation
0, and 3/4/5 revisit them in generation 1. A single bit toggled on every iteration
will be wrong for some stage counts and protocols. Use the selected library's
pipeline state or a per-slot generation derivation, including its initial
full/empty convention. Do not reset one side at a work-tile boundary while the
other side carries its state forward.

## Preserve the Hopper issuing model

**Inspected DG:** the math side is organized in 128-thread warpgroups. Its FP8
selector uses `MMA_64xNx32_F32E4M3E4M3_SS_TN` atoms with two shared-memory
descriptors and FP32 register fragments. Its helper named `warpgroup_arrive`
emits `wgmma.fence.sync.aligned`; commit and wait emit WGMMA group operations.
The helper name does not mean an mbarrier arrival.

**Proposed audit:** ensure every thread in a participating warpgroup follows the
required aligned WGMMA/fence/commit/wait sequence. Distinguish SS (both operands
in shared memory) from the supported RS forms (A register fragments, B shared
memory) for the chosen instruction and type. Validate the actual operand
fragment/descriptor layout; adding `ldmatrix` unconditionally changes the path.

## Retained upstream contradictions

- **KW `hardware/mbarrier`:** its prose says the phase changes when arrivals reach
  zero; that omits outstanding transaction count. Its multistage example toggles
  a scalar parity every iteration. PTX87's completion conditions and DG's
  slot-generation calculation are the applicable qualifiers.
- **KW `techniques/warp-specialization` and `pipeline-stages`:** their teaching
  SM100 snippets release an input slot after MMA issue plus `__syncwarp`, without
  showing async-MMA completion. The release cannot be imported as a safe Hopper
  schedule. Their SM90 tags do not change the snippet's architecture.
- **KW `migration/wgmma-to-tcgen05`:** its A-register/`ldmatrix` story describes a
  path, not all WGMMA. DG and C2139 explicitly use SS descriptors. The migration
  page's single-thread tcgen05 example is excluded from Hopper recipes.
- **KW `hardware/tma`:** several property and format-conversion generalizations
  are not established by this readset. Re-derive descriptor legality from the
  selected API and instruction; the guide here makes no automatic conversion,
  arbitrary tile-size or copy-direction synchronization guarantee.
