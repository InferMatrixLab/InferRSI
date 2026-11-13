# Architecture and constrained search

## Ownership and flow

`Omni` / `AsyncOmni` and the serving entrypoints turn public requests into a registered pipeline. Model code fixes topology (`PipelineConfig`); deploy data chooses resources. Resolution produces concrete stage configs. The orchestrator advances requests; stage pools manage replica selection and affinity; clients connect to stage execution; stage schedulers/runners own local work. Connectors transfer payloads and synchronize readiness. Output processors assemble user-visible results.

Qwen3-Omni is a useful concrete trace: Thinker → Talker → Code2Wav, with text and conditioning, codec tokens, then waveform chunks. In the pinned definition stages 0/1 declare `latent`, stage 2 `audio`; do not reinterpret historical latent payloads solely from dtype. Diffusion may be a single registered stage even when it contains text encoding, a denoiser and VAE decode. Those are measurable component phases, not automatically independent deploy stages.

## Search dimensions

E = existing field/capability; I = implementation change; R = research extension. E still requires model/backend support.

| Dimension | Class and source surface | Coupling and admissibility | Measurements / guard |
|---|---|---|---|
| Stage placement / replicas | E: `devices`, `num_replicas` | Stage identity is fixed; colocation shares device capacity; preserve state affinity | Per-stage queue/utilization, end-to-end p95, memory and cleanup |
| Topology / split / fusion | I: registered `PipelineConfig` variant | Preserve checkpoint, inputs, processor and terminal outputs; transport may exceed compute saved | Golden outputs, transfer overhead, startup and failure isolation |
| AR scheduling | E: `max_num_seqs`, `max_num_batched_tokens`, `max_model_len`, async scheduling | KV capacity, prefill size and downstream capacity constrain admission | TTFT, TPOT, p95, starvation and bounded memory |
| Chunk overlap | E: `async_chunk`, supported connector chunk fields | Model receptive context and boundary semantics constrain chunk size; parked state consumes resources | First audio packet, chunk gaps, RTF, waveform seams, abort |
| Active streaming window | E: `active_stream_window` | A downstream capacity policy, not an arbitrary audio length setting | Fairness, stalled streams, first-packet tails |
| Stage runners / graphs | E where supported: `model_runner`, `enforce_eager`, compilation settings | Model/data-plane compatibility, shapes and graph memory; do not assume v1/v2 interchangeability | Eager parity, capture/replay, warm vs cold time |
| Diffusion request batching | E: capacity and supported request batching | Compatibility of shape, guidance, output count and LoRA; pipeline must advertise support | Per-request output/RNG isolation, latency vs throughput |
| Diffusion step scheduling | E: `step_execution`; I: step protocol implementation | `prepare_encode`, `denoise_step`, `step_scheduler`, `post_decode`; single-request support is not batch support | Step parity, cancellation boundaries, request state cleanup |
| Streaming media | E only for emitting pipelines | Step execution does not guarantee intermediate output; final-only pipelines remain final-only | First usable media packet, chunk order/duplication, final coverage |
| Parallel execution | E model-dependent: TP, EP, Ulysses/ring/allgather, CFG, VAE patch, HSDP | Model partition/layout divisibility, rank groups, network topology and memory | Collective correctness, scaling, interconnect bytes, quality |
| Offload / loading | E: CPU/layerwise/DLO/host-weight settings | Host RAM, pinned lifetime, interconnect bandwidth, component residency, quantization compatibility | Peak GPU/host memory, transfer stalls, load vs inference time |
| Caching / precision | E only in compatible model/backend | AR KV/prefix cache differs from approximate diffusion reuse; dtype/quantization may alter outputs | Cache hit benefit plus strict/model-specific quality tolerance |
| New scheduling or transport algorithm | I/R: coordinator, pool, connector | Define policy vs transport boundary, failure semantics, state ownership before coding | Stress/abort/rank-loss, leak check and controlled A/B |

## Constraints and objective

For each device require measured peak weights + KV/state + activations + communication/workspace + graph pools + margin ≤ available memory. A sum of utilization fractions is only a planning hint; startup order, measured free memory and allocations can invalidate it. Include CPU RAM, network/PCIe bandwidth and queue stability.

Use a feasible Pareto frontier over p95 first output, p95 end-to-end latency, throughput, memory and cost **after** quality and correctness gates. For audio, RTF = processing wall time / generated audio duration; state whether queue/transport are included. Keep ASR/text agreement, speaker identity and audio continuity separate from latency. For video, fix duration/FPS/resolution and measure temporal consistency plus perceptual/task quality.

Search order: establish a supported serial baseline → remove memory-infeasible combinations → profile stage/transfer bottleneck → sweep a small set of existing settings → test interactions → consider code/algorithm changes. Do not treat lower media quality or reduced workload as a free execution win.

## Evidence

Use [schema, deploy, merge, orchestrator, affinity, transport, qwen, steps, runner and modes](../../../references/evidence.md). The search table is engineering synthesis from those interfaces, not an upstream claim that every combination works.
