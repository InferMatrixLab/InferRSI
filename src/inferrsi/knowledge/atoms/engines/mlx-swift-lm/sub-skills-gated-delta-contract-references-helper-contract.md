# GDN declaration screener

[audit_gated_delta_declarations.py](../scripts/audit_gated_delta_declarations.py)
is an MIT-attributed, standard-library adaptation of selected
[public gate/state facts](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/GatedDelta.swift#L340-L383)
and [caller geometry](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLLM/Models/Qwen35.swift#L209-L223).
It is newly authored support, not an upstream API, recurrence implementation,
runtime selector or actual shape validator. Its checks are deliberately
**narrower caller declarations**, not invented source guards.

Run `--example` to print complete synthetic input; give a regular JSON file or
`-`/stdin to screen it. No model, MLX package, compiler or device is used, and no
files are written. Input is limited to 64 KiB; duplicate/unknown/missing keys,
nonfinite JSON, invalid types, deep malformed JSON and unsupported domains exit
`2` with a fixed diagnostic. A regular-file precheck rejects known directories,
devices and FIFOs; it is not an atomic filesystem security guarantee.

All these keys are mandatory:

| Field | Helper declaration domain |
| --- | --- |
| `schema_version` | Integer `1`, not boolean |
| `q_shape`, `k_shape` | Equal positive rank-4 `[B,T,Hk,Dk]` |
| `v_shape` | Positive rank-4 `[B,T,Hv,Dv]`; B/T match Q, Hv divisible by Hk |
| `a_shape`, `b_shape` | Each `[B,T,Hv]` |
| `a_log_shape`, `dt_bias_shape` | Each `[Hv]` |
| `input_dtype` | Common declared Q/K/V floating dtype: `float16`, `bfloat16` or `float32`; actual tensors are not inspected |
| `state` | `null`, or exactly `{"shape":[B,Hv,Dv,Dk],"dtype":"float32"}` with dtype also allowing the two lower-precision helper types |
| `mask_shape` | `null` or exactly `[B,T]`; intentionally not all mask forms the ops code can broadcast |
| `use_kernel`, `training` | Booleans; training is caller context, not a parameter of the source public function |
| `unmasked_kernel_availability`, `masked_kernel_availability` | Independently `available`, `unavailable` or `unknown`; declarations only |

Shape entries and derived payload products must fit positive signed-64-bit
arithmetic in this helper. Booleans are not dimensions. This bound and the
accepted dtype/mask domain are support limits, not native kernel maxima. The
source's literal Dk predicate is divisibility by 32, not power-of-two sizing.

API: `audit(plan) -> dict`; malformed declarations raise `ValueError`.
`example() -> dict` returns a fresh synthetic input. CLI exit `0` means only
that the declared schema/relationships were screened; a false/unknown gate or
declared masked fatal branch can still be reported on exit zero. Nothing is
executed or repaired. Read the JSON result, not just the process status.

Important outputs:

- `literal_public_gate`: `false`, `true` or `undetermined`, using only the
  source predicate and declared unmasked availability.
- `declared_branch`: ops fallback, candidate kernel, unresolved availability,
  or selected-masked-nil fatal branch **by declarations**, never actual routing.
- `key_dimension_tail_mod32`: the tail that makes the public gate use ops.
- `expected_carried_state_shape`, `effective_carried_state_dtype` and
  `state_conversion`: FP32 default/retention/upcast.
- `one_carried_state_payload_bytes`: `B*Hv*Dv*Dk*4`; one tensor, not allocator
  footprint, checkpoint total, peak process memory or model fit. It explicitly
  excludes convolution state, checkpoint tensors, offset/padding/length metadata,
  other caches, copies and actual memory pressure; `state_payload_scope` retains
  that boundary in the result.
- `one_output_payload_bytes`: declared Y payload using the common input dtype;
  it excludes copies, lazy intermediates and allocator rounding.
- `training_caller_warning`: expected caller policy when training still sets
  `use_kernel=true`; no differentiation is attempted.
- `masked_output_parity`: flags the unexecuted source asymmetry when a mask is
  declared; no output values or attention/recurrent transitions are simulated.

Every result retains native/compiler `not_run`, actual dispatch/numerical/
stride-provider/physical-fit `not_verified`. Actual availability, tensor dtypes,
values, strides, packing, aliasing and gradient behavior need native evidence.
Do not enter private prompts, model paths, hostnames or credentials: the schema
needs only abstract geometry, flags and availability declarations.
