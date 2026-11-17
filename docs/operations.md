# Operation guide

Packaged engineering tasks use `inferrsi benchmarks list|show` for read-only
discovery and `inferrsi benchmarks run <package> ...` to execute its own entry.
The [task library](engineering-benchmarks.md) links the MoE forward,
Qwen-Image denoising and Qwen3-TTS execution protocols. Their task-specific
entries run inside caller-managed NPU allocations.

For a complete optimization benchmark, the current Agent uses
[`benchmarks session`](optimization-benchmarks.md) to freeze the task, retrieve
permitted context, submit changed candidates, inspect feedback and independently
retest the selection. The first iterative task is Qwen-Image denoising.

One concise map from an agent's intent to the supported entry point. This guide
is navigation only: detailed contracts stay with their owning documents, and it
is not a third primary matrix. The two authoritative matrices remain the
[Reference Matrix](reference-matrix.md) and the [SearchSpace Matrix](searchspace-matrix.md).

Effect classes used below:

- **Read-only** — no writes outside caller-chosen output files.
- **Candidate-writing** — writes only inside one explicitly authorized local store.
- **Report-generating** — writes an HTML report into the caller-selected run directory.
- **Experiment-executing** — runs caller-supplied commands under the experiment contract.

## Intent map

| Intent | Entry | Effect class | Boundary |
| --- | --- | --- | --- |
| Complete a task optimization in the current Agent | CLI `benchmarks session start/knowledge/round/status/final/recover` | Experiment-executing / local records | Frozen budget, actual candidates and independent task outcomes. The current Agent drives edits. Real usage is imported explicitly. Recovery collects an existing execution |
| Optimize an ordinary project in the current Agent | CLI `campaign start/knowledge/round/status/final/recover` | Experiment-executing / local records | Harness freezes explicit caller-provided checks, manages multi-file candidates, executes and assesses retained results. This path does not depend on Benchmark or infer acceptance from the goal. See [shared workflow](optimization-workflow-unification.md) |
| Prepare and record a fresh native Agent | CLI `agents prepare/dispatch/bind/record/status` | Local records / explicit host handoff | The initiating Agent calls native host tools. Records prevent repeated dispatch; exported host observations do not establish task acceptance. See [native sessions](native-agent-sessions.md) |
| Discover packaged tasks | CLI `benchmarks list` / `benchmarks show`; Python `benchmark.registry.builtin_tasks` / `describe_task` | Read-only | Reads the task library's registry and opaque manifests from installed resources |
| Execute one packaged task | CLI `benchmarks run`; Python `apps.benchmark_operations.run_task` | Experiment-executing | Application launches the task entry, supplies the execution callback and preserves arguments and exit status. The task owns its device, measurement and assessment protocol |
| Search packaged records | CLI `knowledge search` / `knowledge show`; catalog API | Read-only | Installed package catalog with the existing tier/repo/backend/scenario filters and IDs; these package-only filters exclude skills and cases from every other authority |
| Prepare model-aware engine research | CLI `knowledge research`; Python `research_knowledge` | Read-only | Independent model/framework/task/modality/mechanism queries over the same package catalog; source-grounded known profiles, deduplicated matches and explicit target annotations; no engine/hardware qualification |
| Discover/read packaged or custom skills | CLI `skills list` / `show` / `resource` / `reference` | Read-only | Metadata-first listing; `show` loads one named instruction body; `resource`/`reference` resolve paths for your file reader without loading or executing them |
| Rank relevant cases, skills and records | CLI `find` | Read-only | Search the registered library and package records in one list. Follow the emitted command to read a hit and its revision |
| Collect normalized knowledge | CLI `collect`; Python `KnowledgeReader.collect` | Read-only | Explicit sources, authority-qualified identities, exact revisions, bounded output and explicit omissions |
| Read exact material/resources | CLI `read` / `resource`; Python `KnowledgeReader.read` / `KnowledgeReader.resource` | Read-only | Returns the requested revision or an explicit unavailable/stale error; never substitutes newer bytes |
| Export legacy cited material | CLI `context` | Read-only | Cited package export for manual use with a coding agent; not a conversation store and not a full Collect equivalent |
| Create/update a store candidate | Python `KnowledgeStore.create` / `KnowledgeStore.update` | Candidate-writing | One explicitly authorized local store; expected-revision updates with reason and evidence; retained history; no promotion and no edits to package/checkout content |
| Inspect a store candidate's history | Python `open_knowledge_store(...).history` | Read-only | Opens an existing store and reads the revision lineage for one store ID |
| Amend repository-owned knowledge | Scoped repository PR | — | Repository review and integration authority apply; this is not a runtime store Update |
| Inspect/prepare experiments | CLI `doctor`; `plan` or `--dry-run` | Read-only inspection / preview | `doctor` may invoke bounded probes and does not certify target compatibility; `plan` previews a specification without persisting a campaign or authorizing execution |
| Execute/inspect experiments | CLI `run`; `status`; `report` | Experiment-executing / read-only / report-generating | `run` executes caller-supplied commands and records evidence; `status` reads recorded progress; `report` generates HTML from recorded evidence |
| Inspect/verify archived evidence | `python tools/verify_evidence_archive.py`; [archive contract](evidence-archiving.md) | Read-only by default; explicit network/local scratch with `--download` | Default validates metadata offline; `--archive`/`--download` authenticates and bounds archive reading; `--recomputed` compares separately generated v2 results; never executes archived code or changes verdicts |
| Rebuild scoped legacy evidence views | `python tools/rebuild_model_evidence.py <manifest> --archive <path> --output <new-directory>` | CPU-only; creates a new output directory | Authenticates original bytes and pinned projection/code; no extraction, network, archived-code execution or campaign qualification |
| Inspect evidence inventory / generate budget input | `python tools/validate_evidence.py [--budget-assets]` | Read-only | Offline layout/hash/schema checks; optional disposable #328 metadata view derived from campaign authority; no downloads |
| Execute one ordinary local CPU command with a fixed record | Python `inferrsi.harness.api.Harness.allocate` / `execute` / `read` | Experiment-executing / record-writing | One explicit RunStore root and one trusted local CPU target; ordinary command mode only; a record holds execution facts, so exit 0 is not a verdict; no device, model or network fallback |
| Visualize a recorded run or campaign | CLI `dashboard`; [dashboard](dashboard.md) | Report-generating / local read-only serving | Writes an offline HTML snapshot or serves an optional live view on loopback; does not run an agent or validate a claim |
| Capture a knowledge context | CLI `campaign capture-context`; [offline dashboard](dashboard.md#record-the-optimization-story-campaign-trace) | Local evidence-writing | Runs `collect` with a context budget and keeps the full envelope and resource hashes in a new `knowledge/<id>.json`; proves what was prepared, not what a model read |
| Retain an executed retrieval | Python `apps.campaign.save_retrieval`; [capture contract](knowledge-retrieval-trace.md#retain-a-standalone-result) | Local evidence-writing | Saves an existing catalog/collect result under a fresh campaign capture ID; no new search or automatic publication |
| Import one round of knowledge searches | CLI `campaign import-search`; [round import](dashboard.md#import-one-rounds-searches) | Local evidence-writing | Reads a Codex rollout window or context captures. With `--archive-review`, retains excerpts of attributable tool returns and reviewed decisions for readers of the evidence bundle. |
| Record the optimization log | CLI `campaign log`; [offline dashboard](dashboard.md#record-the-optimization-story-campaign-trace) | Local evidence-writing | Validates and stores a new numbered campaign log version; the dashboard cross-checks it against captures and runs |
| Assemble an optimization trace | CLI `campaign assemble-trace`; [offline dashboard](dashboard.md#capture-the-optimization-trace) | Local evidence-writing | Copies an explicitly reviewed context into a new bounded campaign-root snapshot; caller owns redaction and narrative accuracy |
| Import a MindIE read | CLI `campaign import-mindie`; [Codex workflow](codex-plugin.md#mindie-knowledge) | Local evidence-writing | Retains caller-supplied query/explain bytes and hashes, exports delivered graded bodies and a trace context fragment; no activation, model call, transcript capture or automatic caller review |
| Associate runs with a local campaign | CLI `campaign init` / `campaign record` / `campaign decide`; [offline dashboard](dashboard.md) | Local evidence-writing | Legacy manual records reference existing artifacts and never start an agent; record/decide cannot mutate a managed optimization campaign |
| Adapt existing Flare delivery evidence | [Offline qualification adapter](flare-qualification.md), `python -m inferrsi.model.validators.flare` | Read-only | Existing raw packets and a separate receipt; one HTTP delivery metric, no model/server/device execution |
| Evaluate selected skill revisions | [Bounded skill-evaluation driver](skill-evaluation.md) | Experiment-executing | Explicitly authorized real Codex calls, independent task verdicts and private evidence; separate from numeric engine-performance scoring |
| Compare skill additions or updates | [Configured skill comparison](skill-eval-comparison.md), `python -m tools.skill_eval_compare` | Read-only preparation / experiment-executing / report-generating | Fixed Git snapshots and one shared exam; explicit plan authorization for execution; JSON + Markdown regeneration makes no model calls |
| Export a cloud-generated parser pair | [Generation-only protocol](skill-eval-generation-only.md), `python -m tools.skill_eval_cloud_export` | Local evidence-writing; no execution or publication | Validates frozen inputs and retained sources; writes one bounded inert JSON bundle, never executes parser source |
| Run the fixed historical parser generation pilot | [Main-only historical job](skill-eval-historical-job.md), `python -m tools.skill_eval_historical_job` | Authorized paid generation / ledger-writing / evidence-writing | No dispatch inputs; reviewed main policy, pre-secret freeze, existing credentials, two-request cap; no generated-source execution or automatic retry |
| Qualify an artifact verifier host | [Manual reviewer qualification](skill-eval-reviewer-qualification.md), `python -m tools.skill_eval_qualify` | Trusted-control execution / report-generating | Manual main-only workflow; fixed software controls, no model or external artifact input; unavailable isolation fails rather than skips |
| Replay a cloud-generated parser pair | [Isolated cloud replay](skill-eval-cloud-replay.md), `python -m tools.skill_eval_cloud_replay` | Untrusted-artifact execution / report-generating | Manual pinned data ingress; same-host controls before bubblewrap-only replay; no models or credentials |
| Validate one harness-improvement step | [Offline improvement](harness-improvement.md), Python `tools.skill_eval_improve.prepare` / `run_offline` | Snapshot-writing / offline experiment-executing | Supplied declarative INV/DOM edits, shared total limits, rerun and one holdout gate; trusted fixed-output clients only; no real-model or Store execution |
| Plan and report skill PR evaluations | [Skill PR integration](skill-eval-pr.md), `python -m tools.skill_eval_pr` | Read-only planning / authorized experiment-executing / PR-publishing | Trusted mapping, exact operator approval, consumed execution identity and credential-separated publication from retained evidence; no automatic paid trials |
| Recover goal progress and the next proposal | [Offline goal checkpoints](goal-checkpoints.md), `python -m tools.goal_checkpoint` | Read-only | Explicit scope/criteria, pinned owner decisions and existing comparison receipts; a disposable view, never execution or acceptance authority |
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

- **Inputs:** query words plus optional `--tier`, `--repo-type`, `--backend`, `--scenario`, `--limit`, `--json`, `--explain`; `show` takes one record ID.
- **Scope:** the installed package catalog (`repo_packs`, `knowledge_packs`) only.
- **Output:** tab-separated record lines (id, status, backend, title), or a JSON list with `--json`; `--explain` returns a JSON envelope with `items` and `retrieval` (entry, ranking, scores and counts). Python uses `search_knowledge(..., explain=True)` for that envelope. `show` prints one full record as JSON.
- **Side effects:** none.
- **Failure behavior:** no match prints nothing and exits 0 — an empty result is not an error (an empty JSON list with `--json`, or empty `items` in the `--explain` envelope); an unknown `show` ID and unsupported filter values exit 2.
- **Example:** `inferrsi knowledge search 'Qwen-Image-2.1' --repo-type vllm_omni --backend ascend`

The tier/repo/backend/scenario filters are package-only: an empty filtered
result does not mean that no checkout or store knowledge exists. See the
[three-tier guide](../src/inferrsi/knowledge/data/knowledge_packs/README.md) for all sources.

### Prepare model-aware research — `knowledge research`

- **Inputs:** model identity; repeatable `--framework`, `--task`, `--modality`, `--mechanism`; existing `--tier`, `--repo-type`, `--backend`, `--scenario` hard filters and `--limit` output cap; optional `--target-backend`, `--target-device`, positive finite `--target-memory-gib` annotations.
- **Scope:** installed package records only. A packaged MiniMax-H3 profile supplies its source-grounded diffusion/video/audio identity and component roles. Unknown models use only caller-supplied dimensions and need source inspection; no architecture is guessed.
- **Output:** JSON query groups and match counts, a bounded deduplicated union with `matched_queries`, unchanged full records/provenance, active filters, component roles, preparation/example resource paths and an unverified target state. Queries take turns contributing results; this ordering does not rank engine quality.
- **Side effects:** none; no network requests, hardware probes, model download or engine execution. Target annotations do not add runtime backends.
- **Failure behavior:** no match returns an explicit empty envelope and exits 0; invalid limits/memory or unsupported catalog filters exit 2. A zero-match dimension stays visible.
- **Example:** `inferrsi knowledge research MiniMax-H3 --framework mlx --target-backend metal --target-device "M5 Mac Studio" --target-memory-gib 64 --limit 12`
- **Python:** `from inferrsi.knowledge.research import research_knowledge`; `research_knowledge("MiniMax-H3", frameworks=["mlx"], modalities=["video"], limit=12)`.

Exact `knowledge search` and `context` still AND query tokens. Independent
research queries broaden discovery without relaxing the active package filters.
Keep those filters explicit when transferring mechanisms from other backends;
target intent does not qualify their applicability. Read the canonical
[preparation procedure](../src/inferrsi/knowledge/data/skill_library/workflows/inference-engine-research/references/model-aware-preparation.md)
and the repository-owned [h3.c residency audit](../src/inferrsi/knowledge/data/skill_library/repositories/h3-c/audit-h3-runtime-residency/SKILL.md)
for native-engine reference selection, full encoder/DiT/VAE accounting,
quantized-package compatibility and target hardware decisions. Returned resource
paths are relative to `importlib.resources.files("inferrsi")` and ship in the wheel.
The small model profile links that skill's full inventory and worked example;
those resources retain their repository owner and source attribution.

### Discover/read packaged or custom skills — `skills list` / `show` / `resource` / `reference`

- **Inputs:** `list` reads frontmatter and sidecar metadata; `show <skill>` selects one instruction body; `resource <skill> <relative-path>` and `reference <skill> <relative-path>` resolve one path. The default is the installed library's registered skills; an explicit `--root` selects a custom flat tree or a categorized library with `skill-index.json`. The optional `skills` extra supplies the YAML parser.
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

Three properties distinguish it from the Collect selection path below. Cases are
ranked beside skills instead of being reachable only after their owner is
chosen, because a recorded rejected direction is the material retrieval can
supply that re-reading current source cannot. One matching term is enough to
rank an entry, and `--limit` caps the result list. Scoring reads corpus
files directly rather than Bundles, whose metadata lists the whole packaged
library as one dependency closure. The reader validates the returned material
without pinning a revision during search.

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

Chinese query terms expand through `data/query_aliases.json` before ranking.
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
  `checkout:` read reference uses the installed library as `--skill-root`.
  Where recorded, items carry source, summary, applicability, limitations and
  local verification status. Case findings are ordered by query overlap,
  with `findings_total` and `findings_withheld` describing the available preview.
  Each finding carries its outcome, reason, revisit condition and any assessed
  scope and bounds. `bounds_source` identifies whether bounds apply to the
  finding or the whole entry. The envelope reports `corpus_size`, `matched`,
  `no_match`, any `expanded` terms and retrieval limitations.
- **Reading a hit.** Plain output prints a POSIX `open` command or a labelled
  PowerShell command on Windows. JSON exposes the rendered command as `ref`,
  full subprocess arguments as `open_argv` and InferRSI CLI arguments as
  `read_args`. The arguments include the source-qualified ID and a skill root
  where needed. They use `read --material --omit-resources` to return the
  entrypoint, provenance and revision with a smaller response. Remove
  `--omit-resources` to list the bundle's resources. Hits that fail the reader's
  material check carry `unreadable` with the reason.
- **Base installation fallback.** When a Skill hit requires PyYAML, run a new
  search of the packaged Skills with
  `inferrsi collect --relevance "<same query>" --limit 1 --material --json`.
  It may select a different Skill. Check that the returned Skill fits your
  task, then fetch its `skill_documents.original` with
  `inferrsi resource <ref> <path> --revision <revision> --output <file>` using
  the `ref` and `revision` from the new result.
- **Side effects:** none. No revision is pinned; use `read`/`resource` when a capture or evidence record needs exact bytes.
- **Example:** `inferrsi find "NPU OOM after caching per-step masks" --limit 3` returns the casebook entry recording that attempt first. A vaguer phrasing ranks the procedural skills above it, which is the first limit below rather than a defect.

#### External channels are not installed with this package

`find` also queries external read-only channels when the task backend is
declared. **A fresh install has none**, so a query that the packaged corpus
cannot answer returns `no_match` with no external results. That is the default
state, not a fault:

```text
no_match    135 entries searched; rephrase, or search the corpus directly with rg

external (not locally verified; scores are not comparable across channels)
  cannbot-knowledge  [not_enabled]  cannbot knowledge is not enabled for this project
     fix: inferrsi cannbot enable --checkout <path> --python <interpreter>
```

Enabling a channel is a deliberate, per-checkout action by a person; see
[external knowledge channels](external-channels.md). This repository does not
clone, download or bundle the corpus automatically. Review the upstream terms
for the intended use before granting access; source permissions remain separate
from this integration mechanism.

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

Optional `--relevance <CUE>` ranks generated packaged skills after the existing
query and filters; `--context-bytes <N>` returns their complete core plus bounded
whole reference resources in a separate view. They preserve default calls,
explicit-ID membership/order, `material` and the serialized-item `max_bytes`
budget. Context counts UTF-8 body bytes separately and reports unavailable or
oversized context explicitly. See [selection and context](knowledge-operations.md#optional-packaged-skill-selection-and-context)
for scoring, provenance and accounting. For example:
`inferrsi collect 'cpu.stat.local' --relevance cgroupv2 --context-bytes 65536 --json`.

- **Inputs:** optional query, `--kind`, repeatable explicit `--id`, repeatable `--revision ID=REV`, `--limit`, `--max-bytes`, `--material`; `--skill-root` selects an explicit skills root, `--store` opens an existing store read-only (the store records its reserved skills root and rejects a mismatched or missing `--skill-root`).
- **Scope:** installed package records plus (with `--skill-root`) skills and cases from the explicitly selected root, plus (with `--store`) store candidates; bounded output.
- **Output:** with `--json`, the complete **normalized** envelope — items carrying the bundle's normalized metadata, resources and dependencies, plus `no_match`, `omissions`, `collisions`, `material_bytes` and the recorded limitations; fields that exist only in a package record's original entrypoint document are not projected into the normalized metadata and are read via `--material` or `resource`. Without `--json`, the envelope's selection is projected line-wise: one tab-separated line per item (`ref`, `revision`, `kind`, `state`, recorded `applicability`; free-text fields are control-character-escaped so one item stays one line), `collision` lines for multi-authority IDs, `omitted` lines with reason codes, an explicit `no_match` line when nothing was selected (query, filters or limits; when items were skipped the `omitted` lines above it carry the per-item causes), and — with `--material` — the entrypoint content in delimited blocks. The text mode does not print `material_bytes` or the envelope limitations; use `--json` for the complete envelope. The recorded `state` and applicability are printed as recorded and no validation status is invented. Exit 0 covers a result envelope, including no-match and omissions.
- **Side effects:** none; both adapters and the read-only store connection are read-only.
- **Failure behavior:** discovery-wide invalid identities fail the call; per-item omissions are reported individually. Package repo/tier/backend/scenario filters exclude checkout items.
- **Example:** `inferrsi collect 'Ascend OOM' --kind case --limit 3 --material --skill-root src/inferrsi/knowledge/data/skill_library`

### Read exact material/resources — `read` / `resource` / `KnowledgeReader.read` / `.resource`

- **Inputs:** `read` takes a qualified or unambiguous public ID and an optional `--revision` (the current revision when omitted); `resource` takes the ID, a relative resource key, and the **required** exact `--revision` returned by collect/read plus the required `--output` path.
- **Scope:** one selected bundle from the package, checkout or store adapter.
- **Output:** the bundle view at the requested revision, or the resource bytes (`resource` writes them to the required `--output` path).
- **Side effects:** `resource` writes only the caller-chosen output file.
- **Failure behavior:** ambiguous identity names the qualified choices; unavailable/stale revisions and missing/unsafe resources fail explicitly — no fallback to newer bytes.
- **Example:** `inferrsi read calibrate-serving-simulation --skill-root src/inferrsi/knowledge/data/skill_library --material`

## Store candidates (Python)

Open the store with `inferrsi.apps.knowledge.open_knowledge_store`. Pass the
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

### Inspect/prepare — `doctor`, `plan`, `--dry-run`

- **Inputs:** repository/backend/device flags; `plan` takes the full experiment specification.
- **Scope:** environment inspection and specification preview.
- **Output:** environment facts, or a preview of the RunSpec.
- **Side effects:** `doctor` may invoke bounded read-only probes; `plan`/`--dry-run` persist nothing.
- **Failure behavior:** unavailable devices or invalid flags are reported explicitly.
- **Example:** `inferrsi doctor --repo . --repo-type vllm_omni --backend cpu`

`plan` previews a specification. That preview alone does not persist a frozen
campaign and does not authorize execution. Inspection does not certify target
compatibility.

### Execute/inspect — `run`, `status`, `report`

- **Inputs:** the full experiment specification (`run`); a run ID and output directory (`status`/`report`).
- **Scope:** caller-supplied benchmark, candidate and validation commands under the experiment contract.
- **Output:** a run ID and evidence directory; recorded progress; an HTML report.
- **Side effects:** `run` executes the supplied commands and owns child-process cleanup; `report` writes HTML into the run directory.
- **Failure behavior:** exit codes 0 PASS, 1 FAIL, 2 INCONCLUSIVE/input errors; cancellation is recorded.
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
- **Example:** [campaign summary chart](campaign-summary-chart.md)
