# Splash verification contract

The following is an operational interpretation of the bounded source readset
at the root provenance's immutable Splash revision. Source paths and line spans
identify evidence, not external files a future agent must open or execute.

## Target/draft and representation identity

The native draft validator requires `DFlash2DraftModel`, matching target hidden
and vocabulary sizes, the supported attention/window/selector contract, a valid
mask token, sufficient block length and captured target layers within bounds.
Captured layer order and the hidden reduction are part of the learned interface:
hyper-connected targets use a stream mean; another declared reduction is refused.
A shape-compatible file is not automatically an equivalent trained checkpoint.

The target's quantized token table can lose a very small mask row; the draft may
therefore carry its own BF16 mask embedding. Keep its presence and bytes in the
identity. The draft's checkpoint representation and the prepared af4g64 weight
images are different artifacts: the inspected preparation path quantizes draft
projections and preserves other tensors. Compare the images actually read by the
engine, while separately recording streamed expert/PLE bytes not held among
resident images. Source byte identity is not proved by a shared filename.

Evidence: `runtime/model/ModelDescriptor.mm:663-722`;
`runtime/model/DFlashDraft.hpp:21-123`;
`DEVELOPMENT.md:1925-2025`; `dev/benchmarks/backend_regression.py:1-50`.

## DFlash2 cycle and state invariants

| Stage | Inspected mechanism | Required invariant/check |
| --- | --- | --- |
| Draft | Per-lane anchor, target-hidden context and draft rings feed the selector; sampled lanes record proposal probabilities, uniforms and confidence | Target/draft/tokenizer/capture identity and logical positions agree; no lane aliasing |
| Verify-row choice | Dense targets verify the available block; MoE auto policy chooses rows using online acceptance probabilities and recent cycle costs, including streaming misses | At least an anchor and at most the lane's retention limit; record `verify_rows` and policy history, not only draft block size |
| Target verification and acceptance | Target policy applies penalties/filtering; sampled acceptance reads draft and target probabilities and correction draws; greedy acceptance matches selected tokens | Test the full policy and first rejection, not only top-1 agreement or mean acceptance |
| State commit | Target auxiliary commit and draft-state commit follow acceptance; GDN retained rows are folded through the state machinery | Only retained rows advance visible target/draft/logical state; physical suffix allocation is not committed history |
| Finalization | Counts are range-checked; invalid selections or unreadable spilled KV produce request failure without committing their state/tokens; successful lanes advance parity and lengths | Preserve failures, verify subsequent continuation and prevent invalid snapshots/reuse |

Inspected implementation anchors: `runtime/ops/DraftSelector.hpp:22-106` and
`.cpp:40-151`; `runtime/ops/Sampling.hpp:16-81,101-148` and
`.cpp:350-399`; `runtime/model/Runtime.cpp:1928-2001,2161-2188,2223-2343`.
The GPU acceptance kernel was sampled at
`runtime/metal/kernels/decode/sampling.metal:1466-1509,1665-1707`; this is code
inspection, not a complete kernel audit or runtime proof.

A cached composite state requires committed page-aligned target lengths and a
complete/current draft context window. Decode state can have pending retained
rows; an arbitrary token-length edit cannot manufacture a cacheable frontier.
The inspected warmup/oracle code exercises restore followed by real speculative
continuation, including overwriting a speculative page suffix and checking the
advance by committed KV-bearing output, not only returned token count.
Evidence: `runtime/model/QwenState.cpp:406-426,550-588,628-656`;
`runtime/model/Runtime.cpp:3400-3460`.

The scheduler owns a distinct plan/commit/complete state machine. It rejects a
plan that no longer matches the request phase/offset/decode stage and a completion
with changed request order or consumed prompt rows. Model-level retained-prefix
correctness does not independently establish scheduler fairness, admission,
cancellation or E2E correctness. Evidence:
`runtime/engine/Scheduler.cpp:511-568,572-648`.

## Acceptance, retention and API counters

- A native cycle normally produces eight draft rows: one anchor and seven
  proposals. Remaining output budget and verify-row choice can reduce the
  verified/retained portion. Unverified proposals are not acceptance failures.
- `draft_n` counts proposals actually verified. `draft_n_accepted` counts those
  verification accepted, excluding accepted proposals past the output limit or
  from a model stop token onward. A later server-side `stop`-string cut does
  **not** subtract those proposals: they still count. Thinking-budget end tokens
  substituted for draft proposals count as neither proposed nor accepted.
  Do not divide by every internally produced proposal, or recalculate accepted
  counts from only the final visible string. Retain these definitions with the
  raw counters; visible retained output and verification acceptance differ.
- `metrics.speculation.cycles` and `1 + accepted / cycles` describe speculative
  yield. They omit preparation, prefill, queueing and the cost of the draft,
  target verifier, state/cache work and corrections. More accepted tokens can
  still mean a slower or lower-quality task.
- A complete response in one emission can report a zero unavailable decode
  rate. It is not evidence that no tokens were generated.

Evidence: `DEVELOPMENT.md:1220-1243,1960-2012`;
`runtime/model/Runtime.cpp:2321-2336`.

## Precision, ANE and reproducibility controls

| Control | What changes | What does not follow |
| --- | --- | --- |
| `--kv-format int8` / `bf16` | Target KV storage and memory/timing; restart required; SSD cache retains the selected stored bytes | BF16 KV does not imply BF16 weights, FP32 recurrent state or ANE disabled |
| `--state-format fp32` / `bf16` | GDN recurrent storage; BF16 stores round at prefill chunk/capture/decode boundaries despite FP32 arithmetic | Equal chunk lengths, cache paths or long-context outputs are not guaranteed after a switch |
| `--verify-rows auto` / `all` | Timing/history-dependent MoE verification budget versus all available rows | `all` alone does not remove cache-prefix/chunk/batch/precision variation |
| `--disable-ane` | Eligible dense-target FFN prefill runs on GPU alone | It does not select a different decode backend or turn MoE decode from ANE into Metal |

The ANE split runs a W8A8 portion of dense FFN channels in parallel with GPU
work; mixers, MoE and decode remain on the GPU in the inspected design. Startup
calibration and memory/context constraints choose the share and minimum chunk
size, or leave GPU-only execution. The split's buffers consume memory that could
otherwise support KV/cache staging. A different automatically chosen context or
cache capacity confounds a supposed arithmetic-only comparison. Record actual
startup/status selection and separate calibration/startup from measured work.

For reproducible greedy/seeded MoE comparisons, select `--verify-rows all`,
isolate the request and control cached prefixes/chunking, concurrency and all
precision flags. Use an independent `cache_salt` for each repeat intended to
avoid earlier cached computation. That salt is an experimental isolation
control, not proof that all arithmetic is unchanged. Sampling distribution,
seeded token equality, model numerical fidelity and task quality are distinct
contracts. Do not change a frozen equality gate after seeing a mismatch.

Evidence: `DEVELOPMENT.md:418-452,1092-1158,2992-3075`;
`runtime/model/VerifyBudget.hpp:3-38,48-112`.

## Measurement and attribution

1. Freeze same-machine power/charger, chip/GPU cores, memory, OS, engine/shader,
   target/draft and prepared/streamed bytes. Record prompt/tokenizer/template,
   thinking/sampling/penalties, concurrency, output limit, cache salt/hits,
   precision, actual ANE share/context and verify-row policy. Keep failed and
   noisy rounds; do not cherry-pick a stable-looking subset after observing them.
2. Separate preparation/loading/calibration, cold prefill, partial/exact-prefix
   cached TTFT and steady decode. API `prompt_ms` starts at native work, not
   initial admission; `predicted_ms` starts at first emission. Its rate excludes
   the entire first emission, possibly several speculative tokens. These are
   elapsed native intervals, not isolated GPU time or client E2E latency.
3. Use baseline/candidate/candidate/baseline rounds on one idle machine.
   The bundled [descriptive summarizer](../scripts/summarize_rounds.py) computes
   four sample medians, baseline/candidate means, relative change and within-pair
   spread for a positive lower-is-better metric. It deliberately omits the
   upstream release helper's fixed noise/regression verdict thresholds. Only
   the separately frozen experiment gates may determine a result.
4. A same-weight numerical comparison should score the same token prefixes,
   including full-vocabulary logits, not only separately generated trajectories.
   Distinguish top-1 agreement, KL/NLL and complete task/output quality. An
   expected-arithmetic/layout-change switch changes what the upstream harness
   checks; it cannot retroactively authorize weaker acceptance.
5. Add client-observed admission-to-first-token/completion, tail latency, service
   load/concurrency, error/cancellation/recovery and correctness/quality for an
   E2E claim. A native kernel/backend benchmark is not an agent-task benchmark;
   a UI token rate is not an E2E latency result.

The published launch and same-GGUF comparisons are **author-reported**, not
locally reproduced by this extraction. They differ in release, model package,
hardware/core/memory, workload and controls. In particular the documented
GGUF numerical comparison used BF16 KV and disabled ANE; default INT8-KV
numbers are separately reported. Do not stack those ratios or transfer them to
another Mac, precision mode or task.
Evidence: `docs/performance.md:5-70`;
`DEVELOPMENT.md:1220-1243,4104-4207`;
`dev/benchmarks/backend_regression.py:1-50` and `abba.py:1-71`;
`dev/benchmarks/logit_compare.py:1-25`; `http_regression.py:1-8,31-45`.

## Required evidence and script boundary

| Layer | Representative source anchor | Meaning/remaining limit |
| --- | --- | --- |
| Source and CPU policy/statistics | ABBA helper/tests, selected Python protocol or model-free logic | Verifies only that logic and guidance, not Metal/ANE or model execution |
| Native operator/state | Draft selector, target sampling, GDN and restore/continuation fixtures | Needs the supported Mac/Metal/ANE paths actually exercised; synthetic CPU tests cannot substitute |
| Matched model | Runtime oracle, same-prefix logits and actual cache/restore requests | Requires compatible target/draft weights and exact selected precision/layout |
| Service/quality | Isolated HTTP cold/cache/decode/burst/follow-up and complete task-quality workload | Needs client E2E and frozen quality/SLO evidence; not established by native throughput |

The inspected `make check` includes Metal work and is not a portable CPU-only
check. Native CPU targets still belong to the supported platform/build chain.
No model/native execution was performed by this lane. Required Metal/ANE/model
and actual device/disk-state evidence remains `BLOCKED_REQUIRED_BACKEND`.

Script inventory: the small ABBA statistical reduction is adapted into the
bundled no-verdict helper. Full native/HTTP regression, logit dumping and release
harnesses are reference-only because they require model/native binaries, start
isolated servers, write large artifacts or need numerical policy. Install/model
and client-launch helpers are excluded here because they download/prepare large
weights or mutate external application/process state. Their useful controls
are distilled above; no source-checkout script is a runtime dependency.
