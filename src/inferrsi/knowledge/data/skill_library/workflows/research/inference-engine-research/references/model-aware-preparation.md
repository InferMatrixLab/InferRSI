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

## 2. Research each decision with an ordinary question

For MiniMax-H3 on a 64 GiB Apple Silicon target, start with the model and its
total component inventory.

```bash
inferrsi find "MiniMax-H3 component inventory on Apple Silicon"
```

Open the h3.c residency audit with the read command on its hit. Its
[model profile](../../../../systems/engines/h3-c/audit-h3-runtime-residency/references/minimax-h3-profile.json)
contains the model-card revision, aliases, tasks, modalities, component roles
and proposed research topics. Use the hit's owner and revision to read
`references/minimax-h3-profile.json`. The same owner has the
[weight inventory](../../../../systems/engines/h3-c/audit-h3-runtime-residency/references/minimax-h3-weight-inventory.json)
and [Apple feasibility comparison](../../../../systems/engines/h3-c/audit-h3-runtime-residency/references/minimax-h3-apple.md).
For a new model, get the corresponding facts from its card, configs and selected
checkpoint before choosing the next questions.

```bash
inferrsi find "MLX lazy evaluation and buffer lifetime"
inferrsi find "video VAE temporal tiling and audio decoding"
inferrsi find "SSD streaming quantization and weight loading"
```

Pick further questions when the task, input modality or mechanism changes the
decision. Open each relevant source and record its owner, revision, applicability
and verification. Give each question a chance to contribute a source. When the
same owner and revision answer several questions, keep one source and list the
questions it answers. Record empty results and any change in scope.

In an optimization round, add `--session DIR` to each Find call and follow that
call's scoped read arguments, including for linked resources. This retains each
query, its hits and the resources actually returned. Put the candidate machine,
available memory, software and required workload in the task or experiment plan.
Use source reports from other devices as leads and check their claims on the
specified target.

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
