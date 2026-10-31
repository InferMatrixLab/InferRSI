# Transferable observations from this campaign

These are scoped observations backed by the linked receipts, not a completed
performance acceptance or new repository-wide policy. Governing issue:
[InferRSI #293](https://github.com/InferMatrixLab/InferRSI/issues/293).

| Observation | Evidence | Consequence for another experiment |
| --- | --- | --- |
| A reply can precede peer cold-decode completion. | [Audio baseline](audio-ab-baseline.json): warmups 325.26/256.12 s, then measured requests near 196.67 s. Per-rank traces are described in the campaign README. | Freeze a warmup policy for both arms and retain warmup timings. A single post-warmup request can include residual cold work; do not rank steady-state configurations from it. Two warmups are this campaign's choice, not a universal rule. |
| Fewer replicated decoder calls did not improve the measured steady-state objective. | [Audio selection](audio-owner-selection.json): 196.67 to 199.09 s in one paired pilot; the implementation was removed. | Test the requested E2E objective before retaining an apparently cheaper local operation. Keep the rejected result and its source revision. |
| Server/container exit zero does not prove clean worker shutdown. | Original dense and Cache-DiT screening forced workers; the [later production candidate](audio-ab-candidate.json) records all eight actual worker exit codes. | Capture worker exits and forced signals separately from HTTP success and container exit. A longer diagnostic grace must not be presented as an unchanged production baseline. |
| An error named for DLO can guard execution without DLO. | [KV timeout](reference-kv2-failure.json) and [HSDP timeout](hsdp-screening-failure.json): both hit the common 600-second execution deadline. | Inspect the call path and set matched execution and HTTP deadlines before a long workload. Raising a deadline is not a speedup. An interrupted profiler timer is not a completed inference result. |
| A configured cache limit is not necessarily the observed hit sequence. | [Installed-backend counter probe](cache-counter-probe.json), plus retained actual hit indices in screening receipts. | Pin the cache library and record observed reuse. Do not silently relabel old measurements or assume a parameter name proves behavior. This probe is narrower than a complete cache-policy correctness test. |
| Transfer volume is a hypothesis generator, not a causal speedup measurement. | [Host KV failure](reference-kv2-failure.json) retained 167.09 GB H2D per rank; [device-residency CPU checks](reference-kv-residency-cpu.json) establish payload behavior only. | Isolate residency at the same refresh interval, measure actual device memory, then validate the final combined configuration. Neither byte counts nor CPU parity establish NPU E2E benefit. |

The complete paired timing campaign belongs in one device reservation. CPU media
scoring is scheduled after timing so it does not compete with the timed host
work. Multiple requests within one server remain distinct from independent
process rounds. Every final accepted configuration still requires output gates,
request completion and lifecycle evidence at the final source revision.
