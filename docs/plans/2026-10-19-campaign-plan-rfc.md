# [RFC] Iteration Campaign Plan: one table for model, hardware, goal, search plan and test plan

> Status: Proposed. Base revision `f55b4bc`, 2026-10-19.
> Creates no threshold, revision pin, campaign or execution authority.
> Filed as [issue #30](https://github.com/InferMatrixLab/InferRSI/issues/30).

| Item | Value |
| --- | --- |
| Scope | `evidence/_template/plan/`, the campaign acceptance form, template layout tests |
| Out of scope | CLI and runtime code, the four CI lanes, hardware runs, new skills, in-tree numeric defaults, engine implementation |
| Reuses | The [Drama3 plan.json](../../evidence/drama3-b300-scale150/plan/plan.json) key names and the [freeze.json](../../evidence/drama3-b300-scale150/plan/freeze.json) hash-freeze mechanism |
| Deliverables | One template slice and one test slice, as separate reviewable PRs |

## 1. The table

`evidence/_template/plan/campaign-plan.md` **is** this table;
`campaign-plan.yaml` is the same seven rows as machine-readable keys, preceded by
the fixed preamble in section 3. Header
fields: campaign ID, accountable owner, goal-acceptance owner, acceptance issue
link, base revision, plan revision.

| # | Row | Freeze | Required content |
| --- | --- | --- | --- |
| 1 | Model | Frozen | repository · exact revision · weight format and hash · tokenizer and template · modality and task · precision policy · supported modes · excluded modes · semantic reference · license |
| 2 | Hardware | Frozen | backend · vendor and exact SKU · device count and IDs · visibility mechanism · per-device memory · interconnect and topology · host CPU, NUMA and RAM · OS, driver and firmware · runtime, compiler and container digest · qualification status · exclusivity record |
| 3 | Optimization goal | Frozen | primary metric, unit and direction · target line per load level, relative to a locally measured baseline · quality gate with exact and tolerant rows · guard metrics (peak memory, failure rate, latency or RTF percentiles) · required validation levels |
| 4 | Iteration search plan and state | **Mutable, versioned** | one entry per direction: ID · plane · target stage and its measured exposed share of E2E · conditional headroom with assumptions, target/noise comparison and uncertainty · bounded diagnostic if attribution is unresolved · hypothesis · mechanism class · risk class · cost tier · prior art or negative record · kill criterion · status · evidence link. Search state: current incumbent revision and its evidence link · parent of the next candidate · isolation and import path used |
| 5 | Test plan | Frozen | load-test concurrency set · requests per repetition and repetition count · dataset or corpus with hash, seeds and held-out split · benchmark command and timing boundary · warmup protocol · AB/BA pairing count · quality script and judge · statistical method and rollback line · validator path and hashes · held-out release point and use limit · abort and resume policy |
| 6 | Budget and stop conditions | Frozen | candidate and round cap · device-hour cap · retry cap · per-round planned versus spent accounting · stop conditions · reserve held back for the formal acceptance regime |
| 7 | Control and authority | Frozen | owner of the device, the validator and the freeze · who may revise which row · generator and evaluator separation and how it is enforced · held-out release authority |

Rows 1, 2, 3, 5, 6 and 7 are the **frozen comparison contract**. Row 4 is the
**versioned search strategy and search state** that is expected to change.

Row 4 entry format:

```text
D-01 | plane=model | stage=prompt encode, 23% of E2E | hypothesis=... | mechanism=ownership/layout
     | headroom=<conditional removable exposed time, assumptions, target/noise comparison and uncertainty>
     | diagnostic=<observation, cost cap within row 6 and kill criterion, or none>
     | risk=lossless-exact | cost=scenario@c1 | prior=casebook#qwen-ascend | kill=... | status=planned
```

Mechanism classes are tags: config, ownership/layout,
fusion/operator, graph/launch, residency/memory, parallelism/communication,
precision/approximation. Entries reference relevant [Reference Matrix](../reference-matrix.md)
sources and [SearchSpace Matrix](../searchspace-matrix.md) resource × stage cells;
they do not duplicate global coverage or validation status. Risk classes:
lossless-exact, tolerance-gated, semantics-changing. Cost tiers, cheapest first: static/config, microbench,
profile run, scenario at concurrency 1, multi-regime, full cohort.

## 2. Freeze semantics

| Change | Allowed | Requirement |
| --- | --- | --- |
| Row 4: add, block, or edit an entry that has not yet run | Yes | New plan revision with date, entry diff, reason, and the evidence that motivated it. History is appended, never rewritten |
| Row 4: change an entry's hypothesis, mechanism or kill criterion after its first run | No | Create a new entry ID instead; a stated kill criterion is immutable once that entry has run |
| Row 4: promote an entry to `kept` | Yes | Re-run that entry's own required validation levels |
| Row 4: advance the incumbent | Yes | Only once the promotion rule and the frozen test plan are satisfied; record the new incumbent revision and its evidence link |
| Freeze manifest (`freeze.json`) | Yes, required | Retain the original snapshots and manifest; preserve each revision and its whole-file manifest. Manually compare all frozen fields in both representations against the originals and link the record from the change log. Hashes identify revision integrity, not unchanged-contract evidence; validator hashes remain unchanged |
| Rows 1, 2, 3, 5, 6 and 7 | No | New campaign ID, new table, new acceptance issue; previous evidence is retained and stays cited |
| Row 5 after results exist | No | Thresholds, concurrency set, corpus and validators are never edited after the fact. A validator modified after freeze makes the campaign `INCONCLUSIVE` |
| Row 6 budget | Bounded | Only the authorized owner, recorded as a new plan revision; the acceptance reserve is never spent on exploration |

## 3. Filling rules

The template opens with a fixed preamble, identical in every campaign and not
fillable: no shrinking the real workload, no replaying or caching final outputs,
no reuse of stale cross-request state, no dropping failed requests, no
hard-coding results to samples, and no modification of a frozen row, the baseline
or the validator.

**Row 1 —** the semantic reference and the performance baseline are different
identities; name both. A weight hash is required or explicitly declined, and
declining downgrades weight-integrity claims.

**Row 2 —** qualification is per combination (`validated`, `unsupported`,
`unverified`) with an evidence pointer. "Same hardware class" is not "same
device"; a backend name is not a compatibility claim; tool presence is not model
support. Re-run the qualification probe every round: if the stack or the device
state has drifted from the frozen row, stop the round and re-enter it or mark it
`INCONCLUSIVE`.

**Row 3 —** the target line is relative to a locally measured baseline; an
imported or author-reported number is prior evidence, never the baseline. Exact
and tolerant quality rows stay separate: image RGB and alpha checked separately,
pixel identity is not the tolerance gate. State the combination rule: which load
levels must improve, and which must not regress beyond the rollback line.

**Row 4 —** one variable per round and one plane per step per
[AGENTS.md](../../AGENTS.md). Justify conditional headroom against the campaign
target and locally measured noise using
[performance-ceiling-analysis](../../src/inferrsi/data/skill_library/methods/performance-ceiling-analysis/SKILL.md)
and its [bounds guidance](../../src/inferrsi/data/skill_library/methods/performance-ceiling-analysis/references/papers-20261015/knowledge/bounds-predictions-and-decisions.md).
Record conditionally removable exposed critical-path time, assumptions and
uncertainty, including overlap, synchronization, capacity, queueing, batching and
bottleneck migration. A non-dominant stage is not by itself a rejection reason;
overlapping kernel durations are not an additive E2E decomposition. When
attribution is unresolved, name a discriminating diagnostic with a cost cap within
row 6 and a kill criterion; stop at the cap and retain `INCONCLUSIVE` if unresolved,
without promotion. Record these in each entry's `conditional_headroom` and
`diagnostic` fields. A matching negative record raises the burden of justification
and requires the changed condition to be stated; untried directions stay listed.
Each round names its parent revision, builds the candidate in an isolated
directory or environment, and records the
exact import path, so a candidate can never be confused with the incumbent. An
entry's hypothesis, mechanism and kill criterion freeze at its first run.

**Row 5 —** the timing boundary is chosen explicitly (`client_full_response`,
`server_inference` or `offline_pipeline_with_sync`) together with what is
excluded; baseline at least 3 rounds per dominant stage gives sigma, the rollback
line is `max(5%, 2 sigma)`, and an improvement below `2 sigma` is "not measured"
rather than a win; validators freeze before candidate search. Name the held-out
release point and use limit, and state the abort or resume policy for a crash,
timeout, OOM or lost device.

**Row 6 —** caps are numbers, not intentions: candidates, rounds, device-hours
and retries, with per-round planned versus spent accounting, and the stop
conditions that end the campaign — target met, two rounds below noise, budget
exhausted, direction list exhausted, evidence insufficient. Keep a reserve for
the acceptance regime, sized from measured restart and warmup cost.

**Row 7 —** name the owner of the device, the validator and the freeze, and who
may revise which row. State how generator and evaluator are separated — separate
account, container, read-only mount or manual import — because hashes detect
tampering but do not prevent it.

## 4. Why these rows

| # | Gap today | Where it shows |
| --- | --- | --- |
| 1 | The delivery scaffold requires a "campaign contract" that no file defines | [engine-task.md](../template/engine-repo/.github/ISSUE_TEMPLATE/engine-task.md) and [reproducibility.md](../template/engine-repo/docs/reproducibility.md) point at a contract, while [plan/README.md](../../evidence/_template/plan/README.md) is three bullets and [campaign-acceptance.yml](../../.github/ISSUE_TEMPLATE/campaign-acceptance.yml) carries a free-text checklist |
| 2 | Model and hardware identity are not a required set | A RunSpec has no SKU, IDs, topology, driver, container digest or weight hash; [drama3-npu-readiness.md](../drama3-npu-readiness.md) had to invent a TBD tuple |
| 3 | Search intent has no home and no version | Directions are reconstructed from the H1–H19 ledger ([qwen-image-2.1-turbo-b300.md](../qwen-image-2.1-turbo-b300.md)) or casebook rejections; "one plane per step" has nothing to check against |
| 4 | The test plan is split and partly contradictory | L0–L4 in [contributing.md](../contributing.md) versus L0–L5 with different L2/L4 in [dense-performance-evidence](../../src/inferrsi/data/skill_library/methods/dense-performance-evidence/SKILL.md); [inference-benchmark-design](../../src/inferrsi/data/skill_library/methods/inference-benchmark-design/SKILL.md) proposes plan files that do not exist |
| 5 | Imported evidence cannot be checked against a plan | The Ascend 910B1 cohort is `INCONCLUSIVE` for exactly these fields ([qwen-image-2.1-turbo-ascend.md](../qwen-image-2.1-turbo-ascend.md)) |
| 6 | No budget, spend accounting or stop condition | `experiment_protocol` in [plan.json](../../evidence/drama3-b300-scale150/plan/plan.json) states a stop rule in prose, but no cap, no planned-versus-spent account and no acceptance reserve |
| 7 | Freezing detects tampering, it does not prevent it | [freeze.json](../../evidence/drama3-b300-scale150/plan/freeze.json) is a hash manifest; nothing names who owns the device, the validator or the freeze, or how the generator is kept away from them |

## 5. Compatibility with the existing plan.json

The Drama3 plan already carries most of the table: `goal`, `baseline_sha`,
`starting_candidate_sha`, `concurrency`, `requests_per_repetition`,
`repetitions`, `target_frames_s`, `quality`, `controls` (`corpus_sha256`,
`sampling`, `warmup`, `OMP_NUM_THREADS`, `connection`), `diagnostic_hypotheses`,
`experiment_protocol`, `readme_example`. `freeze.json` already hashes
`plan/plan.json` and `validator/validate.py`.

| Existing key | Disposition |
| --- | --- |
| `goal` | Kept; primary statement of row 3 |
| `baseline_sha`, `starting_candidate_sha` | Stay in the acceptance issue; the table header links it |
| `hardware` (string) | Generalized into row 2 as an object |
| `precision` (string) | Split: artifact precision in row 1, runtime precision policy in row 2 |
| `concurrency`, `requests_per_repetition`, `repetitions` | Kept verbatim in row 5 |
| `target_frames_s` | Generalized into row 3 as a per-level target map, not restricted to frames per second |
| `quality` | Kept in row 3; audio-specific keys become task-specific sub-keys |
| `controls` | Kept in row 5, extended with validator hashes |
| `diagnostic_hypotheses` | Generalized into row 4 `search_plan[]` entries, with lifecycle and versioning |
| `experiment_protocol` | Kept: one isolated variable per run, frozen source SHA, stop on numerical or state error |
| `readme_example` | Kept as the publication boundary |
| `freeze.json` | Kept as a whole-file hash manifest for each preserved plan revision and the unchanged validator; original snapshots plus manual frozen-field comparisons establish contract preservation |

Field names are kept; they are regrouped under the row each field serves, so a
compatibility reader looks inside the row objects rather than at the top level.

That file has five limits, and they are the reason for this RFC: no model row;
`hardware` and `precision` are uncheckable prose; `diagnostic_hypotheses` is a
bare string list with no lifecycle; one-blob freezing makes adding a hypothesis
break the frozen hash exactly as editing the quality gate would; and
`experiment_protocol` carries no cap, no spend accounting and no acceptance
reserve.
Historical evidence is not migrated — frozen campaigns keep their recorded bytes
and names ([negative diagnostics plan](2026-10-18-negative-diagnostics.md)).

## 6. Worked example: Qwen-Image-2.1-Turbo on one Ascend 910B1

Filled from the existing imported cohort
([qwen-image-2.1-turbo-ascend.md](../qwen-image-2.1-turbo-ascend.md)); it changes
nothing about that cohort's `INCONCLUSIVE` verdict.

| # | Row | Content |
| --- | --- | --- |
| 1 | Model | `Qwen/Qwen-Image-2.1-Turbo`; revision `<TBD>` (the source states none; the B300 pin `d65dbc9a...` must not be borrowed); BF16, CFG=1, native 8 sigmas, 1280×704; weights hash `<TBD>`; semantic reference = upstream Diffusers at its pinned revision; baseline = locally re-measured, not the reported 3111.5 ms |
| 2 | Hardware | `ascend`; 1× Ascend 910B1, IDs `<TBD>`; eager, `TORCH_SDPA`; vLLM 0.31.0 + patch `399cc01d1`; driver, CANN, torch_npu and container digest `<TBD>`; qualification `unverified`; exclusivity snapshot required — the source records a later-host reservation failure |
| 3 | Optimization goal | End-to-end image latency, minimize, 30% below the locally measured baseline; the 2178 ms line holds only once the imported 3111.5 ms is reproduced locally; SSIM ≥ 0.99 and PSNR ≥ 35 dB, pixel identity as a separate row; guards: peak NPU memory, allocator failure, no OOM |
| 4 | Iteration search plan | `D-01` model, prompt encode ≈550 ms of ≈2.4 s, exact conditioning reuse, lossless, kill if pixels differ · `D-02` infra, denoise ≈1.5 s, NPU interleaved rotary via `npu_rotary_mul`, lossless, kill if the half-mode pairing changes output · `D-03` infra, VAE decode ≈190 ms, VAE fastpath, tolerance-gated, kill on gate failure · `D-04` graph/launch, **rejected by prior art** · `D-05` attention fusion, **rejected by prior art** · `D-06` residency, **blocked by prior art**, revisit after a lifetime inventory. Incumbent `<TBD>` — nothing locally verified; parent and import path `<TBD>` |
| 5 | Test plan | Concurrency set `<TBD>` — the source measures single requests and cannot support a service claim; 3 prompts, seeds 42/43/44; corpus hash `<TBD>`; benchmark = offline pipeline with synchronization, service boundary not established; 2 warmup rounds; ≥5 AB/BA pairs `<TBD>`; quality judge `<TBD>`; rollback `max(5%, 2 sigma)`; validator `<TBD>`; held-out release point and use limit `<TBD>` |
| 6 | Budget and stop conditions | None recorded: no candidate, round, device-hour or retry cap, no spend accounting, and no stop condition beyond the 30% target; `<TBD>` |
| 7 | Control and authority | Author-reported and imported: no local device owner, no local evaluator, and no generator/evaluator separation; the cohort is owned by the importing campaign |

The `D-04` to `D-06` entries are the casebook's recorded directions
([qwen-ascend-rejected-directions.md](../../src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/qwen-ascend-rejected-directions.md));
their revisit conditions are diagnostic suggestions, not reproduced causes.
Filling the table mechanically reports the missing fields — model revision, weight
hash, corpus hash, validator, driver stack, service timing boundary and AB/BA
pairing — which is the same conclusion the repository already reaches, now
derived from a fillable table.

## 7. Rollout

1. **Templates** — add the table, header fields and row-4 change log; update the
   plan segment README; link from [contributing.md](../contributing.md) and the
   delivery scaffold's evidence guide ([template/README.md](../template/README.md)).
2. **Tests** — extend [test_template_layout.py](../../tests/test_template_layout.py)
   or add `tests/test_campaign_plan_template.py`: every row present and named
   consistently across Markdown, YAML and README; rows 1, 2, 3, 5, 6 and 7 frozen,
   row 4 mutable with a change log, and the fixed preamble present verbatim; placeholders only (no 40-hex revision, no real
   date, no numeric gate); YAML parses and every `search_plan[]` entry has all
   fields; relative links resolve; every key in section 5 still exists, so the
   format stays a superset.
3. **Acceptance form** (separate PR, maintainer decision) — one required input
   linking the frozen table, plus one line in the acceptance checklist.

Slices 1 and 2 follow the existing contract (`pytest`, `ruff check src tests`,
DCO sign-off, no CI lane changes). Prerequisite for slice 2: the link check reads
documents with the platform default encoding (`document.read_text()` in
[test_template_layout.py](../../tests/test_template_layout.py)), so under a
non-UTF-8 locale such as a Windows GBK console 114 of 167 scanned documents raise
`UnicodeDecodeError`, starting with [README.md](../../README.md). Reading them
explicitly as UTF-8 is a one-line existing fix.

## 8. Open questions

1. **Ladder authority** — [contributing.md](../contributing.md) defines L0–L4;
   [dense-performance-evidence](../../src/inferrsi/data/skill_library/methods/dense-performance-evidence/SKILL.md)
   defines L0–L5 with different L2/L4. Row 3 must cite one by name.
2. **File and format** — keep the existing `plan.json` name and JSON encoding so
   `freeze.json` and current readers keep working, or move to `campaign-plan.yaml`?
3. **Ownership** — canonical table under `evidence/_template/plan/` (this RFC) or
   under `docs/template/` (delivery scaffold)?
4. **Enforcement** — template and tests only, or also a required acceptance-form
   field and a reviewer checklist item before a `PASS`?
5. **Reconcile the benchmark-design plan set** — fold the
   [inference-benchmark-design](../../src/inferrsi/data/skill_library/methods/inference-benchmark-design/SKILL.md)
   files (`hypothesis.md`, `runspec.json`, `slo.yaml`, `decision.yaml`) into this
   table, keep them as optional sub-artifacts, or drop them?
6. **Change approval** — does a row-4 revision need an approver, or is appending
   a revision with reason and evidence enough for the accountable owner?
7. **Freeze granularity** — row-level `freeze.json` entries plus a separate
   `search-plan-r<n>.yaml`, or keep the search plan outside the hashed set?
8. **Evaluator isolation** — is a separate account, container or read-only mount
   required for the frozen rows, the baseline and the validator, or is hash
   verification plus review sufficient?

## 9. Not claimed

No runtime or CLI capability, no threshold, no pin, no campaign, no hardware or
performance result; no recorded verdict changes. Conventions followed:
[agent collaboration](../agent-collaboration.md),
[rsi-evidence](../../src/inferrsi/data/skill_library/workflows/rsi-evidence/SKILL.md), [AGENTS.md](../../AGENTS.md).
