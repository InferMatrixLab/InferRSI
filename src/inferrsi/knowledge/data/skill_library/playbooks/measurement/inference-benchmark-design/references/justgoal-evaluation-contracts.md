# JustGoal: controlled harness evaluation and kernel acceptance

Status: source-derived candidate. The [source record](justgoal-source.json)
owns the pinned repository, paired paper, selected file identities, read regions
and license dispositions. Benchmark outcomes below are author-reported. Native
execution, numerical correctness and performance were not run locally; agent
efficacy was not evaluated.

Use this reference when deciding whether added kernel-agent machinery improves
results beyond a goal-only control. It extends benchmark design and evidence
interpretation; it supplies no kernel implementation or campaign runner.

## Freeze the comparison before attributing a gain

Declare the actual generation model and effort, agent environment, total search
budget, task constraints, reference implementations, input distribution,
correctness oracle, timing boundary and aggregation. Preserve model fallbacks
and constraint violations in their own fields. Reevaluate the comparison when
the generation model or task scope changes.

The paper's controlled experiments use the same 24-hour budget and distinguish
two axes: `{goal-only, added harness}` and `{one shape, whole definition}`.
Compare the harness at equal scope; compare scope under the same harness.
Different task scopes cannot isolate the harness contribution. A complete 2x2
exists only for Fable 5.1. The paper uses one optimization run per
configuration/task, rather than repeated independent campaigns. The published
KDA kernels use an unknown
generation model/effort and are a kernel-quality comparator, not a same-model
harness control. The reproduction also lacks the complete original KDA-0.5
prompts/search configuration, limiting its fidelity.

Table 2 reports a single-shape harness effect of 0.95x and a whole-definition
effect of 1.37x. The single-shape cells use same-GPU paired re-measurement;
the whole-definition cells use official-evaluator timing and await the same
paired rerun. Retain these protocol differences with the ratios. They do not
establish that any individual knowledge base, profiler skill or workflow causes
the full-configuration difference. The ablations cover one model and three
shapes; they do not establish a universal return on specialized skills.

Source: [paper](https://github.com/OpenBMB/JustGoal/blob/f052fc0b28fc7f10b2ef1ae7aa4682aabbbe868d/paper.pdf),
Sections 4.1-4.5 and 6, Table 2, Appendix C.1/Tables 6-9.

## Separate generation feedback from final acceptance

For a new comparison, fix the acceptance oracle, input coverage, numerical
criteria and complete outputs before candidate search. Keep them independent
of the model's self-authored check. JustGoal's prompt suggests a naive FP32
implementation and reference-relative tolerance; the authors acknowledge that
this is expert numerical guidance. Its generation process therefore is not
literally free of expert instructions.

The authors separately validate final kernels with FlashInfer-Bench, except
FA4 backward, which follows upstream FA4 gradient criteria. Their final
acceptance does not use the agent's chosen tolerances. This external acceptance
is distinct from generation-time feedback; do not describe the goal-only
generation loop as having enforced an independent hard gate.

Check every output and state update, including auxiliary outputs such as
log-sum-exp (`lse`), rather than only the primary attention tensor. Preserve
official-evaluator and stricter-recheck outcomes separately. Appendix C.2
reports that an evaluator missed absent `lse`; its stricter recheck also finds
small DSA `lse` tolerance exceedances and MoE row differences accepted by the
official matched-ratio rule. Neither result should overwrite the other.
Finite-input acceptance is not a guarantee for all valid inputs, concurrent
execution or production integration.

Source: paper Sections 3.1-3.2, 4.5, 6 and Appendix C.2.

## Keep coverage and repair denominators explicit

Whole-definition generation covers 23 DSA, 100 GDN, 19 MoE and 3 FA4-backward
workloads; FA4 has fixed-length and variable-length definitions. The authors
time three selected shapes per operator in the main comparison. Passing a
definition's official evaluator and having independent timing for every
workload are different claims. Also retain which length distributions were
substituted and which sessions actually used another model.

Maintain separate columns for the released artifact and any repaired artifact:
revision, build/runtime outcome, complete-output correctness, constraint
compliance, repair and retimed result. In the NCU-family ablations, three of six
released versions fail retest and pass after repair; the speed table uses the
repaired timing. Table 4 counts a repaired-only directory as a released failure.
Its denominator is retested directories, not all generated candidates, and
constraint-violating runs that passed correctness remain in its passing count.
This is a released-version pass rate, not first-generated-attempt success.

Best observed, final delivered, released, repaired and independently retimed
results need their own identities. Figures 4-5 describe session trajectories;
their selected points and timing protocol cannot be spliced into the paired
final-kernel comparison or read as a complete attempt/failure inventory.

Source: paper Sections 4.3-4.6, Table 4, Figures 4-5, Appendices B and C.

## State the timing and cache contracts

The paper's device metric is a cold-L2 CUPTI span from the first kernel's start
to the last kernel's end at the entry point. It excludes JIT compilation,
cache flushing and synchronization overhead. It is not host launch-inclusive
latency, search cost or service/E2E latency. Distinguish same-GPU alternating
pairs, official-evaluator rounds and independent measurements on another B200.
Do not combine absolute latencies from different batches to make a new ratio.

Appendix C retains unpaired DSA top-k audit records but excludes them from the
speedup figure. It also records model fallback, four substituted length
distributions, baseline variation between batches, a milliseconds/microseconds
error, input-pointer CUDA-graph caching and timing on self-generated inputs.
For a new evaluation, verify work and input identity independently of the
reported latency; changing input values and allocation identity are relevant
controls where graph or output reuse could hide the actual work.

Keep three different meanings of cache separate: the hardware L2 measurement
policy, compiled-module reuse, and mutable workspace/input-dependent execution
state. Warming one of them does not establish the contract of the others.

Source: paper Section 3.2, Figures 4-5 and Appendix C/C.1-C.2.

## Trace workspace ownership through the launcher

These two selected DSA paths illustrate contracts to recover before reuse;
they are source observations, not executed correctness or concurrency tests.

| Path | Observed ownership and launch behavior | Qualification still needed for reuse |
| --- | --- | --- |
| Single-shape Fable DSA `t8_topk2048` | Python caches partials, arrival counters and per-SM counters by token count and device; its CUDA consumer mutates monotonic counters and launches on the current CUDA stream. The selected kernel fixes top-k at 2048 and admits token counts 1-32. | Match the selected layout/device limits and repeated-call counter behavior. A shape/device cache key does not establish per-stream ownership, reentrancy or multi-device configuration safety. |
| Whole-definition Fable DSA | Python retains a capacity-growing workspace and host epoch/ticket state per device; CUDA consumes those same buffers, increments host state and launches using the caller's current stream. Compilation is cached separately from the workspace. | Establish invocation ordering and workspace lifetime. Reusing one mutable device workspace cannot itself justify simultaneous calls on different streams; require independent ownership or demonstrated ordering before making that claim. |

The concurrency conditions in the last column are deductions from mutable
shared scratch and launcher boundaries, not reproduced races or blanket
rejections of the source kernels. Before extending a supported use, validate
fresh-process and repeated calls, changing supported shapes/inputs, the caller's
stream, and the intended overlap/reentrancy contract. Keep these proposed
checks separate from the paper's author-reported numerical results.

Code: [single-shape wrapper](https://github.com/OpenBMB/JustGoal/blob/f052fc0b28fc7f10b2ef1ae7aa4682aabbbe868d/goal_single_shape/fable-5.1/dsa_decode_fwd/t8_topk2048/dsa_kernel.py)
and [CUDA consumer](https://github.com/OpenBMB/JustGoal/blob/f052fc0b28fc7f10b2ef1ae7aa4682aabbbe868d/goal_single_shape/fable-5.1/dsa_decode_fwd/t8_topk2048/dsa_kernel.cu);
[whole-definition wrapper](https://github.com/OpenBMB/JustGoal/blob/f052fc0b28fc7f10b2ef1ae7aa4682aabbbe868d/goal_full_shape/fable-5.1/dsa_decode_fwd/dsa_sparse_attention_h16_ckv512_kpe64_topk2048_ps64/main.py)
and [CUDA consumer](https://github.com/OpenBMB/JustGoal/blob/f052fc0b28fc7f10b2ef1ae7aa4682aabbbe868d/goal_full_shape/fable-5.1/dsa_decode_fwd/dsa_sparse_attention_h16_ckv512_kpe64_topk2048_ps64/dsa_decode.cu).
The source record lists the inspected regions; mathematical kernel bodies
outside that contract readset were not comprehensively audited.

## Interpret a supplied claim

| Supplied evidence | Supported conclusion | Withhold |
| --- | --- | --- |
| Single-shape goal-only versus whole-definition harness | A configuration comparison with different task scopes | A causal harness or individual-skill benefit |
| A released failure followed by a correct repaired kernel and better timing | Repaired-artifact correctness/timing under its recorded retest | Released-version or first-attempt success |
| An official pass that omits a required auxiliary output | An evaluator coverage gap under the complete-output contract | Complete kernel correctness |
| Cached mutable scratch and a current-stream launch | A source-level ownership/ordering contract to qualify | Concurrent-safe or service-ready execution |

Return the comparator identity, coverage/repair counts, accepted outputs,
timing/cache boundary and unresolved checks with the supplied report's actual
verdict semantics. This source reference does not create an InferRSI PASS.

## Distribution and evidence limits

The repository [README](https://github.com/OpenBMB/JustGoal/blob/f052fc0b28fc7f10b2ef1ae7aa4682aabbbe868d/README.md)
releases final operator kernels, not the full optimization campaign process.
Its root license declaration is Apache-2.0; NOTICE lists BSD-3-Clause CUTLASS
exceptions and an omitted proprietary `fmha_helpers.py`. The selected DSA
files are outside the listed BSD exceptions. No kernels or helpers are
redistributed here. The paired paper's separate license remains UNKNOWN;
this reference supplies attribution, links and original analysis, without
redistributing the PDF or figures. Exact dispositions and exclusions are in
the source record.

The source hardware is NVIDIA B200/SM100a, with CUDA/toolchain exceptions
recorded in the README. These observations add benchmark verification
methodology, not implementation coverage or compatibility for another device.
The original KDA prompts/process, external retest raw artifacts and other
kernel bodies were not independently reconstructed. Passing reader, integrity
or packaging checks cannot establish the paper's numerical, performance or
agent-efficiency claims.
