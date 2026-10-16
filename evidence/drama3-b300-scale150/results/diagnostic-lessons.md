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


## Native structure follow-up: correctness and performance remain separate

Issue#10 remains INCONCLUSIVE. Distinguishing queued admission from runnable
admission raises two-frame eligibility from139/1902 to625/1246 lifetime ordinary
launch decisions, including warmup. The complete1088-request pair observes
4481.280→4583.673frames/s with both quality groups passing, but p50/p95 first
audio rises. One feasibility pair is not a repeated gain or final acceptance.

Private native-BF16 Linear parameter caching removes40 repeat autocast kernels
from the codec. Original FP32 codec parameters, norm/layer-scale arithmetic and
reference encoding remain unchanged. Local273 exact checks,46 captured shapes,
and fixed80-request/414-entry dynamic replay pass. Yet full service observes
4726.771→4585.126frames/s with all1088 outputs scored in each arm and quality
passing. Output lengths and delivery tails differ; do not attribute the entire
service delta to codec compute. The cache remains default off. The control is
the best complete-quality single observation, not a claimed repeatable winner.

Preserving native GDN warp/reduction order restores exact real-layer and full
state results, while fused recurrence/norm is slower. Resource accounting must
use the production specialization (182 registers/thread), not a debug output
variant (177). A CPU lifetime change raises allocation to185 and is stopped.
Shared MoE metadata removes duplicate routing work but the complete partition
path still loses to native. Neither fewer launches nor exact outputs imply a
performance gain. New resident-expert proposals remain unverified CPU designs.

Autotuning comparisons must control algorithm-plan caches, not merely switch a
flag. The first native cuDNN comparison reused a thread-local cache populated by
control; its benchmark flag was absent from the key. Fresh host threads expose
a PCM exact mismatch before timing. Preserve the original result and explicit
correction, and keep a failed exact check distinct from unmeasured task quality.
No user quality bound, precision boundary, expert count or acceptance gate is
changed. Detailed artifacts are pinned by status.json's runtime evidence commit.

The cache control follows the installed [pinned PyTorch implementation](https://github.com/pytorch/pytorch/blob/cf30153c4c131c8164ee7798e5022d810682e2cb/aten/src/ATen/native/cudnn/Conv_v8.cpp); this dependency source is kept in issue-scoped evidence rather than the vLLM-only imported source list.


A fixed-work replay now separates causal codec contention from variable-length
service scores. All4,177 exact checks pass on80 requests/414 trace entries;
normal overlap lengthens model spans yet remains faster than serialization.
Native weight caching reduces isolated codec time but only0.402% of combined
wall time in this fixture. Its packed-prefill/single-step scope excludes the
current mixed/frame-pipeline executor, whose separate event ledger is retained.
Never present this replay as a complete service benchmark.

Prefix reuse opportunities must be evaluated against arrival groups. Adjacent
identical references can be simultaneous cold misses; completed-prefix hits and
same-group deduplication require different state ownership. Cache identity must
include all acoustic code rows. A valid suffix executor needs prefix K/V,
convolution history and recurrent state, correct teacher labels and independent
writable branch state. Count extra model traversals and precision boundaries
before translating duplicate-row counts into a latency forecast.


## Native arithmetic compatibility is an explicit implementation boundary

The resident-MoE arithmetic foundation now has expanded component evidence.
FC1's first discrepancy contains a physical16-element store permutation and a
quantization-scale formula mismatch. Correcting those passes a single expert,
but a subsequent zero-input expansion still fails. Native SASS lacks the
candidate's tiny-amplitude clamp. A separate correction passes438 checks over
15 native layer/routing fixtures plus original-native zero and near-threshold
references. FC2's corrected physical BF16 store passes306 expanded checks, and
a shared-memory activation body passes2063. Every original failure is retained.
Do not substitute a plausible library reimplementation for the actual frozen
native arithmetic reference; test layouts, scales, signed zero, partial routes,
changed graph metadata and retained storage before timing.

Resource capacity must be checked in final machine code and launch attributes.
Correction: the FC1 source hints sum to53248, but the tested CUBIN reports REG32
and contains no SASS register-reconfiguration instruction. The source-hint sum
does not prove actual allocation or a one-CTA restriction. Shared intermediates require producer publication,
consumer-completion synchronization and explicit lifetime reuse. Individually
exact stages do not establish a connected cluster or end-to-end performance.

An independent H/O GDN fusion keeps original BF16 intermediate rounding and
passes90 real layer cases plus complete graph/state checks per variant. Yet
three repetitions show no useful complete-MixedGraph reduction. The first V32
variant doubles QK calculation relative to original O V64. Preserving V64
removes that duplication but raises shared/TMEM allocation and still regresses
the primary shape slightly. Eliminated intermediate bytes are not guaranteed
DRAM savings or speed: live values, resident blocks and chunk parallelism also
change. Both candidates stay out of production. No more tile sweep follows
these negative results, and none changes service acceptance or quality bounds.

The component evidence is
[pinned with all raw gates and repetitions](https://github.com/david6666666/drama-3-single-b300-inference/tree/f1dc31d57e4d29699a5bfbe5b0fc29ed5e163333/evidence/20261016-ceiling).
The component-only stage is superseded by the complete-call results below. C64 still needs
6765.407frames/s, all-concurrency repeated acceptance remains incomplete, and
no successful README example is claimed.


## Resident composition and M128 layout/resource evidence

The selected-expert resident FC1/activation/FC2 chain now passes489 exact checks
for valid rows0–8, including graph replay, five original numeric boundaries and
ownership. The native finalizer check substitutes only tested branches into an
otherwise native oracle and is explicitly oracle-assisted. Full256 routing and
performance are not implied. Actual complete launch uses79,488bytes perCTA and
one outer-owned TMEM allocation, not a sum of individual component estimates.
The initial host invocation passed compile-time constants to the runtime ABI;
its failure occurred before candidate kernel execution and remains archived.

An independently validated CuTe activation translation passes2066 checks; the
previous C++ helper's2063 checks were not inherited. A separate M128 FC1 attempt
fails its exact gate because four TMEM slices were stored as adjacent channels.
A fixed32-channel permutation explains the observed bytes but does not pass the
checker. The corresponding corrected M128 FC2 store preserves original K32/K128
arithmetic and passes306 expanded checks across15native oracles/all256experts.
The32,768 versus53,248 source-hint sums originally motivated a capacity
hypothesis. Final machine-code inspection rejects that occupancy inference;
the explicit correction and actual resource facts are recorded below.

The GDN H/O negative experiments were independently recomputed. Their pre/post
GPU process checks do not prove uninterrupted exclusivity; reports now state
that limitation. Both original local continuation gates still fail. Every new
component result remains below full-service acceptance scope, and C64's6765.407
frames/s target and confirmed WER/SIM requirements are unchanged.


## Complete-call evidence rejects both initial native MoE candidates

The resident chain now passes1371 full256-expert boundary/ownership checks;
its build without global debug exports passes1262 more, including empty work.
Yet all15 complete-call scenarios regress across three alternating repetitions.
Real layers0/19/39 are14.16%,21.51%,37.11% slower than the optimized vendor path.
Global intermediate traffic is a small part of expert-weight traffic. A fused
implementation also changes phase serialization, cluster synchronization and
PDL behavior; eliminating buffers alone does not imply a net speedup.

The M128 global-buffer body passes1253 checks and626 timed-run checks but only
reduces latency by1.304%,0.569%,2.871% in the three real cases. Each misses the
predeclared5% continuation gate. Preserve that failure even though some synthetic
routing cases improve more. Neither implementation is promoted into the service.

Native routing metadata can legally change physical row order between calls.
Check actual-map bijection, token/expert ownership, bounds and prefix counts
before comparing logical intermediate bytes. An archived physical mapping is
not an invariant. Both original harness failures remain preserved; no mapping
was inferred from output values and no numeric tolerance was relaxed.

Final SASS also corrects the earlier register explanation. The tested M64/M128
Prims TS and resident CUBINs report REG30–32 and no register-reconfiguration
instructions. Vendor FC1 reports REG128 and eight `USETMAXREG` instructions.
Searching only for `SETMAXNREG` misses that Blackwell spelling. The source
53,248→32,768 hint sums do not establish occupancy doubling. Actual thread and
shared-memory changes remain facts; performance attribution requires controls.

A more concrete prefix proposal preserves original prefill on misses and exports
FP32 recurrent state at an aligned internal boundary. Its CPU-only conservative
ready-cache budget is roughly0.243s; adding same-group forks gives roughly1.235s.
These are optimistic estimates, not observed savings. Same-group sharing needs
per-layer state forks and suffix-aware kernels; ordinary cache insertion does
not provide it. This route alone does not explain the missing service budget.

C64's target remains6765.407 frames/s, best complete-quality observation remains
4726.771, and all-concurrency repeated acceptance is incomplete. The next PDL
candidate has a separate protocol; it cannot retroactively pass either failed
complete-call experiment.

Completed-call evidence and the resource correction are [pinned at runtime 13d0566](https://github.com/david6666666/drama-3-single-b300-inference/tree/13d0566bf71b2ccf634c79cdef3aea938decc96e/evidence/20261016-ceiling).


## Enabled PDL still requires a useful dependency schedule

A separate M128 PDL-enabled candidate passes1498 exact checks, including empty
work and graph reuse with changed metadata. Its preliminary three real cases
reduce latency by1.988%,3.832%,6.315% in one AB round; the first two miss the5%
continuation criterion. Thus three-repetition timing and pressure-case timing
are not run. The raw feasibility schema's vacuous stress flag does not establish
stress performance. Preserve this scope explicitly when summarizing results.

Inspect where dependencies wait, not just whether PDL is enabled. The native FC2
can start weight loading before consumer waits, while this prototype blocks at
entry. Moving that wait requires an explicit proof for metadata visibility and
retained waits before activation-dependent reads. Neither machine-code inspection
nor an enabled launch flag proves useful overlap or a safe replacement schedule.
The follow-up remains a hypothesis, with unchanged service and quality targets.

The PDL feasibility and dependency audit are [pinned at runtime e347d15](https://github.com/david6666666/drama-3-single-b300-inference/tree/e347d15f872e685f66b2cecf37318a4565fd8f8f/evidence/20261016-ceiling).


## Metadata readiness and loaded-library identity

The separate metadata-ready FC2 candidate passes 1516 exact checks, including
all 15 layer/routing fixtures and the same captured graph moving from empty to
positive work and back. The graph guard records every metadata producer from
capture, adds a DEFAULT full-memory edge to FC2, and retains the original body
PROGRAMMATIC dependencies and their ports. Independent weight loading may start
earlier, but activation-dependent reads keep their original waits. The empty
probe has six captured metadata copies and two GEMMs; it does not assume empty
activation/finalizer semantics. Shape/configuration validators and retained IO
are checked before restricted execution and graph instantiation.

One AB screening of the three real layers reduces complete-MoE latency by
2.7294%, 3.1834% and 4.1453%. Every result misses the frozen 5% continuation gate,
so the launcher stops. Stress correctness is covered, while all 12 stress
performance cases and three-repetition timing are NOT_RUN, with an explicit
null stress-performance verdict. Input quantization and logits-to-top8 are
excluded equally from this local boundary. The conditional outer-model graph
integration design is CPU-only and is not implemented. No service or quality
promotion follows. Raw scope and commands are retained in
`expert-m128-pdl-metadata-ready/summary.md`; independent recomputation is in
`metadata-ready-independent-screen-review.json` under the pinned runtime tree.

A separate bounded dense-projection investigation first finds no algorithm
meeting the strict capability filter. The numerical follow-up keeps exactly two
serialized descriptors and their original BF16 input/output, FP32 compute and
reduction contracts. They pass 84 eager byte comparisons and 84 captured-graph
output/owner/guard/RNG checks on actual model projections. The non-split family
runs 30 calls in 0.3319395 ms with F.linear versus 0.3319917 ms explicitly; the
FP32-workspace split family runs 54 calls in 0.4124048 versus 0.4125987 ms. Neither
is selected. The final 223-call sequence has `replaced_calls=0`: both arms are
F.linear, so its roughly 0.0265 ms difference is A/A variation, not a saving.
The declared 0.3 ms continuation budget is unmet; no repeated or service trial
follows. These intercepted `model.linear` calls do not cover direct matrix
operations in every module. See `native-lt-real-contract/summary.md`.

Library identity is part of the numerical contract. Python Torch and ctypes
load the environment's cuBLASLt 13.1.1, while the initial C++ query accidentally
loads system 13.7 because inherited loader search paths override its RUNPATH.
A child-only path correction repeats the query against the same 13.1.1 binary;
the original cross-version evidence remains preserved. Matching library
identity does not resolve the reported input-precision capability discrepancy.
The two descriptors therefore remain numerical diagnostics, without native
runtime qualification, despite their finite-fixture byte equality. The
correction is recorded in `native-lt-dtype-contract/same-library-capability.json`.

Both experiments retain sampled process audits, which are not proof of
continuous exclusivity. Best complete-quality C64 observation remains 4726.771
frames/s versus the unchanged 6765.407 target. Repeated all-concurrency
acceptance and a successful README example remain incomplete. These scoped
results add portable review rules without changing imported catalog sources,
verification status, the original frozen plan or its validator.

The metadata-ready and dense-algorithm records are [pinned at runtime 22403f7](https://github.com/david6666666/drama-3-single-b300-inference/tree/22403f7589a1c9ca6264b003199d078c636196ed/evidence/20261016-ceiling).
