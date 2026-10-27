# Causal convolution decision cases

These five operational examples apply the pinned
[forward/update contract](../references/causal-conv1d-contract.md).
They specify expected decisions and evidence requests, not executed tests or
benchmark results. All dimensions are illustrative. The owner remains a
source-derived candidate with native execution and efficacy unevaluated.

## 1. Stateless sequence versus persistent update

**Situation.** A classifier supplies `x=(2, 16, 128)` and weight `(16, 4)`.
It has no continuation history. A serving integration exposes an update
function and asks to use it because the model family also supports decoding.

**Decision.** Qualify `causal_conv1d_fn` for the stateless full sequence, then
check its dtype/layout/activation. Do not create a persistent cache merely to
fit the update API. For a separate continuation caller that already owns a
writable convolution state, qualify update; a two-dimensional input is expanded
to one token, while a three-dimensional update may contain multiple tokens.
An explicit chunk caller may instead pass forward's initial/final history.

**Required observations.** Identify the concrete caller and whether it supplies
history, requests final history or mutates persistent state. A model-family
name and sequence length do not establish that choice. Keep output and state
semantics in the later numerical comparison.

**Stop/recovery.** If the caller is unknown, retain both possible APIs as
unresolved and request its source. Do not report the serving binding as
qualified from this operator's interface alone.

Source: contract [API choice](../references/causal-conv1d-contract.md#choose-the-api-by-state-ownership),
ledger A/B.

## 2. Logical shape matches but forward layout fails

**Situation.** Forward input has logical shape `(2, 10, 11)`, channel-last
strides `(110, 1, 10)`, BF16 input, FP32 weight `(10, 4)` and FP32 bias.
A proposed substitution checks only shape and supported dtype names.

**Decision.** The mixed input/weight dtypes are allowed by the compiled entry,
and bias follows weight dtype. The selected channel-last forward path still
fails its channel/stride divisibility-by-8 requirements. The wrapper does not
automatically copy this input because channel stride is already 1. Shape and
dtype checks are insufficient.

**Required observations.** Capture the real input strides and selected
forward layout. If the caller can use a sequence-contiguous representation,
qualify that explicit change and its copy cost independently. Initial/final
history and packed IDs still need the channel-last forward path. Update has
different layout gates and is not a drop-in escape from forward's state
semantics. A BF16 update input also requires BF16 `conv_state`, even if its
weight is FP32.

**Stop/recovery.** Reject the current call contract before benchmarking.
Do not silently select another API or claim a layout conversion is free.

Source: contract [dtype/layout](../references/causal-conv1d-contract.md#check-common-values-and-forward-layout),
ledger A/B/C/E.

## 3. Packed inputs with history and a requested final state

**Situation.** A valid channel-last forward input uses `D=16`, `W=4` and
`seq_idx=[0, 0, 1, 1, -1]` in a batch row. The caller supplies initial history
and requests `return_final_states=True`.

**Decision.** `seq_idx` with initial history is permitted when the complete
dtype/device/shape/stride contract holds. The history applies to the first
sequence ID; the ID transition masks history from the earlier sequence, and
the negative current ID produces zero output. The requested final-state
combination is rejected by the public wrapper.

**Required observations.** Verify CUDA int32 contiguous `(B, L)` IDs and
input-dtype CUDA history `(B, D, W - 1)` with channel stride 1. Preserve the
sequence boundary even when two adjacent sequences share a batch row.
Establish a separate supported final-state extraction path if that output is
required; this readset does not qualify the varlen extractor implementation.

**Stop/recovery.** Do not ban all initial history with packed IDs. Do not drop
the requested final-state behavior to make the call run. Split or redesign the
caller only after its state-output contract is established.

Source: contract [packed boundaries](../references/causal-conv1d-contract.md#preserve-packed-boundaries-and-forward-history),
ledger A/C/D/G. The tests supply assertion intent, not a local parity result.

## 4. Gathered request rows and a circular cursor

**Situation.** Update has `B=3`, `D=16`, `L=2`, `W=4`, state `(8, 16, 7)`,
`conv_state_indices=[5, -1, 1]` and `cache_seqlens=[13, 0, 6]`. Indices and
cursors meet the CUDA int32 `(B,)` stride contract.

**Decision.** Input row 0 updates state row 5; input row 2 updates state row 1.
The negative selection for input row 1 produces zero output and leaves state
rows untouched for that input. Cursor values belong to input batch positions,
not to the allocated-state row numbers. For row 0, history positions are
3, 4, 5 and new values go to positions 6, 0 in the seven-slot ring.

**Required observations.** Compare output and the complete state tensor,
including unselected rows. Verify the caller preserves valid row ownership,
nonnegative logical cursors and completion ordering. The operator does not
advance the cursor: after two accepted tokens, the caller must account for a
logical position of 15 for row 0. Reusing 13 would select the old write start.
If a row is reassigned, initialize or restore that request's history/cursor
under the actual caller's lifecycle contract.

**Stop/recovery.** Do not infer bounds/uniqueness checking from the index
shape check, or safety for concurrent writers to the same state row. Resolve
the caller's row/cursor ownership before issuing those calls. The upstream
padding test exercises the non-circular case; the circular padding branch
above is an implementation reading, not a reproduced test result.

Source: contract [state rows/cursors](../references/causal-conv1d-contract.md#keep-update-rows-and-cursors-attached-to-the-caller),
ledger A/B/C/E/G. Implementation and tests resolve the reversed "If None"
phrase in the update docstring.

## 5. sm_89 build advice does not establish readiness

**Situation.** A worker is labeled sm_89. A proposed readiness check treats
package import and an architecture environment variable as proof that causal
convolution uses the compiled operator, and treats an `F.conv1d` call as this
package's automatic fallback.

**Decision.** The pinned build list has no explicit sm_89 entry. That fact
does not establish runtime incompatibility, nor does the variable prove an
sm_89 cubin was emitted. A downloaded wheel may have different contents from
the local source-build expectation. The binding directly calls
`causal_conv1d_cuda`; the named reference function is not its automatic
fallback. A downstream worker's fallback policy remains a separate question.

**Required observations.** Resolve actual hardware and stack identity, the
installed extension artifact and its architecture contents, the caller's bound
forward/update function and an observation of the selected operator. A
readiness policy that fails on downstream `F.conv1d` dispatch needs that
integration's source and a concrete failure-path check. Follow with numerical
and state checks before any latency comparison.

**Stop/recovery.** Report readiness unresolved when those observations are
missing. Do not install, compile or run an upstream example as a side effect
of reading this case. Keep source compatibility, observed dispatch, numerical
qualification and service latency as separate conclusions.

Source: contract [build/binding/readiness](../references/causal-conv1d-contract.md#separate-build-targets-bound-operator-and-readiness),
ledger A/B/F. No hardware or service result is asserted.
