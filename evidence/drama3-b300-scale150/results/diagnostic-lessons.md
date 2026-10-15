# Diagnostic lessons; campaign INCONCLUSIVE

Scope: [acceptance issue #10](https://github.com/ThinkFlowLab/OmniRSI/issues/10).
The user-confirmed bounds and frozen validator remain unchanged. All baseline
quality repetitions are now complete. No candidate has passed the required
all-concurrency performance and quality matrix, so no successful README example
is added.

The [published runtime evidence](https://github.com/david6666666/drama-3-single-b300-inference/tree/e58c8418005af8972d1616d5368009bc07dbe651/evidence/20261015-scale150)
retains the following useful failures and controls:

- Compare actual batch sizes when attributing decode kernels. Mixed-batch
  averages and a full-batch diagnostic cannot establish a kernel regression.
  When streams overlap, summed kernel durations exceed elapsed graph time.
- A whole-network single/batch parity failure needs an unchanged control.
  Both packed and unchanged padded prefill exceeded the initial whole-network
  error bound. That failure remains recorded. A separately declared experiment
  compared each operator on identical real layer inputs and retained its
  numeric threshold, graph/eager parity and exact ownership checks.
- State ownership checks must include real rows, dummy primary rows and GDN
  suffix scratch rows. Snapshot unrelated state before CUDA Graph replay;
  checking only eager execution misses replay-specific writes. Invalid test
  setup failures are retained separately from runtime failures.
- Removing an existing atomic prefill reduction resolved the tested packed
  graph/eager mismatch. Experimental packed serving uses ordered reduction;
  this observation does not establish bitwise equivalence for every model path.
- Fused tower projections improved a real decode microbenchmark but did not
  improve the full service trial. Multi-step decode passed exact state/output
  checks but delayed admission and did not improve service throughput. Neither
  is selected on its kernel result alone.
- Concurrent prefill/decode preserved tested states on an isolated GPU, but the
  diagnostic excludes first-frame sampling, scheduling and codec. Its timing
  cannot be promoted as service throughput. An earlier timing on a device with
  an observed external worker is explicitly unqualified.

Complete quality from an individual feasible configuration is useful evidence,
but it does not fill missing concurrency or repetition groups. The imported
catalog guidance remains `locally_verified=false`; these observations do not
automatically qualify another engine, revision, GPU or workload.

The user confirmed that further optimization must retain native computation,
all eight routed experts, and no additional lossy quantization. Historical
precision-reduction trials remain rejected; frozen acceptance gates are intact.

New fixed-request controls cover complete generated codes, model/codec state,
PCM bytes, completion ordering and two generations of slot reuse. Decode/codec
and prefill/codec concurrency both preserve the tested outputs exactly. Yet
fresh asynchronous service trials fail complete WER in both the unchanged
control and the fused-input candidate. These failures remain in the runtime
evidence and the async configuration is not selected. Do not infer a CUDA race,
a successful fix, or acceptable dynamic-service quality from those replay
controls alone. No root cause has been established.

Nonblocking CUDA events also show substantial existing codec/decode overlap.
Exclude warmup using the raw request interval, distinguish submission from
codec execution, and do not count overlapped time twice as an available gain.
Event spans can contain submission gaps and do not measure SM utilization.

The new native MoE input preparation preserves every FP8 activation byte,
scale and router value, and complete B16/B64 replay state. This numerical result
is separate from serving acceptance, which remains incomplete.

A separate native-fusion pair with synchronous codec subsequently completed on
the frozen physical GPU0. All 1088 outputs in each arm meet the issue's quality
bounds, but throughput still misses the updated baseline and acceptance target.
This is one feasibility repetition, not a qualified all-concurrency result.
The successful fixed-input fusion and this limited service observation do not
promote the rejected asynchronous configuration or resolve its failure cause.


## Continuous-admission profile and mixed backbone, 2026-10-16

A new diagnostic sends 256 requests at C64 with continuous client replenishment.
The analyzer counts CPU `user_annotation` execute-context scopes, rather than
PIECEWISE GPU graph fragments. It observes 802 scheduler steps: one pure
prefill, 37 mixed, 762 pure decode and two empty steps. Scheduled prompt entries
can include chunks, so their count is not the unique-request count.

Client timestamps provide an admission/drain proxy. The admission interval has
321 steps (one prefill, 36 mixed and 284 pure decode). Its pure-decode batch
averages 60.718 of 64, with range 52–64; mixed steps average 7.083 scheduled
prompt entries / 1179.33 prompt tokens plus 54.083 decode requests. This interval
includes initial filling; initial large mixed steps should be distinguished
when describing the later refill pattern, without dropping any request from
performance or quality acceptance. Final drain contains 481 steps and its
pure-decode batch averages 8.793. Across the whole trace, the pure-decode average
falls to 28.146. This is direct evidence that whole-run mean batch must not be
substituted for sustained-admission occupancy.

Within the client-admission interval, correlated GPU annotation unions sum to
999.20 ms for mixed work and 3069.41 ms for pure decode. They are annotations,
not summed kernel duration or SM utilization. CPU wall/monotonic alignment is
an approximation; client in-flight requests include queueing and codec work.
Neither this phase split nor the profiler timings establish a performance gain.
The prior single-wave trace remains retained with its original limitations.

Local source: `/home/zjy/code/hsliu/artifacts/drama3-mixed-20261016/vllm-continuous-schedule.json`.
Its raw trace SHA-256 is
`29e5cafe329cb85eaba69db7536a28a83fb7e3ac29bc154fc8747f317f6a4b3f`;
request-metadata SHA-256 is
`bd50166976a4753b33c8aeb5a774ebb5711c74ccbba0df1843885f353ecdc996`.

The native mixed-backbone prototype shares projection/MoE rows while preserving
separate attention/GDN segments and teacher-forced prompt-tower handling. The
initial D58/P6 check passes 730 layer/graph/ownership checks. The expanded
D58/P6, D40/P3 and D12/P1 probe passes 2190 checks, including reused slots in the
latter cases and exact untouched-state checks. These are two overlapping
validation cohorts, not 2920 unique cases. Existing numerical limits remain
unchanged; a passing layer check is not complete generated-audio validation.

The expanded probe ran on physical GPU0, where external work was observed.
Its numerical results remain recorded; its timing is explicitly unqualified.
The local artifacts are `mixed-layers.json` and `mixed-layers-expanded-v2.json`
in the same artifact directory. The same-source GPU6 complete service comparison
has finished: control 3816.466 and mixed 4094.177 frames/s. All 1088 outputs in
each arm were scored: control WER 1.607636%, SIM 64.48894; mixed WER 1.582517%,
SIM 64.28628. Both meet the single-group quality bounds, but the mixed result
remains below the frozen vLLM C64 baseline and acceptance target. This is one
feasibility repetition on another physical device, not formal acceptance.

Generated frames differ (102946 versus 101162). Makespan decreases 8.398%,
while frames/s increases 7.277%; shorter final drain contributes about 34% of
the makespan difference. Retain these stochastic workload differences instead
of attributing all observed change to fixed-work kernel acceleration.

The standalone mixed timeline retains all 384 measured requests. Its 9.998 s
window contains 6.060 s of pure-decode event spans, 1.969 s of mixed backbone
including teacher-forced tower, and 1.454 s of synchronous codec. During ongoing
admission, decode averages 61.071/64 active requests. Event spans and client
phase proxies do not measure SM utilization or establish causal attribution.
The first-frame CPU scope mostly waits for earlier mixed GPU work; it is not
evidence that rewriting the scheduler in another language would remove that cost.

Six actual-input native FP8 expert GEMMs from three B64 layers show DRAM peak
fractions of 56.36–75.54% and tensor activity of 3.46–4.48%. Measured DRAM reads
are close to one logical active-expert weight footprint. Expert counts come
from a same-logit top-k recomputation with unproven FlashInfer tie equivalence;
Nsight replay, three-layer coverage and a single position limit interpretation.
These samples support inspecting weight traffic, not a many-fold speedup from
unused tensor arithmetic. No expert is removed and no extra quantization is used.

A separate fixed-state mixed-span probe reduces the static prompt maximum while
keeping token-row capacity unchanged. All 339 output/state checks across three
real cases are exact. This trims diagnostic graph time by about 2.5 ms per case;
the change also affects attention and convolution bounds, so it is not solely
a GDN result. A GPU0 service pair and complete quality checks are required before
selecting it. Frozen plan and validator remain unchanged.


A later dynamic replay finally reproduces an asynchronous divergence with fixed
request order. Default capture has a shared ATen cuBLAS workspace and first
changes generated codes at trace entry 207. Dedicated codec capture observes
disjoint workspace ranges and matches serial codes, PCM, completion ordering
and every model/codec state across all 414 trace entries for 80 real requests.
Both configurations also have identical serial trace and PCM hashes. This fixes
the reproduced case; it is not proof that every historical WER failure shares
the cause. Extra diagnostic D2H reads can alter overlap timing. The default-off
candidate is undergoing a fresh full-corpus service/quality comparison.

For mixed large-M MoE, six counter samples use actual FlashInfer routing and
read only 1.011–1.017 times the unique active-expert weight footprint. The test
preserves original outputs when recording routing. These inputs do not support
a redundant-weight-HBM-read hypothesis, so another blind layout search is not
justified. Three layers and one mixed position remain insufficient for a global
lower bound or a claim that the all-concurrency target is impossible.


The fresh GPU0 same-source async service pair is now complete. All 1088 outputs
per arm were scored. Shared capture has WER 6.162606% and SIM 63.124403, failing
the WER gate; private capture has WER 1.590890% and SIM 64.191350, passing the
single-group limits. Private throughput is 4360.917 frames/s, TTFA p50/p95
143.351/278.698 ms and mean RTF 0.307843. It still misses the frozen C64 baseline
and target. New runtime startup rejects async codec without explicit dedicated
capture, preventing the reproduced unsafe configuration. This is not formal
all-concurrency acceptance or proof about every historical quality failure.

All new raw groups, diagnostics, source snapshots and limitations are indexed in
[the published mixed investigation](https://github.com/david6666666/drama-3-single-b300-inference/tree/dfdd598a9810cf6e7b8aa6a102f6ab9270ff9cc6/evidence/20261016-mixed).
The runtime PR remains draft and the campaign remains INCONCLUSIVE.


## C64 reference-gap investigation, 2026-10-16

The target remains6765.407 frames/s with native full-top8 computation and the
frozen quality gates. The measured isolated B64 reference is approximately7734
frames/s; it is neither a hardware upper bound nor a service guarantee. The
complete1088 asynchronous trace replaces old synchronous timing proportions.
Client continuous in-flight is about63.98, with only about6ms equivalent missing
client-slot time. Client dispatch starvation is not supported as the major gap.

Rich tracing separates183228 real prompt tokens from208384 captured rows and
2122 codec frame-bucket groups from2265 actual graph calls. Only143 calls are
avoidable same-bucket partitions; frame-bucket diversity accounts for833 groups
beyond the emit count. Neither percentage is a time-saving estimate. The trace
records multi-step decode explicitly instead of equating graph calls with steps.

Compact GDN passes2099 exact checks. Mixed-layout and empty-convolution changes
pass339 checks each and339 combined. Nevertheless, their full one-run GPU0
candidate is4306.693 frames/s versus4371.393 for the same-source control; both
score all1088 outputs and pass WER/SIM. The candidate's frame count is2.106%
higher and drain1.092s longer. Preserve the failed full throughput score and the
fixed-state graph improvement as different observations.

Deferred codec host submission preserves the original producer event and passes
414-event dynamic exact replay. Its GPU6 feasibility is4430.811 frames/s versus
4366.914, but it produces2.677% more frames, takes1.197% longer and regresses TTFA.
Both complete quality groups pass; this is not a fixed-work throughput win or a
reason to change the default.

A controlled native interference probe passes all60 code/PCM/state comparisons.
Four B64 steps take33.33ms alone, versus34.65–36.92ms with three real F8 codec jobs
of batch1–8. Concurrent pair completion is still better than serial. Model-high
stream priority has no material gain; queried graph flags confirm launch-stream
priority was the tested variable. This establishes contention for those fixed
inputs, not the recoverability of every service overlap interval.

The existing FI GDN adapter was tested on the current mixed path. An initial
numeric gate fails on a private padding sequence and remains recorded as FAIL.
A separate FP32-reference and padding-isolation diagnostic identifies the live
versus unused domain, but final prefill hidden RRMS is0.09118. The local timing
gain is only1.776%, below the predeclared5% criterion, so no full service trial or
promotion follows. Do not silently reinterpret the original failure as success.

Short reserved attention contexts pass 1023 exact checks across 9 cases and a
complete GPU7 service/quality pair. Combining this with compact GDN, mixed layout
and empty-convolution guards gives a same-source GPU0 one-pair result of
4353.909 → 4591.038 frames/s. Candidate TTFA p50/p95 is 140.774/268.097 ms,
mean RTF 0.295911, WER 1.925814%, SIM 63.693694. Both 1088-output quality groups
pass, and the candidate's +0.858% generated frames are retained. The observed
single-run +5.446% is not a repeated speedup claim. It is only 1.0179× the frozen
vLLM baseline and fails the 1.5× target.

Codec minimum-launch repartitioning changes 5/80 PCM outputs; the original exact
gate remains FAIL even after identifying private scratch versus real final state.
A new MoE residual fusion also fails its first exact static check; no timing is
claimed for that candidate. Codec resource limiting remains experimental.
No all-concurrency acceptance or successful README example is claimed; the
campaign remains INCONCLUSIVE. Complete source, commands, numeric failures and
full service/quality records are [published at the frozen runtime revision](https://github.com/david6666666/drama-3-single-b300-inference/tree/ab2d9015d6b0115530e675f25bbf5f188b1d65b1/evidence/20261016-ceiling).


## Native pipeline, rounding and resource-allocation follow-up

The corrected MoE residual fusion preserves the reference compiler's native BF16
FMA and passes2374 exact checks. The original separate-operation failure remains
archived. Explicit reserved-slot routing passes2574 production checks while
preserving every real full-top8 route and native activation/scales; its local
benefit is limited to partially populated decode batches.

The checkpoint embeds semantic/code1 for the next backbone. A native two-frame
pipeline can therefore overlap its next backbone with eight remaining tower
layers. Its production gate passes3689 exact checks, including slot reuse,
max_frames and a separately injected first-EOS boundary. A callback-local buffer
had been allocated on the main stream and consumed on an auxiliary stream after
its reference expired. Retaining its lifetime is supported by a one-variable335
exact-check diagnostic. An additional validation failure came from an eager call
rebinding a Python tensor attribute; graph replay still updated the old captured
storage. Both failed records remain, and the corrected validator pins addresses.
These are model correctness gates; complete service evaluation is still separate.

An actual emission ledger leaves47.58% of supported ordinary calls not already
blocked by known audio boundaries. This is an upper bound, not actual pair use.
Correlated chunk phases contradict an independent-row estimate. New capture
warmups also advance the global sampling counter, so the service comparison must
retain output lengths and cannot be labeled fixed-output merely because inputs
match.

Native codec resource caps require capture-time kernel assignment. NCU verifies
all284 nodes of the inspected native B4/F8 graph. The full dynamic diagnostic
covers46 captures and28 actual shapes, preserving414 trace entries,80 full PCM
outputs and all model/codec state across normal/capped-sync/poll/thread modes.
The complete service pair observes4412.554→4470.317 frames/s, with fewer output
frames and arm-specific measured-cost DP feedback. Both1088-output quality groups
pass (WER1.909068%/1.565771%, SIM63.902018/64.244919); the candidate remains below
the baseline and target. Adjacent codec group coalescing likewise passes complete
quality but regresses4513.299→4414.243 frames/s. Neither changes the campaign verdict.

The best complete single-run quality-qualified observation remains4591.038frames/s,
and the all-concurrency three-repeat requirement remains incomplete. All new raw
results, preserved failures, source snapshots and limitations are
[pinned in runtime evidence](https://github.com/david6666666/drama-3-single-b300-inference/tree/171acc82460f479b56372a57d9f7de7a154795aa/evidence/20261016-ceiling).
No successful README example is added; the campaign remains INCONCLUSIVE.
