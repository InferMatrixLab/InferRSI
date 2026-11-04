# Approved 8K statistical decision component

Refs [Issue #67 owner decision](https://github.com/InferMatrixLab/InferRSI/issues/67#issuecomment-6357921043).
The owner explicitly approved the pending statistical question in the active
conversation. This prospective record supersedes the pending-statistics wording
in earlier proposals and the 8K scope amendment. Those historical bytes remain
unchanged. No historical diagnostic is upgraded to formal acceptance.

For each of TTFT and TPOT, pair the same ten fixed 8192-token input IDs and
three repetition IDs across baseline and candidate. Each request must generate
2048 actual tokens. The primary statistic is the median of all 30 paired
candidate/baseline ratios. Resample ten input IDs with replacement as clusters,
retaining the three repetitions within each sampled input, for 10000 draws
using Python random.Random seed 670032. Reuse the same sampled indices for both
metrics. Quantiles use linear interpolation; the 95th percentile of bootstrap
medians is the one-sided upper bound.

A metric is PASS only when both median and upper bound are <=1.03. A median
above1.03 is FAIL; median<=1.03 with upper>1.03 is INCONCLUSIVE. This does not
claim simultaneous confidence for both metrics or quantify shared service
restart effects. All raw samples and repetition-level results remain required.

The versioned reducer in validator/statistics-8k-v1 checks the complete60-row
matrix, identity types, duplicate records/JSON keys, actual output counts,
positive finite measurements and finite ratios. TPOT is derived as
(latency-TTFT)/2047. Invalid or incomplete input emits no metric verdict.
The valid flag must be independently authenticated from the original client,
wire response and protocol evidence. This reducer cannot authenticate a caller's
flag, hardware, source, model, cleanup or task quality; campaign_verdict therefore
remains INCONCLUSIVE. statistics_approved records owner policy only and is not
full campaign activation. The request timeout belongs to the separate execution
protocol; the numeric reducer introduces no unapproved latency cap.

The old three-length proposal remains byte-for-byte intact. The new component
uses8192 only. Synthetic checks are CPU-only, consume no GPU budget and are not
model measurements. The surrounding full plan, runtime/source/quality bindings
and execution commands still require completed qualification and freeze before
formal candidate search. Approved phased GPU caps remain2/4/8/30GPU-hours.
