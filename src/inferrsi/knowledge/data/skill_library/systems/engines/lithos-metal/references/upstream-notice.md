# Third-party provenance

Monolith is a standalone codebase (design D15). Code copied or adapted from other projects keeps its original license
header and carries a one-line provenance comment naming the source repository, path and commit. This file is the
registry of every such file or fragment. Add an entry in the same change that copies the code.

Format: `<path in this repo>` — adapted from / copied from `<repo>` `<path>` @ `<commit>` (`<license>`); what was taken.

## MPK / mirage (lithos-ai/mirage, branch `low_latency`, Apache-2.0)

- `monolith/registry.py` — adapted from `python/mirage/mpk/models/_registry.py` @ 5beaed8 (Apache-2.0): the
  duplicate-refusing decorator registry pattern (`register_model`), generalized to every registry kind.
- `monolith/nn/module.py` — adapted from `python/mirage/mpk/layers_v2/_base.py` @ 5beaed8 (Apache-2.0): the
  three-method module contract (oracle / lower / weights) and the streaming `load_weights` routing idea; the
  compile/grid methods, which are CUDA-specific, were not taken.

- `monolith/packs/transforms.py` — `rope_head_perm` adapted from `python/mirage/mpk/models/qwen38/modeling.py` @ 5beaed8
  (Apache-2.0): the head-dim permutation that implements partial RoPE as a load-time row permutation.
- `monolith/nn/rope.py` — `rope_tables_permuted` adapted from `python/mirage/mpk/models/qwen38/modeling.py`
  `build_rope_tables` @ 5beaed8 (Apache-2.0): the cos/sin tables in the permuted head layout.
- `monolith/models/qwen3_5/config.py` — adapted from `python/mirage/mpk/models/qwen38/configuration.py` @ 5beaed8
  (Apache-2.0): the field-for-field text-config mirror.
- `monolith/models/qwen3_5/model.py`, `monolith/models/qwen3_5/weights.py` — adapted from
  `python/mirage/mpk/models/qwen38/modeling.py` @ 5beaed8 (Apache-2.0): the layer structure, the stacked projection
  layouts (`[q | gate | k | v]`, `[qkv | z | a | b]`) and the checkpoint key routing; tensor parallelism dropped.
- `monolith/models/qwen3_5_moe/config.py`, `monolith/models/qwen3_5_moe/model.py` — extend the above
  hybrid config and model composition with the existing sparse/shared-expert library; retain the same provenance.
- `tools/goldens/hf_golden.py` — adapted from `tests/runtime_python/models/qwen38/hf_golden.py` @ 5beaed8
  (Apache-2.0): the golden recipe (BF16, eager attention, hidden states + greedy tokens), extended with
  teacher-forced top-k logits and a torch-free output format.

## transformers (huggingface/transformers 5.17, Apache-2.0)

* `monolith/nn/rope.py::scaled_inv_freq`: NumPy implementation of the YaRN
  equations and amplitude scaling in `src/transformers/modeling_rope_utils.py::_compute_yarn_parameters`.

- `monolith/nn/oracle.py`, `monolith/nn/attention.py`, `monolith/nn/gdn.py` — the layer oracles reproduce the
  semantics and rounding order of `src/transformers/models/qwen3_5/modeling_qwen3_5.py` (`Qwen3_5RMSNorm`,
  `Qwen3_5RMSNormGated`, `torch_recurrent_gated_delta_rule`, `Qwen3_5GatedDeltaNet`, `Qwen3_5Attention`,
  `apply_rotary_pos_emb`); written against that file, no code copied verbatim.

- `monolith/models/llama/rope.py` — the frequency-dependent Llama 3 scaling rule
  follows `src/transformers/modeling_rope_utils.py::_compute_llama3_parameters`
  @ `v5.17.0` (Apache-2.0), implemented with NumPy for the standalone packer and
  checked against the installed HF reference. The model package composes the
  existing layer library; its checkpoint convention is `LlamaForCausalLM`.

## MLX (ml-explore/mlx, MIT)

- `kernels/common/gemv_bf16_small.metal` — adapted from `mlx/backend/metal/kernels/gemv.h`
  @ `1f8e74e3f12f31365464a6867c6579f0e9b29d85` (MIT): GemvWide's four-vector prefetch/reuse
  and row reduction, extended for MPK's packed weights, permuted activations, row ranges,
  residual/statistic and SiLU/multiply epilogues. License: `third_party/MLX-LICENSE`.

- `monolith/formats/nvfp4.py` — `NVFP4_DECODE = 3` in the MSL snippet adapted from `mlx/backend/metal/kernels/fp4.h`
  (v0.32, MIT): the E2M1 nibble decoded by placing its three magnitude bits into a half's exponent field
  (`as_type<half>(ushort((bits & 7) << 9))`, the sign a select) with the 2^14 folded into the block scale; the
  quantized-checkpoint reader also follows MLX's `nvfp4` layout (codes eight per U32, E4M3 scales as U8), no code
  copied for that.
  The E4M3 block-scale conversion also adapts `mlx/backend/metal/kernels/fp8.h`
  @ `1f8e74e3f12f31365464a6867c6579f0e9b29d85`: construct a half from the magnitude
  bits and apply the exact exponent-bias correction in float, including subnormals.
  License: `third_party/MLX-LICENSE`.

- `kernels/common/gemv_nvfp4_rows.metal` — adapted from `mlx/backend/metal/kernels/fp_quantized.h`
  @ `1f8e74e3f12f31365464a6867c6579f0e9b29d85` (MIT): quantization-group dot products
  reusing four activation vectors across output rows, extended for MPK's packed
  weights, permuted activations, row ranges and epilogues. License: `third_party/MLX-LICENSE`.

- `kernels/common/gemv_bf16_rows.metal` — adapted from `mlx/backend/metal/kernels/gemv.h`
  @ `1f8e74e3f12f31365464a6867c6579f0e9b29d85` (MIT): activation-vector reuse across
  output rows, extended for packed BF16 weights, fused normalization and epilogues.
  License: `third_party/MLX-LICENSE`.

## Original

- `probes/` — original to this repository.

- `monolith/compiler/moe_fusion.py`, `monolith/compiler/moe_ready.py`, `monolith/compiler/moe_down.py`,
  `kernels/common/moe_group.metal` — independent
  Metal implementations informed by Mirage PR #786's expert task grouping and
  separation of task decomposition from worker placement. Reference:
  `mirage-project/mirage`, `include/mirage/static_megakernel/expert_queue.cuh`
  and `python/mirage/mpk/moe.py` at
  `c28cac618b98fda1e0f1d590923b5f69b4ef3603` (Apache-2.0).
  No CUDA source copied; no Mirage dependency.

## DeepSpec (deepseek-ai/DeepSpec, MIT)

- `monolith/spec/dspark/model.py`, `tests/spec/test_dspark_oracle.py` — the DSpark drafter's semantics (feature
  projection, KV injection, bidirectional block attention, the vanilla Markov head, the confidence head, the
  confident-prefix rule) follow `deepspec/modeling/dspark/qwen3/modeling.py`, `deepspec/modeling/dspark/markov_head.py`
  and `deepspec/eval/dspark/draft_ops.py` (MIT); written against them, no code copied; the oracle test imports the
  reference implementation from a local checkout to compare against.
