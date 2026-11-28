# Verification contract

## Evidence and mode identity

The following contracts were distilled from the pinned DwarfStar source named
by the root provenance. Source paths and line ranges below identify inspected
evidence; this reference contains the operational interpretation and does not
require those files to remain available.

### Sampling semantics

| Mode | What it preserves or changes | Appropriate check |
| --- | --- | --- |
| Ordinary target-only | Selected target graph and its sampling policy; no accepted draft block | Frozen reference for the same build/model/backend/configuration |
| Greedy speculation | Proposed tokens are accepted when they agree with the target verifier's argmax | Check accepted-prefix/state consistency and continuation quality; batched arithmetic need not be byte-identical to serial decoding |
| Opportunistic, nonzero temperature | Ordinary boundary tokens are sampled, while matching greedy drafts can be committed directly | Treat as a distinct sampling policy; compare quality and speed, not as proof of the target distribution |
| Exact sampled speculation | Greedy point-mass or sampled proposals use the applicable acceptance/correction rule | Verify filtering and probability correction, then backend state and model behavior; additional random draws defeat simple seeded-identity expectations |

For sampled proposals, the inspected V4.1 implementation builds draft and target
probabilities using the selected temperature/top-k/top-p/min-p filters, accepts
using the target-to-draft ratio and draws a correction from residual mass on
rejection. The point-mass/greedy-proposal path has its own correction. Do not
substitute an argmax comparison for that probability calculation.

Evidence: `docs/SPECULATIVE_DECODING.md:112-137`; `ds4.c:86072-86195`;
`tests/test_sampling.c:279-354`; `QA_BEFORE_RELEASES.md:257-309`.
The histogram test exercises selected synthetic logits; it does not prove the
complete model's distribution, GPU kernels or end-to-end quality. Its embedded
tolerance is that test's contract, not a new reusable campaign gate.

### Model-specific route matrix

| Target | Draft source and selected constraints | Qualification caution |
| --- | --- | --- |
| DeepSeek V4 Flash 0731 or Vision Experimental | Separate, checkpoint-matched DSpark support GGUF; not a standalone model; not interchangeable between checkpoints | The V4 Flash external DSpark route requires a resident target; do not extend this restriction or support to V4.1 by name similarity. PRO is not a DSpark target in the inspected guide. |
| DeepSeek V4.1 Flash | Its own support weights and draft graph; the inspected code maintains a draft-feature window and falls back to ordinary decode when that window is incomplete after restore | Source describes resident and SSD single-host routes. Network-TP DSpark documentation conflicts; retain the unresolved physical-backend qualification gap below. |
| GLM | Built-in MTP block in the main GGUF; selected code caps its cycle and has mode-dependent fallbacks | Exact nonzero-temperature GLM sampling under active network TP falls back to a one-token evaluation in the inspected dispatcher. Do not count the fallback as speculative acceleration. |
| Qwen3.8 Flash Next | Built-in MTP; adaptive second chained draft is separate from fixed-depth diagnostic overrides | Exact sampled behavior is model/backend/serving-mode specific. The server guide describes a Metal batched exception to a broader no-speculation statement in the speculation guide. |

Evidence: `docs/SPECULATIVE_DECODING.md:13-110,139-140`;
`ds4.c:87073-87157`; `docs/SERVER.md:86-95` for the batched Qwen exception.
Do not promote documentation's capacity or speed examples into portable defaults.

### Unresolved V4.1 network-DSpark conflict

`docs/SPECULATIVE_DECODING.md:66-78` describes V4.1 DSpark on two Metal or
CUDA hosts. `docs/DISTRIBUTED.md:89-98,139-144` instead says V4.1 speculation
is unsupported in the described network routes. Inspected implementation contains
a V4.1 worker verification/prefix-commit path (`ds4.c:82967-83022`) and
model-specific speculative dispatcher, not merely a parser flag.

This supports the bounded statement **implementation paths exist**, not a
resolved support/QA guarantee. No physical native run in this extraction clears
the conflict. Before using that tuple, obtain revision-specific support evidence
and run both ranks, exact chosen transport and matched checkpoint with rejection,
partial commit, cancellation and restore coverage. Until then, report the tuple
unverified; do not choose one document as proof that it works or cannot work.

## Accepted-prefix and rewind invariants

1. Before speculative evaluation, session token length, valid checkpoint and
   graph position must agree. An invalid checkpoint is an error, not an empty
   reusable prefix.
2. The verifier may evaluate more rows than it commits. Only the accepted prefix
   may advance visible target state. The V4.1 worker validates commit mode and
   count; failures invalidate its graph/checkpoint.
3. Recent exact rewind can restore a pre-verify frontier and commit a retained
   prefix. It also invalidates draft-capture state and restores the drafter
   window where required. Arbitrary or stale rewinds have a different
   invalidate/rebuild contract; truncating token history is insufficient.
4. A verified block crossing into or out of greedy tool syntax can require
   resampling at the boundary under exact sampling. Preserve the changed
   sampling mode, not the previously drafted suffix.
5. A failed peer verification or transport gate must not leave the local
   session apparently reusable.

Evidence: `ds4.c:82967-82985,86072-86195,87084-87095,87250-87289`;
`ds4_server.c:14236-14265`. These inspected bodies do not constitute execution
evidence for their accelerator paths.

## Topology is part of the algorithm

| Mechanism | Distilled setup/ownership contract | Distinct failure surface |
| --- | --- | --- |
| Local CUDA layer placement | Complete layers placed on selected GPUs; budget includes graph/context headroom | Unsupported CPU spill or insufficient per-device capacity |
| In-process CUDA TP | `--cuda-tensor-parallel` pairs local devices; layer-home devices precede partners; routed experts are split while selected dense work is replicated | Wrong physical pairing, interconnect bottleneck or unsupported grouped shape |
| Network TP | `--tensor-parallel` with complementary coordinator/worker roles; exactly two ranks in the described route | Identity/gate-schedule mismatch, transport timeout, cancellation disagreement or failed prefix commit |
| Pipeline | Complete non-overlapping layer ranges; final range owns the output head; activations pass between stages | Missing route, overlap/gap in coverage, worker disconnect or transport-precision change |

The CUDA network validator rejects combining network TP with SSD streaming or
in-process CUDA TP. Pipeline and network-TP modes are exclusive. Do not infer
that a flag accepted by one backend enables it on another.

Network hello checks include protocol/role, model/layout attributes and gate
schedule. These checks are not cryptographic weight-payload authentication.
Freeze actual model bytes/hashes separately. A successful ping or local socket
exchange does not prove an active RDMA data plane. Keep transport selection
explicit and report the one actually negotiated. The described network
protocols provide neither authentication nor encryption; trusted-network scope
is a precondition, not a feature supplied by the engine.

Evidence: `docs/CUDA_MULTI_GPU.md:24-68`;
`docs/DISTRIBUTED.md:5-32,80-98,100-171,192-205`;
`ds4_tp.c:700-738,2327-2405`.

## Qualification ladder and minimal discriminating checks

| Question | Smallest useful evidence | What it cannot establish |
| --- | --- | --- |
| Are probability filters/correction and selected RNG invariants implemented coherently? | Model-free sampling tests with synthetic logits and rejected/accepted proposals | GPU recurrence, target model quality or exact seeded parity |
| Do command frames reject bad flags, desynchronization, malformed counts and failed acknowledgments? | Model-free socketpair protocol tests; both success and failure cases | Physical TCP/RDMA, peer GPU execution or hardware throughput |
| Does backend rewind restore actual KV/recurrent/indexer state? | Native accelerator fixture with serial control, partial acceptance and continuation after rewind | Complete matched-model quality or concurrent service stability |
| Does the chosen target/drafter/quant tuple behave correctly? | Matched checkpoint vectors and ordinary/opportunistic/exact model continuations under frozen policy | Another model family, backend or transport |
| Is there a useful service gain? | Authorized end-to-end workload with request latency, concurrency, correctness/quality, memory and cleanup | A universal gain or a portable default beyond that RunSpec |

Source native candidate identities are `tests/test_sampling` and
`tests/test_tp_commands`; the inspected Makefile compiles the former with CPU
test hooks and the latter against model-free CPU core objects. Those identities
describe verification provenance, not instructions requiring the original
checkout. Both remain subject to actual execution/result reporting by the
verification owner. Physical backend/model tests remain distinct required
evidence even if these CPU candidates pass.

## Frozen experiment worksheet

Before an authorized run, fill and freeze:

- **Identity:** baseline/candidate revisions and patches; compiler/toolkit/driver;
  backend, devices, peer layout and negotiated transport; target/support payload
  hashes and quantization/layout.
- **Workload:** exact tokenized inputs, image/tool state where applicable,
  prefill/context/output limits, request count/concurrency, sampling/filtering,
  thinking policy, seed/repetition policy, cold/warm/restore controls.
- **Change and gates:** one hypothesis, declared mechanism, numerical or
  distributional equivalence standard, quality protocol, latency/throughput and
  memory limits, validator/input hashes, authorized resources and stop condition.
- **Observations:** preparation/prefill/draft/verify/commit/replay/transport
  timings; proposed/accepted lengths, full/partial commits, correction and
  fallback counts, verifier errors; first divergence and complete quality output;
  per-request and aggregate metrics; peak memory; both-peer logs and cleanup.

For already installed binaries and already authorized local model files, a
single-host diagnostic can compare a target-only invocation such as
`ds4 -m <MODEL_GGUF> --ctx <TOKENS> --temp 0 -p <PROMPT>` with a matching
candidate adding `--dspark --mtp-model <MATCHED_SUPPORT_GGUF>`. Keep all other
controls fixed and record whether the requested path actually activated.
This template is not a download/build instruction, a safe automatic run or a
complete service experiment. A server benchmark needs its own request-level
workload, not only CLI tokens per second.

Source-script decisions: model download/conversion helpers are excluded from
this route because they perform large network/storage operations and need
separate model/license decisions. Hardware-specific server launchers are not
portable wrappers. Long-running acceptance and benchmark scripts are
reference-only: their controls are distilled above; executing them is not
necessary to use this knowledge procedure and is not authorized by reading it.
