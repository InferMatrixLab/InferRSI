# Task intake records (intake/v1)

`intake/v1` is the confirmation record an Agent fills before a measured task.
A native question card, a numbered text fallback and an optional check-in
interview all write the same record; the record decides which fields still
block the next stage. It sits next to, not inside, the shared YAML task file
(`task-input/v1`, [task input](task-input.md)): the record states where each
value came from, and only fields mapped to `task-input/v1` are expected to
reach a task file.

The contract is `inferrsi.apps.cli.intake_contract`; the commands are
`inferrsi task intake ...`. Nothing here starts a process, probes a device or
freezes a gate. `evaluate` and `answer` update the named record under a sibling `.lock` file.
If an update is in progress, retry after it finishes.

## Files

| File | Owner |
| --- | --- |
| `src/inferrsi/apps/cli/intake_contract.py` | Record validation, question selection, answers, summary; pure functions |
| `skill_library/tasks/task-performance/intake.json` | Field spec for a performance round |
| `skill_library/tasks/task-day-0/intake.json` | Day-zero fields; none map to `task-input/v1` |
| `src/inferrsi/apps/cli/task_intake.py` | Record file I/O and the commands |
| `tests/fixtures/intake/` | Complete, partial and frozen-gate fixtures |

## Record

```json
{
  "schema_version": 1,
  "record_id": "intake-...",
  "revision": 3,
  "task": "task-performance",
  "primary_task": {"value": "task-performance", "source": "prompt", "status": "confirmed"},
  "phase": "intake",
  "fields": {
    "acceptance.reference": {"value": "<acceptance-issue>", "source": "prompt", "status": "confirmed"},
    "acceptance.metric_key": {"value": "p95_ttft", "source": "issue", "status": "confirmed",
                              "authority_reference": "<acceptance-issue>"},
    "protocol.comparison": {"value": null, "source": "answer:q:protocol.comparison:<issued-token>",
                            "status": "unknown", "asked": true}
  },
  "open_questions": [],
  "blockers": [],
  "conflicts": [],
  "allowed_next": ["read_only_preparation"],
  "execution": "not started"
}
```

- `source` names where a value came from: `prompt`, `answer:<question-id>`,
  `task_file`, `issue`, `repo_inspection`, `derived`, `default`,
  `grilling_brief`, `frozen_gate` or `unknown`. The caller declares it; InferRSI
  records it and does not authenticate it.
- `status` is one of `confirmed`, `proposed`, `assumed`, `unknown`,
  `conflicting`, `stale`, `superseded`.
- `allowed_next` is derived by `evaluate`; a caller never fills it by hand.
  `service_execution` and `device_execution` never appear there: they need a
  separate authorization.

## Field specs

Each primary task owns an `intake.json` next to its `SKILL.md`. A field declares:

| Key | Meaning |
| --- | --- |
| `path` | Field path; `acceptance.*` paths carry the gate boundary |
| `maps_to` | `task-input/v1`, `campaign-protocol`, `session-protocol`, `summary-only` or `day0-spec` |
| `batch` | Question batch (1 = goal and gates, 2 = environment identity, 3 = protocol, scope and budget) |
| `type` | `text`, `number`, `integer` or `choice` |
| `question`, `options` | Card text and options; `{value, hint}` objects |
| `depends_on` | Fields that must be settled before this question applies |
| `required_when` | Conditional applicability, e.g. service reuse fields |
| `required_before` | Stages this field blocks while it is not settled |
| `user_choice` | Repository-derived values for this decision become suggestions for the user |

`task-day-0` fields map to `day0-spec` and stay in the record and the summary.
They do not enter a `task-input/v1` file, which rejects unknown keys.

## Commands

```text
inferrsi task intake evaluate --task task-performance --record <record.json> \
    --set optimization.objective="reduce p95 TTFT" --source prompt [--json]
inferrsi task intake answer --record <record.json> --question <id> --value <value> [--json]
inferrsi task intake answer --record <record.json> --question <id> --unknown [--json]
inferrsi task intake summary --record <record.json> [--json]
```

`evaluate` creates the record when it does not exist, merges `--set` values,
writes the record back and prints the questions that unblock the next stage.
`answer` applies one recorded question, bumps the revision and re-evaluates.
`summary` reads without writing.

Every command accepts `--frozen <gate.yaml>`: a schema-v1 task file whose
`acceptance` section is compared with the record, except `acceptance.reference`,
which names the gate record itself. A disagreement is reported as a conflict and
blocks candidate search.

## Question selection

1. Ask applicable missing fields and unconfirmed suggestions. Return the suggested value and its source as an option. Preserve a user’s explicit unknown answer until new confirmed information arrives.
2. A conflicting field is asked before anything else; its options are the
   recorded candidate values with their sources. Answering the card selects one
   value and clears the other options. An acceptance choice stays proposed until
   the selected authority confirms it. A differing issue value reopens the choice.
3. Otherwise the lowest missing `batch` is asked as one batch. Answers to other
   batches wait until earlier batches settle.
4. `unknown` is a recorded answer: the field is not asked again, and it blocks
   every stage named in `required_before`.
5. Reply with the full ID returned on the displayed card. Its token binds the
   record, field, dependencies and options at issuance. Re-evaluation keeps the
   IDs of open, unchanged questions. A changed or reopened card receives a new
   token. For a legacy field-only card, re-evaluate and present its new ID.
   An answer is rejected as
   `stale_answer` when the snapshot changed, as `already_answered` when the same
   question was answered once, and as `unknown_question` when it was never
   issued. A late reply to a superseded question changes nothing.

## Acceptance boundary

The user identifies the acceptance issue or gate file in the initial prompt, a
confirmed interview brief or a subsequent card answer. A reference suggested by
the workspace or by the gate file itself remains an open question. After intake
has begun, record the user's selection with `answer`. The host is responsible for
passing actual user input to the CLI. The CLI cannot authenticate conversation turns.

For an issue, first record the user's reference, then include the same
`--set acceptance.reference=<acceptance-issue>` with the issue's values and
`--source issue`. For a frozen task file, pass `--frozen` when recording the
user's selection. For example, after the user chooses the file on a card:

```text
inferrsi task intake answer --record <record.json> --question <returned-question-id> \
    --value <gate.yaml> --frozen <gate.yaml>
```

The record retains the selected file's explicit acceptance values. Defaults and
arbitrary `--set` values cannot fill missing gate fields. If the file is first
presented later, or its acceptance contents change, evaluating it reopens the
reference question. Conflicting metric values remain visible. Reconfirm the
file and resolve conflicting proposals with the user before search.

For mapped numeric fields, intake uses the task-input/v1 bounds. Repetitions
and rounds must be positive integers, the time budget must be positive and at
most seven days, and the minimum improvement percentage must be nonnegative.
Invalid replies leave the question open. Older records with out-of-range values
reopen those questions and require a fresh brief approval after correction.

## Final performance brief

A final goal has a metric, direction and numeric target. For an absolute
target supply the bound in the metric unit. For a relative target supply the
minimum percent improvement over the pinned baseline. The per-candidate
retention rule remains a separate input. State the workload, accuracy benchmark
and split, quality metric, comparison, numeric threshold and unit. Include the
command that evaluates that condition. Repository findings are suggestions
until the user chooses them.

Once all applicable fields and acceptance sources are settled, `evaluate` or
the last field `answer` returns a `task_brief`, `brief_review:
awaiting_confirmation` and one revision-specific question. Read the **whole**
brief back in the user's language and send a separate native approve-or-revise
card. Hosts without cards use the same explicit decision in text. Record the
reply against the exact question displayed:

```text
inferrsi task intake answer --record <record.json> --question <brief-question-id> --value approve
```

An explicit `revise` or unknown reply keeps work paused until edits and a new
review. A missing reply leaves the card open. Capture corrections through intake,
resolve any conflicts and present the revised brief before asking again. If the
user selects a different acceptance reference after returning the brief, pass
that correction to `evaluate --set acceptance.reference=...` with the new
`--frozen` file when applicable. Intake discards values bound to the former
authority.
The question ID binds the record, field revision and applicable values.
Evaluation and summary alone cannot grant approval. Measured work requires
`brief_review: approved`. Older records are re-evaluated on use.

## Campaign hand-off

For an executable campaign, prepare the complete launch before presenting the
final card. Pass the same project, protocol and budget options to both commands.

```text
inferrsi campaign start ... --intake <record.json> --prepare-intake
# Read back the returned task_brief, including campaign_launch. Wait for the user's card reply.
inferrsi task intake answer --record <record.json> --question <returned-brief-id> --value approve
inferrsi campaign start ... --intake <record.json>
```

Preparation stages the inputs in a temporary directory, compares them with the
intake and returns an executable brief. It starts no campaign or measurements.
The final approval binds the effective settings, including defaults, candidate
inputs, commands, sampling, budget and the evaluation configuration. Running
preparation again with the same settings preserves an existing approval. A
changed launch needs a fresh card. Planning-only briefs can still be reviewed.
Before service configuration is bound, the brief labels its quality inputs
provisional. Show the prepared inequality on the final card for a measured run.

Start rechecks the selected gate and the approved launch before creating the
campaign. Missing, stale and mismatched approval exits with status 2. A matching
preapproval starts unattended. The frozen `plan.json` references a receipt in
`plan/` with the SHA-256 and revision of the retained `intake.json`.

For a local frozen gate, the brief and retained intake record bind the
SHA-256 of the selected file. Any change to the file requires selecting the
gate again, preparing the launch and approving the new brief. Older intake
records with a selected gate also require this confirmation before a new
campaign can start.

For AB/BA the two approved measurement commands describe the same script with
the candidate path supplied at execution. For a scored quality check, the
frozen script self-reports the dataset it evaluated in the top-level `dataset`
field. Harness compares that label with the approved `--quality-benchmark`,
including its version and split. The script supplies the evidence for which
corpus it loaded. A missing or mismatched label makes a scored result
`INCONCLUSIVE`. An explicit `status: candidate_failure` is an unscored
rejection. A candidate rejection is `FAIL`, and a baseline rejection leaves
the comparison `INCONCLUSIVE`. A scored result also supplies the boolean
acceptance key and a numeric result under the approved quality metric
(JSON dotted paths are supported). A boolean metric on the acceptance key is
compared as 1 or 0 when its approved unit is `boolean`. Numeric quality results
declare their scale in the top-level `unit` field. Both campaign modes compare the
score in the unit on the final card. The harness converts between `fraction` /
`ratio` and `%` / `percent`; other units must match exactly. Missing or
incompatible numeric units give `INCONCLUSIVE`. Service baseline tolerances
are additive in the approved score unit. For percent scores, a tolerance
of one permits a difference of one percentage point. The independent final checks the approved absolute bound or
relative improvement against the pinned baseline. For service reuse, the first
ranked objective names the final metric and the configuration supplies its
dataset, score key, threshold or allowed degradation, commands and sampling.
The bound brief displays an absolute score threshold or the allowed change from
the retained baseline for the current comparison epoch. Higher-is-better scores
may drop by the approved tolerance; lower-is-better scores may rise by it.
The comparator applies to the candidate score in both modes. For a relative
gate, the brief labels the numeric allowance as `protocol.quality_baseline_tolerance`
and identifies the retained score in `protocol.quality_reference`.

## Cards and text fallback

When `evaluate` returns `needs_user_input: true`, the host presents its questions
and waits for a reply. In Codex Desktop the agent invokes the native question
tool. Hosts without cards show the questions as a numbered list. Both record
the user's replies through `task intake answer`. The CLI itself does not display
a desktop widget.
