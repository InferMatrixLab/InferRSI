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
freezes a gate. `evaluate` and `answer` write only the `--record` file the caller names.

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
    "protocol.comparison": {"value": null, "source": "answer:q:protocol.comparison",
                            "status": "unknown", "asked": true}
  },
  "open_questions": [],
  "blockers": [],
  "conflicts": [],
  "allowed_next": ["read_only_preparation", "baseline_measurement"],
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
   recorded candidate values with their sources.
3. Otherwise the lowest missing `batch` is asked as one batch. Answers to other
   batches wait until earlier batches settle.
4. `unknown` is a recorded answer: the field is not asked again, and it blocks
   every stage named in `required_before`.
5. Each question carries a dependency snapshot. An answer is rejected as
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
inferrsi task intake answer --record <record.json> --question q:acceptance.reference \
    --value <gate.yaml> --frozen <gate.yaml>
```

The record retains the selected file's explicit acceptance values. Defaults and
arbitrary `--set` values cannot fill missing gate fields. If the file is first
presented later, or its acceptance contents change, evaluating it reopens the
reference question. Conflicting metric values remain visible. Reconfirm the
file and resolve conflicting proposals with the user before search.

For a vague performance request, the objective and metric must be selected before
baseline measurement. Workspace facts can identify the hardware and model.
Inferred objectives, quality checks, workloads and protocol choices produce
questions. User answers can select a metric for baseline calibration, while
candidate search also requires the acceptance values from the selected authority.
Records created by earlier versions are re-evaluated when opened or handed to
a campaign. A cached complete result or a standalone source label cannot confirm
a user's choices.

## Campaign hand-off

```text
inferrsi campaign start ... --intake <record.json>
```

`campaign start` evaluates the record for `task-performance` before writing any
plan. A blocked record prints the gate payload and exits `2`; nothing is
created. A ready record is written to `intake.json` in the campaign directory
and its sha256 is returned in the start result. Without `--intake`, start
prints a warning to stderr that the gate was not evaluated and proceeds as
before.

The gate checks that the record is complete. It does not yet compare the record
with the campaign's own metric, quality and budget flags or with a frozen gate
file, and the digest is not part of `plan.json`; use `task intake evaluate
--frozen` for the gate comparison.

## Cards and text fallback

When `evaluate` returns `needs_user_input: true`, the host presents its questions
and waits for a reply. In Codex Desktop the agent invokes the native question
tool. Hosts without cards show the questions as a numbered list. Both record
the user's replies through `task intake answer`. The CLI itself does not display
a desktop widget.
