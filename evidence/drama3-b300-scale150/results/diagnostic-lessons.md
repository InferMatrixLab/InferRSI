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
