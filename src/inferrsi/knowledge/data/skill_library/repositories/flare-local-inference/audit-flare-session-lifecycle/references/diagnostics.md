# Admission and restoration diagnostics

These are proposed source-grounded diagnostic cases, not reproduced incidents.
F1–F7 resolve in [source notes](source-notes.md). Use retained observations;
running the server or altering files needs its own authorization.

## Admission outcomes

`server/runtime.rs::admit_with_host_store` maps the actual branches to
`offload::LookupOutcome` (F3/F5). It can reject an expensive deepest endpoint
and then try a shallower one, so outcome counters are not necessarily one
mutually exclusive final value per user request.

| Outcome | Actual condition | Next observation / action |
|---|---|---|
| `NoMatch` | Initial lookup yields no eligible host chain above the GPU-resident endpoint | Check model/layout namespace, history, endpoint row, required ancestors and whether the GPU already covers the useful prefix |
| `CostRejected` | A found chain fails `worth_fetching`; lookup continues strictly below its endpoint | Retain endpoint, resident tokens, estimated seconds, tier and effective prefill rate; inspect any shallower accepted chain |
| `CapacityRejected` | Host-aware `admit_planned` returns an admission-capacity error | Inspect free/reserved page and snapshot counts and active tickets; normal admission is attempted, so distinguish host reservation pressure from an invalid request |
| `EnqueueRejected` | Reservation succeeded but `store.fetch` returns error and no future event is promised | Confirm ticket failure/cleanup and ordinary re-admission; inspect queue/store disposition rather than waiting for a nonexistent `Fetched` |
| `Admitted` | A new fetch is enqueued, or the request joins an existing ticket with no new fetch | Correlate key → completion → publication → `Restore` → actual reused tokens; admission is not completed restoration |

The pinned policy is

```text
estimated_seconds < 0.5 * (consumed_tokens - resident_tokens)
                        / max(prefill_tokens_per_second, 1)
```

It compares transfer time with the **additional** prefill avoided. Equality
rejects. Initial memory/disk/prefill estimates are bootstraps, not measured
bandwidth guarantees; later estimates depend on the source's observations.
This is an upstream strategy example for its workload and cost model, not an
InferRSI acceptance threshold or universal recommendation.

For example, an endpoint of 32,000 tokens above 24,000 resident tokens saves
8,000 tokens. At a 4,000 token/s prefill estimate its permitted transfer is
strictly below 1 second. A 1.2 second transfer is rejected even though using
the entire 32,000-token prefix instead of the additional 8,000 tokens would
appear attractive.
These numbers explain the inequality; they are not device measurements.

## Incomplete recovery after restart

**Symptom:** a matching `.ckpt` filename exists, but no safe continuation is
restored, or a prior hit becomes a miss.

P: Check the record header/version, namespace identity and layout fingerprint;
then check row presence and the entire required chain back to the actual GPU
resident ancestor. `record::scan` validates structural identity/shape and
prunes invalid/orphaned records; payload corruption can still be detected
during fetch. A file with complete pages but no row remains page-only and can
supply ancestors, while it is unusable as a restore endpoint. Permission or
device read errors fail the scan and retain the file; they are not ordinary
cache misses or permission to delete a chain (F3).

**Counterexample:** recovering full KV pages but omitting the endpoint's
partial tail/recurrent/convolution row cannot reproduce the session state.
The server test source corrupts record payloads and expects fetch failure,
zero restore launches and normal initialization/prefill, followed by a
consistent subsequent answer (F6). This is a test assertion, not a local pass.

**Next evidence:** the selected namespace and record headers; the deepest
candidate and rejected ancestor/row; fetch failure versus restored token count;
settled `flare_host_cache_fetch_failed_total`, restore/init launch and prefill
token deltas. Do not accept partially copied bytes as a successful checkpoint,
or delete a valid namespace simply because another configuration cannot use it.

## Version mismatch at the preparation boundary

**Symptom:** package load rejects an execution contract or prepared contract.

P: Read all version domains independently. `execution::ABI_VERSION` is 4;
`Package::validate` rejects a different execution ABI and
`PreparedContract::validate` rejects a prepared version other than 2 (F1).
The loader decodes the typed prepared contract and validates embedding-table
references. A format/carrier version cannot substitute for either contract.

**Next action:** identify the actual exporter/source pin, package identity and
required runtime; re-export with the matching preparation path when authorized.
Do not edit a version number to silence validation or claim that Python graph
handles can be reused in another process. See the existing loading owner's
[preparation reference](../../../../methods/weight-loading-optimization/references/flare-preparation-boundary.md).

## Cancelled request while restore is in flight

**Symptom:** client disconnected but pages/snapshot or a parent pin remain held.

P: Check whether the request was only a waiter on a scheduler-owned ticket.
Removing the last waiter still does not cancel an accepted DMA transfer.
The ticket can complete into a useful checkpoint with zero waiters (F4).
Demand the transfer completion record before treating retained resources as
a leak. Conversely, a missing or failed drain is not permission to recycle
the IDs. Separate a fetch-enqueue rejection, confirmed fetch failure and
unaccountable transport failure; their release conditions differ (F3/F5).

## Lookup hits without verified reuse

**Symptom:** host-hit counters rise, but useful prefill or request latency does
not improve.

P: Join records by request and prefix key. Keep lookup eligibility, each cost
decision, admission, completed fetch, published checkpoint, `Restore` and actual
reused tokens distinct. Scheduler host-hit/reused-token counters increment on
inbound admission, before `finish_inbound`; pair them with `Fetched`, actual
`Restore` execution and request/result evidence. Check complete generated output and prefill work before
interpreting a latency difference. Metric deltas require a settled interval and
known concurrent workload; a process-wide hit count alone cannot identify one
request (F5/F7).

**Counter-signals:** cost rejects a genuine match; capacity rejects a feasible
host chain; an admitted waiter shares an existing transfer; a completed fetch
has no surviving waiters; delivery overhead hides saved native work. None is
equivalent to corruption.

## Mixed clocks or token groups

**Symptom:** negative, implausible or overstated first-token/per-token timing.

P: `stream_request` timestamps completed SSE events using client
`perf_counter_ns` relative to that request's start. `analyze_events` preserves
tokens arriving in one event as a group; it does not invent intra-group arrival
times. Native timestamp metadata is in a separate process-relative domain.
Compute delivery TTFT/ITL from client arrivals and native core durations from
native endpoints; never subtract a client absolute time from a native absolute
time (F7).

The qualification source defines core TTFT from native chat-handler entry
after JSON extraction to CPU token observation after scheduler completion.
It is not pure GPU prefill time. HTTP-derived prompt-tokens/TTFT throughput is
also a delivery metric, not a kernel throughput measurement. Verify raw SSE,
request/corpus hashes, grouping and observation identity before aggregation.
`provenance::file_record` identifies exact file bytes; a declared checkout or
package digest does not establish that a backend path executed (F7).
