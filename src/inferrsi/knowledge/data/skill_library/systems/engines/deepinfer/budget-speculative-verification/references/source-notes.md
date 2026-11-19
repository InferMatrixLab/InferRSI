# Source notes: budget speculative verification

## Provenance and limits

- Upstream: [deepseek-ai/DeepInfer](https://github.com/deepseek-ai/DeepInfer), revision [`8b16149741a4935e1dec8cea27853f273b374c5b`](https://github.com/deepseek-ai/DeepInfer/commit/8b16149741a4935e1dec8cea27853f273b374c5b).
- Snapshot: `source.tar.xz`, SHA-256 `7de61b01434549e2871779b12dec307fb4e283e5da3255bb19036e7be52c65ea`, 1,086 regular files. That is archive size, not reading coverage: selected parent paths were read statically; nothing was built, installed or executed, and no weights were fetched.
- The parent's [Apache-2.0 license](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/LICENSE#L1-L3) was inspected; source headers attribute the vLLM origin. The six vendor submodules retain independent licenses; this source map does not extend the parent's attribution over them.
- Bounded excerpts below are attributed to DeepSeek-AI. The operational procedure in `SKILL.md` is proposed here, not an upstream endorsement.
- **F** means code behaviour at this pin. **P** means a proposed, unvalidated procedure. Empirical validation: **not_run**.

Line references use four-digit line numbers and are stable at this pin. Upstream comments in the cited files are Chinese; the glosses below are translations and are marked as such.

## F evidence ledger

### F1 — The budgeted path is optional

[`deepinfer/environ.py:129-132`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/environ.py#L129-L132):

```python
DEEPINFER_USE_NEXTN_DECODE = EnvVar.int(default=5)
DEEPINFER_ENABLE_MTP_VARLEN = EnvVar.bool()
DEEPINFER_MAX_BACKTRACKING_TOKENS = EnvVar(lambda v: max(_int(v), envs.DEEPINFER_USE_NEXTN_DECODE + 1))
```

`EnvVar.bool()` defaults to false (`environ.py:70-71`). So the fixed-width path is the default and the budgeted path must be enabled. Speculation itself is on by default at width 5; setting `USE_NEXTN_DECODE=0` disables it.

### F2 — Draft cost is full width; only verification is budgeted

[`csrc/engine/mtp_varlen.hpp:150-158`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/mtp_varlen.hpp#L150-L158) controls non-budgeted verification lengths, not draft generation. The actual producer chain is [sampler.py:225-251](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/layers/sampler.py#L225-L251) → [DFlash.decode_forward/run_drafts:347-387](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/models/mtp/dflash.py#L347-L387). DFlash's width comes from `USE_NEXTN_DECODE` (`dflash.py:103,141`), builds request-count × fixed-width draft inputs (`:230-239`) and samples every configured position (`:308-336`). The inspected DFlash path remains full width while variable-length scheduling saves verification rows; this is not a claim about arbitrary draft-model implementations.

### F3 — Cumulative, sorted, prefix grants

[`mtp_varlen.hpp:204-214`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/mtp_varlen.hpp#L204-L214) builds two queues of `(accept_rate, seq_idx)` pairs and sorts both descending by rate, breaking ties by ascending sequence index:

```cpp
// descending by rate, ascending by sequence index on ties
static bool by_rate_desc(const Pair& a, const Pair& b) {
    return a.first != b.first ? a.first > b.first : a.second < b.second;
}
```

Grants walk this sorted order one row at a time, so a request can only receive verification for position `k` if it already received positions `< k`.

### F4 — Cost model and the non-negative slope clamp

[`mtp_varlen.hpp:216-247`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/mtp_varlen.hpp#L216-L247):

```cpp
const double sampler_ms = estimate.value_or(0.0);
const double slope_ms = std::max(0.0, _forward_time_slope.get());
...
const double time_ms = baseline_ms + slope_ms * graph_size + sampler_ms;
const double cur_throughput = cur_expected / time_ms;
```

The sampler term is a per-request-count median over a 9-sample window with a 5-sample minimum before it is trusted (`mtp_varlen.hpp:22-46`). The forward slope is fitted from `(forward_ms - baseline_ms) / graph_size` and aggregated per graph size before a second median (`mtp_varlen.hpp:43-60`). Clamping prevents a negative slope from extrapolating to a non-positive time at larger graphs.

The optimized quantity is `cur_expected / time_ms`, where `cur_expected` starts at `num_seqs` and accumulates the acceptance rate of each additional row (`:231`, `:252`). Fewer verified rows can therefore lower the accepted-token count while still raising this ratio.

### F5 — The floor is asserted, not trusted

[`mtp_varlen.hpp:260`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/mtp_varlen.hpp#L260): `TORCH_CHECK(best_bsz >= num_seqs);`

One row per request is the minimum meaningful verification, and the search is seeded with that (`:231-232`).

### F6 — Per-position independence is a correctness constraint

[`mtp_varlen.hpp:160`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/mtp_varlen.hpp#L160) states, translated from the Chinese source comment: "confidence for positions `i+1, …, nextn` must not affect whether `draft_token_i` is verified."

The comment continues to describe the two-round protocol as the way to satisfy that requirement while the scheduler runs ahead of sampling: use round N−2's rates for the global batch size and round N−1's rates for the per-request split. This makes the lag a correctness requirement on *which* rates may be combined, not only a workaround for an unavailable value.

[`mtp_varlen.hpp:161-183`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/mtp_varlen.hpp#L161-L183) implements it. Per-request `schedule_cnt` and `process_cnt` counters decide which round's vector is valid:

- `schedule_cnt == process_cnt` — the request's forward and post-process are paired, so `accept_rates` is from round N−1 and `prev_accept_rates` from N−2.
- `schedule_cnt == process_cnt + 1` — the latest forward has not produced rates yet, so both shift back one round.

The asserted invariant is `process_cnt <= schedule_cnt <= process_cnt + 1`. The pairing flag selects the batch-size queue's N−2 vector (`:204`). The per-request CPU queue always reads `accept_rates` (`:207`), hence N−1 when paired and N−2 when one forward is in flight. In the latter overlapping ZOS path, [worker.py:191-219](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/worker.py#L191-L219) uses the previous sampler's GPU confidence to redistribute fixed `total_q`. This correction feeds the current main forward, then its D2H metadata is synchronized before sampling ([worker.py:118-152](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/worker.py#L118-L152)). The CPU queue alone is not the final N−1 per-request allocation.

The source computes cumulative confidence by multiplication ([scheduler.hpp:1243-1250](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/scheduler.hpp#L1243-L1250)). Its description of individual token estimates must not be read as a demonstrated statistical-independence theorem; DFlash's optional Markov branch uses the preceding sampled token (`dflash.py:308-320`).

### F7 — Confidence is a model property, not an engine option

[`deepinfer/model_executor/models/mtp/dflash.py:159-160`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/models/mtp/dflash.py#L159-L160): `self.enable_confidence = True` with the comment that the HF DFlash checkpoint always contains a confidence head. The head is exported as `confidence_head_fused` (`:15`, `:73`).

Consequence for transfer: a model without a trained confidence head cannot use this procedure as written. A substitute per-position acceptance estimate would need its own validation, because the procedure assumes the vector is already calibrated.

### F8 — Two distinct temperatures

The confidence-head temperature is a per-position scale applied **inside the confidence head**, defaulting to `1.0` and clamped to `SAMPLING_EPS` = `1e-5` (`F`: `environ.py:134-147` defines the variable; `dflash.py:62-64` applies `max(value, SAMPLING_EPS)`; `dflash.py:76` passes `self.temperature[step_i]` into `confidence_head_fused`).

The request sampling temperature is separate. It is a field of `SamplingParams`, and values below `SAMPLING_EPS` are raised to `SAMPLING_EPS` with `top_p` set to `1.0` and `top_k` to `-1` (`F`: `deepinfer/sampling_params.py:76-79`).

Neither value implies the other. Confidence calibration does not tell you how the request samples, and the request's sampling temperature does not change the acceptance estimate.

### F9 — The reject path is gated on draft logprobs

[`deepinfer/model_executor/layers/tilelang_ops/fused_sample.py:200`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/layers/tilelang_ops/fused_sample.py#L200) sets `do_reject_sampling = last_nextn_token_logprobs is not None`; the flag then gates the residual computation, the acceptance comparison and the residual resample. Request temperature is not part of that condition. The sampler contract describes the decode path as accepting or rejecting drafts by the speculative-decoding rule (`F`: `deepinfer/model_executor/layers/sampler.py:76-77`, source comment).

Combined with the clamp in F8, this supports the statement that a request configured as greedy still goes through rejection. That reading is from the gating logic; no run confirmed it end to end.

### F10 — Structured output interacts with per-draft verification

[`deepinfer/model_executor/layers/sampler.py:363-376`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/layers/sampler.py#L363-L376) advances the grammar matcher once per draft, fills a mask per draft position, and rolls back by the number of accepted drafts. A grammar-constrained request therefore gets a per-position mask alongside the per-position acceptance rate; the two are independent signals and must not be conflated.

## P — Proposed items in the parent skill

- The framing of "expected accepted tokens per unit time" as the objective to report is F; the specific reporting template in `SKILL.md` is P.
- The recommendation to log realized-versus-predicted acceptance error is P.
- The statement that near-zero acceptance can still favour a one-row budget is derived from the cost objective at `:243-252` plus the one-row floor, not from a measurement.

## Not established

- No gain was reproduced. The source's own reported figure is a DOC-class claim in a deployment Q&A, not a local measurement.
- Whether the fitted slope generalizes past the graph sizes seen at warmup is unknown; the code only clamps it.
- Cross-backend equality of the rejection comparison has no assertion and was not tested.
- Memory behaviour of wide top-k verification pools was not measured.
- The greedy-still-verifies reading (F9) was not confirmed by running a temperature-0 request through the verify path.
