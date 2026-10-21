# Source notes: bound windowed-attention replay

## Provenance and limits

- Upstream: [deepseek-ai/DeepInfer](https://github.com/deepseek-ai/DeepInfer), revision [`8b16149741a4935e1dec8cea27853f273b374c5b`](https://github.com/deepseek-ai/DeepInfer/commit/8b16149741a4935e1dec8cea27853f273b374c5b).
- Snapshot: `source.tar.xz`, SHA-256 `7de61b01434549e2871779b12dec307fb4e283e5da3255bb19036e7be52c65ea`, 1,086 regular files. That is archive size, not reading coverage; the selected paths below were read statically. Nothing was built, installed or executed; no weights were fetched.
- The parent's [Apache-2.0 license](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/LICENSE#L1-L3) was inspected. The six vendor submodules retain independent licenses.
- **F** means code behaviour at this pin; **P** means proposed, unvalidated procedure. Empirical validation: **not_run**.
- The model this implements is DeepSeek-V4.1-Flash. Window sizes, layer counts and ring lengths below are that model's; the *rule* is what transfers, and only the rule.

## What the architecture actually is

This is the part that decides whether the procedure transfers, so it comes first.

DeepSeek-V4.1-Flash splits the decoder stack at `n_prefill_layer`. Layers before the split are producer layers and run over the full chunk. Layers from `n_prefill_layer` onward are **consumer** layers and run over a compact query built from a retained suffix (`F`: `deepinfer/model_executor/models/v4_modules/yoco.py:15-25`).

Three properties make the shortening valid, and all three are architectural rather than incidental:

1. **A shared hidden is captured at the boundary.** The first consumer layer's attention-norm output is the shared hidden; later consumer layers consume it, and some SWA layers project their KV from it (`F`: `yoco.py:24-42`, `decoder_layer.py:145-152`).
2. **Full-length KV is written at the boundary.** The consumer KV-source layer projects KV from the full hidden and stores main/index KV at full length, so the persistent cache is complete even though the query is compact (`F`: `attn.py:672-719`).
3. **The SWA path has an explicit visible-region rule.** Its visible region intersects the sliding window, retained rectangle and valid-state start (F3 below). This does not restrict every consumer attention path to SWA: the main/index KV path above preserves full historical keys while query rows are compacted.

None of these follows from "the layers have a finite window". A stack of individually windowed layers could still have a consumer whose dependence reaches further back, through a shared state or a compressed index. That is why `SKILL.md` step 1 asks for the dependency closure rather than a per-layer window check.

## F evidence ledger

### F1 — The retain rule and the rollback floor

[`deepinfer/environ.py:132`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/environ.py#L132):

```python
DEEPINFER_MAX_BACKTRACKING_TOKENS = EnvVar(lambda v: max(_int(v), envs.DEEPINFER_USE_NEXTN_DECODE + 1))
```

The rollback depth cannot be configured below the speculation width plus one. That floor is what makes `window + rollback` sufficient: a full-width rollback after a full-width draft still leaves a full window.

### F2 — The retain rule is enforced at three layers

The C++ metadata builder checks it at [`csrc/engine/input_metadata/prepare_tensor_input_v4.cpp:350-357`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/input_metadata/prepare_tensor_input_v4.cpp#L350-L357):

```cpp
if (args.yoco_prefill_truncation_mode == YocoPrefillTruncationMode::OFF)
    return;
const int32_t keep_tokens = args.yoco_prefill_keep_tokens;
TORCH_CHECK_GT(keep_tokens, 0);
TORCH_CHECK_GE(keep_tokens, args.window_size + args.max_backtracking_tokens)
    << "DEEPINFER_YOCO_PREFILL_KEEP_TOKENS must be >= window_size (" << args.window_size
    << ") + DEEPINFER_MAX_BACKTRACKING_TOKENS (" << args.max_backtracking_tokens << ")";
```

Note the guard: the whole entry point returns early when the mode is `off`, so these checks apply only when truncation is enabled. There is no assertion about `keep_tokens` in the disabled path. `KEEP_TOKENS` is `EnvVar.int()` with no default (`F`: `environ.py:194-197`), which resolves to 0, so enabling truncation without setting it fails this check rather than silently clipping.

The same condition appears twice more before that:

- [`deepinfer/model_executor/model_metadata_utils.py:90-92`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/model_metadata_utils.py#L90-L92) asserts `yoco_enabled and n_prefill_layer > 0` and `KEEP_TOKENS > 0`, under the same `!= "off"` guard.
- [`deepinfer/worker/model_runner.py:107-114`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/model_runner.py#L107-L114) asserts `window_size > 0` and the `window + rollback <= keep` relation, again under the same guard.

### F3 — The visible-region formula

[`prepare_tensor_input_v4.cpp:155`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/input_metadata/prepare_tensor_input_v4.cpp#L150-L167):

```cpp
int32_t abs_lo = std::clamp(std::max({pos - window_size + 1, rect_lo, valid_start}), 0, pos + 1);
```

Three lower bounds intersect: the sliding window start, the retained rectangle's lower bound (`rect_lo = data_len - keep_tokens`, documented at `:145`), and `valid_start`. The third exists because zero-state recompute clears SWA state in `[0, valid_start)`, so the window must be clamped past it to avoid attending to cleared slots (`:153-155`). Skipping that clamp is a silent numerical bug, not a crash. An empty visible region is represented by `abs_lo == pos + 1` (`:150-152`).

### F4 — Two modes with different costs

[`deepinfer/environ.py:188-194`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/environ.py#L188-L194):

```python
DEEPINFER_YOCO_PREFILL_TRUNCATION_MODE = EnvVar.choice(default="off", choices=("off", "mask", "compact"))
```

- `mask` keeps every query row and only narrows the visible region. Compute-neutral; useful as a reference.
- `compact` removes the clipped query rows, which is where the compute saving is.

The metadata mirror is [`deepinfer/model_executor/input_metadata/yoco.py:32-72`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/input_metadata/yoco.py#L32-L72): `mask` mode produces `yoco_mask_swa_index_pivots` on the full layout, `compact` mode produces the `yoco_consumer_*` family on the compact layout, and `get_mask_view` / `get_consumer_view` are the two consumers.

The C++ side states the same split in the clip computation: `mask` mode sets `clip_prefix = 0` for all requests, so no rows are dropped (`F`: `prepare_tensor_input_v4.cpp:224-225`).

### F5 — Compact is gated on mode, not on CP

[`yoco.py:67-72`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/input_metadata/yoco.py#L67-L72) makes `yoco_compaction_enabled` a check of the truncation mode alone. Context parallelism is handled separately by compacting first and then applying the CP mirror (`F`: `yoco.py:55-77` computes the contributed-token count per rank and the compact-plus-CP length), rather than by disabling compaction.

### F6 — Full layout and compact copy coexist

[`deepinfer/model_executor/models/v4_modules/yoco.py:93-122`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/models/v4_modules/yoco.py#L93-L122) defines `compact_yoco_boundary`, whose docstring states it "returns the compact copies and the original full hidden/residual". The caller at [`decoder_layer.py:134-141`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/models/decoder_layer.py#L134-L141) stores `consumer_full_hidden = self.attn_norm_forward(*full_inputs)[1]` and only then replaces `hidden_states, residual` with the compact versions.

The correct statement is therefore: the full-layout representation is computed and retained for the boundary's full-length KV write, while the compact copy continues downstream. It is **not** a global ordering rule that KV writes precede gathers; in the consumer's forward the full KV write is a separate pass over the full metadata (`F`: `attn.py:672-719`, `_store_yoco_full_kv`).

`gather_hc_lazy` exists because the hyperconnection state is a structured bundle rather than a plain tensor: each per-token field has to be gathered over the kept intervals separately (`F`: `yoco.py:79-90`). The reason is field structure, not host residency — the bundle holds device tensors, and nothing in the module places them in host memory.

### F7 — Ring sizing has two separate additions

[`deepinfer/worker/cache_engine.py:88-110`](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/cache_engine.py#L88-L110):

```python
def get_inference_swa_block_size(window_size: int) -> int:
    return (window_size + envs.DEEPINFER_MAX_BACKTRACKING_TOKENS) if window_size > 0 else 0

def get_yoco_store_extra_tokens() -> int:
    return max(0, envs.DEEPINFER_YOCO_PREFILL_KEEP_TOKENS) if envs.DEEPINFER_YOCO_PREFILL_TRUNCATION_MODE != "off" else 0

def get_kvstore_swa_block_size(window_size: int) -> int:
    return get_inference_swa_block_size(window_size) + (
        (envs.DEEPINFER_PREFILL_STORE_EXTRA_SIZE + get_yoco_store_extra_tokens()) if envs.DEEPINFER_PREFILL_STORE_EXTRA_STATE else 0
    )
```

A nonpositive window produces an inference-ring size of zero. For a positive window, the inference ring is `window + rollback` per sequence. The kvstore function adds margins under nested conditions: `DEEPINFER_PREFILL_STORE_EXTRA_STATE` gates both additions; within that branch the store-granularity margin is added, and the truncation keep margin is added only when the mode is not `off`.

The comment states the store-granularity reason: kvstore writes only at multiples of 128, so prefill may not trigger a write and an extra span is needed to guarantee multi-round hits.

### F8 — The equivalence harness ships

`examples/yoco/yoco_equiv.py` and `run_yoco_equiv_l2.sh` are present at the pin, with `examples/yoco/README.md` describing the two-level check. This is TEST-SOURCE only: the harness was read, not run, and it requires a built extension plus the target device.

## P — Proposed items in the parent skill

- The dependency-closure step is P. The source implements one specific architecture; the requirement to derive the closure before shortening is a generalization proposed here, not something the source states.
- Separating query-row compaction from historical-key retention as two independently-decided questions is P. The source makes the first decision and preserves full-length KV at the boundary; the framing is proposed to prevent over-reading it.
- Recommending that a rejecting engine reject prompt-logprob requests rather than silently disabling them is P. The source disables with a warning.
- The instruction to state the anchor and document preemption movement is P.

## Not established

- No equivalence run. Metadata equivalence between `mask` and `compact` is argued from the shared `abs_lo` formula, not measured.
- Transfer to another architecture, including one with a different compressed index or historical top-k dependency, was not analysed. Its required historical state and query dependency closure must be derived independently.
- Preemption behaviour during a comparison run was not observed; whether recompute moves the anchor in practice was not tested.
- The kvstore ring's extra span was read from code and comments, not from an executed boundary case.
