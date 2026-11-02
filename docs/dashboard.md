# Offline optimization dashboard

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

Record one decision for a round with `inferrsi campaign decide --directory
<CAMPAIGN_DIRECTORY> --candidate <CANDIDATE_ID> --round <ROUND_NUMBER>
--outcome <OUTCOME>`. Existing decisions are not overwritten.

```text
<CAMPAIGN_DIRECTORY>/
  campaign.json
  rounds.jsonl
  summary-chart.json                 # optional, explicitly recorded chain
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
`agent_trace_ref`, and `profile_ref`. An explicit reference is an object with a
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
`inferrsi.harness.campaign_trace.CampaignTrace` instance as its existing event
callback; it appends the original event with time and caller-supplied IDs. The
caller associates the completed trace with `agent_trace_ref` using its SHA-256.
The dashboard links a pre-run event when its campaign and uniquely identified
candidate match; any supplied run and round must also match. Events with
incomplete or ambiguous identity remain visibly unlinked and do not count as
stage coverage or tool calls. Explicit mismatches are not attributed.
The callback does not allocate IDs or intercept unrelated agents. Existing runner phases are mapped to execution and
validation. The dashboard reads allowlisted event metadata; it does not include
raw agent requests, arbitrary event messages, environment data, or raw logs.
For recorded execution events it identifies expected logs and their hashes,
without embedding their contents. Trace line numbers and artifact references
can be included in a local review export. Missing agent tool-call events and
corrupt round-record line numbers are also shown explicitly.

The existing [summary chart](campaign-summary-chart.md) renderer is reused.
An explicitly recorded, valid `summary-chart.json` with a chain layout produces
a cumulative chart. Otherwise the dashboard uses a branch chart of independent
candidate results, so it does not imply that unrelated trials accumulated.
Failed candidates without a numeric measurement remain in the table and trace.
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
  agree. Otherwise the aggregate and shared chart are withheld. Private device
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
- The stage matrix describes recorded coverage. The separate time chart does not
  infer durations or result timestamps when they are missing. Noise bands that
  differ across candidates are not represented as one shared band.
- The review button creates a local Markdown download and displays its content
  for copying if a browser blocks downloads. It does not send or publish it.
- Existing non-dashboard files and symbolic-link outputs are never overwritten.

## Privacy

The exporter does not traverse and link the entire run tree. It reads known
records and explicit references, escapes data before embedding it in HTML, and
withholds raw logs and environment values. Common addresses, URLs, paths and
credential-shaped strings in displayed labels are replaced, but this is not a
general anonymizer. IDs, relative artifact names and review text can still
identify a person or contain secrets. Inspect and sanitize the actual HTML,
screenshots and exported Markdown before sharing them; follow
[privacy and security](privacy-security.md).
