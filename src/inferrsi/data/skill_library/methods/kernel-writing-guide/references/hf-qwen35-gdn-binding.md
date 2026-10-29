# Transformers Qwen3.5 convolution and GDN binding

Use this reference to qualify a concrete HF Qwen3.5 caller before adapting
convolution or Gated DeltaNet (GDN). State: candidate; native/model/device/
numerical/performance execution `not_run`; agent efficacy `not_evaluated`.
The [source ledger](hf-qwen35-gdn-source.json) owns both release identities,
inspected spans, Git blob IDs and SHA-256 digests. These are research-source
revisions, not experiment results or installation instructions. Read the
[five source cases](../cases/hf-qwen35-gdn-binding.md) after resolving the layer.

Both snapshots define
`transformers.models.qwen3_5.modeling_qwen3_5.Qwen3_5GatedDeltaNet`.
The decoder constructs it only for `linear_attention`; `full_attention` uses
a separate token mixer. Projection, gated norm and output projection remain
outside the chunk/recurrent operator. [D10, D17, M10, M17]

## Resolve the version and binding lifetime

| Boundary | Transformers 5.10.2 | Transformers 5.17.0 |
|---|---|---|
| Module setup | Imports Dao `causal_conv1d_fn/update` when conv availability succeeds, and FLA gated norm plus chunk/fused-recurrent GDN when FLA availability succeeds; otherwise sets the respective globals to `None` | Defines PyTorch conv/GDN functions decorated by `use_kernel_func_from_hub_with_fallback`; forward uses `torch_chunk_gated_delta_rule` and `torch_recurrent_gated_delta_rule` |
| Selection | Constructor saves `self.causal_conv1d_fn/update`, `self.chunk_gated_delta_rule` and `self.recurrent_gated_delta_rule`; missing update/chunk/recurrent globals independently choose local fallbacks | Fallback decorator resolves an original-package callable while decorating: conv from `causal_conv1d`, recurrence from `fla.ops.gated_delta_rule`; failed imports or missing symbols retain the local function |
| Forward lookup | Calls those saved instance fields | Inspected Python forward reads module globals; constructor has no corresponding four saved fields |
| Additional replacement boundary | Inspected GDN class has no whole-forward Hub decorator | Class has `use_kernelized_func` and `use_kernel_forward_from_hub("Qwen3_5GatedDeltaNet")`; explicit Hub kernelization can replace functions or the whole forward |
| Adapter consequence | Changing only a module global after construction leaves the saved field unchanged; establish binding before construction or audit an authorized instance change | Resolve actual forward and wrapper first; changing the obsolete `chunk_gated_delta_rule` name alone does not replace the global called by this Python forward |

The 5.10.2 helpers require CUDA availability plus a discoverable conv package;
FLA additionally requires version at least 0.2.2. Its import-time aggregate
`is_fast_path_available` controls a warning, rather than forcing every
operator onto one branch. Conv can be external while GDN falls back, or
conversely. FLA presence also selects the constructor's gated RMSNorm.
A chunk replacement alone does not select conv or gated norm. [I10, M10]

In 5.17.0, a `torch_` name does not establish execution of its PyTorch body.
The decorator captures the chosen implementation and parameter names during
module setup, then filters keyword arguments to those names. Exporting calls
use the local body when an original-package implementation was captured.
Ordinary calls use that captured implementation; invocation failure is not
caught and retried on PyTorch. Do not impose 5.10.2's availability predicate
on this new import path. [H17]

HF's Hub integration gives requested Hub replacements precedence over the
original package and local reference. Class decorators are inert when
`kernels` is unavailable; the installed-kernels branch honors
`USE_HUB_KERNELS`. Its `kernelize` delegates replacement to that external
package. External Hub bodies, architecture support and resulting forwards
are outside this readset. Resolve active Hub or worker method replacements
before applying the Python-forward contract below. [H17]

## Classify phase from state, not token count alone

Both text-model forwards create `DynamicCache` only when `use_cache` is true
and no cache was supplied. A supplied cache is still forwarded; setting
`use_cache=False` does not remove that object. GDN checks `cache_params` and
its layer's `has_previous_state` (state index 0 in 5.17.0). A first one-token
input without prior state follows the chunk route. [T10, T17, C10, C17]

| Actual GDN input state | Convolution | GDN and state handling |
|---|---|---|
| `cache_params=None`, any positive sequence length | Full causal conv; no persistent history write | Chunk call, `initial_state=None`, `output_final_state=False`; no cache update |
| Cache supplied, no previous state | Full conv; record initial history | Chunk starts without recurrent state, requests final state and copies it into cache |
| Previous state, one token | In-place conv update; 5.17.0 additionally requires `record_past=False` | Recurrent call receives prior matrix, requests final state and updates cache |
| Previous state, multiple tokens | Prepend old context; retain outputs for the new segment | Chunk call receives prior matrix, requests final state and updates cache |
| 5.17.0 previous state, one token, `record_past=True` | Cache-managed full-conv assembly | Still recurrent GDN; the conv and recurrence guards differ |

In 5.10.2, forward concatenates old history for continuation and pads or
truncates new history to convolution width before `update_conv_state`.
In 5.17.0, `update_conv_state` returns the full context-plus-new input;
forward trims conv output to the current sequence. Ordinary cache mode
retains only trailing width; `record_past` retains assembled conv input.
The helper's returned tensor is not necessarily the retained history size.
[M10, M17, C10, C17]

## Preserve dtype, layout and two different states

Let `B,T,Hk,Hv,Dk,Dv,W` mean batch, current tokens, key/value head counts,
head dimensions and convolution width. Read actual config; defaults do not
prove checkpoint geometry. Source constructs depthwise conv with
`C=2*Hk*Dk+Hv*Dv` channels, groups `C` and no bias. Projection is transposed
to `[B,C,T]`; squeezed weights are `[C,W]`. That transpose is not a general
contiguous-stride guarantee. Check the [Dao layout contract](causal-conv1d-contract.md)
before binding its native API. [M10, M17, Q10, Q17]

| Value | Source-level caller contract |
|---|---|
| Q/K/V | Split conv output; Q/K become `[B,T,Hk,Dk]`, V becomes `[B,T,Hv,Dv]`; when the head-count quotient exceeds one, HF repeats Q/K along heads before GDN |
| Gating | `beta=sigmoid(b)`; log decay is `-exp(A_log.float())*softplus(a.float()+dt_bias)`; explicit float conversions are part of the numerical boundary |
| Normalization/output | Caller requests Q/K L2 normalization inside GDN; core output `[B,T,Hv,Dv]` is reshaped for gated norm with `z`, then output projection |
| Conv history | Ordinary retained history `[B,C,W]` belongs to layer cache and is mutated/copied during updates; it is neither attention KV nor the recurrent matrix |
| Recurrent matrix | Local PyTorch GDN uses `[B,Hv,Dk,Dv]`, starts from zero when initial state is absent and returns `None` when final state is not requested |
| Accumulation | Both local GDN bodies perform the main recurrence in FP32 and return core output in query dtype; external FLA/Hub numerical bodies are not audited here |
| Cache dtype difference | 5.10.2 initializes recurrent storage using conv-derived cache dtype/device; 5.17.0 uses `zeros_like(recurrent_states)` |
| Normalization-order difference | 5.10.2 applies optional Q/K normalization before its FP32 conversion; 5.17.0 converts to FP32 first. Similar signatures do not establish release-to-release parity |

HF's inspected call uses dense batch rows, with no vLLM cache-row IDs or
packed/speculative state-index matrix. Local recurrent orientation differs
from the [vLLM contract](vllm-gdn-causal-conv-contract.md)'s per-row
`[value_heads_per_rank,Dv,Dk]`. Reuse needs an explicit shape, row, dtype
and mutation adapter plus separate numerical/state checks. [M10, M17, C10, C17]

HF chunk calls supply q-side cumulative lengths as `cu_seqlens`; 5.10.2 conv
separately supplies `seq_idx`. Retained local fallback bodies do not consume
those packed boundaries. Neither `**kwargs` nor a shared name establishes
packed support; qualify the resolved implementation and effective kwargs.
5.17.0's padding helper masks the local continuation segment; 5.10.2's text
helper drops the mask once previous state exists. Arbitrary padded/packed
continuation equivalence is not established. [M10, M17, T10, P17, H17]

Cache `reset()` zeroes initialized conv/recurrent tensors and clears the
prior-state flag; `reorder_cache()` selects the same batch indices for both.
Zeroing preserves allocation, while reorder can replace tensor objects.
Request ownership, concurrent isolation, release and engine paging remain
outside this readset. 5.17.0 reports layers with initialized recurrent state
as non-croppable; recording conv history does not prove recurrent rollback.
[C10, C17]

## Bound a classification-prefill adaptation

A cache-free full-prompt classifier can use the first phase row only after
proving the actual layer receives `cache_params=None`. Require one admitted
sequence when the adapter only accepts one, no initial recurrent state, no
requested final state, original padding/packing semantics and the same
normalization/gate/output contract. Such an adapter can exclude decode and
continuation, but must reject those calls. This is a conditional transfer
rule, not a measured worker result.

Bounded caller context: Clef at
`504b272c46dc1963f981c6bed9ef0c7ebdd40c69` selects its module chunk before
loading the model, and its wrapper rejects initial/final recurrent state.
PPLX at `509bdd2161ca5bef8f5e158d466514862fac7c9e` installs its binding
before construction and can subsequently install a GVA forward override
on loaded layers. That override makes stock HF forward insufficient to
describe its active path. These sources locate the seam; checkpoint-owned
executable modules, dependency bodies, native dispatch, model fidelity and
performance are outside this audit. [W-Clef, W-Clef-Load, W-PPLX]

Before acceptance, resolve actual layer method and conv/GDN callables
separately, account for import/construction and overrides, then validate
output and state on the intended phase. Source compatibility, build/import
success, executed operator, numerical parity, full model outputs and matched
performance comparisons are separate evidence. No target GPU is qualified.

## Source map and rights

The ledger hashes complete files; inspected spans bound the claims. Generated
modeling files are the imported runtime modules. Modular authoring sources,
external FLA/Dao/Hub bodies, weights, checkpoint code and native tests are
excluded. Existing Dao/vLLM readsets preserve their own scopes and dates.

Transformers root LICENSE is Apache-2.0, copyright 2018- the Hugging Face
team. Modeling headers credit the Qwen Team and HuggingFace Inc. in 2025;
Hub integration credits the HuggingFace Team. This reference paraphrases
mechanisms and links immutable source, without copying implementation.
HF's license does not grant model, worker-checkpoint or dependency rights.

[M10]: https://github.com/huggingface/transformers/blob/0dad7b822255a0ae261ec45ae937371e859ffd1a/src/transformers/models/qwen3_5/modeling_qwen3_5.py#L66-L556
[M17]: https://github.com/huggingface/transformers/blob/856157a2f3e9594954310df18fdccc31ffddebe9/src/transformers/models/qwen3_5/modeling_qwen3_5.py#L237-L668
[D10]: https://github.com/huggingface/transformers/blob/0dad7b822255a0ae261ec45ae937371e859ffd1a/src/transformers/models/qwen3_5/modeling_qwen3_5.py#L757-L800
[D17]: https://github.com/huggingface/transformers/blob/856157a2f3e9594954310df18fdccc31ffddebe9/src/transformers/models/qwen3_5/modeling_qwen3_5.py#L861-L905
[T10]: https://github.com/huggingface/transformers/blob/0dad7b822255a0ae261ec45ae937371e859ffd1a/src/transformers/models/qwen3_5/modeling_qwen3_5.py#L1156-L1235
[T17]: https://github.com/huggingface/transformers/blob/856157a2f3e9594954310df18fdccc31ffddebe9/src/transformers/models/qwen3_5/modeling_qwen3_5.py#L1239-L1314
[C10]: https://github.com/huggingface/transformers/blob/0dad7b822255a0ae261ec45ae937371e859ffd1a/src/transformers/cache_utils.py#L702-L837
[C17]: https://github.com/huggingface/transformers/blob/856157a2f3e9594954310df18fdccc31ffddebe9/src/transformers/cache_utils.py#L893-L1105
[I10]: https://github.com/huggingface/transformers/blob/0dad7b822255a0ae261ec45ae937371e859ffd1a/src/transformers/utils/import_utils.py#L836-L844
[H17]: https://github.com/huggingface/transformers/blob/856157a2f3e9594954310df18fdccc31ffddebe9/src/transformers/integrations/hub_kernels.py#L62-L890
[P17]: https://github.com/huggingface/transformers/blob/856157a2f3e9594954310df18fdccc31ffddebe9/src/transformers/masking_utils.py#L1469-L1504
[Q10]: https://github.com/huggingface/transformers/blob/0dad7b822255a0ae261ec45ae937371e859ffd1a/src/transformers/models/qwen3_5/configuration_qwen3_5.py#L71-L112
[Q17]: https://github.com/huggingface/transformers/blob/856157a2f3e9594954310df18fdccc31ffddebe9/src/transformers/models/qwen3_5/configuration_qwen3_5.py#L77-L122
[W-Clef]: https://github.com/InferMatrixLab/system1-omni/blob/504b272c46dc1963f981c6bed9ef0c7ebdd40c69/src/models/clef/engine.py#L306-L395
[W-Clef-Load]: https://github.com/InferMatrixLab/system1-omni/blob/504b272c46dc1963f981c6bed9ef0c7ebdd40c69/src/models/clef/engine.py#L548-L556
[W-PPLX]: https://github.com/InferMatrixLab/system1-omni/blob/509bdd2161ca5bef8f5e158d466514862fac7c9e/src/models/pplx_decider/engine.py#L257-L287
