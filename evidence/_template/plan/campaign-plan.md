# Campaign Plan: `<campaign-id>`

Copy this file with the rest of `evidence/_template/` into
`evidence/<campaign-id>/plan/`. Fill every `<...>` placeholder before the first
candidate search, and keep the filled table in the campaign's `plan/` segment.

**Fixed rules** (identical in every campaign, not editable per campaign): no
shrinking the real workload; no replaying or caching final outputs; no reuse of
stale cross-request state; no dropping failed requests; no hard-coding results to
samples; no modification of a frozen row, the baseline or the validator. An
imported or author-reported number is prior evidence and never the baseline for a
`PASS`. Missing required evidence yields `INCONCLUSIVE`, never `PASS`.

## Header

| Field | Value |
| --- | --- |
| Campaign ID | `<campaign-id>` |
| Accountable owner | `<accountable-owner>` |
| Goal-acceptance owner | `<goal-acceptance-owner>` |
| Acceptance issue | `<issue-url>` |
| Base revision | `<40-hex-revision>` |
| Plan revision | `<n>` (`<YYYY-MM-DD>`) |

## The plan

Rows 1, 2, 3, 5, 6 and 7 are the frozen comparison contract. Row 4 is the
versioned search strategy and search state, and is expected to change.

| # | Row | Freeze | Content |
| --- | --- | --- | --- |
| 1 | Model | Frozen | repository `<org/model>` · exact revision `<40-hex>` · weight format `<...>` and hash `<sha256 or declined with reason>` · tokenizer and template `<...>` · modality and task `<...>` · precision policy `<...>` · supported modes `<...>` · excluded modes with expected error `<...>` · semantic reference `<framework@revision>` · performance baseline identity `<...>` · license `<...>` |
| 2 | Hardware | Frozen | backend `<...>` · vendor and exact SKU `<...>` · device count `<n>` and IDs `<...>` · visibility mechanism `<...>` · per-device memory `<...>` · interconnect and topology `<...>` · host CPU, NUMA and RAM `<...>` · OS, driver and firmware `<...>` · runtime, compiler and container digest `<...>` · qualification status `<validated\|unsupported\|unverified>` with evidence `<path>` · exclusivity record `<allocation owner and pre/post device snapshot>` |
| 3 | Optimization goal | Frozen | primary metric `<metric>` in `<unit>`, `<minimize\|maximize>` · target line per load level `<level: target>`, relative to a locally measured baseline · combination rule `<which levels must improve, which must not regress>` · quality gate with exact rows `<...>` and tolerant rows `<metric: threshold>` · sample identity recorded separately from the tolerance gate `<...>` · guard metrics `<peak memory, failure rate, percentile latency>` · required validation levels `<ladder and level names>` |
| 4 | Iteration search plan and state | **Mutable, versioned** | search state: incumbent revision and its evidence `<... or TBD>` · parent of the next candidate `<revision>` · isolation `<separate directory or environment>` · import path `<exact path the candidate uses>`. Entries: one per direction, in the format below |
| 5 | Test plan | Frozen | load-test concurrency set `<levels>` · requests per repetition `<n>` and repetitions `<n>` · dataset or corpus with hash `<sha256>`, seeds `<...>` and held-out split `<visible to the implementer or hidden>` · held-out release point and use limit `<...>` · benchmark command `<command>` and timing boundary `<client_full_response\|server_inference\|offline_pipeline_with_sync>` · excluded from timing `<...>` · warmup protocol `<...>` · AB/BA pairing count `<n>` · quality script `<path>` and judge `<...>` · statistical method `<baseline sample size per dominant stage and rollback line>` · validator `<path>` and input hashes `<sha256>` · abort and resume policy `<on crash, timeout, OOM or lost device>` |
| 6 | Budget and stop conditions | Frozen | candidate cap `<n>` · round cap `<n>` · device-hour cap `<n>` · retry cap `<n>` · per-round planned versus spent accounting `<...>` · acceptance-regime reserve `<sized from measured restart and warmup cost>` · stop conditions `<target met, two rounds below noise, budget exhausted, direction list exhausted, evidence insufficient>` |
| 7 | Control and authority | Frozen | owner of the device `<...>`, the validator `<...>` and the freeze `<...>` · who may revise which row `<...>` · generator and evaluator separation and how it is enforced `<separate account, container, read-only mount or manual import>` · held-out release authority `<...>` |

## Row 4 entries

```text
D-01 | plane=<model|infra|harness> | stage=<stage>, <measured share> of E2E
     | headroom=<conditional removable exposed time, assumptions, target/noise comparison and uncertainty>
     | diagnostic=<if attribution is unresolved: observation, cost cap within row 6 and kill criterion; otherwise none>
     | hypothesis=<one line> | mechanism=<config|ownership/layout|fusion/operator|graph/launch|residency/memory|parallelism/communication|precision/approximation>
     | risk=<lossless-exact|tolerance-gated|semantics-changing> | cost=<static|microbench|profile run|scenario@c1|multi-regime|full cohort>
     | prior=<casebook entry or none> | kill=<what ends this direction> | status=<planned|running|kept|rejected|blocked> | evidence=<path>
```

One variable per round and one plane per step. Justify conditional headroom
against the campaign target and locally measured noise, following
[performance-ceiling-analysis](../../../skills/performance-ceiling-analysis/SKILL.md)
and its [bounds guidance](../../../skills/performance-ceiling-analysis/references/papers-20261015/knowledge/bounds-predictions-and-decisions.md).
Record conditionally removable exposed critical-path time, assumptions and
uncertainty. A non-dominant stage is not by itself a reason for rejection:
overlap, synchronization, capacity, queueing, batching and bottleneck migration can
change its E2E impact. Overlapping kernel durations are not an additive E2E
decomposition. If attribution is unresolved, allow a bounded diagnostic with a
discriminating observation, explicit cost cap within row 6 and kill criterion.
Stop at the cap; unresolved evidence remains `INCONCLUSIVE` and cannot justify
promotion. A matching negative record raises the burden of justification and
requires the changed condition to be stated. Untried directions stay listed. Each
round names its parent revision, builds the candidate in an isolated directory or
environment, and records the exact import path. An entry's hypothesis, mechanism
and kill criterion freeze at its first run; a later change is a new entry ID.

## Row 4 change log

| Plan revision | Date | Entry | Change | From | To | Reason | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `<n>` | `<YYYY-MM-DD>` | `<D-xx>` | `<added/edited/blocked/promoted>` | `<previous statement or none>` | `<new statement>` | `<why>` | `<path or negative result>` |

Append history; never rewrite it. Rows 1, 2, 3, 5, 6 and 7 may not be edited after
the first candidate search: a change to any of them starts a new campaign ID with
its own plan and acceptance issue. Before search, retain the original plan
snapshots and `freeze.json`, including the validator hashes. Preserve each later
plan revision with its own whole-file hash manifest; never overwrite earlier
snapshots or manifests. For every row-4 revision, manually compare every frozen
field in both representations against the original snapshots and link the
comparison record from the change log's evidence field. Any frozen-field change
starts a new campaign; validator hashes must remain unchanged. Whole-file hashes
identify revision integrity, not proof that the frozen comparison contract is
unchanged. No row-level hashing is assumed.

## Fill-in checklist

- [ ] every `<...>` placeholder is replaced or explicitly resolved as `<TBD>`
- [ ] no frozen row was edited after the first candidate search
- [ ] original snapshots and manifest are retained, and every row-4 revision
      links a manual comparison of all frozen fields against those snapshots
- [ ] `freeze.json` lists `plan/campaign-plan.md`, `plan/campaign-plan.yaml` and
      the validator, with current hashes; earlier revisions and manifests remain
      available and validator hashes are unchanged
- [ ] the acceptance issue links this plan and names the same base revision
