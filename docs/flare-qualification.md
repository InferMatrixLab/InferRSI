# Offline Flare delivery evidence

The adapter reads existing Flare qualification artifacts and writes a separate
receipt. It never launches Flare, downloads a model or executes imported code.
Run it with `python -m inferrsi.model.validators.flare`. The existing
`external_benchmark` scenario, `validation_command` and evaluator own execution
and verdicts.

## Supported source and metric

Input contract: Flare
[`bce032c014bae34502ba22d3304fa084d5b40afe`](https://github.com/NVIDIA/flare-local-inference/tree/bce032c014bae34502ba22d3304fa084d5b40afe).
The frozen readset is:

| Source | Contract used |
| --- | --- |
| [`qualify/performance.py`](https://github.com/NVIDIA/flare-local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/qualify/performance.py) — `validate_corpus`, `stream_request`, `analyze_events`, `idle_metrics`, `run` | Ordered corpus groups, request/token fingerprints, raw SSE and timestamped observations, native completion metadata, preparation capacity and raw counter snapshots |
| [`qualify/provenance.py`](https://github.com/NVIDIA/flare-local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/qualify/provenance.py) — `digest`, `file_record` | File-byte SHA-256 identities; source/package declarations remain distinct from runtime qualification |

Exactly one scalar is exported: `metrics.delivery_ttft_ns`. It is the median
first nonempty token-event arrival across **all measured `ttft-512` requests**
in the supplied complete corpus, in nanoseconds. Its clock domain is
`client.perf_counter_ns.elapsed`; comparison scope is
`flare_http_delivery_ttft_512`. Connection opening happens before the upstream
send barrier. HTTP delivery TTFT includes request/frontend/scheduling/delivery
work and does not isolate GPU prefill.

Native `token_timestamps_ns`, `ingress_ns` and `enqueue_ns` are checked within
their own domain. They are never subtracted from client timestamps. One SSE
event containing several token IDs remains one arrival group. Such groups do
not establish exact per-token delivery intervals.
The pinned [native observation contract](https://github.com/NVIDIA/flare-local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/model-contract.md)
allows `usage=null` on preceding chunks; the adapter ignores null optional
metadata and uses the actual terminal usage/timing records.

## Packet schema v1

A packet is a caller-assembled directory with `packet.json` and unchanged source
artifacts beneath the same root. Paths are root-relative; external paths and
symlink escapes are rejected. The output receipt must be outside that directory.
The wrapper does not change the upstream JSON or raw SSE formats.

| Manifest field | Required value / meaning |
| --- | --- |
| `schema` | `inferrsi-flare-delivery-packet-v1` |
| `source` | Exact `repository`, `revision` and ordered `readset` object from `SOURCE` in the adapter |
| `metric` | Exact `key`, `unit`, `clock_domain`, `grouping`, `comparison_scope` object from `METRIC` in the adapter |
| `synthetic` | Explicit boolean; `true` for constructed fixtures |
| `package` | Path to actual package bytes; synthetic fixtures use an explicitly labelled non-model file |
| `corpus` | Path to the frozen `flare-http-performance-v1-corpus` JSON |
| `memory_report` | Path to the actual preparation memory report, including `prefill_chunk_size` |
| `measurements` | Path to the completed native Flare `measurements.json` |
| `run` | Root-relative directory containing upstream per-group artifacts |
| `snapshots` | Map from every corpus group ID to `[before_path, after_path]`, selecting the raw idle `/metrics` captures used for that group |
| `files` | Map from every referenced asset path to its SHA-256; includes package, corpus, memory report, measurements, selected snapshots and per-request `request.json`, `observation.json`, `response.sse` |

The complete ordered upstream matrix is required: warmup, both TTFT lengths,
decode concurrency 1/2/4, 65536-token prefill, prefix seed and prefix hit for
each declared repetition. Warmup and prefix seed are checked but excluded from
the exported TTFT samples. Missing/duplicate groups or requests cannot be filled
with zeroes. The adapter checks corpus token geometry and recorded fingerprints;
it does not load a tokenizer or prove that a rendered prompt tokenizes correctly.

Each observation must match its sidecar and raw SSE payloads, successful HTTP
completion, terminal DONE, prompt/output/usage counts and sent request identity.
Coalesced groups must agree with any recorded grouping analysis. Summary TTFT
numbers are not metric inputs. Explicit failed qualification/group flags and
stream errors remain rejections even if other raw checks pass.

The native `prefill_chunk_size` label must match the preparation report. Selected
raw snapshots must contain unlabelled integer samples for the scheduler gauges,
completed/failed/cancelled request counters, reused-token counter, and free/cached
KV-page and snapshot/checkpoint gauges named in the adapter. Duplicate samples,
missing values, nonfinite values, non-idle schedulers, incorrect request/reuse
deltas and resource-conservation failures reject the packet. A cache lookup hit
does not substitute for actual `reused_prompt_tokens`: cold cases require zero,
and the pinned prefix-hit cases require 4096, agreeing with raw counter deltas.
P0 does not reconstruct offload admission decisions or implement a cache policy.

## CLI and existing runner integration

Both measurement commands must name their peer. Before exporting either metric,
the adapter validates both packets and requires matching source, metric contract,
synthetic status, package bytes, corpus bytes and prepared capacity. This keeps
an incomplete or incomparable pair out of the evaluator's performance inputs.

```text
python -m inferrsi.model.validators.flare measure \
  --packet <baseline>/packet.json --peer <candidate>/packet.json \
  --output <receipts>/baseline.json

python -m inferrsi.model.validators.flare validate-pair \
  --baseline <baseline>/packet.json --candidate <candidate>/packet.json \
  --output <receipts>/pair.json
```

For `RunSpec`, use these argv sequences:

```python
cli = (python, "-m", "inferrsi.model.validators.flare")
baseline_command = cli + (
    "measure", "--packet", baseline, "--peer", candidate, "--output", "{result}",
)
candidate_command = cli + (
    "measure", "--packet", candidate, "--peer", baseline, "--output", "{result}",
)
validation_command = cli + (
    "validate-pair", "--baseline", baseline, "--candidate", candidate, "--output", "{result}",
)
```

Set `scenario="external_benchmark"`, `metric_key="metrics.delivery_ttft_ns"`,
`metric_unit="ns"`, `direction="minimize"` and
`comparison_scope="flare_http_delivery_ttft_512"`. The ordinary RunSpec controls
the comparison threshold and trial count. Re-reading one packet several times
does not create independent service measurements; freeze independent captured
inputs when designing a real campaign.

Exit zero means the offline contract passed. Invalid/incomplete evidence returns
2 and writes a rejection receipt with **no metric**. Through the standard
executor this is an incomplete measurement, so the existing evaluator retains
`INCONCLUSIVE`. A valid pair's receipt is suitable for the fixture integration
test's `validation_command`; a real campaign must also include its separately
frozen task-quality validator. Pair consistency is not a model-quality oracle.
Hardware equality, workload representativeness and actual measurement execution
remain campaign acceptance requirements.

The receipt retains per-request groups and selected samples, packet/asset hashes,
source/readset, package/corpus identities, actual prepared capacity, and hashes
of the adapter and its artifact helper. These bind the receipt to the supplied
bytes; they do not attest that a package was built from a declared source or
qualify its ABI/model/frontend compatibility. ABI/preparation preflight and
session-state recovery scenarios remain separate future work.

## Reproducible synthetic sample and negative cases

From a development checkout with InferRSI installed:

```text
python tests/fixtures/flare_packet.py <sample-directory>
python -m inferrsi.model.validators.flare measure \
  --packet <sample-directory>/packet.json --peer <sample-directory>/packet.json \
  --output <outside-sample-directory>/receipt.json
pytest tests/test_flare_adapter.py
```

The fixture writer saves a complete one-repetition packet, including raw SSE,
coalesced token events, a prefix-hit case and before/after resource snapshots.
It labels every packet `synthetic=true`; no tokenizer, model, server or device
is used. Synthetic delivery timings and model/package placeholders are parser
test inputs, not measured service results.

Tests cover raw recomputation and unchanged originals; missing raw/group/request
records; wrong clock declarations; invented coalesced-token timing; capacity,
counter and resource mismatches; stream failures and digest drift; pair scope;
and real local runner execution of both adapter commands. Fixture acceptance
does not establish service quality, a performance gain or agent efficacy.
