# Offline optimization dashboard

For existing Ascend experiments, see [external optimization records](dashboard-external-records.md)
to connect protocol-specific measurements, verdicts and events without fabricating a harness run.


The dashboard renders a recorded InferRSI run or an explicitly assembled
campaign as a single HTML file. It needs no web service or external assets.
It is a read-only view of recorded data; generating it does not run an
experiment, capture an agent, validate performance, or accept a campaign.

## Generate and open

Install InferRSI as described in [quickstart](quickstart.md), then run:

```sh
inferrsi dashboard --input <RUN_OR_CAMPAIGN_DIRECTORY> --output <OUTPUT_HTML>
```

Omit `--output` to write `dashboard.html` in the input directory. Open the file
in a browser. Filters and review export work locally. A generated snapshot does
not update as an experiment runs; regenerate it to show new records.

### Live observation

To observe a run or campaign while its records are being written, start the
optional read-only server on that machine:

```sh
inferrsi dashboard --input <RUN_OR_CAMPAIGN_DIRECTORY> --live --port 8765
```

Open the printed URL in a browser. The page checks for recorded changes about
every three seconds without reloading and keeps the language, filters, selected
candidate, expanded details and review text where possible. The header shows
the last successful check and warns when refresh fails; the last view remains
visible while it retries. Press Ctrl-C to stop the server. `--translations`
also works in live mode. Use the original command without `--live` whenever an
offline HTML snapshot is needed.

The server always binds to `127.0.0.1`, with no non-loopback binding option,
and serves only the dashboard and its view data, not the experiment directory.
For a remote machine, use an SSH local port
forward, for example `ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 <remote>`.
The server has no authentication: other users on the same host can access its
loopback port. Review recorded context before exposing a forwarded port or
sharing a snapshot.

Live mode reads the same files as the offline export; it does not start an
experiment, capture an agent's reasoning, or create records. A running result
can be incomplete, and concurrently written files do not form a transactional
snapshot. Benchmark verdicts and metrics appear only once recorded. Context,
search space and narrative must be captured and updated by the caller during
the experiment.

### Follow one round

Select a candidate to open its **Run review**. The first four sections show
the initial assembled context, the options considered, the recorded selection
rules and the path taken. Each round has its own hash-bound trace. In the
search path, an event link opens the matching source record in a dialog.
The Markdown feedback export includes the selected round's inputs and path.

Before starting a candidate, save the final assembled context verbatim. Freeze
its options and rationale in the trace template, then use
`campaign assemble-trace --context-file <FILE>` as shown below. Record a new
snapshot for each round and retain the initial one when appending results.
The optional `search_space.selection_rules` array holds the criteria in order.
For example, a lossless image campaign might require identical decoded RGB
pixels before ranking latency. Missing historical fields display as unrecorded.

The native runner records phase starts for source snapshots, measurements and
validation. The dashboard checks the source snapshot and each command's
`execution.json` for completion. The latest start matching the running phase
in `status.json` identifies the open step. A recorded command duration excludes
the runner's surrounding source probes. The phase finish time stays unknown
unless the log contains a matching `_end` event. Paired events can also show
the full phase duration and wall-clock span. Service latency comes from the
measured request metric.

Performance progress counts completed baseline and candidate trial commands.
Accuracy progress counts the validator command by default. A validator that
knows its own workload can atomically replace `validation/progress.json` in
its run with `{"unit":"cases","completed":4,"total":10}`. A single writer owns
the absolute count. Units are `cases`, `samples` or `manifests`; use null for
an unknown total. The Qwen image validator writes each checked manifest count
beside the executor's `RUN/validation/result.json`, including failed checks.
A missing or malformed counter leaves the command-level progress and verdict
intact.

Run directories separate repeated attempts. Duplicate edges within one run
count once; conflicting observations or older starts with no finish leave the
count unknown. Agent events still need the campaign correlation fields. Codex
turns, command completions and errors and Anthropic request, tool and completion
events have readable labels. The raw event type and source line remain available;
command output and message content stay in the original trace.

### Language

The header switches the offline interface, chart labels and review export between
English and Chinese. The language choice is saved in browser storage when
available. Filter and candidate selections stay in place when switching.

Recorded narratives are caller-provided text; the dashboard does not send them
to a translation service or infer translations. To include reviewed translations,
pass `--translations <FILE>` when exporting. The UTF-8 file maps the exact
recorded text to its translation in each target language:

```json
{
  "schema_version": 1,
  "zh": {"Reduce launch overhead": "减少启动开销"},
  "en": {"减少启动开销": "Reduce launch overhead"}
}
```

Both language maps are optional. Each key must match the complete original
field, including whitespace; the file is limited to 2 MiB and duplicate keys
are rejected. The overlay applies only to explicitly marked caller-authored
narrative fields; verdicts, quality, evidence states and other fixed UI labels
use code-owned translations even if the overlay contains the same text.
Untranslated text remains in the original language. Commands, identifiers,
structured event fields and chart labels other than the recorded chart title are kept as recorded. When a knowledge
context has a supplied translation, the page labels it as a translation and
offers the complete original separately. The overlay is supplied and reviewed
by the caller, not verified by InferRSI; review it for accuracy and sensitive
content before exporting or sharing. It is embedded in the resulting HTML.

The input can be one existing run directory containing `run.lock.json`, or a
campaign containing `campaign.json`. Existing runs need no migration. Missing
events, validation, trace and other evidence are shown explicitly; no missing
metric is replaced with zero.

## Campaign integration

The following optional layout associates multiple runs with candidate and round
records. Create the manifest and supply your own campaign ID and optional target:

```sh
inferrsi campaign init --directory <CAMPAIGN_DIRECTORY> --id <CAMPAIGN_ID> \
  --target-pct <TARGET_FROM_ACCEPTANCE_ISSUE>
```

Use `inferrsi run --output-dir <CAMPAIGN_DIRECTORY>/runs` to produce the existing
run directories. After a run ID exists, associate it with a candidate and round:

```sh
inferrsi campaign record --directory <CAMPAIGN_DIRECTORY> --candidate <CANDIDATE_ID> \
  --run-id <RUN_ID> --round <ROUND_NUMBER> --title '<CANDIDATE_TITLE>'
```

Optional `--agent-trace` and `--profile` arguments point to existing,
campaign-relative files; the recorder hashes them and does not copy them. The
caller assigns IDs and must serialize campaign record updates. Neither command
starts an agent or validates the experiment.

### Import one round's searches

A search import writes `search/round-<n>.json` inside an existing campaign.
The record can exist before a candidate or run. Read it directly with a JSON
viewer. The agent or host selects the trace for its own session and keeps the
original private. When the Desktop host exposes `CODEX_THREAD_ID`, the agent
can locate its own rollout by matching that exact thread ID in the filenames
under the local Codex sessions directory. A host can also supply the trace
path directly. The import command only opens the supplied file.

For example, set `campaign` to the campaign directory, `trace` to the local
Codex Desktop rollout JSONL and `corpus` to the absolute skill-library path
**as it appeared in that session**. The importer normalizes path components
such as `.` and `..` lexically. Use the root spelling recorded in the trace,
including any symlink names, so replay also works after the checkout is gone.
In the agent's first shell call of the round, save the next line number.
In separate shell calls, use the knowledge
directory normally. Once the completed tool events are visible in the rollout,
run the import from the agent's closing shell call:

```sh
# Start of round 1. Save the printed value as FIRST for the closing call.
awk 'END { print NR + 1 }' "$trace"

# Separate agent shell calls with the skill library as the tool working directory.
rg -Hn 'Operator tests passed' methods/inference-optimization-casebook/cases
cat methods/inference-optimization-casebook/cases/qwen-b300-rejected-directions.md

# End of round 1. FIRST is the value retained at the start of this round.
LAST=$(wc -l < "$trace")
inferrsi campaign import-search --directory "$campaign" --round 1 \
  --trace "$trace" --lines "$FIRST" "$LAST" --knowledge-root "$corpus" --complete
```

For round 2 take a new first/last pair, even in the same session. Windows are
one-based and inclusive. If the host buffers events, import after they have
flushed. After an interruption the host can do the same handoff. Use
`--context-id <id>` once per `campaign capture-context` performed in this round.
These inputs can be combined with the rollout or used alone for an Indexer-only
round. Each capture is verified and its returned refs, revisions, request and
resource paths are recorded. Opening a resource and receiving a prepared context
are distinct observations. A bare `collect` leaves no such capture.

The importer reads Desktop `CommandExecution` events. It supports direct text
or filename-match searches with `rg`, literal `cat`, `nl -ba` and `sed -n N,Mp`
reads. Use `rg -Hn` for unambiguous filenames and matching lines. File results
are corpus-relative. `-H` / `--with-filename` establishes the filename prefix,
including for numeric filenames. Without it, nonempty text output is attributed
only when the recorded scopes establish directory search or multiple operands.
If a single operand's file/directory type is unknown, the event stays incomplete;
the importer does not infer its format from text that resembles a path or number.
Without a line-number option, a numeric prefix such as
`42:` remains part of the matched text, with no source line number inferred.
Drive-qualified `rg` paths retain their drive prefix when parsed. Unnumbered
Windows output that could also be a single-letter filename plus text is attributed
only when the recorded scopes establish one interpretation; otherwise it stays partial.
Source lines are counted at LF or CRLF boundaries; form feeds remain within
their source line.
In shell commands, an unquoted `#` starts a comment only at a word boundary;
`guide#v2.md` remains one filename.
A shell event establishes the command's recorded output;
the outer agent tool may have displayed a shorter excerpt. The default local
record keeps locators and omits source text, output and assistant replies. Multiline
retrieval scripts, unsupported pipelines and unparseable output leave
unresolved event line numbers. Other tools and scripted/remote
retrievals require separate evidence. Review query text and paths before sharing.

- `observed` counts recognized searches, distinct materials per search (hits),
  distinct hit refs across searches, and distinct refs with supported use.
  A later file read is a separate event. File paths and versioned Indexer
  entries keep their original identities, with no inferred cross-tool alias.
- Supply `--complete` only when the selected inputs cover every in-scope
  retrieval for the round. Otherwise only observed counts are known and
  `counts` is null. A complete round without a search has zero searches.
  With no inputs the command records missing coverage. A failed query or
  unresolved supported command also makes totals unknown. For example,
  `rg -C 2` without line numbers cannot reliably separate context text from
  matching filenames. A failed multi-file `cat` may have read only some
  operands. These commands retain an unresolved trace locator.
- Use and rejection apply to materials observed in the imported round.
  A decision based only on a previous round's material is outside this
  record's scope. The existing optimization log can supply evidence when
  its iteration references the exact verified capture. If that log claims
  use of a selected item whose text was omitted, the record retains the
  claim under `conflicts`. Counting it as used requires separate evidence.
  For a decision recorded
  in an assistant message, a reviewer can pass `--used REF LINE` or
  `--rejected REF LINE` with the actual material ref and the JSONL line of
  the relevant message. This explicitly attributes use; the importer validates
  the locator and requires a material observation before the decision. A flag
  referring only to an unordered capture stays under the material's
  `declarations`, with `reason: observation_order_unknown`; it does not count
  as adopted. Use archive review with a verified capture return to establish
  that ordered passage-to-decision link. Unattributed use stays unknown.
  Distinct use and rejection decisions for the same ref are both retained
  and it counts once as used. Candidate links carry the recorded evaluation verdict
  when present. `evaluation_state` reports the source file's status, including
  `missing` for an absent file and `corrupt` for invalid JSON.
- Serialize imports along with other campaign updates. Repeating an import
  rebuilds the snapshot without adding events. To attach a later decision or
  run, retain the same trace, start line, capture IDs and scope, and extend the
  end line if necessary before the next round starts. Separate rounds cannot
  claim overlapping windows or the same command event ID from one session,
  even when duplicate events appear in disjoint windows.
  Saved `--used` / `--rejected` claims survive reimport without repeated flags.
  An explicit flag for the same material and decision line replaces the saved
  status; claims at different decision lines remain distinct.
  An accepted declaration stays uncounted if an extended window only adds
  ordered observations after its decision; it does not block the closing import.
  Its reason becomes `no_prior_ordered_observation`: none of the currently
  orderable observations precedes that decision. This does not establish the
  order of a capture whose return is still unknown. With no orderable
  observations, the reason remains `observation_order_unknown`.
  If correcting the corpus root reveals an observation before that decision,
  reimport can establish adoption and clears the declaration's old reason.
  A newly supplied decision that precedes every observation is still rejected.

#### Archive evidence for readers outside the session

Use `--archive-review review.json` on the same import when a campaign calls
for independently readable evidence. Use the historical knowledge directory
as `--knowledge-root`. In the review file, identify the repository, revision
and repository-relative directory from the experiment's frozen inputs. These
are caller-declared source coordinates. The importer obtains the passages
from the recorded tool return, so it can also handle a corpus that the host
copied into a temporary directory.

For example, this reviewer input links a visible match to a passage of the
agent's actual decision. The line numbers for the event and decision locate
records in the private input. The `passage_line` field locates a line in the material.
Use a verbatim, contiguous decision excerpt. The importer checks the cited
event, passage and message before recording the reviewed relation.

```json
{
  "task": "Decide what to check before combining three Qwen Ascend optimizations.",
  "corpus": {
    "repository": "InferMatrixLab/InferRSI",
    "revision": "f6d200775d554d08fb73673833611dd6ac02d14b",
    "root": "src/inferrsi/data/skill_library"
  },
  "decisions": [{
    "use": "used",
    "ref": "methods/inference-optimization-casebook/cases/qwen-ascend-rejected-directions.md",
    "event_line": 73,
    "passage_line": 18,
    "decision_line": 108,
    "decision_quote": "报告称 **RoPE + VAE fastpath + 融合 attention 在初始化时 OOM**，并建议先盘点初始化驻留。因此这是这次组合的首要风险，应先做资源检查，再决定是否进入组合试验。"
  }]
}
```

```sh
inferrsi campaign import-search --directory "$campaign" --round 1 \
  --trace "$trace" --lines "$FIRST" "$LAST" --knowledge-root "$corpus" \
  --archive-review review.json --complete
```

The command keeps `search/round-1.json` as the local window record and
returns the portable file `search/archive/round-1.json`. The latter embeds
the evidence selected by this review. Supply all intended decisions on each
archive import. Existing `--used`, `--rejected` and optimization-log claims
retain their local meaning. In the portable record they appear under
`declarations`, including saved flags restored from the local round record.
They do not count as reviewed adoption in the archive. Reviewed passage-to-decision
links appear under `materials[ref].evidence` and contribute to its adopted-material count.
If a source excerpt was redacted, its root normalized, or its text shortened,
the adoption entry also carries `passage_redacted`, `passage_root_normalized`,
or `passage_truncated`, respectively. Its `passage_text` is then a transformed
display excerpt, not an unchanged quotation of the source line. The decision
quotation must still match the assistant message exactly.

In the portable file, inspect the model-visible tool return and its
passages before the adoption entry. A search can match three lines of one
file and still count as one material hit. A reviewed decision can use one
of those lines. Hit counts include references the command matched or the Indexer
selected. Use each event's `delivery` to see which of those references can
be placed in the agent's return. A material marked `ref_visible` has a
confirmed reference but no archived content excerpt for that material. A zero `observed.used` means there were no
reviewed positive uses. Each unattributed material retains `use: unknown`.
Runtime truncation describes what the agent received. Archival omissions
describe what the reader can inspect. An ambiguous host
return leaves delivery unknown. A verified Indexer capture establishes what
the Indexer prepared. Its campaign-relative source is the evidence for that
preparation. When a tool actually returned its rendered context, the review
file can also supply `"capture_returns": {"r1-diagnosis": 52}`, where 52 is
the line of the model-facing tool response in the round. Pass the corresponding
`--context-id r1-diagnosis`. Only complete resource blocks with matching
owner, revision, path and body count as visibly delivered. A return that just
names the capture file or prints its digest leaves delivery unknown.
To review the use of a delivered Indexer passage, use its return line as
`event_line`, the entry ID as `ref`, and its capture resource path as
`passage_path`. The one-based `passage_line` selects a line within that
resource. Cite the later assistant decision in the same way as for a file.

To include a round in repository evidence, copy the portable file to
`evidence/<campaign-id>/search/round-1.json`. Retain the campaign-relative
paths to cited `knowledge/`, candidate and run artifacts, or document which
are unavailable in the published bundle. Review the generated text,
commands and referenced artifacts under the [privacy rules](privacy-security.md).
The raw Codex rollout stays local. A missing candidate is expected for a
decision-only exercise. See the [Qwen round archive](../evidence/search-attribution-qwen-s2-b1-20261110/README.md)
for the generated evidence and its interpretation. To follow one material across
events and then see its reviewed uses, set `record` to the portable JSON:

```sh
ref=methods/inference-optimization-casebook/cases/qwen-ascend-rejected-directions.md
jq --arg ref "$ref" '{
  returns: [.events[] | {event: .id, action, query,
    passages: [.delivery.passages[]? | select(.ref == $ref)]}
    | select(.passages | length > 0)],
  decisions: .materials[$ref].evidence
}' "$record"
```

### Record the optimization story (campaign trace)

Use `campaign init --profile-first` for a new profiled campaign, or set
`"review_layout": "profile_first"` in an existing `campaign.json`.
The live view and HTML export keep the performance trend visible. Other sections
start collapsed. Each capture has separate disclosures for its prior searches
and timeline. Below the trend are
acceptance criteria, recorded request profiles, the baseline breakdown and
target gap, each round's measurements, and adoption decisions. The trend uses each
candidate's paired medians. For example, a target latency reduction of 50%
is a 2× speedup. When there is one verified baseline profile, only runs
with its measurement signature share the trend line and compete for its best
result. Pairs from different conditions appear separately beside the chart.
Cancelled runs retain their records in the round list.

Attach a complete, reviewed worker trace before the first trial. Store a
Chrome Trace Event JSON (plain or gzip) directly in the campaign's `profiles/`
directory. Write a small UTF-8 review, for example:

```json
{"title":"Warm worker request","phase":"baseline","round":null,"workload_id":"fixed-image",
 "comparison_key":"same-card-input-and-capture-boundary","takeaway":"Denoising dominates.",
 "next_action":"Measure the chosen kernels separately, then repeat the same request."}
```

```sh
inferrsi campaign attach-profile --directory <campaign> --id baseline \
  --source profiles/baseline.chrome.json.gz --review baseline-review.json
```

A reviewed profile can also include these optional fields:

```json
{"started_at":"2026-01-20T10:00:00Z","context_ids":["choose-scope"],
 "timing":{"basis":"CUDA events on the pipeline stream",
           "stages_ms":{"worker":51.4,"encode":7.1,"denoise":42.8}}}
```

Use `YYYY-MM-DDTHH:MM:SS[.fraction]` followed by `Z` or a numeric UTC offset
such as `+08:00` for profile and ledger timestamps. Fractions have one to six
digits. The reader also accepts the compact legacy form `YYYYMMDDTHHMMSS`
with the same fraction and timezone rules.

Use the caller-recorded profile start and only the IDs of knowledge
captures relevant to this profile. The reader shows a search as prior evidence
only if its capture verifies and its timestamp precedes the start time supplied
by the caller. The search view shows the
query, selection method, ordered results, what was loaded or used, omissions
and the original assembled context. A missing link stays explicit.

The stage history reads the reviewer’s `timing.stages_ms` values and clock
description (`basis`). The importer checks that each duration is finite and
nonnegative. The verified baseline breakdown stays visible alongside this
history. The table compares columns only within the same
workload, comparison key and timing basis. It leaves absent measurements blank,
preserves nested stages, and does not sum them or substitute HTTP medians.
Command durations for the experiment itself appear separately in round details.
Older captures without these optional fields retain their timelines.

The timing panel also orders experiment steps on a UTC clock. It reads InferRSI
run boundaries, per-trial measurement commands, validation, profile starts,
saved knowledge searches and review log versions. In a linked agent trace,
an `agent.request` and `agent.response` with a unique matching request number
in the same run and source produce a client-side call duration.
The headline span uses the earliest and latest bounds from execution tasks,
runs, runner steps, model calls, operations and profile requests. The full
timeline also includes search and review saves. Set
`provider_model` on the response to label the model. Concurrent calls may
overlap each other and the benchmark. Missing boundaries stay unmeasured.

For an external controller, save a reviewed UTF-8 `experiment-timing.json`
in the campaign root and place its SHA-256 in `campaign.json` as
`experiment_timing_sha256`. The document has this shape:

```json
{"schema_version":1,"campaign_id":"example","steps":[
  {"kind":"model_call","actor":"experiment agent","model":"example-model","label":"#1",
   "start":"2026-01-20T10:00:00Z","end":"2026-01-20T10:00:03Z",
   "basis":"Client send to completed response","round":1}
]}
```

Supported kinds are `experiment`, `operation`, `profile_request` and `model_call`.
Supply either or both timestamp bounds with timezone. The actor and timing
basis identify the observer and clock boundary. Include only additional
observations that are absent from native events. The file accepts up to
5,000 steps and 2 MiB. Keep raw prompts and transport logs local.


Repeat after a measured change, with a new ID, `"phase":"candidate"` and the
actual round number. Use the same comparison key only for the same hardware,
input, execution boundary and profiler configuration. Run ordinary validation
without the profiler. On attachment, the importer reads complete Chrome `X`
events with positive durations. Zero-duration events and other phases are
skipped. It records the source digest and writes a compact event table. Its fields
are lane, event name, start and duration; raw event arguments are not served.
Trace labels themselves can identify a workload: review them before sharing.

A campaign accepts up to 16 captures. Each source file may occupy at most
64 MiB on disk (compressed size for `.json.gz`). The importer limits the
decoded stream to 2³⁰ characters and accepts up to 2,000,000 input events
and 512 distinct duration-event lanes. The uncompressed compact event table
is limited to 128 MiB.

The compact table preserves each complete event name. Overview labels longer
than 220 characters are shortened, and GPU statistics use the original name
for aggregation and matching across captures. To recover names truncated by
an older importer, reattach the original trace under a new capture ID.

When Chrome trace captures are present, the timeline covers the capture's full
time range on its recorded stage, CPU and GPU tracks. The initial view shows
one representative track per type, selected by summed event counts across
the full time range. The track toggle reveals the remaining lanes. Each track shows the
density of overlapping timed events and a selection of long events. Drag over
a range to zoom, pan with the slider, or select an event to inspect its timing.
Captures with the same comparison key report their individual spans.
In a live dashboard, **Expand full timeline** loads the capture's complete
event table on demand. Live overview refreshes reuse verified source hashes
while file identity, size, mode and timestamps match. Opening the full event
table rechecks the selected source and the compact table against their recorded
SHA-256 digests. Under **Capture scope and source files**, the offline
view accepts either the saved event table or the original Chrome trace.
The browser verifies the file's SHA-256 and renders every timed `X` event.
The file stays local. Use the compact event table or open the source in
Perfetto if the source exceeds the browser's 384 MiB decompression limit.

In the round trace, `applied_skills` records the name and takeaway of each
skill actually used. Verified retrievals, original inputs, hashes and events
open under round details. A `diagnosis` with scope `baseline_request` or
`denoiser_step` supplies the profile table when its `source_sha256` matches
the attached profile artifact. The gap uses the acceptance baseline measurement.

The shared **Knowledge retrieval and evidence navigation** panel explains actual
entry points, recorded ranking and assembly, and local v1/portable v2 search
records. It links explicit round/candidate/run identities in both layouts and
preserves active selections during live refresh. See the [retrieval contract and
integration guide](knowledge-retrieval-trace.md) for standalone captures,
compatibility, historical gaps and the offline synthetic example.

The **Optimization story** section is the campaign-level trace a reviewer reads
to understand the whole optimization: what knowledge was retrieved and why, the
declared search space and how it was narrowed, each round's hypothesis and
reason, the decision, and the success and failure summaries. It has two parts.

**1. Capture the knowledge context while working.** Run the same retrieval the
agent uses through `campaign capture-context`. It calls `collect` with a context
budget and keeps the complete envelope: the request, everything search selected,
everything left out and why, and every resource body with its SHA-256. The
dashboard re-derives the assembled text from those resources and withholds a
capture whose bytes or hashes no longer match.

```sh
inferrsi campaign capture-context --directory <CAMPAIGN_DIRECTORY> --id r1-diagnosis \
  --relevance '<WHAT_THE_PROFILE_SHOWED>' --backend <BACKEND> --context-bytes 65536
```

Each call writes a new `knowledge/<id>.json` and prints its SHA-256; an
existing id is never overwritten. The capture records what InferRSI prepared,
not what a model read. Hash checks detect changes relative to the cited bytes
and internal inconsistencies; they do not authenticate who produced a capture.
The campaign root and its `knowledge` directory must remain trusted and stable
while reading or writing. Captured text comes from the selected knowledge
sources; review it before sharing if a store or checkout source was added.

**2. Record the optimization log.** Write a JSON log (`schema_version: 2`) and
record it with `campaign log`. Every call adds a numbered version
(`optimization-log-vN.json`) and an entry in `optimization-log.jsonl`; earlier
versions remain. The latest version is shown only when its hash matches;
otherwise the dashboard reports the problem instead of silently falling back.

```sh
inferrsi campaign log --directory <CAMPAIGN_DIRECTORY> --file <LOG_JSON>
```

To show a retrieval in **Run review**, list its ID in the matching iteration's
`context_ids` and its capture hash in `knowledge`. Record this log as soon as
the candidate is registered. The round then shows the search request, hits,
files included, omissions and declared uses above the assembled round input.
If the round input quotes a skill directly from a checkout, include its
`SKILL.md` path, line locator and revision in the trace's context sources.

| Field | Content |
| --- | --- |
| `goal` | `statement`, `metric`, optional `baseline`, `target`, `constraints` |
| `knowledge[]` | `context_id` and `sha256` of a capture, `stage`, `purpose` (why it was retrieved), `used_refs`, `takeaways`, optional `rejected_refs[]` with `ref` and `reason` |
| `search_space` | `state`, `missing_reason`, `dimensions[]` with `id`, `name`, optional `rationale`, and `options[]` (`id`, `description`, `status` = `tried`/`pruned`/`untried`, `reason`, optional `source_refs`) |
| `iterations[]` | `round` (increasing), `hypothesis`, `rationale` (why this optimization), `knowledge_refs`, optional `context_ids`, `observations`, `next_step`; `candidates[]` with `candidate_id`, `option_ids` (`<dimension>.<option>`), `why`, optional `expected`; `decision` with `outcome` (`adopted`, `rejected`, `rolled_back`, `no_gain`, `noise`, `pending`), `reason`, optional `candidate_id` |
| `summary` | `state`, `missing_reason`, `successes[]` and `failures[]` with `text` and `evidence` (`candidate:<id>` or a knowledge ref), failures may name a `cause_stage`; `lessons`, `limitations` |

Set `reviewed_by_caller` to true only after reviewing the text for private
values. Validation errors name the offending field.

The narrative is caller-authored. The dashboard does not verify reasoning; it
resolves every reference and lists each disagreement under **Narrative vs
evidence**:

- a cited knowledge ref that no capture retrieved, or that search selected but
  whose text was omitted from the context;
- a decision that differs from `rounds.jsonl`, or an adopted candidate whose
  recorded outcome is not an improvement;
- a search option marked `tried` that no round tried, or the reverse;
- a candidate whose run evidence is missing or unreadable, and a summary that
  cites a run before its outcome is recorded; candidate metadata alone is not a run;
- a success whose evidence did not improve, and a recorded failure, regression
  or rollback that no failure summary cites;
- a capture that is missing, edited or fails its hash checks (its text is withheld).

A recorded iteration indicates available run evidence, not a completed result.
For example, an in-progress run may have no recorded outcome; a success or
failure summary citing a run with no recorded outcome is flagged.

### Per-candidate narrative (schema version 1)

The dashboard can show the assembled knowledge text and the caller's account of
the search and optimization process for each candidate. Collect this while
performing the work; old run logs and request hashes cannot reconstruct an
unrecorded context or reasoning. The runtime does not intercept an unrelated
agent or prove that a model received a prepared context.

First save the exact assembled context that was prepared for the agent. For
example, `inferrsi context ... --output <CONTEXT_FILE>` writes the text
produced by that operation; a host agent that combines other material must save
its own final assembly. Inspect the complete file and the narrative for
credentials, private values and unrelated material **before** recording. If a
safe copy omits or redacts anything, mark its state and explain the gap; do not
call it the complete original. Public source attribution may be retained.

Create a UTF-8 JSON template like the following. Every field shown is required
except `round`, `run_id`, and `event_ref`. Values below are illustrative; record the actual search,
attempts and conclusions, including failures and omissions. Set
`reviewed_by_caller` to true only after reviewing the template and context.

```json
{
  "schema_version": 1,
  "reviewed_by_caller": true,
  "campaign_id": "<CAMPAIGN_ID>",
  "candidate_id": "<CANDIDATE_ID>",
  "round": 1,
  "run_id": "<RUN_ID>",
  "context": {
    "state": "complete",
    "text": "",
    "queries": ["<ACTUAL_QUERY>"],
    "sources": [
      {"ref": "<SELECTED_REFERENCE>", "revision": "<REVISION>", "locator": "<RESOURCE>"}
    ],
    "missing_reason": ""
  },
  "search_space": {
    "state": "partial",
    "selection_rules": ["<CRITERION_USED_TO_CHOOSE_AN_OPTION>"],
    "items": [{"id": "option-a", "description": "<CONSIDERED_OPTION>"}],
    "missing_reason": "<WHAT_WAS_NOT_RECORDED>"
  },
  "steps": {
    "state": "partial",
    "items": [
      {"sequence": 1, "kind": "attempt", "action": "<ACTION>",
       "motivation": "<WHY>", "outcome": "inconclusive", "result": "<RESULT>",
       "search_id": "option-a",
       "event_ref": {"source": "events", "line": 1, "sha256": "<EVENT_FILE_SHA256>"}}
    ],
    "missing_reason": "<WHAT_WAS_NOT_RECORDED>"
  },
  "summary": {
    "state": "partial",
    "successes": ["<SUCCESS_OR_OBSERVATION>"],
    "failures": ["<FAILURE_OR_ROLLBACK>"],
    "limitations": ["<EVIDENCE_LIMITATION>"],
    "missing_reason": "<WHAT_WAS_NOT_RECORDED>"
  }
}
```

Each section state is `complete`, `partial` or `redacted`; partial and
redacted sections require a nonempty `missing_reason`. The context text must
be nonempty when complete. Empty lists indicate no entries were supplied.
Source revisions and locators are caller-provided; use an empty string when
unknown. Search-space entries describe options, not necessarily attempts.
Steps have increasing sequence numbers, kinds `observation`, `attempt`, or
`decision`, and outcomes `succeeded`, `failed`, `inconclusive`, `skipped`,
or `not_recorded`. The `search_id` field is required; leave it empty when
there is no linked option. An optional `event_ref` names the `events` or `agent_trace`
source, its one-based line number and the source file's SHA-256; a jump is
offered only when that exact linked event and hash are present. Narrative
conclusions are not experiment verdicts. If `run_id` is omitted, the snapshot
is candidate-level and is not asserted to describe the selected run.

Insert the complete, reviewed context file without manually escaping or
truncating it; this creates a **new** snapshot and never overwrites an existing
file:

```sh
inferrsi campaign assemble-trace --directory <CAMPAIGN_DIRECTORY> \
  --template <TRACE_TEMPLATE_JSON> --context-file <REVIEWED_CONTEXT_FILE> \
  --output optimization-v1.json
```

Use `--optimization-trace optimization-v1.json` with `campaign record`.
An existing candidate record may instead contain an explicit
`optimization_trace_ref` with the snapshot filename and SHA-256:

```json
{"path": "optimization-v1.json", "sha256": "<SNAPSHOT_SHA256>"}
```

The CLI does not update an existing candidate's reference; use a new campaign
record or explicitly update the record and its hash. Preserve earlier snapshots.
After modifying a referenced file its hash no longer matches, so it is
withheld rather than silently displayed.
Alternatively, a caller may create the complete JSON itself. The entire JSON
snapshot is limited to 2 MiB; larger snapshots are rejected, never silently
truncated. Trace snapshots must be single files directly in the campaign root.
Treat the campaign root itself as a trusted directory that is not concurrently
replaced. IDs, optional round/run, filename and SHA-256 are
checked before the content is shown. Source references in the narrative remain
caller assertions; inspect the separate evidence artifacts for measured claims.

To explain a candidate, pass `--details-json <FILE>` to `campaign record`.
Supported fields are filtered and saved in the candidate record. The JSON can
contain these optional fields (text is caller-supplied, not inferred or verified
by the dashboard):

```json
{
  "change_kind": "code",
  "summary": "Reuse a recorded decode path",
  "hypothesis": "Reduce launch overhead",
  "benchmark": "Describe the workload and measurement method",
  "accuracy": "Describe the dataset, checks and recorded result",
  "commands": [
    {"label": "Candidate server", "argv": ["python", "-m",
     "vllm.entrypoints.openai.api_server", "--speculative-config",
     "{\"method\":\"mtp\",\"num_speculative_tokens\":1}"]}
  ],
  "code_locations": [
    {"scope": "engine repository", "path": "src/example.py",
     "line_start": 10, "line_end": 15, "revision": "abcdef1234567",
     "note": "Recorded change location"}
  ]
}
```

`change_kind` may be `code`, `configuration`, `mixed`, or `other`. Locations
must be relative to the caller-described scope; optional line numbers and
revision are not independently checked against a repository. A configuration
change may have no code location. Existing candidate records can include the
same `details` object. The recorder stores supplied commands only after
conservative argument filtering; their displays are not runnable commands.
Text fields receive basic redaction, which is not a general anonymizer, so
callers must still supply only information safe to retain and share. Additional
commands and their labels are caller-supplied and do not prove execution.
Missing notes or locations are shown as not recorded.

Record one decision for a round with `inferrsi campaign decide --directory
<CAMPAIGN_DIRECTORY> --candidate <CANDIDATE_ID> --round <ROUND_NUMBER>
--outcome <OUTCOME>`. Existing decisions are not overwritten.

```text
<CAMPAIGN_DIRECTORY>/
  campaign.json
  rounds.jsonl
  summary-chart.json                 # optional, explicitly recorded chain
  optimization-v1.json               # optional, reviewed narrative snapshot
  candidates/<candidate_id>/
    candidate.json
    agent_trace.jsonl                # optional, explicitly referenced and hashed
  runs/<run_id>/                     # existing InferRSI run artifacts
```

`campaign.json` may include `campaign_id`, `synthetic`,
`goal.target_improvement_pct`, `noise.band_pct`, and `stages_declared`. The goal is supplied by the
campaign's acceptance issue, not a dashboard default. Mark demonstrative data
with `"synthetic": true` so the page displays its synthetic-data banner.
An undeclared stage is marked `not_applicable` when `stages_declared` is supplied;
otherwise a stage with no recorded events is marked `stage_not_recorded`.

Each `candidate.json` may provide `candidate_id`, `title`, `round`, `run_id`,
`agent_trace_ref`, `optimization_trace_ref`, and `profile_ref`. An explicit reference is an object with a
campaign-relative `path` and the file's SHA-256 in `sha256`. Missing references
can instead specify `state: "missing"` and `missing_reason`. Paths escaping the
campaign, including through symlinks, are rejected. A missing hash or hash
mismatch is shown as missing, and its file is not read as a trace.

`rounds.jsonl` contains one JSON object per round with an integer `round` and
may include a `decision` object with `candidate_id` and `outcome` (including
`rolled_back`).
Agent trace JSONL can contain the existing `agent.*` event types and the
optional `stage` field (`diagnosis`, `knowledge`, `search`, `execution`,
`validation`, or `review`). An agent integration can pass an opt-in
`inferrsi.harness.records.campaign_trace.CampaignTrace` instance as its existing event
callback; it appends the original event with time and caller-supplied IDs. The
caller associates the completed trace with `agent_trace_ref` using its SHA-256.
The dashboard links a pre-run event when its campaign and uniquely identified
candidate match; any supplied run and round must also match. Events with
incomplete or ambiguous identity remain visibly unlinked and do not count as
stage coverage or tool calls. Explicit mismatches are not attributed.
The callback does not allocate IDs or intercept unrelated agents. It writes the
event object supplied by the caller verbatim: callers must remove secrets and
private material before invoking it, and protect the trace file itself.
Existing runner phases are mapped to execution and validation. The dashboard
reads allowlisted event metadata, including recorded request counters, token
usage, tool names, file manifests, hashes and selected check/benchmark receipt
fields; it does not independently verify a receipt or include raw agent
requests, arbitrary event messages, environment data, or raw logs. Runner and
agent events retain their source and line number. The review export orders event references by timestamp, with untimed records last.
For recorded execution events it identifies expected logs and their hashes,
without embedding their contents. Trace line numbers and artifact references
can be included in a local review export, including references attached to
visible events. Missing agent tool-call events and
corrupt round-record line numbers are also shown explicitly.

The performance overview and **Successes and failures** share the
[experiment measurement projection](dashboard-experiments.md), chart renderer,
filters and selected identity. They show absolute metrics by recorded round,
explicit order or real timestamp. Compatible configurations connect; unknown
comparability, repeated runs and missing measurements are kept explicit.
Events occupy their own lane and never become zero measurements. Original
summary text, limitations, lessons and partial state remain expandable.

The dashboard also plots recorded terminal events and stage events on a shared
UTC time axis. Results without a terminal timestamp are omitted from that plot;
failed runs without a measurement appear in a separate no-value row. Stage dots
mark events, not inferred durations. A common recorded noise band and target
are shown when available, with distinct quality-failure, failure and rollback
markers. Unrelated candidate measurements are not joined into a cumulative line.

## Interpretation and limits

- Best gain includes only completed runs with a PASS or FAIL verdict, a supplied
  quality command with a recorded zero exit code, verified source integrity,
  and no recorded rollback. Successful validation
  covers only that command, not untested quality properties.
- Multiple measured runs are summarized together only when their declared model,
  model revision, workload, scenario, backend, verified physical CUDA device,
  driver, host platform, target Python/packages, baseline source snapshot,
  baseline and validation commands, comparison scope, metric, unit and direction
  agree. Otherwise the aggregate is withheld. Experiment curves retain separate
  compatible groups and independent points with explicit reasons. Private device
  identity is used only for the comparison and is not included in the export.
  Cross-run comparison for other device backends is currently withheld.
- Noise uses the campaign's declared band, or the larger recorded trial range
  when no band is supplied. It is descriptive; statistical significance is not
  established.
- Diagnostics currently cover recorded execution failures, rollbacks, noisy or
  regressed measurements, and a quality failure accompanying a positive
  measurement. Missing stages are not diagnosed as
  successful. Profiling interpretation, automatic root-cause attribution,
  automatic capture of unrelated agents and framework write-back are not implemented.
- The time chart does not infer durations or result timestamps when they are
  missing. Noise bands that
  differ across candidates are not represented as one shared band.
- The review button creates a local Markdown download and displays its content
  for copying if a browser blocks downloads. It does not send or publish it.
- The selected candidate shows the recorded baseline, candidate and validation
  command argument structure from `run.lock.json`, with its source hash. Unknown
  options and argument values, directories, credential-like options, inline
  shell scripts and environment assignments are deliberately hidden. Python
  script basenames may remain visible. Numeric `--gpu` ordinals and
  `--candidate` values matching a displayed campaign candidate ID may also be
  shown. Review these identifiers before sharing. These displays are not runnable
  commands. Caller-supplied benchmark and accuracy descriptions state what was
  measured; they are not independently verified. A validation exit code does not
  establish an accuracy result when no result was recorded.
- Overview statistics show all candidates. Experiment workload/metric/axis filters
  are shared between the overview curve and summary. The candidate, run and stage
  filters select the run review and candidate rows.
- Existing non-dashboard files and symbolic-link outputs are never overwritten.

## Privacy

The exporter does not traverse and link the entire run tree. It reads known
records and explicit references, escapes data before embedding it in HTML, and
withholds raw logs, environments and arbitrary command arguments. Explicitly
reviewed optimization trace snapshots are embedded with their supplied text;
the exporter does not automatically sanitize that text. Common addresses, URLs, paths and
credential-shaped strings in displayed labels are replaced, but this is not a
general anonymizer. IDs, relative artifact names and review text can still
identify a person or contain secrets. Inspect and sanitize the actual HTML,
screenshots and exported Markdown before sharing them; follow
[privacy and security](privacy-security.md).
