# Operation guide

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
| Search packaged records | CLI `knowledge search` / `knowledge show`; catalog API | Read-only | Installed package catalog with the existing tier/repo/backend/scenario filters and IDs; these package-only filters exclude skills and cases from every other authority |
| Prepare model-aware engine research | CLI `knowledge research`; Python `research_knowledge` | Read-only | Independent model/framework/task/modality/mechanism queries over the same package catalog; source-grounded known profiles, deduplicated matches and explicit target annotations; no engine/hardware qualification |
| Discover/read packaged or custom skills | CLI `skills list` / `show` / `resource` / `reference` | Read-only | Metadata-first listing; `show` loads one named instruction body; `resource`/`reference` resolve paths for your file reader without loading or executing them |
| Collect normalized knowledge | CLI `collect`; Python `KnowledgeReader.collect` | Read-only | Explicit sources, authority-qualified identities, exact revisions, bounded output and explicit omissions |
| Read exact material/resources | CLI `read` / `resource`; Python `KnowledgeReader.read` / `KnowledgeReader.resource` | Read-only | Returns the requested revision or an explicit unavailable/stale error; never substitutes newer bytes |
| Export legacy cited material | CLI `context` | Read-only | Cited package export for manual use with a coding agent; not a conversation store and not a full Collect equivalent |
| Create/update a store candidate | Python `KnowledgeStore.create` / `KnowledgeStore.update` | Candidate-writing | One explicitly authorized local store; expected-revision updates with reason and evidence; retained history; no promotion and no edits to package/checkout content |
| Amend repository-owned knowledge | Scoped repository PR | — | Repository review and integration authority apply; this is not a runtime store Update |
| Inspect/prepare experiments | CLI `doctor`; `plan` or `--dry-run` | Read-only inspection / preview | `doctor` may invoke bounded probes and does not certify target compatibility; `plan` previews a specification without persisting a campaign or authorizing execution |
| Execute/inspect experiments | CLI `run`; `status`; `report` | Experiment-executing / read-only / report-generating | `run` executes caller-supplied commands and records evidence; `status` reads recorded progress; `report` generates HTML from recorded evidence |
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

- **Inputs:** query words plus optional `--tier`, `--repo-type`, `--backend`, `--scenario`, `--limit`, `--json`; `show` takes one record ID.
- **Scope:** the installed package catalog (`repo_packs`, `knowledge_packs`) only.
- **Output:** tab-separated record lines (id, status, backend, title), or a JSON list with `--json`; `show` prints one full record as JSON.
- **Side effects:** none.
- **Failure behavior:** no match prints nothing and exits 0 — an empty result is not an error (an empty JSON list with `--json`); an unknown `show` ID and unsupported filter values exit 2.
- **Example:** `inferrsi knowledge search 'Qwen-Image-2.1' --repo-type vllm_omni --backend ascend`

The tier/repo/backend/scenario filters are package-only: an empty filtered
result does not mean that no checkout or store knowledge exists. See the
[three-tier guide](../src/inferrsi/data/knowledge_packs/README.md) for all sources.

### Prepare model-aware research — `knowledge research`

- **Inputs:** model identity; repeatable `--framework`, `--task`, `--modality`, `--mechanism`; existing `--tier`, `--repo-type`, `--backend`, `--scenario` hard filters and `--limit` output cap; optional `--target-backend`, `--target-device`, positive finite `--target-memory-gib` annotations.
- **Scope:** installed package records only. A packaged MiniMax-H3 profile supplies its source-grounded diffusion/video/audio identity and component roles. Unknown models use only caller-supplied dimensions and need source inspection; no architecture is guessed.
- **Output:** JSON query groups and match counts, a bounded deduplicated union with `matched_queries`, unchanged full records/provenance, active filters, component roles, preparation/example resource paths and an unverified target state. Queries take turns contributing results; this ordering does not rank engine quality.
- **Side effects:** none; no network requests, hardware probes, model download or engine execution. Target annotations do not add runtime backends.
- **Failure behavior:** no match returns an explicit empty envelope and exits 0; invalid limits/memory or unsupported catalog filters exit 2. A zero-match dimension stays visible.
- **Example:** `inferrsi knowledge research MiniMax-H3 --framework mlx --target-backend metal --target-device "M5 Mac Studio" --target-memory-gib 64 --limit 12`
- **Python:** `from inferrsi.research import research_knowledge`; `research_knowledge("MiniMax-H3", frameworks=["mlx"], modalities=["video"], limit=12)`.

Exact `knowledge search` and `context` still AND query tokens. Independent
research queries broaden discovery without relaxing the active package filters.
Keep those filters explicit when transferring mechanisms from other backends;
target intent does not qualify their applicability. Read the canonical
[preparation procedure](../src/inferrsi/data/skill_library/workflows/inference-engine-research/references/model-aware-preparation.md)
and the repository-owned [h3.c residency audit](../src/inferrsi/data/skill_library/repositories/h3-c/audit-h3-runtime-residency/SKILL.md)
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
- **Example:** `inferrsi collect 'Ascend OOM' --kind case --limit 3 --material --skill-root src/inferrsi/data/skill_library`

### Read exact material/resources — `read` / `resource` / `KnowledgeReader.read` / `.resource`

- **Inputs:** `read` takes a qualified or unambiguous public ID and an optional `--revision` (the current revision when omitted); `resource` takes the ID, a relative resource key, and the **required** exact `--revision` returned by collect/read plus the required `--output` path.
- **Scope:** one selected bundle from the package, checkout or store adapter.
- **Output:** the bundle view at the requested revision, or the resource bytes (`resource` writes them to the required `--output` path).
- **Side effects:** `resource` writes only the caller-chosen output file.
- **Failure behavior:** ambiguous identity names the qualified choices; unavailable/stale revisions and missing/unsafe resources fail explicitly — no fallback to newer bytes.
- **Example:** `inferrsi read calibrate-serving-simulation --skill-root src/inferrsi/data/skill_library --material`

## Store candidates (Python)

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

## Campaign summary figure

### Summarize a campaign figure — `tools/campaign_summary_chart.py`

- **Inputs:** one JSON specification (chain of accumulating steps, or a set of independent trials); an output path.
- **Scope:** recorded values only. The renderer computes gains, validates the specification and writes a figure; it measures nothing.
- **Output:** an SVG figure, plus a Markdown table with the same values when `--markdown` is given. `report` and `run` also write `summary-chart.svg` into the run directory and inline it in the HTML report.
- **Side effects:** writes the requested files; nothing is executed and no network or GPU is touched.
- **Failure behavior:** exit code 2 with the offending field name when the specification is incomplete, ambiguous or inconsistent; a report without a paired measurement states why it has no figure.
- **Example:** [campaign summary chart](campaign-summary-chart.md)
