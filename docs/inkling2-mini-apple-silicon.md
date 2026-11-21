# Inkling 2 Mini on Apple silicon: local adaptation and one RSI round

**RESULTS_HEADLINE**

[Inkling 2 Mini](https://huggingface.co/thinkingmachines/Inkling-2-Mini) is a
26B-total, MoE, looped transformer from Thinking Machines Lab (24 layers; the
first and last 6 run once, the middle 12 run three times; about 3.4B active
parameters, 5.4B effective with the loop). The release checkpoint is ModelOpt
NVFP4 experts with MXFP8 tail layers (about 20 GB) and does not load in Apple
runtimes directly. This page records how it was brought up on one Mac with
community conversions, which runtime was faster, and one InferRSI-style search
round on that runtime. Measurement rules follow the
[scheduling RSI lessons](scheduling-rsi-lessons.md) and the
[Apple silicon playbook](apple-silicon-playbook.md). Nothing here is an
InferRSI acceptance result.

## Machine and sources

- Apple M5 Max, 128 GB unified memory, macOS 27.0 (26A425).
- Labels: **measured** = run on this machine, raw logs in the maintainers'
  run directory (not published); **public** = model card or repository at the
  link given.

| Route | Weights | Runtime | Source |
| --- | --- | --- | --- |
| MLX | [mlx-community/Inkling-2-Mini-4bit](https://huggingface.co/mlx-community/Inkling-2-Mini-4bit) (17.3 GB) | mlx-lm from [ml-explore/mlx-lm#2086](https://github.com/ml-explore/mlx-lm/pull/2086) (`0c4c991`), mlx 0.32.4 | public |
| llama.cpp | [lmstudio-community/Inkling-2-Mini-GGUF](https://huggingface.co/lmstudio-community/Inkling-2-Mini-GGUF) Q4_K_M (17.5 GB) | llama.cpp main `418fe97`, Metal | public |

Not run: Ollama (not installed on the machine), vLLM/SGLang (no Apple
backend for this model), the variable-loop research model
`TML-d24-varloop-research` (released only in the ModelOpt format, no MLX or
GGUF conversion at the time).

## Bring-up

| Observation | Cause | Action | Source |
| --- | --- | --- | --- |
| The release checkpoint does not load in MLX or llama.cpp. | Experts are ModelOpt NVFP4 and the last 4 layers MXFP8; Apple runtimes need their own formats. | Use a community conversion and pin it by repository and file hash. | public |
| Released mlx-lm 0.32.2 has no `inkling2_loop` model. | Support is in an open pull request. | Install mlx-lm from [#2086](https://github.com/ml-explore/mlx-lm/pull/2086) (`0c4c991`); llama.cpp main already has `inkling2_loop`. | measured |
| Two shards arrived larger than their published size (5,140,845,290 bytes against 5,031,793,948; two GGUF segments over-long). | The segmented downloader appended curl's own `--retry` restarts, which resend the range from its start. | Verify every shard against the Hub `lfs.oid` SHA-256 before the first load; re-fetch only segments whose size is wrong. | measured |
| With `reasoning_effort="none"` (template value 0) the model still thinks first: a 512-token cap ended inside the thinking block on both runtimes. | The chat template only adds a system line; the model is not forced to skip thinking. | Give code-generation tests a cap that covers thinking plus answer (4,096 here); count thinking and answer tokens separately. | measured |
| A complete code-generation run on MLX produced 2,244 tokens (thinking, then a 78-line Python file with 3 pytest cases); the 3 tests pass. | — | Keep one end-to-end generation with a checked answer next to any speed number. | measured |
| llama-server's streamed answer appears in `reasoning_content`, not `content`, until thinking ends; repeated requests reused the cached prompt (4 of 61 prompt tokens processed). | Server-side reasoning parsing and prompt cache. | Read both fields for time to first token and send `cache_prompt: false` when timing. | measured |

## Route comparison

Same machine, one runtime at a time (a lock file kept them apart), greedy
decoding, fresh process per route. Idle ComfyUI and a small mlx-lm server were
resident but not working during the runs.

| Metric | MLX 4-bit | llama.cpp Q4_K_M | Command |
| --- | ---: | ---: | --- |
| Prefill, 512-token prompt (tok/s, mean of 3) | 1,677 | 998 | `mlx_lm.benchmark -p 512 -g 128 -n 3`; `llama-bench -p 512 -n 128 -r 3` |
| Decode, 128 tokens (tok/s, mean of 3) | 47.0 | 41.7 | same |
| Decode in a 512-token chat answer (tok/s, 3 runs) | 45.3–47.6 | 41.5–43.4 | `stream_generate`; llama-server `/v1/chat/completions` |
| Time to first token, 61-token chat prompt, warm (s) | 0.24 | 0.29–0.31 | same |
| Peak memory | 17.6 GB (`mx.get_peak_memory`), 19.0 GB in the benchmark | 17.6 GB resident, of which weights are file-mapped | |

MLX was faster on both prefill and decode, so the RSI round below uses MLX.
The first MLX request of a process took 2.17 s to first token because Metal
kernels compile on first use; warm numbers exclude it.

## RSI round

RSI_SECTION

## What we did not establish

LIMITS
