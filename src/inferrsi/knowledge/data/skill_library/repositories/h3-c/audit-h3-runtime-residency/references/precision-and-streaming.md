# Metal precision, approximation and SSD tradeoffs

These **CODE** contracts are scoped to the [source readset](source-notes.md).
Source-preserving intent, inspected test assertions and author's measurements
are separate from local validation. No native result is established here.

## Effective numerical path

`h3_gpu_create` selects M5 TensorOps from the device-name check and `H3_NAX`.
TensorOps compilation failure retries ordinary MPSGraph/direct Metal and clears
the capability flag. `h3_gpu_has_int8_mlp` reports that effective capability;
hardware name alone does not prove the fast path ran. Other devices and shader
compilation/runtime stacks need independent qualification.

| Mechanism / inspected selector | Numerical or state contract | Diagnostic and tradeoff |
| --- | --- | --- |
| Runtime int8 MLP; `!ssd_streaming`, fused MLP, capability and no slower-BF16-MLP flag | Loads raw BF16 matrices, quantizes symmetric per-output-row weights plus F32 scales, submits conversion, frees BF16 unless an A/B/keep diagnostic retains it | `--use-slower-bf16-mlp` selects the close-reference path; normal load and diagnostics have different peak residency |
| Runtime int8 QKV and attention output; capability, `sequence >= 128`, no SSD and respective slower-BF16 flag | Dynamically quantized activations and symmetric int8 weights; checkpoint QKV layout is interleaved by head/QKV/dimension and consumed in head-major attention layout | `--use-slower-bf16-qkv` and `--use-slower-bf16-attention-output` isolate these changes. Do not transpose weights under an assumed contiguous-Q/contiguous-K/contiguous-V layout |
| Grouped FC2 activation quantization versus `--use-int8-row-fc2` | Grouped scales and one scale per whole FC2 row are different approximations | Whole-row mode is more aggressive, capability-gated and explicitly incompatible with SSD in public parameter validation; require full media checks |
| Output heads; `bf16_final = getenv("H3_DIT_F32_FINAL") == NULL` | Default converts originally F32 final-head weights to BF16; inputs already use BF16 | Set `H3_DIT_F32_FINAL=1` before loading to retain the F32-head diagnostic. The variable is presence-tested: setting it to `0` still selects F32 |
| Gate/AdaLN and projection-input fusions | BF16 residual is rounded/stored before normalization; normalized modulation is rounded again before int8 scale estimation | Preserve `h3_f32_to_bf16` tie-to-even conversion and the materialized rounding points when fusing. Algebraic equality in F32 is insufficient |
| Exact-path fusion diagnostics | Gate→MLP AdaLN, cross-block AdaLN and final slice/head fusions have separate fallback controls | `H3_DISABLE_FUSED_GATE_ADALN`, `H3_DISABLE_FUSED_CROSS_BLOCK_ADALN`, `H3_DISABLE_FUSED_FINAL_SLICE`, `H3_DISABLE_FUSED_FINAL_HEAD` restore comparison boundaries; inspect load-time versus run-time reads and clear retained state |
| Scheduling/cached graph paths | `h3_gpu_continue` commits and retains in-flight commands without waiting; `h3_gpu_submit` waits for every retained command and checks errors | Submitting additional segments changes host/driver scheduling and intermediate lifetime. A CPU encode timer or root GPU timestamp alone is insufficient for completion latency |

Int8 here is a runtime symmetric representation, not an MLX affine `U32`
checkpoint reader. The raw loader validates names/shapes/ranks/dtypes and reads
BF16/F32 payloads; it does not interpret MLX scales/biases/group layouts from the
[retained export inventory](minimax-h3-weight-inventory.json). A compatible
model export is an engine-and-format pair, not a freely exchangeable file.

**PROPOSED baseline discipline:** freeze all layers, whole/core reuse, token
reduction, internal canvas, RoPE policy, MLP/QKV/output projection precision and
head precision explicitly. Fifty layers with `--reuse 1` restores evaluation
coverage but leaves default M5 int8 and BF16-head choices possible. A reference
using all three slower-BF16 flags and F32-head diagnostic remains a mixed
BF16/F32 pipeline, not a full-F32 oracle. Use separate processes or clear the
interactive cache when changing environment controls.

## Approximation is a separate decision

| Control | What is reused or removed | Counter-case / check |
| --- | --- | --- |
| `--layers <50` | Gate-ranked active blocks; early/final structural blocks protected; inactive core weights and schedule tables omitted after schedule precompute | Lower storage/compute also changes the model. Restore 50 before attributing improvement to an exact fusion |
| `--reuse >1` | Full denoiser velocity on selected steps, including first/last; skipped video/audio velocities extrapolate on their independent schedules | Counts of requested steps and fresh forwards differ; short schedules can be especially sensitive. Check both final latents and joint outputs |
| `--core-reuse >1` | Retains full-core residual; patch projection and time-aware output head still refresh | Mutually exclusive with whole-velocity reuse in the public validation. Needs residual allocation and valid per-run reset; retained model is not permission to retain a prior run's residual |
| `--token-reduction` | Pools adjacent video tokens through a middle block interval while preserving a full-resolution residual for expansion | Upstream reports color/fidelity failure when combined with both 40 layers and reuse 3. That is a source-local rejected combination, not a universal ban at every revision |
| Lower render canvas / native 256 RoPE adaptation | Changes internal denoising geometry or spatial positional grid before output upscale | A fast preview is a different workload. `--use-reference-rope` restores the released grid at native 256; very small output/condition geometries require separate quality qualification |

The README's reported low-budget schedule experiments also preserve failures:
tail-heavy schedules could sharpen a subject while harming motion/background,
and sparse RES/long extrapolation could fail visibly. Treat those as leads for
quality protocol design, not proof every schedule change will fail. Avoid
turning a single favorable frame, operator error or task-specific upstream
observation into acceptance of complete video, audio, synchronization and
conditioning fidelity.

## Three different I/O/residency paths

1. **Copied shared buffers.** `h3_gpu_tensor_load_file` allocates
   `MTLResourceStorageModeShared` and `pread`s directly into it. There is no
   extra full intermediate host tensor in that load routine; other host media,
   maps and outputs still exist.
2. **File-backed persistent weights.** M5 transformer-path weights default to
   `mmap(MAP_PRIVATE)` plus a no-copy shared Metal buffer. The deallocator
   unmaps on buffer release. `H3_ZERO_COPY_WEIGHTS=0` disables the default;
   explicit `1` or `transformer` changes its scope. This makes backing
   reclaimable; it does not bound physical footprint or prove no faults/swap.
3. **Explicit SSD streaming.** Core loading retains small block norms and
   records exact BF16 matrix source paths/offsets. Two complete matrix slots
   hold QKV, attention output, FC1 and FC2. A worker fills the alternate slot in
   checkpoint-offset order while the current block runs. After computation,
   synchronous submit completes current GPU use and `pthread_join` completes
   the next read before the slot becomes ready. The last active block reads
   the first again for the next evaluation. Failure to create/join/read is a
   returned error, not successful overlap. Darwin reads request `F_NOCACHE`,
   but its return value is ignored here; verify actual cache/I/O behavior.

SSD mode suppresses int8 MLP/QKV/output selection. For a meaningful comparison,
compare streamed BF16 against a resident BF16 configuration with the same head
and numerical controls. Comparing the default resident M5 int8 mode against
streaming changes precision as well as residency. SSD reduces core residency
at the cost of repeated reads and more synchronization; a slower drive or
small compute workload can expose most of that wait.

Qwen prefetch is independent of SSD mode. `H3_QWEN_PREFETCH` selects zero for
synchronous loading or up to eight read lanes; `H3_QWEN_PREFETCH_DEPTH` selects
up to six future-layer slots, default three on M5 and two otherwise. Increasing
read lanes need not increase overlap, and increasing depth allocates more
future weights. Compare one dimension at a time with fixed cache/thermal state.

## Measurement interpretation

`--profile` / `H3_PROFILE` reports each GPU context's wall, command encoding,
commit-to-fence wait, root-command GPU time, tracked peak/live/cumulative tensor
bytes and dispatch/submission counts. Freed tensors decrement tracked live
bytes; file mappings are counted too. These counters omit OS/display memory,
other processes, some driver/framework allocations and host media/output arrays.
Per-context peaks also cannot be summed without checking concurrent lifetimes.

SSD statistics are emitted when the DiT is freed: total BF16 bytes, read time,
throughput and unhidden join wait. A retained interactive DiT delays that
summary. Zero join wait alone does not prove zero I/O cost. Combine phase
timestamps with actual physical/compressed memory, swap, faults and device I/O.
The roughly 2 GiB tracked DiT and 128 GB M5 upstream results remain
[UPSTREAM-REPORT evidence](minimax-h3-apple.md), not total-RAM or 64 GiB
qualification.
