# Splash memory and format contracts

## Provenance and limits

Source: `incoai/splash` revision
`39a97385f8560cf8a93972cec9b0a963c9195250`. This is a bounded source readset, not
a complete allocator/kernel audit or a native execution result. Source Apache-2.0
and third-party notices remain separate from weights' licenses. `NO_LICENSE` in
the generated skill is the AREX authenticated-CLI lookup fallback, not a finding
that the source has no license. The bundled parser is an adapted Apache-2.0
source subset with its adaptation stated in its header.

## Model and draft compatibility

The installer asks the engine's configuration check to identify the family.
An MLX `config.json` or a GGUF-derived configuration plus scalar metadata must
match the served architecture's dimensions, scaling, GDN/FFN/expert geometry and
other declared constraints. It checks the target before its vision tower and
again with the selected draft. Repository/model-card names do not prove this
compatibility; remote Python model code is not loaded.

| Representation | Supported contract at this revision | Do not infer |
| --- | --- | --- |
| MLX target | Declared quantization; affine 2/3/4/5/6/8-bit groups 32/64/128, MXFP4 groups 32, NVFP4 groups 16; module overrides determine actual formats | Every integer bit width, arbitrary group sizes, whole unquantized projections, or a differently shaped model are accepted |
| Mixed GGUF | Loaded tensors must have an allowed type for their particular role; mixed BF16/F16 tensors can be legal in a quantized model | A whole-BF16/F16/F32 target is supported because an individual tensor is |
| GGUF header screening | Missing/unsupported tensors and invalid all-unquantized projection/expert sets are refused before downloading weights | Header acceptance verifies complete tensor shapes, payload bytes or native execution |
| DFlash2 draft | Target-compatible family/configuration, hidden/vocabulary/mask and target-layer relationships; expected BF16 draft weights and optional mask embedding | A small generic draft or another architecture can replace the trained draft by matching size alone |
| Vision | Target source's compatible tower/projector and valid loaded tensor layout | Text-family acceptance qualifies a separately supplied vision component |

The target's MLX projections, experts and head must be quantized; selected other
roles such as router, shared-expert gate, token table and GDN parameters have
their own allowances. The GGUF loader similarly distinguishes linears, norms,
router and other roles. This route deliberately does not reproduce a full
per-tensor type catalog: an unlisted role/format must be checked against the
target's actual accepted metadata, not guessed from the table above.

## Memory: floor, priority, observation

The automatic hard ceiling is the recommended Metal working set less the
runtime margin; a nonzero requested `--max-memory` is used only if smaller.
The governor separately considers host availability/pressure and reservations.
An engine-budget refusal and a host-pressure refusal are different diagnostic
classes; a driver can still reject an admitted allocation.

| Allocation or state | Plan/owner | Interpretation |
| --- | --- | --- |
| Target/draft/vision weights | Loaded model footprint | Count the actual selected formats; draft is not optional in the normal decoding architecture |
| Shared prefill/decode arenas and reserves | Fixed runtime | Shared execution scratch does not imply shared logical lane state |
| ANE FFN split and disk-state write staging | Explicit fixed categories | Optional path choices can change available context/store capacity |
| Expert store | Replaces streamed routed-weight residency in target-weight accounting | Auto loads whole where context allowance fits; otherwise streams within the remainder; minimum format-mix/layer stores must fit |
| PLE row cache | Host storage charged as fixed alongside device footprint | Streaming removes the full table from weight residency, not all RAM cost; extra host overhead is outside the reservation |
| Lane state, cached composite states and KV extents | One dynamic governor-controlled budget | Capacity is not preallocation for every lane; KV extent geometry affects usable request capacity |
| Sparse-KV hot readers and history staging | Spill-capable target's dynamic/floor accounting | SSD spill still requires index, window/dense pages, reader and staging memory |

The streaming planner first fits mandatory loaded weights, geometry-dependent
arenas, reserves, state staging, one lane state and KV runway, minimum expert/PLE
stores and spill floors. It then prioritizes automatic routed experts and PLE
capacity while retaining the selected context's KV allowance. The automatic
PLE share is bounded in this revision; it is not a universal optimal cache size.
An explicit undersized store or excessive hot-cache request is refused.
Streaming can enlarge arena requirements; the planner reconciles that geometry
and may reload weights with the final stores.

For a spill-capable block-sparse target with a writable disk tier, context can
be bounded by model window, resident KV, memory spill floors or disk room for
active KV. Inspect `/status` at `memory_plan.budget.context_bounds`:
`window`, `resident`, `spilled`, `disk` and `bound`. A model's advertised native
window is not a promise that every concurrent request can retain that much KV.

The native audit requires real warmup measurements, compares bounded categories,
validates dynamic totals and backend/device accounting, charges the PLE cache
beside device footprint, and detects hard-budget/reserve excesses. A pure plan
or synthetic report is not an observed process-memory peak or a backend pass.
`MemoryControl` performs idle release, host-pressure sampling and paced reclaim
at command-free points; pending transfers can defer complete reclamation.

## Streaming controls and failure-sensitive details

- `--expert-memory SIZE` streams missing routed experts from their source files.
  Its store must hold a layer's required format mix, including uniquely mixed
  layers. `off`, or a size holding all experts, loads them all.
- `--ple-memory SIZE` streams supported PLE n-gram rows through a host row cache
  and Metal staging. `off`, or a size holding the full table, loads it whole.
  NVFP4/rebuilt or rotated-table layouts cannot use this row-streaming path;
  requesting a size for them is refused. Other models can ignore the setting
  with a warning: record the effective path.
- PLE source-file changes, short files or failed reads can poison/fail a step;
  a row enters cache only after source identity checks. Reusing a pathname is
  not proof of original bytes. The row cache is not released with idle weights.
- `--sparse-kv-memory` sizes a hot block cache for supported spilled KV, cannot
  drop below its floor and does not accept `off`. Disk-cache quota is separate;
  `--max-cache-disk 0` disables that tier.

## Precision and parser distinctions

Target KV defaults to `int8`; `bf16` avoids KV quantization and takes roughly
twice KV storage, not twice total process memory. Recurrent GDN state defaults
to `fp32`; `bf16` reduces stored state but keeps FP32 arithmetic and rounds at
prefill chunk ends, captured states and decode-step boundaries. Those boundaries
therefore matter to a frozen numerical comparison. Restart to change formats;
cached states of different formats must remain separated.

For byte-size controls, `K`, `M`, `G`, and their `KB`/`KiB` equivalents use binary
multipliers. Fractional values require a suffix and round down to whole bytes;
`2.5G` is 2,684,354,560 bytes. Bare integers are bytes, not MiB or expert slots.
Zero is invalid for ordinary memory/store sizes, but the exact string `0`
disables `--max-cache-disk`. `auto` requests planner policy rather than a number.
The bundled `parse_budget.py` implements only these selected syntax contracts.
It cannot check minimum stores, family compatibility, actual fit or native APIs.
Context uses a different grammar: `K` means 1024 tokens, but `M` means 1,000,000
tokens. Context beyond the native window activates static YaRN and can change
answers at other lengths too; it is not an accuracy-free capacity knob.

## Bounded readset

- `README.md:15-25,60-125`: platform, model formats and exposed controls.
- `DEVELOPMENT.md:191-252,288-365,418-452`: plan priorities, streaming and precision.
- `DEVELOPMENT.md:1655-1738,1789-1858,1925-1954`: target/draft identification and formats.
- `server/serve_options.py:35-43,115-192,434-524`: byte grammar and flag meanings.
- `install/gguf.py:905-949`: whole-unquantized and per-tensor screening bodies.
- `runtime/engine/MemoryPlan.hpp:51-300`: footprints, streaming inputs and ceilings.
- `runtime/engine/MemoryPlan.cpp:167-250,407-448,612-741`: floor/priorities, reconciliation and plan result.
- `runtime/engine/MemoryGovernor.cpp:104-151,170-230`: charges, reservations and refusal classes.
- `runtime/engine/MemoryControl.cpp:32-55`: command-free pressure/reclaim pass.
- `runtime/engine/MemoryAudit.hpp:13-77`, `MemoryAudit.cpp:45-190`: actual-category requirements and accounting.
- `dev/tests/server/test_serve_options.py:80-139`: parser examples (read, not executed in this lane).
- `dev/tests/engine/engine_memory_plan_test.cpp:239-257` and
  `dev/tests/engine/memory_audit_test.cpp:167-190`: PLE budget/audit test anchors
  (read as evidence, not native runtime validation).
