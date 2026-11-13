# Serving cookbook

## Environment and baseline

Use an isolated target Linux environment with the appropriate accelerator stack. Source metadata allows Python >=3.10,<3.14; the pinned quickstart uses Python 3.12 with vLLM 0.31.0. Do not reuse the old AREX 0.26 environment assumption. Resolve a matching release/wheel/driver combination before installation; this skill does not include wheels or weights.

After installing the matching environment, inspect the local CLI:

```bash
vllm serve --omni --help
vllm bench serve --omni --help=all
```

Minimal pinned quickstart example (requires model access and sufficient GPU memory):

```bash
vllm serve Tongyi-MAI/Z-Image-Turbo --omni --port 8091
```

```bash
curl -s http://localhost:8091/v1/images/generations   -H 'Content-Type: application/json'   -d '{"prompt":"a cup of coffee on the table","size":"1024x1024","response_format":"b64_json","seed":42}'
```

Check response status, valid nonempty media and dimensions. A 200 response alone does not prove image quality. For local Python use `from vllm_omni.entrypoints.omni import Omni`, instantiate the selected model and call `.generate(prompt)`; public output fields depend on modality. Close owned resources according to the selected API's lifetime contract.

## Stage configuration

Deploy YAML overlays select existing `stage_id`s. `devices`, replicas, TP and resource budgets can vary by stage. Top-level engine fields in `DeployConfig` apply pipeline-wide; legacy pass-through fields exist, so inspect the resolved config instead of inventing a universal precedence shortcut. Model sampling constraints remain model-owned.

For Qwen3-Omni, source deploy uses async chunks and SharedMemoryConnector with `initial_codec_chunk_frames: 4`, `codec_chunk_frames: 25`, `codec_left_context_frames: 25`; those are model-specific defaults, not a recommendation for every TTS pipeline. Keep the codec context semantics while exploring latency. Capture each stage's effective queue/sequence/token/graph limits.

## Diffusion execution template

At this pinned revision, Qwen-Image documents request batching and step-wise continuous batching. Recheck the capability if the source/model revision changes. Start with this serial baseline:

```bash
vllm serve Qwen/Qwen-Image --omni --port 8091 --max-num-seqs 1
```

Then compare one change at a time: request batching with `--max-num-seqs N`, or step scheduling with `--step-execution --max-num-seqs N`. Request admission wait `--request-batch-max-wait-ms` affects request mode, not step mode. Step support alone does not authorize batched steps. `--diffusion-streaming-output` enables step execution as needed but only chunk-emitting pipelines produce intermediate media.

## Experiment contract

Keep model and tokenizer/processor revision, deployment digest, precision, backend, request corpus, output shape/duration/steps, sampling and seed, arrival process, concurrency, warmup, repetitions and failures. Record actual fallback and resolved settings. Compare matched repeats; report p50/p95/p99 and sample count, throughput units, peak GPU/host memory, stage times and transfer bytes.

For speech, distinguish text TTFT from first audio TTFP, report chunk-gap tails and RTF with its timing boundary. Define whether first audio means first received delta, first decoded packet or first audible speech; leading silence and encoding can otherwise confound comparisons. These may require extra instrumentation. For images/videos use generated media units and end-to-end latency; a fixed denoiser kernel speed is not full service throughput. Record correctness/quality failures before filtering; a faster invalid configuration is not eligible.

## Failure recovery

| Symptom | Inspect | Next bounded action |
|---|---|---|
| `--omni` unavailable / import incompatibility | Active vLLM/Omni versions, executable path | Align pinned source environment; do not guess old CLI ownership |
| Startup OOM despite utilization sum below one | Actual weights, graph/workspace pools, stage startup logs | Reduce capacity/graph coverage or change placement; remeasure rather than increasing utilization blindly |
| No first audio / large chunk gaps | Request-to-stage trace, waiting upstream data, chunk contract, downstream queue | Baseline one request, isolate stage/transport delay, inspect error path |
| Invalid batch/step combination | Pipeline capability and runner guard | Return to serial request path; add capability only as tested implementation work |
| Corrupt/repeated/missing media | Payload shape/type, chunk identity/order, accumulation, completion event | Preserve trace and output; stop perf search and run output/transport tests |
| Multi-GPU hang | Collective group, placement, per-rank startup/error and peer failure | Reproduce smallest supported topology, test affected native transport/collective |

See [pinned quickstart, schema, deploy, modes and qwen-deploy](../../../references/evidence.md). Commands are source-checked recipes; they were not executed as GPU serving in this package.
