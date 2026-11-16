# Causal convolution forward and update contract

Status: source-derived candidate. Use this reference to qualify one causal
depthwise-convolution caller before substituting an operator or writing a kernel.
The source is [Dao-AILab/causal-conv1d](https://github.com/Dao-AILab/causal-conv1d)
at `cd81f0413cad2fc1e6f17e785ac39f59aae690cd`, package version 1.7.0,
BSD-3-Clause. Source inspection establishes the contracts below; native
correctness, binary compatibility, serving integration and performance remain
`not_run`.

## Choose the API by state ownership

Record the caller's input shape, dtype, strides, activation, packed-sequence
boundaries and continuation-state ownership. Use the same observations when
comparing a proposed replacement. Let `B` be call batch size, `D` channels, `L`
input sequence length, `W` convolution width, `S` update-state length and `N`
allocated state rows.

| API | Input and output | State behavior | Decision |
|---|---|---|---|
| `causal_conv1d_fn` | `x` and output `(B, D, L)` | Optional `initial_states`; optional returned or caller-provided final-state output | Use for a full sequence or a chunk whose history is supplied explicitly |
| `causal_conv1d_update` | `(B, D)` or `(B, D, L)`; output retains that logical shape | Mutates `conv_state` in place; can gather state rows and use a circular cursor | Use when the caller owns persistent writable convolution state |

The update wrapper adds and removes a sequence axis for a two-dimensional
input; update also accepts multiple input tokens. Sequence length alone does
not select the API. A stateless classification request does not acquire a
decode cache merely because a serving engine has an update operator. Trace
the actual model caller before choosing either API. [A, B]

The reference functions express depthwise convolution with one weight row per
channel, causal history and optional SiLU activation. They return the input
dtype. Their presence supplies an oracle to qualify later; it does not prove
bitwise identity or any particular tolerance on a device. [A]

## Check common values and forward layout

| Item | Compiled forward/update contract | Wrapper distinction |
|---|---|---|
| Input and weight | CUDA tensors; each independently FP32, FP16 or BF16; weight `(D, W)`; `W` is 2, 3 or 4 | Do not invent a same-dtype requirement between input and weight |
| Bias | Optional CUDA `(D,)`, weight dtype, last stride 1 | Forward makes bias contiguous; update passes it through |
| Activation | `None`, `"silu"` or `"swish"` | Both nonempty names select the SiLU branch; other names raise `NotImplementedError` |
| Output | Same logical shape and dtype as input | Binding helpers allocate `empty_like(x)` |

For compiled **forward**, input must have `x.stride(2) == 1` or
`x.stride(1) == 1`. The C++ entry selects channel-last precisely when
`x.stride(1) == 1 and x.stride(2) > 1`. That path additionally requires
`D % 8 == 0`, `x.stride(0) % 8 == 0` and `x.stride(2) % 8 == 0`.
The public wrapper copies `x` to contiguous storage if neither accepted axis
has stride 1. Account for that copy separately when interpreting a profile;
logical shape alone does not establish the compiled layout. [A, B, C]

The update entry passes input and state strides to its kernel and does not
apply forward's channel-last/divisibility gates. Do not transfer those gates
to update or use update's layout behavior to qualify forward. [C, E]

## Preserve packed boundaries and forward history

Forward's `seq_idx` is CUDA int32 with shape `(B, L)`, contiguous at the
compiled boundary and supported only on the channel-last path. The public
wrapper makes it contiguous. For each output, the selected forward kernel
uses history only where the sequence IDs match that output's ID. A negative
current sequence ID denotes padding and produces zero output. Distinct packed
sequences must retain their boundaries when batching or reshaping. [A, C, D]

`initial_states` and `final_states_out` each have shape `(B, D, W - 1)`,
input dtype, CUDA placement and channel stride 1. The C++ entry requires the
channel-last forward path for either state. The wrapper allocates a suitable
final-state tensor when `return_final_states=True` and none was supplied;
otherwise it discards the final-state output argument. Supplying an arbitrary
contiguous history tensor does not establish the required channel stride. [A, C]

The public forward rejects `seq_idx` together with
`return_final_states=True`. It **permits `seq_idx` with `initial_states`**:
the initial history is associated with the first sequence ID in each batch
row, while subsequent sequence boundaries still mask older contributions.
This combination is present in the reference and selected tests. Do not
invent a blanket ban on packed inputs with initial history. To obtain packed
final states, establish a separately supported extraction/caller path; the
varlen state-extraction implementation is outside this readset. [A, C, D, G]

## Keep update rows and cursors attached to the caller

`conv_state` is a writable CUDA tensor in input dtype, with `S >= W - 1`.
Without `conv_state_indices`, its shape is `(B, D, S)`. With indices, its
shape is `(N, D, S)` and each input row selects one of those state rows.
`conv_state_indices` must be CUDA int32, shape `(B,)`, stride 1. The kernel
uses `conv_state_indices[b]` when present and row `b` otherwise. The interface
docstring's phrase "If None" for selecting a larger state tensor is reversed;
the C++ branch, kernel and batch-gather test establish selection **when indices
are supplied**. [A, C, E, G]

A negative selected row produces zero output and returns before accessing or
mutating a state row. This is update padding, distinct from forward's negative
`seq_idx`. The shown C++ entry checks index shape/dtype, but does not check
positive index bounds or uniqueness. Address arithmetic therefore requires
caller-proven valid nonnegative row selections for active requests. The
readset establishes no safety for concurrent writes to the same row. Preserve
request-to-row ownership and completion ordering at the caller. [C, E]

| Cursor | State interpretation | Caller responsibility |
|---|---|---|
| `cache_seqlens=None` | Non-circular history: retain the latest `S` values from previous history plus input | Preserve chronological state and the correct request row |
| CUDA int32 `(B,)`, stride 1 | Circular history: read the preceding `W - 1` values and write input starting at `cache_seqlens[b] % S`, wrapping at `S` | Supply the cursor for input row `b`, even when state rows are gathered; maintain logical cursor advancement outside the operator |

The kernel reads `cache_seqlens` and mutates `conv_state`; it does not advance
the supplied cursor. Its modulo/address arithmetic requires caller-proven
nonnegative logical sequence lengths; the C++ entry does not check cursor
values. This is a source-based caller obligation, not a new runtime guard.
Reusing a stale cursor can overwrite a different part of the ring. A request
reassignment needs the correct history and cursor, not just an available row.
The binding declares `out` and `conv_state` as mutated, excluding the cursor.
[B, C, E]

For example, with `W=4`, `S=7`, a cursor of 13 reads history positions
3, 4 and 5, then a two-token update writes positions 6 and 0. Advancing the
logical cursor to 15 is a separate caller action. This arithmetic example
illustrates the source contract; it is not an executed kernel trace.

## Separate build targets, bound operator and readiness

`cpp_functions.py` directly imports `causal_conv1d_cuda`. Its registered
`DaoAILab` custom operations call the compiled extension. The public
`causal_conv1d_ref` and `causal_conv1d_update_ref` are explicit reference
functions; this path does not automatically switch to them when the compiled
extension is unavailable. A downstream model may have its own import/fallback
policy, which requires that model's source and actual binding evidence. [A, B]

In `setup.py`'s CUDA build branch, the explicit `-gencode` list contains
sm_75, sm_80 and sm_87; CUDA toolkit 11.8 or later adds sm_90, 12.8 or later
adds sm_100/sm_120, and 13.0 or later adds sm_103/sm_110/sm_121. The
toolkit check rejects versions below 11.6 when `CUDA_HOME` is present.
There is no explicit sm_89 entry in this list. This source fact neither
certifies nor rules out execution on an sm_89 device: binary contents and
runtime compatibility are separate evidence. An environment-variable recipe
alone does not prove that this build emits an sm_89 cubin. [F]

The wheel command can retrieve a prebuilt wheel before falling back to a
source build; `CAUSAL_CONV1D_FORCE_BUILD=TRUE` bypasses that retrieval path.
Neither local build flags nor an import identify the contents of a separately
downloaded binary. `CAUSAL_CONV1D_SKIP_CUDA_BUILD` is a packaging switch, not
proof of a runnable operator. [F]

Before a later native qualification, retain these distinct observations:

1. Identify the actual device and compute capability, package/extension
   artifact, PyTorch/CUDA stack and ABI. Resolve conflicting hardware labels
   before comparing results.
2. Identify the caller's bound forward/update function, its contract and any
   fallback branch. Import success establishes only that the import completed.
3. Inspect the installed binary's architecture contents and observe the
   operator selected for the concrete workload. A build target list does not
   prove dispatch.
4. Compare output and mutated state against an appropriate independent
   reference under a frozen numerical protocol. Include packed boundaries,
   padding, gathered rows and wraparound only where the caller uses them.
5. Apply the caller's explicit readiness policy, then measure the intended
   boundary after correctness. A policy requiring readiness failure on a
   downstream `F.conv1d` fallback belongs to that integration; it is not
   implemented by this source contract.

These observations define a later verification path. No installation recipe,
automatic dispatch code, CUDA graph contract, model-specific fallback policy,
classification latency or service improvement is qualified here. Use the
[five operational cases](../cases/causal-conv1d-dispatch-state.md) to check the
decision before requesting that evidence.

## Source ledger

The ten retained files total 119,136 bytes. Their exact bytes were matched to
the pinned Git tree using Git blob SHA-1 identities; retention does not mean
every body was extracted. All links use the same full source revision.

| Key | Pinned path / inspected lines | Extracted boundary |
|---|---|---|
| A | [Interface, 10–66](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/causal_conv1d/causal_conv1d_interface.py#L10-L66), [102–261](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/causal_conv1d/causal_conv1d_interface.py#L102-L261) | Public forward/update wrappers and reference semantics; backward body excluded |
| B | [Bindings, 1–31](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/causal_conv1d/cpp_functions.py#L1-L31), [71–114](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/causal_conv1d/cpp_functions.py#L71-L114), [163–183](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/causal_conv1d/cpp_functions.py#L163-L183) | Direct compiled-extension calls, output allocation and mutation declarations |
| C | [C++ entry, 77–115](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/csrc/causal_conv1d.cpp#L77-L115), [150–258](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/csrc/causal_conv1d.cpp#L150-L258), [465–562](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/csrc/causal_conv1d.cpp#L465-L562) | Dtype/shape/layout/state/index/cursor gates and dispatch; backward excluded |
| D | [Forward kernel, 235–359](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/csrc/causal_conv1d_fwd.cu#L235-L359) | Selected initial-history, sequence-ID masking, padding and channel-last launch branches; full instruction/performance audit excluded |
| E | [Update kernel, 23–146](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/csrc/causal_conv1d_update.cu#L23-L146) | Row selection, padding early return, circular/non-circular state update and width specialization |
| F | [Build, 41–44](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/setup.py#L41-L44), [137–204](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/setup.py#L137-L204), [315–347](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/setup.py#L315-L347) | CUDA toolkit/architecture gates, build switches and wheel/source branch; setup not executed; ROCm qualification excluded |
| G | [Tests, 71–137](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/tests/test_causal_conv1d.py#L71-L137), [154–321](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/tests/test_causal_conv1d.py#L154-L321), [416–623](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/tests/test_causal_conv1d.py#L416-L623), [642–713](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/tests/test_causal_conv1d.py#L642-L713) | Forward/history, update/gather/padding and packed-sequence assertion intent; tests not run |
| Context | [README](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/README.md), [package version](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/causal_conv1d/__init__.py), [license](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/LICENSE) | Published intent, version and retained notice |

### Exact retained file identities

| Source path | Bytes | Git blob SHA-1 |
|---|---:|---|
| `LICENSE` | 1558 | `5860e4b33f3d9d85fc636137c559331d51783a5b` |
| `README.md` | 1086 | `1c1691f6f1e228bdbccd65fc4b1bf147bcf158f4` |
| `causal_conv1d/__init__.py` | 112 | `9a251332aa5be96e55884fc54e119bc6e9aa109b` |
| `causal_conv1d/causal_conv1d_interface.py` | 9810 | `0e7b0299ac6b320a9343c20e427ecc7d2d3826c0` |
| `causal_conv1d/cpp_functions.py` | 4609 | `af27abe87c459b76fbb99a338299148fa3a99d83` |
| `csrc/causal_conv1d.cpp` | 24830 | `02d9d85d957e2fe609c5c4b7517222ae2c496bca` |
| `csrc/causal_conv1d_fwd.cu` | 21923 | `95e34bbdfd330a58d4e161657622b680255a3b43` |
| `csrc/causal_conv1d_update.cu` | 7188 | `ccbf296a36b2794e37f830a911eb2aecb52f5a64` |
| `setup.py` | 13958 | `0bcdd8153f87461bd2051cb25c4a8db516e5e05b` |
| `tests/test_causal_conv1d.py` | 34062 | `7eb54c14a23f2313f32df394b42d9fcd6883bbc9` |

Uncovered: backward CUDA implementation, full variable-length state extraction,
ROCm execution, CUDA compilation/import/kernel tests, binary architecture
compatibility, graph capture, request scheduling and cursor advancement in a
real caller, Transformers/vLLM/SGLang/FLA/FlashInfer integration, numerical and
quality acceptance, performance and agent efficacy. The source-derived addition
preserves the owner's candidate state and `empirical_validation=not_run`.

## Upstream BSD notice

The guidance paraphrases the inspected source; no upstream implementation is
vendored. The source files credit Tri Dao. The complete pinned license notice is
retained below.

```text
BSD 3-Clause License

Copyright (c) 2022, the respective contributors, as shown by the AUTHORS file.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
