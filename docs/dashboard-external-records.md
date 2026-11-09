# External optimization records in the dashboard

A campaign with no candidate/run records is **not connected**, not a successful
comparison. `stages_declared: []` explicitly declares no applicable stages;
omitting the field leaves unobserved stages **not recorded**. Do not set an empty
list merely because a backend has no built-in collector.

For existing Ascend experiments, a caller may adapt their artifacts into native
candidate rows without manufacturing a CUDA run or evaluation. Create
`candidates/<candidate-id>/candidate.json` with `candidate_id`, `title`, and
`external_record_ref: {"path": "records/<record>.json", "sha256": "<sha256>"}`.
Paths are campaign-relative and hashes cover exact file bytes. These candidates
must not also name a harness run. The external record has this shape (illustrative
values only):

```json
{
  "schema_version": 1,
  "kind": "external_optimization_record",
  "candidate_id": "example",
  "backend": "ascend",
  "protocol": "example-two-service-protocol",
  "state": "completed",
  "source_refs": [{"path": "sources/result.json", "sha256": "<sha256>"}],
  "performance_verdict": "INCONCLUSIVE",
  "quality": {"verdict": "NOT_RUN"},
  "metrics": [{
    "name": "example-tier", "unit": "ms/token",
    "baseline": 42, "samples": [40, 38],
    "aggregate": 39, "aggregation": "two_round_median", "target": 25
  }],
  "events": [{"stage": "validation", "time": "2026-01-01T12:00:00Z",
              "summary": "Two service records captured; quality not run"}],
  "note": "Recorded intermediate measurements, not final acceptance."
}
```

All source references must resolve with matching hashes. No automatic directory
scan or inference of verdicts is performed. Publish immutable content-addressed
source and record files first, then atomically replace candidate metadata. A
partial file, hash mismatch, mismatched candidate or malformed record is withheld;
the UI reports missing evidence rather than an invented success.

This version represents lower-is-better latency metrics; absolute target gaps
are aggregate minus target. Each metric supports a positive parent, up to two positive samples, a positive
aggregate and target; omitted values remain unrecorded. `two_round_median`
requires two samples and their arithmetic midpoint, accepting floating-point
serialization differences with relative tolerance `1e-9` and absolute tolerance
`1e-12` in the metric unit. This is not a measurement/noise tolerance; coarser
rounding must not be used to change a recorded aggregate. The caller value is
preserved. Records without metrics stay in candidate/event views and are counted
in the chart note; no measurement is fabricated. Keep concurrency tiers and
protocols separate. Absolute plots do not establish cross-run comparability.
Performance and quality verdicts remain separate; quality may include `correct`
and `total`. Neither an external PASS nor a source hash promotes a record into
the generic verified gain ranking. Hashes establish bytes, not the correctness
of the caller's mapping, frozen gates, execution, or experimental conclusions.
Only recorded events populate workflow stages. Summaries are explicitly distinct
from a full campaign optimization log; use `campaign log` for that history.

Optional `environment` keys `hardware`, `runtime`, `model`, `workload`, `protocol`
and `source` accept SHA-256 fingerprints for caller-declared identity completeness.
They do not certify comparable experiments. For native harness runs the environment
signature additionally accepts `backend: ascend`: verified device selection with
UUID, name and driver; host platform; target Python and package versions including
`torch`, `vllm`, `torch_npu`, `vllm_ascend`; and
`ascend: {cann_version, firmware_version}`. Existing RunSpec, workload, source and
command comparisons still apply. Missing runtime identity remains unverified.

Collectors and campaign-specific paths, targets and revision pins belong outside
the shared dashboard. Collect existing files read-only, label freshness and
missing history, and preserve failed, partial and running attempts.

Collectors can atomically update campaign metadata with
`collection: {"state": "live" or "stale", "observed_at": "<ISO-8601 timestamp>"}`.
The UI shows this source timestamp separately from the browser's connection to
the dashboard. On collection failure, mark it stale and keep the last complete
source set; a successful HTTP refresh alone does not mean the source is fresh.
