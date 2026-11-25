# Operation guide

Use the intent map to choose a command or Python entry point, then follow the
linked contract for the complete procedure.

Effect classes used below:

- **Read-only** — no writes outside caller-chosen output files.
- **Candidate-writing** — writes only inside one explicitly authorized local store.
- **Report-generating** — writes an HTML report into the caller-selected run directory.
- **Experiment-executing** — runs caller-supplied commands under the experiment contract.

## Intent map

| Intent | Entry | Effect class | Boundary |
| --- | --- | --- | --- |
| Verify whether RSI knowledge improves optimization efficiency | CLI `benchmarks compare`; [comparison workflow](benchmarks/benchmark-comparison.md) | Local experiment records / explicit native handoff / report-generating | Apps freezes two-task on/off plans, returns host actions, verifies retained finals and reports Benchmark comparisons; no hidden Agent launch |
| Complete a task optimization in the current Agent | CLI `benchmarks session start/knowledge/round/status/final/recover` | Experiment-executing / local records | Frozen budget, actual candidates and independent task outcomes. The current Agent drives edits. Real usage is imported explicitly. Recovery collects an existing execution using its [pinned runtime](guides/optimization-workflow-unification.md#release-boundary-recovery) |
| Optimize an ordinary project in the current Agent | CLI `campaign start/knowledge/round/status/final/recover` | Experiment-executing / local records | Harness freezes explicit caller-provided checks, manages multi-file candidates, executes and assesses retained results. This path does not depend on Benchmark or infer acceptance from the goal. See [shared workflow](guides/optimization-workflow-unification.md) |
| Reuse one project service across multi-scenario checks | CLI `campaign start --evaluation-mode service_reuse`, then `baseline/round/profile/status/recover/final` | Experiment-executing / local records | Caller supplies protocol and service scripts. An optional profiler can run inline or on a settled round. `resume`, `refresh-references` and explicit retry retain recovery decisions. See [service reuse](guides/service-reuse-campaigns.md) |
| Prepare and record a fresh native Agent | CLI `agents prepare/dispatch/bind/record/status` | Local records / explicit host handoff | The initiating Agent calls native host tools. Records prevent repeated dispatch; exported host observations do not establish task acceptance. See [native sessions](guides/native-agent-sessions.md) |
| Discover packaged tasks | CLI `benchmarks list [--iterative]` / `benchmarks show`; Python `benchmark.registry.builtin_tasks` / `describe_task` | Read-only | Reads the installed registry and [task manifests](benchmarks/engineering-benchmarks.md). The optional filter selects task packages with an `optimization.py` file at their root |
| Execute one packaged task | CLI `benchmarks run`; Python `apps.workflows.benchmark_operations.run_task` | Experiment-executing | Application launches the task entry, supplies the execution callback and preserves arguments and exit status. The task owns its device, measurement and assessment protocol |
| Find relevant cases, skills and records | CLI `find` | Read-only | Default discovery across the registered library and package records. Follow the emitted command to read a hit and its revision |
| Inspect the package catalog | CLI `knowledge search` / `knowledge show`; catalog API | Read-only | Filtered inventory and existing catalog scripts. Uses the installed package's tier/repo/backend/scenario filters and IDs |
| Prepare model-aware engine research | CLI `knowledge research`; Python `research_knowledge` | Read-only | Independent model/framework/task/modality/mechanism queries over the same package catalog; source-grounded known profiles, deduplicated matches and explicit target annotations; no engine/hardware qualification |
| Enter an inference task or discover/read skills | CLI `skills enter` / `list` / `show` / `resource` / `reference` | Read-only | `enter` loads one primary owner's complete procedure before evidence search. `list`/ `show` inspect skill metadata and instructions. `resource`/`reference` resolve paths for your file reader. |
| Retrieve and cite external round knowledge | CLI `benchmarks session knowledge / knowledge-read`, AB/BA `campaign knowledge / knowledge-read` | Local evidence-writing | Requires an explicit `--cannbot-platform` at start and an approved project grant. Retains search and read metadata. Cite a delivered receipt with `round --knowledge-ref`. See [round retrieval](benchmarks/optimization-benchmarks.md#include-cannbot-in-the-round) |
| Collect selected knowledge | CLI `collect`; Python `KnowledgeReader.collect` | Read-only | Batch selection and budgeted assembly by query or exact IDs, with revisions and omissions. The only accepted explicit `--relevance-method` value is `find-lexical-v1` |
| Read exact material/resources | CLI `read` / `resource`; Python `KnowledgeReader.read` / `KnowledgeReader.resource` | Read-only | Returns the requested revision or an explicit unavailable/stale error; never substitutes newer bytes |
| Export legacy cited material | CLI `context` | Read-only | Cited package export for manual use with a coding agent; not a conversation store and not a full Collect equivalent |
| Create/update a store candidate | Python `KnowledgeStore.create` / `KnowledgeStore.update` | Candidate-writing | One explicitly authorized local store; expected-revision updates with reason and evidence; retained history; no promotion and no edits to package/checkout content |
| Inspect a store candidate's history | Python `open_knowledge_store(...).history` | Read-only | Opens an existing store and reads the revision lineage for one store ID |
| Amend repository-owned knowledge | Scoped repository PR | — | Repository review and integration authority apply; this is not a runtime store Update |
| Validate or preview a YAML task file | CLI `task validate` / `task preview [--json]` / `task schema` / `task template`; [task input](guides/task-input.md) | Read-only | Reads one schema v1 task file and prints field errors, effective normalized values, their sources and plan/run blockers. Starts no process or probe and writes no workspace, plan, run or evidence file. A complete preview does not authorize execution |
| Inspect/prepare experiments | CLI `doctor`; `plan` or `--dry-run` | Read-only inspection / preview | `doctor` may invoke bounded probes and does not certify target compatibility; `plan` previews a specification without persisting a campaign or authorizing execution |
| Execute/inspect experiments | CLI `run`; `status`; `report` | Experiment-executing / read-only / report-generating | `run` executes caller-supplied commands and records evidence; `status` reads recorded progress; `report` generates HTML from recorded evidence |
| Deliver retained results | CLI `export --input --output [--agent-job]`; Python `apps.delivery.export_bundle` / `read_bundle` | Report-generating | Publishes Markdown, offline HTML, versioned result JSON and artifact index from one snapshot without remeasurement. Optional native-job input verifies standalone Benchmark terminal token usage. Iterative CLI final returns separate delivery status. See [result delivery](guides/result-delivery.md) and [Benchmark metrics](benchmarks/benchmark-metrics.md) |
| Inspect/verify archived evidence | `python tools/verify_evidence_archive.py`; [archive contract](guides/evidence-archiving.md) | Read-only by default; explicit network/local scratch with `--download` | Default validates metadata offline; `--archive`/`--download` authenticates and bounds archive reading; `--recomputed` compares separately generated v2 results; never executes archived code or changes verdicts |
| Rebuild scoped legacy evidence views | `python tools/rebuild_model_evidence.py <manifest> --archive <path> --output <new-directory>` | CPU-only; creates a new output directory | Authenticates original bytes and pinned projection/code; no extraction, network, archived-code execution or campaign qualification |
| Inspect evidence inventory / generate budget input | `python tools/validate_evidence.py [--budget-assets]` | Read-only | Offline layout/hash/schema checks; optional disposable #328 metadata view derived from campaign authority; no downloads |
| Execute one ordinary local CPU command with a fixed record | Python `inferrsi.harness.api.Harness.allocate` / `execute` / `read` | Experiment-executing / record-writing | One explicit RunStore root and one trusted local CPU target; ordinary command mode only; a record holds execution facts, so exit 0 is not a verdict; no device, model or network fallback |
| Seal a generation request before execution | Python `inferrsi.harness.generation.prepare_generation`; [original bounds](contracts/generation-bounds.md) | Local record-writing | Seals approved context, plan and original deadline/budget metadata; allocates no attempt, starts no process and does not enable generation-lineage evaluation |
| Verify a frozen preparation binding before registration | Python `inferrsi.harness.prepared_binding.verify` / `read` / `project` | Read-only / pure projection | Fixed ArtifactRef and read-only stream capability; no registration, entry resolution or execution; [binding contract](contracts/harness-prepared-binding.md) |
| Verify and execute one frozen source evaluation entry | Python `inferrsi.harness.api.Harness.execute` with trusted `LocalCpuTarget(module_root=...)` | Experiment-executing / record-writing | Fixed preparation and expected code digest; actual source captured after registration; T37 refusals start no worker; [source-entry contract](contracts/harness-entry-verification.md) |
| Evaluate one retained generated candidate | Python `inferrsi.harness.api.Harness.execute` with `generation_record_ref`; [same-Store lineage](contracts/generation-lineage.md) | Experiment-executing / record-writing | Same authorized Store, sealed successful generation and exact retained candidate; distinct attempt, original deadline/budget scope and policy; registered replay precedes fresh source reads; no worker-manifest parsing or automatic rerun |
| Capture and seal evaluation proofs | Python `Harness(..., evidence_capture=...)`; [capture contract](contracts/harness-evidence-capture.md) | Read-only capture callback / record-writing | H authorizes attempt bytes, seals actual provenance and retains drafts before one commit; ordinary mode and replay never call the observer |
| Assemble evidence capture by role | Python `apps.api.EvidenceCapture`; [host adapter](contracts/apps-evidence-capture.md) | Read-only byte assembly / injected pure projection | Reads only H-authorized candidate/report refs; no grading, producer sealing or record/archive writes; reentry is short-circuited by H |
| Replay the same saved execution request | Python `inferrsi.harness.api.Harness.execute` | Existing-state query / fixed record-reading | Same attempt and canonical digest; existing state short-circuits fresh binding/execution; [replay and original limits](contracts/harness-evaluation-replay.md) |
| Freeze a configured P1 preparation | Python `benchmark.preparation.PreparationService.prepare`; [production prepare](contracts/production-prepare.md) | Read-only resource access / pure encoding | Verifies supplied frozen worker/resource bytes and returns a preparation, protocol and role-keyed closure; Apps separately archives them before publishing a Ref |
| Evaluate saved requests | CLI `evaluate prepare/execute/assess`; [saved-request CLI](guides/apps-evaluate-cli.md) | Local archive/output writing; execute additionally runs the configured H target | Explicit saved request, output ID, storage and trusted runtime configuration; reuses Apps ports and results without allocating attempts, selecting feedback or retrying |
| Assess one fixed P1 record offline | Python `benchmark.assessment.assess`; [production assess](contracts/production-assess.md) | Read-only retained evidence / pure encoding | Verifies the frozen protocol, actual capture and proof bytes; returns independent claims without launching a worker or writing an archive; Apps selects the primary key and archives the result |
| Project P1 worker reports into capture drafts | Python `benchmark.proofs` codecs / `ProofProjector.project`; [proof drafts](contracts/production-proofs.md) | Pure computation | Produces proof bytes from supplied capture facts and reports; H must authenticate, retain and seal them before commit; no worker or grader execution |
| Configure the CPU evidence-smoke task | Python `benchmark.cpu_smoke.prepare_service`; [task contract](contracts/p1-cpu-smoke.md) | Read-only owned resource configuration | Freezes the standalone worker and same-source baseline for the existing prepare port; actual execution/retention stays in H; no performance-gain claim |
| Seal a generation with frozen feedback authorization | Python `harness.generation.prepare_generation`; [opt-in feedback profile](contracts/generation-feedback-policy.md) | Local context / policy / generation-plan retention | Optional fixed policy and source record Refs authorize original scope/check proofs before provider calls. Absent-policy calls remain a trusted-host path; no automatic execution or policy-approval authentication |
| Seal host-approved generation context without a policy Ref | Python `harness.generation.prepare_generation`; [feedback boundary](contracts/generation-feedback.md) | Local context / generation-plan retention | The trusted host authorizes feedback and excludes final-only results before handoff. Without the opt-in policy Ref, H seals supplied material and does not prove feedback-policy enforcement or execute a worker |
| Visualize a recorded run or campaign | CLI `dashboard`; [dashboard](dashboard.md) | Report-generating / local read-only serving | Writes an offline HTML snapshot or serves an optional live view on loopback; does not run an agent or validate a claim |
| Capture a knowledge context | CLI `campaign capture-context`; [offline dashboard](dashboard.md#record-the-optimization-story-campaign-trace) | Local evidence-writing | Saves assembled context and resource hashes in a new `knowledge/<id>.json`. Supports ordinary questions and explicit IDs. The only accepted explicit `--relevance-method` value is `find-lexical-v1` |
| Retain an executed retrieval | Python `apps.workflows.campaign.save_retrieval`; [capture contract](guides/knowledge/knowledge-retrieval-trace.md#retain-a-standalone-result) | Local evidence-writing | Saves an existing catalog/collect result under a fresh campaign capture ID; no new search or automatic publication |
| Import one round of knowledge searches | CLI `campaign import-search`; [round import](dashboard.md#import-one-rounds-searches) | Local evidence-writing | Reads a Codex rollout window or context captures. With `--archive-review`, retains excerpts of attributable tool returns and reviewed decisions for readers of the evidence bundle. |
| Record the optimization log | CLI `campaign log`; [offline dashboard](dashboard.md#record-the-optimization-story-campaign-trace) | Local evidence-writing | Validates and stores a new numbered campaign log version; the dashboard cross-checks it against captures and runs |
| Assemble an optimization trace | CLI `campaign assemble-trace`; [per-candidate narrative](dashboard.md#per-candidate-narrative-schema-version-1) | Local evidence-writing | Copies an explicitly reviewed context into a new bounded campaign-root snapshot; caller owns redaction and narrative accuracy |
| Import a MindIE read | CLI `campaign import-mindie`; [Codex workflow](guides/plugins/codex-plugin.md#mindie-knowledge) | Local evidence-writing | Retains caller-supplied query/explain bytes and hashes, exports delivered graded bodies and a trace context fragment; no activation, model call, transcript capture or automatic caller review |
| Associate runs with a local campaign | CLI `campaign init` / `campaign record` / `campaign decide`; [offline dashboard](dashboard.md) | Local evidence-writing | Legacy manual records reference existing artifacts and never start an agent; record/decide cannot mutate a managed optimization campaign |
| Adapt existing Flare delivery evidence | [Offline qualification adapter](benchmarks/flare-qualification.md), `python -m inferrsi.benchmark.validators.flare` | Read-only | Existing raw packets and a separate receipt; one HTTP delivery metric, no model/server/device execution |
| Evaluate selected skill revisions | [Bounded skill-evaluation driver](skill-evaluation/README.md) | Experiment-executing | Explicitly authorized real Codex calls, independent task verdicts and private evidence; separate from numeric engine-performance scoring |
| Compare skill additions or updates | [Configured skill comparison](skill-evaluation/skill-eval-comparison.md), `python -m tools.skill_eval_compare` | Read-only preparation / experiment-executing / report-generating | Fixed Git snapshots and one shared exam; explicit plan authorization for execution; JSON + Markdown regeneration makes no model calls |
| Export a cloud-generated parser pair | [Generation-only protocol](skill-evaluation/skill-eval-generation-only.md), `python -m tools.skill_eval_cloud_export` | Local evidence-writing; no execution or publication | Validates frozen inputs and retained sources; writes one bounded inert JSON bundle, never executes parser source |
| Review the historical parser generation pilot | [Main-only historical job record](skill-evaluation/skill-eval-historical-job.md) | Historical audit | The checked-in authorization expired at 16:00 UTC on 2026-10-30. The workflow and frozen controls remain available for audit. |
| Qualify an artifact verifier host | [Manual reviewer qualification](skill-evaluation/skill-eval-reviewer-qualification.md), `python -m tools.skill_eval_qualify` | Trusted-control execution / report-generating | Manual main-only workflow; fixed software controls, no model or external artifact input; unavailable isolation fails rather than skips |
| Replay a cloud-generated parser pair | [Isolated cloud replay](skill-evaluation/skill-eval-cloud-replay.md), `python -m tools.skill_eval_cloud_replay` | Untrusted-artifact execution / report-generating | Manual pinned data ingress; same-host controls before bubblewrap-only replay; no models or credentials |
| Validate one harness-improvement step | [Offline improvement](guides/harness-improvement.md), Python `tools.skill_eval_improve.prepare` / `run_offline` | Snapshot-writing / offline experiment-executing | Supplied declarative INV/DOM edits, shared total limits, rerun and one holdout gate; trusted fixed-output clients only; no real-model or Store execution |
| Build an offline candidate tree and completion menu | Python `harness.search_tree` / `harness.verification_plans.completion_menu`; [control contract](speculative-search.md) | Read-only / in-memory transitions | Immutable candidates, scoped caller-supplied receipts and bounded exact plans; execution, durable state, accounting, learned roles and final acceptance require separate adapters |
| Run bounded speculative Engine search and role updates | `inferrsi search engine`; [support and configuration](speculative-search.md) | Execution / candidate writes / CPU model updates | Explicit shared RunStore, permissions, checkpoint, budgets, domain and final gate; actual device allocation is caller-owned |
| Inspect/export speculative search | `inferrsi search status` / `search export` | Read / output artifact | Reads the existing store; never restarts search, training or final evaluation |
| Compose Skill speculative search | Python `apps.workflows.search_benchmarks.SkillEvaluator` and checkout `tools.speculative_skill.Comparator` | Explicit provider execution through existing comparator | Frozen original baseline, split descriptors, independent grader and bounded provider; see campaign accounting limits in the support matrix |
| Plan and report skill PR evaluations | [Skill PR integration](skill-eval-pr.md), `python -m tools.skill_eval_pr` | Read-only planning / authorized experiment-executing / PR-publishing | Trusted mapping, exact operator approval, consumed execution identity and credential-separated publication from retained evidence; no automatic paid trials |
| Recover goal progress and the next proposal | [Offline goal checkpoints](guides/goal-checkpoints.md), `python -m tools.goal_checkpoint` | Read-only | Explicit scope/criteria, pinned owner decisions and existing comparison receipts; a disposable view, never execution or acceptance authority |
| Summarize campaign gains | `tools/campaign_summary_chart.py`; `report`/`run` figure | Figure-generating | Renders recorded values into one gain figure plus a matching table; validates the specification and computes nothing new |

The `collect`, `read` and `resource` commands share the reader's rules; they
are distinct from `knowledge search`, whose package catalog filters
(tier/repo/backend/scenario) intentionally exclude checkout and store items.

## Discovery and reading

### Discover MLX hardware — doctor --backend mlx

- **Inputs:** a prepared Git checkout and its existing repo type, target Python,
  optional case-insensitive --device-model chip match. Discrete --device-ids are
  unsupported for this unified-memory discovery probe.
- **Effect:** read-only. On macOS, the existing bounded command runner queries
  sysctl hw.optional.arm64 machdep.cpu.brand_string. Non-macOS hosts are rejected
  without a sysctl call. Target-Python metadata includes mlx version/null without
  importing MLX.
- **Output:** actual probe facts and chip identity when available; explicit
  unavailable or device_model_mismatch reasons otherwise. doctor exits 1 for
  unavailable/mismatched discovery. compatibility stays unverified even when
  the chip is available or the MLX package is installed.
- **Boundary:** no engine adapter, package installation, model execution or
  Metal/performance qualification. The dependency/mlx source cards are separate
  imported guidance; common skill discovery records are not counted as MLX
  backend records.
- **Example:** inferrsi doctor --repo . --repo-type vllm_omni --backend mlx

### Discover discrete accelerators — doctor --backend rocm|ascend

- **Inputs:** a prepared Git checkout and its existing repo type, target Python,
  optional repeatable --device-ids and one case-insensitive --device-model.
- **Effect:** read-only. The bounded command runner calls `rocminfo` or
  `npu-smi info`; the output is parsed into device records (Agent blocks, or the
  pipe-framed NPU table) rather than searched for loose tokens.
- **Output:** the parsed records plus the probe facts. A requested ID and the
  requested model must match the same record; an ID appearing only in a
  temperature or power cell does not count. Empty or unrecognized output yields
  no records, so discovery stays unavailable and records why. selection_verified
  is true only for a matched record.
- **Boundary:** discovery proves that a tool reported a device, not that the
  backend, engine or kernel path is compatible. compatibility stays unverified.
- **Example:** inferrsi doctor --repo . --repo-type vllm_omni --backend ascend --device-ids 0 --device-model 910B3

### Search packaged records — `knowledge search` / `knowledge show`

Use `find` for ordinary discovery. With no query, `knowledge search` lists
matching package records in ID order. With a query, it uses Find ranking over
the filtered package catalog and still returns complete catalog records. The
`context` export shares this selector. Text query results can change in both
membership and order. Use `--explain` for the recorded ranking and counts.

- **Inputs:** optional query words and `--tier`, `--repo-type`, `--backend`, `--scenario`, `--limit`, `--json`, `--explain`; `show` takes one record ID.
- **Scope:** the installed package catalog (authored records and registered skill views in `skill_library/`) only.
- **Output:** tab-separated record lines (id, status, backend, title), or a JSON list with `--json`; `--explain` returns a JSON envelope with `items` and `retrieval` (entry, ranking, scores and counts). Python uses `search_knowledge(..., explain=True)` for that envelope. `show` prints one full record as JSON.
- **Side effects:** none.
- **Failure behavior:** no match prints nothing and exits 0 — an empty result is not an error (an empty JSON list with `--json`, or empty `items` in the `--explain` envelope); an unknown `show` ID and unsupported filter values exit 2.
- **Example:** `inferrsi knowledge search --repo-type vllm_omni --backend ascend --json`

The tier/repo/backend/scenario filters are package-only: an empty filtered
result does not mean that no checkout or store knowledge exists. See the
[three-tier guide](../src/inferrsi/knowledge/data/skill_library/records/README.md) for all sources.

### Prepare model-aware research — `knowledge research`

- **Inputs:** model identity; repeatable `--framework`, `--task`, `--modality`, `--mechanism`; existing `--tier`, `--repo-type`, `--backend`, `--scenario` hard filters and `--limit` output cap; optional `--target-backend`, `--target-device`, positive finite `--target-memory-gib` annotations.
- **Scope:** installed package records only. A packaged MiniMax-H3 profile supplies its source-grounded diffusion/video/audio identity and component roles. Unknown models use only caller-supplied dimensions and need source inspection; no architecture is guessed.
- **Output:** JSON query groups and match counts, a bounded deduplicated union with `matched_queries`, unchanged full records/provenance, active filters, component roles, preparation/example resource paths and an unverified target state. Queries take turns contributing results; this ordering does not rank engine quality.
- **Side effects:** none; no network requests, hardware probes, model download or engine execution. Target annotations do not add runtime backends.
- **Failure behavior:** no match returns an explicit empty envelope and exits 0; invalid limits/memory or unsupported catalog filters exit 2. A zero-match dimension stays visible.
- **Example:** `inferrsi knowledge research MiniMax-H3 --framework mlx --target-backend metal --target-device "M5 Mac Studio" --target-memory-gib 64 --limit 12`
- **Python:** `from inferrsi.knowledge.research import research_knowledge`; `research_knowledge("MiniMax-H3", frameworks=["mlx"], modalities=["video"], limit=12)`.

Each research query uses Find over the same filtered package catalog. Querying
separate dimensions broadens discovery while preserving the active package filters.
Keep those filters explicit when transferring mechanisms from other backends;
target intent does not qualify their applicability. Read the canonical
[preparation procedure](../src/inferrsi/knowledge/data/skill_library/workflows/research/inference-engine-research/references/model-aware-preparation.md)
and the repository-owned [h3.c residency audit](../src/inferrsi/knowledge/data/skill_library/systems/engines/h3-c/audit-h3-runtime-residency/SKILL.md)
for native-engine reference selection, full encoder/DiT/VAE accounting,
quantized-package compatibility and target hardware decisions. Returned resource
paths are relative to `importlib.resources.files("inferrsi")` and ship in the wheel.
The small model profile links that skill's full inventory and worked example;
those resources retain their repository owner and source attribution.

### Discover/read packaged or custom skills — `skills list` / `enter` / `show` / `resource` / `reference`

- **Inputs:** The agent selects a primary skill by deliverable and runs `inferrsi skills enter task-accuracy`, for example. It returns the primary's complete procedure and host header before supporting evidence search. The base installation can omit the embedded search metadata from this delivery. A pinned `read --resource` exposes the complete source file, including its metadata. An unknown, unavailable or non-primary owner is an error. `list` reads skill frontmatter (and legacy sidecars in historical/custom checkouts); `show <skill>` selects one instruction body; `resource <skill> <relative-path>` and `reference <skill> <relative-path>` resolve one path. The default is the installed library's registered skills; an explicit `--root` selects a custom flat tree or a categorized library with `skill-index.json`. PyYAML, a core dependency, supplies the YAML parser for frontmatter operations; the `skills` extra remains a compatibility alias.
- **Scope:** complete packaged skills under `data/skill_library/`, or the explicitly selected custom root. The 21 English engine and research-router skills remain accessible through catalog records and library navigation, separately from the registry.
- **Output:** metadata listing, one instruction body, or a resolved path.
- **Side effects:** none. `resource`/`reference` do not load or execute the target.
- **Failure behavior:** missing skill, undeclared reference or path escape is an error.
- **Example:** `inferrsi skills show weight-loading-optimization`

Reading instructions does not authorize their commands. The catalog links full
packaged bodies; the two matrices remain authoritative.

### Export legacy cited material — `context`

- **Inputs:** optional query; **required** `--repo-type` and `--backend`; optional `--tier`, `--scenario`, `--limit`, `--output`.
- **Scope:** cited catalog material from the installed package.
- **Output:** a Markdown reference bundle at the chosen path (the resolved path and record count are reported), or to stdout without `--output` (text only).
- **Side effects:** writes only the caller-chosen output file.
- **Failure behavior:** no match produces an empty export (header only), not an error; unsupported filter values exit 2.
- **Example:** `inferrsi context --repo-type vllm_omni --backend cuda --output context.md`

Imported source text is data for your agent, not authorization to execute
upstream instructions.

## Normalized knowledge (Python)

### Find — `find` / `inferrsi.knowledge.knowledge_find.find`

One ranked list for one question, across packaged skills, imported records and
checkout cases. Run a result's `open` command to read its complete entry and
receive a revision. Use that revision with the same ID and source selection
for a pinned `read` or `resource` call.

Cases are ranked alongside skills, so prior rejected directions can surface
directly. One matching term is enough to rank an entry, and `--limit` caps the
result list. Scoring reads the corpus files directly. The reader opens bundles
to validate material for the returned hits.

Scoring is `idf x field weight x sqrt(occurrences)` summed over query terms,
with titles, summaries, tags and case findings weighted above bodies. Bodies
longer than the corpus median get less weight so a broad manual needs more
specific matches to outrank a short case. Separators
do not bind: `kv_cache`, `kv-cache` and `KV cache` all tokenise to the same two
terms, so a query in plain words reaches the punctuated spellings this corpus
also uses. Latin terms still match on boundaries, so `oom` does not match inside
`headroom`. CJK is cut into overlapping bigrams, because single characters make
idf treat grammatical particles as rare terms. Ties break towards the stronger
recorded state rather than alphabetical identity. This is deterministic lexical
matching, not a learned ranking, and a hit never asserts that an entry applies.

Common English function and question words such as `the`, `how` and `should`
are omitted. Conditions such as `not`, `without`, `before` and `after` still
contribute. Backend preference uses platform names in the original query,
including `昇腾` for Ascend. When the query names exactly one supported backend,
results declared for a different backend receive half their lexical score.
`--explain` reports the adjusted contribution of each matched term.

Chinese query terms expand through `data/skill_library/config/query_aliases.json` before ranking.
The packaged library is English by policy while its readers work in Chinese, and
the corpus holds too few Chinese characters for a Chinese query to score on its
subject. Expansion is one-way and query-side: 显存 reaches `device memory`, not
the reverse, and an entry is only listed when that English form actually occurs
in the corpus. A query whose terms were expanded reports them under `expanded`,
so a wrong expansion is visible in the result rather than only in the ranking.

Three limits are inherent to lexical ranking and are recorded here rather than
worked around. A query made only of terms common to this corpus ("operator",
"test", "graph", "speedup") has little to rank on and may bury the intended
entry. A query that shares no words with its target does not reach it: asking
for "moving attention state to host memory" misses an entry that says `kv`,
`offload` and `tier` throughout, because nothing matches. Name the specific
symptom, operator or flag where you can, and when a plausible query returns
nothing useful, search the corpus directly rather than assuming it holds
nothing — `find` ranks words, not meanings.

The third limit is deciding whether the question needs the corpus. `find`
returns `no_match` when no query terms match. On the labelled set, a majority
of queries were ones an engineer should decide without searching at all, yet
each had lexical matches. Their scores overlap the answerable range, so a
cutoff would suppress useful results too. The caller decides whether the
question calls for prior evidence.

- **Inputs:** the query, `--limit`, `--kinds` (subset of `case,skill,record`), `--skill-root` to select the library for cases and skills, `--explain` for per-term contributions, `--json`.
- **Scope:** installed package records and the packaged (or selected) skill library, including its cases. Packaged-skill projections are excluded from the record side so one owner is not ranked under two identities.
- **Output.** Items identify their `id`, `authority` (`package` or `checkout`),
  `source_location` (`installed` or `checkout`), `kind`, recorded `state`,
  `score`, `title` and corpus-relative `path`. `source_location` identifies
  where the material was indexed. For installed skill and case bodies, the
  `checkout:` read reference uses `--installed-library` to resolve the source
  from the reader's installation. A custom root uses `--skill-root`.
  Where recorded, items carry source, summary, applicability, limitations and
  local verification status. The limitations preview contains up to three
  complete entries within a 400-byte UTF-8 JSON list. `limitations_withheld`
  counts omitted entries. Open the owner for the complete list.
  Case findings are ordered by query overlap,
  with `findings_total` and `findings_withheld` describing the available preview.
  Pass `--decision-cards` to add a revision-pinned L1 read and its exact card
  size to each readable Skill, Record or displayed Case finding. Follow the
  selected `decision_card.read_args` to read that atom. See the
  [decision card read contract](knowledge-operations.md#read-a-decision-card).
  Each finding carries its outcome, reason, revisit condition and any assessed
  scope and bounds. `bounds_source` identifies whether bounds apply to the
  finding or the whole entry. The envelope reports `corpus_size`, `matched`,
  `no_match`, any `expanded` terms and retrieval limitations.
- **Reading a hit.** Plain output prints a POSIX `open` command or a labelled
  PowerShell command on Windows. JSON exposes the rendered command as `ref`,
  full subprocess arguments as `open_argv` and InferRSI CLI arguments as
  `read_args`. The arguments include the source-qualified ID and any needed
  source flag. Most hits use `read --material --omit-resources` to return the
  entrypoint content, provenance and revision. For a skill, the procedure
  omits the embedded machine annotation. A readable hit's
  `next_read_content_bytes` counts the UTF-8 bytes in that command's `content`
  on the snapshot inspected by Find. For a future unpinned read this field
  is a size estimate. A later edit can change the content and its size.
  Use Collect's context budget for bounded delivery. The count excludes the
  envelope and additional resources. Remove
  `--omit-resources` to list the bundle's resources. Hits that fail the reader's
  material check carry `unreadable` with the reason.
- **Without PyYAML.** PyYAML is a core dependency. When an install lacks it (for
  example, one made without dependencies), an installed Skill with a
  matching valid package record opens its original text through that record,
  using `read --resource` and its exact revision. The result names the selected
  resource in `content_resource`. A Skill in a custom root may require PyYAML.
- **Side effects:** none. Retain the revision returned by `read` for evidence and resource followups.
- **Example:** `inferrsi find "NPU OOM after caching per-step masks" --limit 3` returns the casebook entry recording that attempt first. A vaguer phrasing ranks the procedural skills above it, which is the first limit below rather than a defect.

#### Show SearchSpace coordinates on Find hits

Run this command from an InferRSI checkout with its verified SearchSpace index.

```text
inferrsi find "graph mode" --skill-root src/inferrsi/knowledge/data/skill_library --show-searchspace-coordinates
```

Find annotates the ranked local Skill hits from the verified registry with their
coverage state and all declared resource × stage pairs. A registered Skill with
`unknown` coverage has an empty pair list. In JSON, `searchspace_coordinates`
is attached to the hit, and `searchspace_source` reports the matrix path and
SHA-256 along with the Skill registry and metadata digests.

Add `--searchspace-coordinate SSD Configure` to restrict the result to Skills
with that exact pair. Each remaining hit still shows all its pairs. Find reports
an error if the index is missing, stale or from a different checkout source.
Run `python tools/build_skill_coverage.py --searchspace-index` in that checkout
to regenerate the index, then retry.

#### External channels are not installed with this package

`find` can also query separately enabled read-only channels. A fresh install
searches the packaged corpus. See [fresh-install output and setup](guides/knowledge/external-channels.md#a-fresh-install-has-no-external-channel)
for the explicit per-checkout grant and source access requirements.

- **Inputs:** `--backend <name>` declares the task backend; **without it and
  without an approved grant, no channel is searched** and each one reports
  `backend_unknown`. `--no-external` skips all channels for CI and offline runs.
  `--external-limit <N>` overrides the per-channel cap (`cannbot-knowledge` 100,
  `mindie-agent` 5). `--external-timeout <S>` bounds discovery and search
  together (8s default); `--platform` overrides the upstream platform in the grant.
- **Output:** `external[]` sits beside `items`, never inside it. Each entry
  carries `state`, `revision`, `elapsed_ms`, `score_scale` and `count`. A state
  other than `ok` (`not_enabled`, `unreachable`, `index_stale`, `timeout`,
  `version_mismatch`, `rejected`, `backend_unknown`) means the channel did not
  answer — it is **not** the same as answering with no hits.
- **Side effects:** none on this repository. A channel reads an external
  checkout that the person approved; nothing is copied into the package, a
  wheel or `evidence/`.
- **Determinism:** `--no-external` reproduces the pre-channel output exactly.

### Collect — `collect` / `KnowledgeReader.collect`

Use Collect to take known material in caller-specified order. With
`--context-bytes <N>`, it assembles complete files up to a UTF-8 body budget and
reports unavailable or oversized context. With no IDs and one question, Collect
uses the same local Find ranking as `campaign knowledge`, `benchmarks session
knowledge`, and `campaign capture-context`. See [selection and context](knowledge-operations.md#ranked-discovery-and-budgeted-context)
for provenance and accounting. To capture an installed Case exactly, follow the
`find` result to `read`, then pass its ref and revision to
`campaign capture-context --installed-library --id-ref REF --revision REF=REV`.

#### Collect a pinned body and its L1 decision card

Keep the qualified ref, revision and source options from Find or a known read.
Repeat `--decision-card` for each selected body that needs a full L1 card. For
a Case, append one original finding selector, such as `id:trace-loss` or
`case.json#/findings/1`, to the ref with `=`.

```sh
inferrsi collect --installed-library --id "$REF" --revision "$REF=$REV" \
  --context-bytes 65536 --decision-card "$REF" --json
```

Apps can call `inferrsi.apps.workflows.knowledge.knowledge_reader` with the same
source and use `reader.collect(ids=[ref], revisions={ref: rev}, context_bytes=65536,
decision_cards={ref: finding})`. Set `finding=None` for a Skill or Record.
Collect delivers the usual context resources first. It then projects requested
cards from those same bundles in ID order. The shared budget counts UTF-8
resource content and each delivered card's compactly serialized, sorted-key JSON.
`decision_cards` reports each request, including `over_budget` with the whole
card size, `no_body` when Collect omitted the body, and `unavailable` for an
invalid decision source or finding. See `omissions` and `context_omissions` for
the body outcome. Store entries retain their existing `unsupported_context` result.
To reopen a projected card's source or body, use `read REF --revision REV
--resource PATH` with the same source options and the returned `source_resource`
or `body_resource`.

#### Migrate old text queries

- `knowledge search QUERY` and `context QUERY` keep their package scope and
  output format. Text queries now use Find and can match entries that contain
  only part of the query. Omit `QUERY` for filtered inventory or use
  `knowledge show ID` for one known record.
- Pass one question as `collect QUERY` or `collect --relevance QUERY`. If an
  old script combines a positional query and a separate cue, write one question
  and express hard constraints with structured flags such as `--kind` and
  `--backend`. Use `--kind knowledge` to search only the package catalog.
- Remove old `--relevance-method` values from scripts and managed calls. Find
  is the default and `find-lexical-v1` is the only accepted explicit value.
  Check the new rank order before using it to select material in automation.
- For exact collection and replay, use the retained IDs and revisions without
  a positional query. With explicit IDs, `--relevance` can order optional
  context resources while membership and caller order remain fixed. Read
  historical captures for their original selected and delivered bytes.

- **Inputs:** optional query, `--kind`, repeatable explicit `--id`, repeatable `--revision ID=REV`, `--limit`, `--max-bytes`, `--material`; `--skill-root` selects an explicit skills root, `--store` opens an existing store read-only (the store records its reserved skills root and rejects a mismatched or missing `--skill-root`).
- **Scope:** installed package records, the selected library, and any explicitly opened store. A text query without a custom library or store can discover bundled Cases and Skills. Exact inventory selects the bundled library with `--installed-library`.
- **Output:** with `--json`, the complete **normalized** envelope — items carrying the bundle's normalized metadata, resources and dependencies, plus `no_match`, `omissions`, `collisions`, `material_bytes` and the recorded limitations; fields that exist only in a package record's original entrypoint document are not projected into the normalized metadata and are read via `--material` or `resource`. Without `--json`, the envelope's selection is projected line-wise: one tab-separated line per item (`ref`, `revision`, `kind`, `state`, recorded `applicability`; free-text fields are control-character-escaped so one item stays one line), `collision` lines for multi-authority IDs, `omitted` lines with reason codes, an explicit `no_match` line when nothing was selected (query, filters or limits; when items were skipped the `omitted` lines above it carry the per-item causes), and — with `--material` — the entrypoint content in delimited blocks. The text mode does not print `material_bytes` or the envelope limitations; use `--json` for the complete envelope. The recorded `state` and applicability are printed as recorded and no validation status is invented. Exit 0 covers a result envelope, including no-match and omissions.
- **Side effects:** none; both adapters and the read-only store connection are read-only.
- **Failure behavior:** discovery-wide invalid identities fail the call. Per-item omissions are reported individually. Repository, tier and scenario filters use the package catalog. A backend filter scopes ranked discovery to the requested backend and shared material.
- **Example:** `inferrsi collect --id package:inferrsi.ascend.skills.ascend_graph_mode --id package:inferrsi.ascend.skills.ascend_device_health --context-bytes 65536 --json`

### Read exact material/resources — `read` / `resource` / `KnowledgeReader.read` / `.resource`

- **Inputs:** `read` takes a qualified or unambiguous public ID and an optional `--revision` (the current revision when omitted). Use `--material` for the entrypoint or `--resource <key>` for a specific UTF-8 bundle resource. The `resource` command takes the ID, resource key, exact `--revision` and `--output` path.
- **Scope:** one selected bundle from the package, checkout or store adapter.
- **Output:** `read` returns the bundle view at the requested revision. With `--resource`, it identifies the returned text with `content_resource`. The `resource` command writes raw bytes to the requested output path. Use the same source flag when following up with either command.
- **Side effects:** `resource` writes only the caller-chosen output file.
- **Failure behavior:** ambiguous identity names the qualified choices; unavailable/stale revisions and missing/unsafe resources fail explicitly — no fallback to newer bytes.
- **Example:** `inferrsi read checkout:case.qwen-ascend-rejected-directions --installed-library --material`

## Store candidates (Python)

Open the store with `inferrsi.apps.workflows.knowledge.open_knowledge_store`. Pass the
authorized `store_root` and the store's reserved `skill_root`, if configured.
The default opens an existing store read-only for history. Pass
`writable=True` explicitly to create or update candidates.

### Create / Update — `KnowledgeStore.create` / `.update`

- **Inputs:** a complete candidate `Bundle`; Update additionally requires the expected current revision, a reason and an explicit evidence list.
- **Scope:** one existing, explicitly authorized local store directory; store-owned candidate IDs only.
- **Output:** the new revision; retained immutable history.
- **Side effects:** writes only the store database; never package, checkout, evidence or matrix files.
- **Failure behavior:** duplicate identity, stale expected revision, adapter-owned ID and validation failures are explicit errors.
- **Example:** see [authorized local Create / Update](knowledge-store.md).

CLI/API availability does not itself grant write authority. Adapting read-only
material into a store uses a distinct ID and records `derived_from` lineage; it
never overwrites the original. Amending repository-owned knowledge follows the
normal scoped PR path.

## Experiments

The public preparation, execution and assessment API remains
`inferrsi.apps.api`. Its fixed artifact access and output publication use
`inferrsi.apps.storage.archive`, `artifact_reader` and `result`; the directory
creation helper is `inferrsi.apps.storage.evidence_layout.ensure_evidence_layout`.
The CLI entry remains `inferrsi.apps.cli:main`. See the
[output contract](guides/apps-output.md) and [migration inventory](apps-module-migrations.json)
for the retired Apps imports and their canonical storage paths.
`inferrsi.apps.handoff.bridge`, `handoff.context_provider` and
`handoff.candidate_provider` implement execution/evidence binding, context
delivery and generation handoff. The API still exports the one canonical
`CandidateProvider`; `EvaluationPort` remains defined in `apps.api`.

### Validate/preview a task file — `task validate`, `task preview`

- **Inputs:** one YAML task file (schema v1: `optimization`, `environment`, `acceptance`); `preview` also takes the mapped `plan`/`run` flags as explicit overrides. `task schema` and `task template` print the packaged schema and template.
- **Scope:** format and value errors by field, the effective normalized task with each value's source (`yaml`, `cli`, `default`, `missing` or `invalid`), and the fields a full plan/run still needs.
- **Output:** text, or JSON with `--json`. Exit 0 for a valid file, even an incomplete draft; 1 for an invalid file or a rejected override; 2 for a malformed flag.
- **Side effects:** none. Reads the task file only: no subprocess, probe, install or file write.
- **Failure behavior:** unknown or duplicate keys, unsupported versions and type or range errors are reported with field paths; an acceptance flag that disagrees with the file is a conflict.
- **Example:** `inferrsi task preview task.yaml --json --repetitions 7`

Explicit flags override YAML values, YAML values override built-in defaults, and an
omitted flag never replaces a YAML value. Acceptance fields come from the file. See
[task input](guides/task-input.md). `plan --task` and `run --task` use a complete file with
the same merge (see [use with plan and run](guides/task-input.md#use-with-plan-and-run)).

### Inspect/prepare — `doctor`, `plan`, `--dry-run`

- **Inputs:** repository/backend/device flags; `plan` takes the full experiment specification as flags, or a complete YAML task file with `--task <task.yaml>` plus explicit mapped overrides.
- **Scope:** environment inspection and specification preview.
- **Output:** environment facts, or a preview of the RunSpec. With `--task`, the preview adds a `task` block equal to `task preview --json` for the same file and flags, and a `frozen_gate` block that reports whether the task's acceptance fields agree in content with the local frozen gate record named by `acceptance.reference`. `agrees` is content agreement only; it does not authenticate the record's provenance.
- **Side effects:** `doctor` may invoke bounded read-only probes; `plan`/`--dry-run` persist nothing.
- **Failure behavior:** unavailable devices or invalid flags are reported explicitly. With `--task`, task field errors, conflicting acceptance flags and blockers are printed by field to stderr, exit 2, before any probe. Without `--task`, `--baseline-command` and `--candidate-command` are required.
- **Example:** `inferrsi doctor --repo . --repo-type vllm_omni --backend cpu`

`plan` previews a specification. That preview alone does not persist a frozen
campaign and does not authorize execution. Inspection does not certify target
compatibility.

### Execute/inspect — `run`, `status`, `report`

- **Inputs:** the full experiment specification as flags or as a complete `--task <task.yaml>` (`run`); a run ID and output directory (`status`/`report`). With `--task`, the caller/host must first establish that `acceptance.reference` names the accepted frozen gate record. InferRSI checks that the task and that local record agree in content (`agrees`); it does not authenticate the record's provenance and takes no expected digest.
- **Scope:** caller-supplied benchmark, candidate and validation commands under the experiment contract.
- **Output:** a run ID and evidence directory; recorded progress; an HTML report. With `--task`, the run directory also holds `task.json`, the task preview, and `frozen_gate.json`, the gate result with the record's SHA-256 for citation in the acceptance issue.
- **Side effects:** `run` executes the supplied commands and owns child-process cleanup; `report` writes HTML into the run directory.
- **Failure behavior:** exit codes 0 PASS, 1 FAIL, 2 INCONCLUSIVE/input errors; cancellation is recorded. With `--task`, task field errors and blockers exit 2 before any probe. A task whose acceptance fields differ from the frozen gate record (`mismatch`), or whose gate cannot be checked (`unverified`: an HTTP(S) reference, a missing file, or a record that is not a schema v1 `acceptance` section stating the gate), also exits 2 before any probe; see [frozen gate record](guides/task-input.md#frozen-gate-record). A baseline checkout `HEAD` that differs from `acceptance.baseline_revision` exits 2 after inspection. In all three cases no command starts and nothing is written.

Task-mode RunSpec validation, including local candidate-directory checks, runs before
environment probes. The frozen baseline also binds the execution through the existing
`RunSpec.revision` field, while the observed source identity binds the existing
`RunSpec.snapshot_id`: Harness compares the actual initial and pre-trial baseline
snapshots, including working-tree changes, with those pins. A later
checkout mismatch starts no trial from that snapshot and leaves the failed diagnostic
run as `INCONCLUSIVE` with its source/error facts retained.
- **Example:** see [quickstart: real remote experiment](quickstart.md#real-remote-experiment)

Operation success, recorded execution state and the experiment verdict are
distinct conclusions; a completed run does not upgrade imported knowledge or
unvalidated candidates.

### Inspect a fixed attempt — `status --record-ref`

Pass a JSON `RecordRef` file and its trusted `--storage-config` JSON. An
optional `--assessment-ref` JSON adds the archived claim outcomes and scopes
for the same record revision. The output shows committed execution facts,
including phase, process outcome, cleanup and recording time. A successful
read exits 0. Invalid references, archive integrity failures and mismatched
revisions exit 2.

The execution view preserves the committed `generation_record_ref` in full.
Reports and Dashboards show its attempt ID, fixed record revision and SHA-256,
without displaying its artifact location. A null reference is shown as
"Not linked"; an older saved view without the field is shown as "Unknown".
Reading the view does not open the referenced generation or resolve a current
record, so it can still present a link whose source is unavailable. This is a
recorded association, not a fresh lineage authorization or an assessment.
A missing or malformed reference field in a v1 committed record is an archive
integrity failure; it is not converted to an unlinked record.

The same read-only view is available through
`inferrsi.apps.api.read_attempt_view`. The legacy `status --run-id` form
reads the legacy experiment directory.

Use the same reference files with `trace`, `report` or `dashboard`.
`trace` prints the view plus recorded steps, checks and error codes. An
unknown step time stays null. `report` and offline `dashboard` accept
`--output <file.html>` and present the same facts and claims. With
`dashboard --live`, the loopback page and its state endpoint serve the
snapshot pinned at startup. The campaign Dashboard remains available through
`--input`, including its reviewed translation overlay.

## Campaign summary figure

### Summarize a campaign figure — `tools/campaign_summary_chart.py`

- **Inputs:** one JSON specification (chain of accumulating steps, or a set of independent trials); an output path.
- **Scope:** recorded values only. The renderer computes gains, validates the specification and writes a figure; it measures nothing.
- **Output:** an SVG figure, plus a Markdown table with the same values when `--markdown` is given. `report` and `run` also write `summary-chart.svg` into the run directory and inline it in the HTML report. When selected trial checks leave the current comparison incomplete, the report omits the figure (including a campaign specification) and removes any previously generated SVG; raw measurements and the campaign JSON remain available.
- **Side effects:** writes the requested files; nothing is executed and no network or GPU is touched.
- **Failure behavior:** exit code 2 with the offending field name when the specification is incomplete, ambiguous or inconsistent; a report without a paired measurement states why it has no figure.
- **Example:** [campaign summary chart](dashboard/campaign-summary-chart.md)

## Optimization requests

- **Measure the value of knowledge.** Start with `inferrsi benchmarks compare --help`
  and follow `next_action`. The default comparison uses Qwen denoising and MoE
  forward in independent on/off sessions. See the [comparison workflow](benchmarks/benchmark-comparison.md).
- **Optimize your project.** Use `inferrsi campaign` in the current Agent
  conversation. Supply the workload, metric, gates, scripts and budget, then
  record the measured bottleneck before candidate search. The
  [shared workflow](guides/optimization-workflow-unification.md) defines round limits,
  recovery and dashboard generation from the Harness control record.
- **Optimize a packaged task.** Follow the [benchmark session workflow](benchmarks/optimization-benchmarks.md)
  through rounds and independent final retest. By default the initiator prepares,
  dispatches and binds one [fresh native session](guides/native-agent-sessions.md). The
  execution Agent owns the optimization lifecycle without redelegating. An
  explicit current-conversation request uses the same workflow directly.
  `benchmarks run` measures one candidate within that workflow.
