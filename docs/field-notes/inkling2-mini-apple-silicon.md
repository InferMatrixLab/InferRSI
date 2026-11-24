# Inkling 2 Mini on Apple silicon: local adaptation and four exploratory RSI rounds

This is an unverified exploration record, not a performance claim. It has no
acceptance issue and is not an InferRSI PASS, so it publishes no speed,
latency or memory figures and no speedup ratios. It records how Inkling 2
Mini was brought up on one M5 Max with MLX and llama.cpp, how four
InferRSI-style search rounds on MLX were run, and the method and failure
lessons from them. The raw measurements stay as unverified records in
[examples/inkling2_mini_mlx](../../examples/inkling2_mini_mlx/README.md)
(`route/` and `rounds/r*/`).

[Inkling 2 Mini](https://huggingface.co/thinkingmachines/Inkling-2-Mini) is a
26B-total, MoE, looped transformer from Thinking Machines Lab (24 layers; the
first and last 6 run once, the middle 12 run three times; about 3.4B active
parameters, 5.4B effective with the loop). The release checkpoint is ModelOpt
NVFP4 experts with MXFP8 tail layers (about 20 GB) and does not load in Apple
runtimes directly. This page records how it was brought up on one Mac with
community conversions, how the two runtimes were compared, and how
InferRSI-style search rounds were run on MLX. Measurement rules follow the
[scheduling RSI lessons](scheduling-rsi-lessons.md) and the
[Apple silicon playbook](apple-silicon-playbook.md). Nothing here is an
InferRSI acceptance result.

## Machine and sources

- Apple M5 Max, 128 GB unified memory, macOS 27.0 (26A425).
- Labels: **measured** = run on this machine; unless a row links raw outputs,
  the logs are in the maintainers' run directory (not published), so treat it
  as unverified; **public** = model card or repository at the link given.

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
resident but not working during the runs. Raw outputs (benchmark logs,
llama-bench JSON, per-run chat timings as JSONL, the model output as a separate text file) are in
[examples/inkling2_mini_mlx/route](../../examples/inkling2_mini_mlx/route/).
Both runtimes ran with default settings; this is one exploratory
default-against-default comparison, not a runtime ranking.

Commands: `mlx_lm.benchmark -p 512 -g 128 -n 3` and
`llama-bench -p 512 -n 128 -r 3`, then three 512-token chat answers through
`stream_generate` and llama-server `/v1/chat/completions`.

The search rounds below used MLX, which was ahead of llama.cpp on both
prefill and decode in this one comparison. The first MLX request of a process
is slow to first token because Metal kernels compile on first use; time warm
requests separately from the first one.

## RSI round

Scripts, candidates and per-round records:
[examples/inkling2_mini_mlx](../../examples/inkling2_mini_mlx/README.md).

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
- a "better" verdict needs a mechanism signal. `rsi_mlx.py` performs only the
  speed screen and prints "speed screen passed, pending mechanism check";
  the mechanism is measured separately with `mechanism.py` and `count_ops2.py`
  (reported per round below). A candidate with an error, fewer pairs than
  `--reps` or a failed revert is INCONCLUSIVE.

The verdict strings stored in the committed `score-*.json` records ("keep",
and "留" in round 1) were written by earlier versions of the scorer and are
superseded by the rules above; the raw paired ratios in the records are kept
unchanged.

**Selection and holdout.** Within each round, every candidate was run on the
evolve and the holdout prompts in the same session. There is no record that
the shipped candidate was fixed from the evolve scores and the 5% rule before
the holdout results were read, so both splits are reported as exploratory
data, not as a held-out confirmation.

**What each round tried and learned.** The per-candidate paired ratios,
noise ranges and mechanism timings are in the committed `rounds/r*/`
records; they are not summarised here.

- Round 1: `mx.compile` around single sub-blocks (message gates, MoE, depth
  residual, gates + MoE). Every candidate was token-identical and below the
  5% rule: no conclusion. The default path drifted upward during the round;
  the first scorer compared each candidate with the median of all default
  runs, which inflated one candidate, so the scorer was changed to adjacent
  pairing before round 2. The "留" verdict and ratio stored in
  `rounds/r1/score-evolve.json` come from that superseded scorer.
- Round 2 (proposed from round 1): combined compile points and a fused MLP
  half per layer. Lesson: per-module compiles move little on a launch-bound
  model; the mechanism probe attributed part of the saving to CPU graph
  construction and part to fewer GPU kernels.
- Round 3 (proposed from a per-module profile at decode shape, where the
  attention half of a layer visit was dominated by small ops): each layer
  visit for B = 1, L = 1 split into a compiled graph before the KV-cache write,
  the cache write and attention eager (their length changes every step), and a
  compiled graph after; conv states become explicit inputs and outputs.
  Options on top: the attention mask/bias as one Metal kernel; q/r/gate/sink
  projections in one quantized matmul; message-gate projections in one
  matmul. Several options were within 5% of each other: no conclusion between
  them.
- Round 4 (proposed from the op count after round 3: each 4-tap short
  convolution was a chain of small ops): one-kernel short convolutions on top
  of the round-3 options. The mechanism probe showed fewer non-view ops and
  less Python graph building per step, and the step stayed launch-bound
  rather than bandwidth-bound. A batched message-gate variant was within 5%
  of it: no conclusion, not shipped.
- Across rounds the default path's own speed moved with temperature, so only
  adjacent-paired ratios are compared, never absolute speeds across rounds.

**How candidates were produced.** The candidates were written by the
assistant running the campaign (Claude Code, `claude-opus-5-5`) from reading
the model source; no automatic mutation chain was used. Each round was
proposed after reading the previous round's scores and, for rounds 3–4, a
per-module profile and an op count of one decode step.

## What we did not establish

- No acceptance issue, frozen campaign evidence bundle or independent rerun;
  no performance figure is established, and none is published here.
- One machine, one macOS build, 128 GB; nothing on 32–64 GB Macs, which the
  model card lists as supported.
- Single stream only; no batching, concurrency or long-context runs (the
  advertised 1M context was not exercised). Prompts are short (61 tokens);
  prefill-heavy work was measured only by the 512-token benchmark.
- Quality was checked only as greedy-token identity on four prompts and one
  passing generated test file; no benchmark accuracy.
- The patch was not measured inside `mlx_lm.server` and was not proposed to
  mlx-lm. "Identical" means identical greedy tokens on the prompts tested; the
  compiled graphs are not proven bit-exact for every input.
- llama.cpp was run with default settings; its flags were not searched, so
  the route comparison is default against default.
