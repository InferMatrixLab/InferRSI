# VLA benchmark boundaries and closed-loop quality

Use this procedure for vision-language-action (VLA) deployment comparisons,
latency-per-action or control-frequency claims, and quantized runtime reports.
The [source record](embodied-cpp-source.json) retains the pinned Embodied.cpp
repository, companion paper v3, selected readset, rights and evidence limits.

## Freeze the observation-to-action contract

Name the input available when timing starts and the output required when it
ends. Record image layout/resolution, state dimensions, instruction, noise,
batch size and output shape. Trace preprocessing, tokenization, host/device
transfers, synchronization, postprocessing and CPU output materialization on
both paths. Include the deployed transport and state any asymmetry. Separate
model loading, fixture construction, sensor/simulator work and action replay
from that timer.

The selected fixed benchmark takes two CHW 512-pixel CPU images, raw 8-D state,
an exact instruction and a 50x32 noise array, and returns a complete 50x7 CPU
action chunk. Its Python path calls the official processors, model and
postprocessor before CPU materialization. Its C++ path includes client
preprocessing, local ZMQ request/response and conversion of the returned chunk;
the server serializes a CPU float vector. This boundary excludes simulator
execution and sensor acquisition. The separate closed-loop experiment has
360-pixel observations and 512-pixel model images; do not silently give the
fixed-fixture test that larger input boundary.

Freeze the campaign's latency/jitter objective, quality gates, repetitions,
seeds and failure accounting before comparison. The source's five warmups,
100 timed requests and twenty separate untimed memory requests describe its
protocol, not universal InferRSI defaults.

Sources: [benchmark predictors and timed loop][bench], [client][client],
[server response][server] and [benchmark standard][standard].

## Separate generated actions, replay and control clocks

For request i producing H_i actions, L_i / H_i is cost per generated action.
It does not say when an action becomes available to a robot or how often a
fresh observation is used. Record the number of actions replayed before
replanning and measure actual observation/action timestamps separately.

| Quantity | Numerator and denominator | Meaning |
|---|---|---|
| Complete request latency | CPU observation to complete CPU action chunk | The declared deployment request |
| Fixed-boundary cost per generated action | Complete request latency / generated horizon | Amortized generation cost |
| Source profiler inf_ms | Server-reported latency_ms_total per unique request | A narrower server timing scope |
| Profiler generated_action_step_ms | Server-reported time / generated chunk size | Server-scope generation amortization |
| Profiler model_step_ms | Server-reported time / configured replay count | Replay-amortized server cost |
| Control cadence | Actual action/observation timestamps, queueing and replay | The execution clock |

Equal denominators do not make server-only and complete client timing
comparable. The source client generates a chunk, queues only the configured
replay prefix and returns one action at a time. The Object experiment uses
generation horizon 50 and replay horizon 1. About 308 ms/request divided by
50 gives 6.161 ms/generated action; it does not establish 6.161 ms action
response latency or roughly 162 Hz control.

Sources: [client queue/request methods][client], [profiler metrics][profiler]
and the standard's performance protocol.

## Reconcile identity and the intended treatment

Compare source checkpoint, tokenizer/processor settings, normalization and
per-instruction layouts; fixture, instruction and noise identities; RNG
device/dtype; flow settings; output shape, generated horizon and replay horizon;
hardware allocation and software stack. Equal tensor names do not establish
equal inference configuration.

Keep source checkpoint storage, converted/resident weight storage and
effective compute precision distinct. A runtime-only comparison needs matched
effective precision. If quantization or compute policy is the intended
difference, name the joint runtime/precision treatment and assess its quality
trade-off rather than attributing the entire difference to runtime overhead.

The inspected pair gate checks backend pairing, plan, boundary/script/fixture/
instruction/checkpoint/tokenizer identities, shape, horizon, memory source and
GPU identity. It does not compare effective compute precision or establish
output-quality equivalence. The retained Python manifest reports BF16/F32
parameter dtypes and disabled autocast; C++ reports Q8_0 resident weights and
F32 compute. These are author manifests, not proof of each executed operator's
dtype.

Sources: [pair validation and result manifests][bench], [standard][standard]
and [retained artifact][artifact].

## Audit per-task quality and the complete trial denominator

Freeze benchmark version, suite/tasks, episodes per task, initial-state order,
control mode, image/prompt construction, noise/seed protocol, action replay,
generated horizon and success definition. Keep requested, evaluable,
successful, skipped and aborted trials visible. Recount task/episode identities
from raw records before making a complete-quality claim. Report per-task
counts alongside totals and the declared uncertainty intervals.

The source's strict Object aggregation checks task/episode IDs and protocol,
cross-checks profile/task records, rejects skips, aborts and incomplete raw
samples, and reconciles quantizer/startup manifests. A complete single-arm
result still sets promotion_eligible=false because the matching comparator is
separate. Those are static source checks until execution and inputs are
established.

The Q8 follow-up reports C++ 166/200 versus Python 172/200 across ten Object
tasks with twenty episodes each. Task 7 is 9/20 versus 20/20. Preserve that
loss when interpreting the aggregate 83% versus 86%. Overlapping Wilson
intervals do not establish equivalence or noninferiority; use the campaign's
frozen quality policy. Keep this Object comparison separate from historical
four-suite runs under an older seed protocol and later small smoke samples.

Sources: [strict aggregation][aggregate], [follow-up][followup],
[historical validation][validation] and [ledger][ledger].

## Interpret the retained sample arrays and memory scope

The committed [artifact][artifact] contains 100 latency samples per backend.
Recomputing those arrays produces the values below. This is an audit of
published samples, not a fresh device measurement.

| Observation | Python | C++ Q8_0 | Boundary |
|---|---:|---:|---|
| Request mean | 490.755 ms | 308.030 ms | Complete fixed CPU-input-to-CPU-output request |
| Request p99 | 518.767 ms | 393.719 ms | Same timing boundary and sample arrays |
| Mean / generated horizon 50 | 9.815 ms | 6.161 ms | Amortized generation cost |
| Sampled peak memory | 1671 MiB | 1029 MiB | Isolated whole-device WSL fallback |

The request-latency ratio is approximately 0.627665; the sampled device-memory
ratio is 0.615799. Both memory records declare process_level_vram=false.
Twenty untimed memory requests produced 73 Python and 13 C++ sampler values:
periodic observations, not twenty per-request memory measurements. Retain the
measurement source and author allocation-isolation claim. Do not relabel
whole-device memory as process-attributed memory or compare allocator bytes,
file size and simulator-inclusive memory as identical quantities.

The closed-loop Python profiler times inside _get_action_chunk with CUDA
synchronization; its memory includes the simulator. Those diagnostic values
are not the denominator for the fixed-boundary table. The follow-up identifies
one timing interval interrupted by host-process suspension using an exact
task/index/value and reason, with raw data and filtered/unfiltered summaries
retained. That disposition does not authorize threshold-based outlier removal
or excluding unsuccessful trials from a future comparison.

Sources: [artifact][artifact], [follow-up][followup], [memory sampler][profiler]
and [Python profiler/aggregation][baseline].

## Bind measurements to the code actually measured

Keep inspection revision, declared experiment revision, actual script/binary
identities and the complete dirty patch separate.

| Identity | Retained observation |
|---|---|
| Inspected repository | 156bed151826780e2ce0132f8d0e3540889ae8cd |
| Current pinned benchmark script SHA-256 | 2a7e94a4df662d2da41169cc2345b75e683c82e082fe590eba713302255e1a7b |
| Artifact's declared experiment revision | 3a3468cfe634e88d93d08aafcae89bd3ef0fb5a2 |
| Public script at that revision SHA-256 | 3ab7f108eb4493dec548e8641a65e54d3dd605bab27076e17abf1422792f9332; its architecture choices omit SmolVLA |
| Recorded measured-script SHA-256 | dee5573089d882ec5fcade6c99ede546ab810c22526c894c68bbca471175a892 |
| Closed-loop source base | dcedfec5721768661bd81f4196a0325d55f814f9 plus uncommitted changes |

Neither public script identity matches the recorded measured script. The
follow-up retains a server-binary hash, but a binary hash or dirty-path count
does not identify the complete source patch. Request exact measured
source/patch and artifact identities before reproduction or current-build
attribution; code presence cannot transfer historical speed or quality.

The public tree retains compact latency arrays and author quality tables.
Referenced raw episode logs, the fixture and complete measurement patch are
absent. When episode recount is unavailable, retain the author-reported
counts and withhold the affected quality/reproduction claim. Missing artifacts
do not erase available sample arithmetic or justify invented replacement data.

Sources: [follow-up provenance][followup], [artifact][artifact],
[current script][bench] and [public historical script][historical].

## Return a comparison at its supported evidence level

Produce a timing/denominator table, input/precision reconciliation, per-task
quality and completion account, artifact/source identities and unresolved
receipts. Distinguish a runtime-only matched comparison from a named joint
runtime/precision trade-off. Withhold quality-preservation, current-build or
control-rate conclusions when their required observations are missing.

Name the missing evidence needed to recover: original episode IDs/outcomes,
the measured script/dirty patch, matched precision/dispatch or actual
observation/action timestamps. Future execution needs its own authorized,
frozen campaign. This reference supplies methodology and source interpretation,
not a runtime integration.

## Attribution and source scope

This is original analysis of SEU-PAISys/Embodied.cpp and Ling Xu et al.,
*Embodied.cpp: A Portable Inference Runtime of Embodied AI Models on
Heterogeneous Robots*, [arXiv:2607.02501v3][paper], dated 2026-08-09.
The paper is [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/);
the repository declares [Apache-2.0][license], retaining Copyright 2026
VinRobotics for original portions and Copyright 2026 SEU-PAISys for
modifications and new files. These notes adapt methodology in original prose;
paper figures/full text, source code and raw arrays are not redistributed.
Dependencies, checkpoints and datasets retain separate rights.

Paper v3/Table 3 supplies independently normalized VLA latency, success and
memory semantics. It predates the September/October SmolVLA follow-up.
Broader WAM/runtime-support, model math and quantizer correctness are outside
this readset's qualification. This source-derived candidate establishes no
native dispatch, model/device correctness, quality preservation, service
performance or agent efficacy.

[bench]: https://github.com/SEU-PAISys/Embodied.cpp/blob/156bed151826780e2ce0132f8d0e3540889ae8cd/scripts/bench_vla_boundary.py
[client]: https://github.com/SEU-PAISys/Embodied.cpp/blob/156bed151826780e2ce0132f8d0e3540889ae8cd/eval/client/vla_cpp_client.py
[server]: https://github.com/SEU-PAISys/Embodied.cpp/blob/156bed151826780e2ce0132f8d0e3540889ae8cd/serving/vla-server.cpp
[standard]: https://github.com/SEU-PAISys/Embodied.cpp/blob/156bed151826780e2ce0132f8d0e3540889ae8cd/eval/VLA_BENCHMARK_STANDARD.md
[profiler]: https://github.com/SEU-PAISys/Embodied.cpp/blob/156bed151826780e2ce0132f8d0e3540889ae8cd/eval/client/libero_profile.py
[aggregate]: https://github.com/SEU-PAISys/Embodied.cpp/blob/156bed151826780e2ce0132f8d0e3540889ae8cd/scripts/aggregate_smolvla_object_eval.py
[followup]: https://github.com/SEU-PAISys/Embodied.cpp/blob/156bed151826780e2ce0132f8d0e3540889ae8cd/eval/smolvla_q8_object_followup_20260930.md
[artifact]: https://github.com/SEU-PAISys/Embodied.cpp/blob/156bed151826780e2ce0132f8d0e3540889ae8cd/eval/smolvla_q8_fixed_boundary_20261002.json
[baseline]: https://github.com/SEU-PAISys/Embodied.cpp/blob/156bed151826780e2ce0132f8d0e3540889ae8cd/scripts/profile_smolvla_python_baseline.py
[validation]: https://github.com/SEU-PAISys/Embodied.cpp/blob/156bed151826780e2ce0132f8d0e3540889ae8cd/eval/SMOLVLA_VALIDATION.md
[ledger]: https://github.com/SEU-PAISys/Embodied.cpp/blob/156bed151826780e2ce0132f8d0e3540889ae8cd/eval/THREE_MODEL_VALIDATION.md
[historical]: https://github.com/SEU-PAISys/Embodied.cpp/blob/3a3468cfe634e88d93d08aafcae89bd3ef0fb5a2/scripts/bench_vla_boundary.py
[paper]: https://arxiv.org/abs/2607.02501v3
[license]: https://github.com/SEU-PAISys/Embodied.cpp/blob/156bed151826780e2ce0132f8d0e3540889ae8cd/LICENSE
