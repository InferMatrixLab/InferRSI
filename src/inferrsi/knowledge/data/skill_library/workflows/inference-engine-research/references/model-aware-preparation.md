# Model-aware engine preparation

Read this before generating a dedicated engine or treating a known family name
as a complete model specification. The output is a cited preparation decision
with explicit gaps. The local discovery operation does not run a model, inspect
hardware, crawl sources, install a tool or select an engine automatically.

## 1. Identify the actual computation

Pin the model card, configs and task checkpoint. Record task, input/output
modalities, conditioning, denoising/AR stages, sampling schedule, supported shapes
and all encoder/decoder paths. Include resolution, duration, batch and input
reference requirements when they change execution. A text encoder inside a video
diffusion pipeline does not make it a language-model serving task. Separate
hosted-only services from locally released components. Unknown architecture facts
remain unknown.

## 2. Discover along separate dimensions

Run the public operation, adding dimensions established from the selected source:

```bash
inferrsi knowledge research MiniMax-H3 --framework mlx --target-backend metal --target-device "M5 Mac Studio" --target-memory-gib 64 --limit 12
```

This emits JSON: the packaged profile and sources, independent query groups,
match counts, bounded deduplicated records with `matched_queries`, active filters,
component roles and target annotations. It searches the installed catalog only.
Round-robin selection lets different queries contribute; it is not an evidence
quality or engine ranking. Read the original records' applicability, sources,
negative results and verification state alongside their full linked procedures.

- **Model:** canonical identity and aliases; preserve checkpoint/task variants.
- **Framework:** preferred runtime and its lazy evaluation, buffers and streams.
- **Task:** diffusion, autoregressive generation or the actual computation.
- **Modality:** video, audio, image and other required input/output contracts.
- **Mechanism:** relevant memory, residency, quantization, tiling, offload,
  scheduling or reuse questions; query presence does not assert support.

Known profiles supply only source-grounded discovery terms and component roles;
their linked repository skills own the detailed source map and inventories. The
MiniMax-H3 profile points to the [h3.c residency audit](../../../repositories/h3-c/audit-h3-runtime-residency/SKILL.md).
For an unknown model, supply `--task` and `--modality` after inspecting its sources;
no architecture is guessed. Repeat dimensions to add queries.
`knowledge search 'model mlx diffusion video'` retains token-AND semantics and
can return less knowledge than the independent union.

Tier/repository/backend/scenario flags remain hard catalog filters. An empty
dimension can mean missing or filtered knowledge: report it, inspect the missing
source and explicitly change scope when useful. Cross-platform records can
suggest mechanisms, but CUDA/Ascend evidence does not qualify Metal. The free-text
`--target-backend` describes the intended runtime; it does not add that backend to
InferRSI's experiment adapters. Avoid a CUDA-only filter when researching common
MLX procedures unless that restricted view is intentional.

## 3. Choose and inspect an implementation reference

Search the target's native ecosystem as well as the preferred framework. Define
eligibility (actual model execution, required modalities, target API/hardware,
available source) before ranking. Distinguish independent engines from UI
wrappers, forks, unrelated projects and hosted API clients.

When the user requests the most-starred reference, record the bounded search,
candidate repositories, star counts and observation timestamp, source revisions,
license state, supported tasks, hardware reports and known approximations. Choose
the highest count among eligible inspected candidates and state that boundary;
do not claim a global maximum from a few results. Popularity does not override
model/format compatibility or target quality requirements. Keep alternatives
when different engines accept different quantized formats.

Use one of two preparation paths before generation:

1. Read the pinned implementation directly and retain a compact source map for
   loaders, component graphs, memory lifetimes, kernels and verification.
2. If an available repo-to-skill workflow helps, distill those same paths into
   owner-local operating knowledge with source attribution, license state and
   validation limits; verify it against source before using it.

The second path is optional. Reading a repository does not authorize installing
an unknown tool or executing upstream commands. No automatic skill promotion or
runtime dependency follows from distillation.

## 4. Account for the complete selected pipeline

Build one inventory row per encoder, denoiser, video/image/audio decoder or VAE,
required adapter and auxiliary asset. Include input encoders needed only by a
conditioning mode. Record:

| Field | What it must distinguish |
| --- | --- |
| Identity | Repository/revision, path/shards, component and task; one selected alternative |
| Tensor count | Shape/dtype-derived elements; distinguish logical weights, buffers and packed quant metadata |
| Representation | Dense dtype or quant format, bits/group size, scales/zeros/biases, unquantized exceptions |
| Storage | Exact selected-file bytes and units; optional alternatives/conversion sources separately |
| Execution | Cold load/conversion/compile, precompute/conditioning/denoise/decode/release order and live component subset |
| Extra memory | Activations, scheduler/KV/latent state, workspaces, caches, copies, compilation and allocator pools |
| Evidence | Source report vs inspected metadata vs measured target peak; missing facts remain explicit |

Do not sum all downloaded task alternatives or repeated shared-component copies
as one execution. Do not infer logical parameters from raw `U32` element counts
in packed quantized files. Count scales and other quant overhead in storage and
residency without calling them additional trained parameters. If inspecting
remote safetensors, bounded HTTP range reads may inspect only the length and JSON
header; stop if the server ignores ranges. Header inspection does not verify
the payload bytes or establish output quality.

Estimate each phase independently:

```text
phase memory = live component weights + activations/state + workspaces/caches
             + staging/dequantization copies + allocator/runtime overhead
machine requirement = largest cold-start or execution peak
                    + OS/display/other-process headroom
```

Evaluate cold loading, conversion and compilation separately from steady-state
phases: source and converted weights, staging buffers and compiled caches can
coexist. Record what is actually released at each transition and any retained
conditioning or decoded outputs. A warm denoising peak alone cannot bound the
whole process. Keep estimated, source-reported and measured peaks distinct.

On unified-memory systems, CPU and GPU allocations share physical capacity;
offloading within the same machine does not create a second independent RAM
budget. File-backed mapping and SSD streaming can reduce residency but add I/O,
page-fault and storage constraints. Measure physical footprint, compression and
swap alongside engine-reported tensor memory. Storage bytes, a backend wired
limit and total installed memory are not interchangeable peak measurements.

## 5. Compare weight/engine pairs and make a conditional decision

For each candidate, check conversion lineage, format/loader compatibility,
complete component coverage, weight/code licenses, quantized exceptions and
task-specific quality. A 4-bit DiT does not account for its text encoder or VAEs;
a framework-specific affine export cannot be assumed loadable by a dense-weight
native loader. Verify the exact loader's formats, component layout and conversion
requirements rather than comparing bit widths alone.
Separate weight-only quantization from activation quantization, exact schedule
precompute from approximation, and fewer steps/layers from a matched workload.

Compare published hardware, memory metrics, shapes/duration/batch, speed and
quality protocol with the target. Record **unsupported**, **unverified**, or a
bounded source-reported/locally verified configuration. If the model cannot fit
all-at-once, evaluate phased release, precomputation, supported quantization and
streaming; do not imply that fitting guarantees useful latency or quality.

Return a concrete next decision: a candidate pair and required validation, a
smaller permitted workload/precision with disclosed costs, or a larger-memory
hardware requirement justified by peak plus headroom. Keep the proposed
workload/quality gates explicit. Freeze them in the acceptance issue/evidence
before candidate experiments, then validate operators, complete media quality and
end-to-end service as required. No hardware feasibility or quality PASS follows
from package tests or this procedure alone.
