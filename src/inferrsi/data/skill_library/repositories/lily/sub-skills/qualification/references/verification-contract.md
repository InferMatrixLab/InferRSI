# Lily verification contract

This reference distills the root provenance's pinned `pplx-garden/lily` source.
Paths and spans identify inspected primary evidence; the operational contracts
are bundled here so source-checkout files are not runtime dependencies.

## What each test can establish

| Evidence layer | Source behavior | Limit |
| --- | --- | --- |
| Compile/typecheck | Selected non-GPU modules are exposed on non-macOS; GPU modules and CPU-reference test module have explicit cfg gates | A library-only non-macOS check does not compile or run every integration target, nor provide CPU inference |
| Plain-Rust reference | F32 numerical reference implementations; BF16 inputs pre-rounded before GPU comparisons | An oracle is not evidence that GPU outputs agree until the actual kernel/readback comparison runs |
| Kernel numeric test | Creates a Metal context, tensors and command pass, dispatches a kernel, waits and compares readback with the CPU reference | Covers its selected shapes/route/numerical tolerance only; not whole-model quality or service |
| Shader/pipeline test | Compiles shipped source through the Metal framework and builds functions at selected MSL versions | Pipeline creation alone does not validate outputs, routing or performance |
| Tokenizer/template golden | Explicitly ignored checkpoint test compares exact rendered prompt token IDs | Distinct from model recurrence, greedy continuation or HTTP/cache behavior |
| E2E greedy golden | Explicitly ignored checkpoint test loads the model and compares generated tokens to a selected stored chat golden | One matched prompt/checkpoint fixture is not general model quality, API qualification or a service SLO |

`src/lib.rs:8-33` gates generation, kernels, Metal, model, serving, tensors,
tokenizer and weights to macOS; `cpu_ref` is exposed only under
`cfg(all(target_os = "macos", test))`. Selected checkpoint integration tests
import those gated modules rather than universally compiling away on Linux.
Do not claim a generic `cargo test` on another OS proves all-target coverage.
This extraction had neither Cargo/Rust nor the supported native platform;
none of these Rust/native stages was executed.

Evidence: `Cargo.toml:1-57`; `CONTRIBUTING.md:1-42`; `src/lib.rs:1-33`;
`tests/support/cpu_ref.rs:1-120`; `tests/unit/kernels/gemm.rs:12-57`;
`tests/test_shader_compile.rs:1-74`; `tests/test_tokenizer.rs:14-52`;
`tests/test_e2e_35b.rs:1-47`.

### Interpreting a green result

The contributor guide warns that absent-fixture early returns can look green
under captured test output. The selected tokenizer/E2E tests currently use
`#[ignore = "requires LILY_MODEL_DIR_35B"]`; when explicitly selected, a missing
variable returns an error. Preserve the actual test implementation and report
which mechanism applied instead of assuming every green is either a skip or a
real run. Capture test enumeration, ignored/cfg/filtered counts, named completed
cases, fixture identity and native device evidence. A short duration is a clue,
not conclusive proof that a test did nothing. Model-loading tests sharing a GPU
need serialized execution under an authorized run, not concurrent memory races.

### Shader and device boundaries

The shader test is macOS gated. Its MSL 3.1 pass permits `gemm.metal` to expose
no functions because that file's tensor-op kernel is MSL4-only; the MSL4 pass
requires functions from every shipped shader. Kernel enumeration/pipeline build
is useful evidence of coverage at that version, not a run of every shape.
`MetalContext::new` requires Apple GPU family 10 or later. Production GEMM
probes its native tensor-unit pipeline at supported MSL4 versions and errors
when none compiles. A broader comment about keeping a 3.1 fallback is not an
implemented production GEMM fallback or support promise for older Macs.

Evidence: `tests/test_shader_compile.rs:1-74`; `src/metal.rs:46-98,105-160`;
`src/kernels/gemm.rs:12-46`.

## Numerical and route checks

- Compare the intended GPU computation to independent plain-Rust F32 formulas,
  not the previous optimized version. Pre-round inputs to BF16 when isolating
  accumulation error; distinguish storage-rounding from accumulation/reduction
  differences. GDN state is F32 because recurrent rounding compounds.
- Cover the actual shape predicate and numerical outputs on both sides. The
  inspected skinny-Q4 route depends on M, output width and complete group-64
  block walks. Fused stacks and their slices must choose the same reduction
  variant; a new route can change arithmetic even with equal real-valued math.
- Include tile tails/odd dimensions where supported, model-shaped tensors,
  subviews/nonzero offsets and packing/dtype rejection. Do not broaden a valid
  group-64 U32-code/BF16-activation result to other four-bit formats.
- Check recurrent output **and** state across chunk/block boundaries and after
  repeated steps. A one-step output match cannot establish a long-context
  continuation or cache restore.
- Record the route actually executed. A shape that falls back safely may pass
  correctness while telling nothing about the candidate kernel's performance.
  Preserve fallback/unsupported/error states rather than hiding them in timing.

Evidence: `CONTRIBUTING.md:30-42`; `tests/support/cpu_ref.rs:1-120`;
`src/kernels/gdn.rs:17-55`; `src/kernels/skinny.rs:15-45,74-112`;
`tests/unit/kernels/skinny.rs:315-370,598-603`;
`tests/unit/kernels/gdn.rs:7-105`. This is a selected readset, not a complete
kernel/state audit.

## Exact checkpoint and golden scope

Both performance reports identify the same immutable
`mlx-community/Qwen3.6-35B-A3B-4bit` snapshot, MLX affine Q4 with group size 64
and checkpoint-declared affine-Q8 router exceptions. The exact snapshot ID is
retained in root provenance/model guidance; it is research identity, not an
experiment default for other models. Preserve model payload, config,
tokenizer/template and quantization identities together.

The selected E2E test consumes `golden_35b_chat.json` prompt token IDs and
chosen-token steps; the separate tokenizer golden renders its prompt with the
test's chosen thinking mode. The HTTP server's thinking-disabled contract is a
different interface. Passing the golden does not prove streaming, tools,
sampling, multimodal inputs or speculative decoding—which the inspected public
interface does not support. Use the bundled serving route for that strict API.

## Production-throughput measurement boundary

The reports compare batch-one greedy in-process generation on an Apple M5 Max
40-core GPU with 128 GB unified memory and macOS 27.0. They use deterministic
synthetic prompt IDs, fresh processes, exact-shape warmup, one measured prefill
and a fixed count of decode deliveries. These are **author-reported** records,
not locally reproduced results from this knowledge extraction.

| Metric/control | Distilled boundary | Incorrect interpretation |
| --- | --- | --- |
| Prefill throughput | Prompt tokens until first delivery with first decode already submitted; MLX uses the first production generator yield | Isolated transformer-prefill kernel time or complete user TTFT |
| Decode throughput | Subsequent literal inter-yield/delivery intervals; one-token lookahead before delivery and final unused lookahead drained outside timing | Single-kernel latency, synchronous identical graphs or HTTP E2E |
| Warmup | Exact measured prompt shape and asynchronous cadence; unused work synchronized before measured state | A generic warmup of another shape or unfinished GPU work leaking into measurement |
| Internal graph | Stock MLX-LM also returns a full-vocabulary logprob vector that Lily does not expose | Equal token counts imply identical executed graphs |
| Tokens/digest | Each engine repeats its own free-running greedy trajectory; cross-engine equality is informational | Repeated within-engine digest proves cross-engine numerical equivalence or same MoE routes |
| Diagnostic flag | Retained command buffers/timestamp records are a separate diagnostic mode | A diagnostic report can silently substitute for production timing |

Source timing evidence: `src/bin/lily-bench.rs:31-180`;
`benchmarks/bench_mlx.py:53-84,97-153`; both performance reports' measurement
sections. Model loading, tokenization, template rendering, HTTP and
detokenization lie outside the reported timed regions. E2E service/quality
claims need their own authorized workload and frozen evidence.

## Version mismatch and preserved negative observations

The September 1 report names MLX **0.31.2**, MLX-LM **0.31.3** and Transformers
**5.14.1**. The September 2 report names MLX **0.32.2** with the same MLX-LM and
Transformers versions, and different binary/harness/requirements digests.
At the inspected source snapshot, `benchmarks/requirements.txt`,
`run_matrix.py:27` and `bench_mlx.py:27-31` pin **0.31.2** and reject another
package map. Therefore the currently checked-out runner is not an exact
reproducer of the later report merely because its filename matches the
instructions. Resolve the historical harness/environment bytes or prepare a
new explicitly versioned experiment; do not edit expected-version checks and
describe the resulting run as unchanged reproduction.

The later report's prefill rows at 32,768, 65,536 and 131,072 context have
Lily/MLX ratios below one. Preserve that longer-context prefill disadvantage
alongside its reported decode advantage. The earlier and later ratios cannot
be pooled into a universal claim or transferred to other devices, model sizes,
formats, API loads or precision modes. Raw historical run artifacts were not
downloaded/authenticated here; source reports and their declared hashes remain
imported evidence with that availability limit.

Evidence: `docs/2026-09-01-performance-mlx-0.31.2.md:1-97`;
`docs/2026-09-02-performance-mlx-0.32.2.md:1-101`;
`benchmarks/run_matrix.py:27,268-278`; `benchmarks/bench_mlx.py:27-31,97-99`.

## Fail-closed evidence workflow

Before an authorized comparison, freeze source/binary/lockfile/harness and model
hashes, expected package map, workload and timing boundaries, diagnostic mode,
sample schedule, quality/metric gates and stop condition. Record baseline and
candidate arms without letting missing/failed/noisy samples disappear.

The source runner checks source/clean state, package pins and report source/mode
counts; alternates engine order and reverses contexts; checkpoints a manifest
before/after each fresh-process arm; records thermal/power/interference; and
refuses incomplete, nonfinite, unstable or within-engine digest-changing rows.
Its fixed publication thresholds belong to that source experiment, not generic
InferRSI defaults. `--ignore-foreign-load` records rather than gates foreign
load and must remain visible as a changed policy. Process survey output, model
paths, host names and command lines require privacy review before publication.

The bundled [record auditor](../scripts/audit_benchmark_record.py) adapts only
the safe supplied-record validation idea: source/mode/count fields, positive
finite times/rates, token IDs and FNV digest. It reads one JSON file and uses
only Python's standard library. It neither imports the upstream runner/MLX nor
surveys processes, runs binaries, reads model files or grants a qualification
verdict. A consistent forged/stale record can still pass; authenticate external
bytes and execution separately.

Script inventory: `run_matrix.py` and `bench_mlx.py` are **reference-only**
because they launch native/MLX model processes, require prepared weights and
perform machine/process surveys with privacy implications. The selected
`validate_lily_report` logic is **adapted** into the offline helper with stricter
identity/value/digest checks, not copied as an executable matrix runner. Model
download commands and toolchain installers are **excluded**; no host setup or
network/model operation is authorized by this procedure.

Required native Rust compile, supported Metal/kernel/model/state/golden and
service evidence remains blocked in this extraction. Static helper or Python
fixture success verifies only that helper and the supplied metadata shape.
