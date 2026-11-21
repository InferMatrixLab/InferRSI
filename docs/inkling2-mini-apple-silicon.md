# Inkling 2 Mini on Apple silicon: local adaptation and one RSI round

**On one M5 Max, MLX ran Inkling 2 Mini at 47.0 tok/s decode and 1,677 tok/s
prefill (512-token prompt), ahead of llama.cpp at 41.7 and 998. Two search
rounds then found a compile patch that raised MLX decode by 6.4% (paired
median, held-out prompts, run-to-run noise 3.9%) with token-identical greedy
output.** These are maintainer measurements without an acceptance issue; they
are not an InferRSI PASS.

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

Scripts, candidates and per-round records:
[examples/inkling2_mini_mlx](../examples/inkling2_mini_mlx/README.md).

**Plane and why.** Decode on this model is launch-bound rather than
bandwidth-bound: a token visits 48 layers (6 + 12 × 3 + 6), each with a MoE
block, two depth-attention residuals and, in loop passes 2 and 3, four
message gates, so many small kernels and Python graph-building per step.
The searched plane is therefore *model-side graph compilation* (`mx.compile`
around pure sub-blocks), not scheduling: one user, one stream, no queue to
order. Loop count was not searched because the variable-loop model has no
Apple-format weights and changing `num_passes` on the released model changes
its output.

**Gates frozen before the run** (inherited from the
[scheduling RSI lessons](scheduling-rsi-lessons.md)):

- greedy decoding; a candidate whose token ids differ from the default path on
  any prompt is rejected;
- each candidate run is paired with the default run immediately before it, 3
  pairs per candidate, score = median paired ratio of decode tok/s;
- below 5% difference: no conclusion;
- candidates are selected on two "evolve" prompts and reported on two
  different "holdout" prompts (TypeScript and Rust code generation);
- a "better" verdict needs a mechanism signal.

**Round 1** (evolve, 256 generated tokens, noise 2.9%). Paired medians:
gates 1.031, MoE 1.015, depth residual 1.012, gates + MoE 1.048. All
token-identical, all below 5%: no conclusion. The first version of the scorer
compared with the median of all default runs; the default path drifted from
47.4 to 48.9 tok/s during the round, which inflated gates + MoE to 1.053. The
scorer was changed to adjacent pairing before round 2.

**Round 2** (proposed from round 1: combine the compile points; fuse the whole
MLP half of each layer).

| Candidate | Evolve (noise 2.3%) | Holdout (noise 3.9%) | Output |
| --- | ---: | ---: | --- |
| gates + MoE (round-1 best, re-run) | 1.043 | 1.054 | identical |
| gates + MoE + depth residual | 1.057 | 1.056 | identical |
| fused MLP half per layer | 1.044 | 1.039 | identical |
| **fused MLP half + q/k/v gates** | **1.068** | **1.064** (1.068, 1.064, 1.060) | identical |

Mechanism (one decode step, synchronous, median of 50 steps, two alternating
processes each): 22.07 → 20.94 ms per step; Python graph building
3.89 → 3.34 ms. About half of the saving is CPU graph construction and the
rest is GPU time from fewer, fused kernels. The winning patch is
`rounds/r2/cands/r2d_fused_half_gates.py`; it changes no weights and no
numerics outside the compiled regions.

**How candidates were produced.** The candidates were written by the
assistant running the campaign (Claude Code, `claude-opus-5-5`) from reading
the model source; no automatic mutation chain was used. Round 2 was proposed
after reading round 1's scores.

## What we did not establish

- One machine, one macOS build, 128 GB; nothing on 32–64 GB Macs, which the
  model card lists as supported.
- Single stream only; no batching, concurrency or long-context runs (the
  advertised 1M context was not exercised). Prompts are short (61 tokens);
  prefill-heavy work was measured only by the 512-token benchmark.
- Quality was checked only as greedy-token identity on four prompts and one
  passing generated test file; no benchmark accuracy.
- The compile patch was not measured inside `mlx_lm.server` and was not
  proposed upstream.
- llama.cpp was run with default settings; its flags were not searched, so
  the route comparison is default against default.
