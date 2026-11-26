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
    "acceptance.metric_key": {"value": "p95_ttft", "source": "issue", "status": "confirmed"},
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

1. A field is asked only when it applies (`depends_on` settled, `required_when`
   satisfied), it is still `unknown` and it was never answered `unknown`.
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

A value for an `acceptance.*` field is `confirmed` only when the declared source
is `issue` or `frozen_gate`. A card answer, a prompt statement, a task file or an
interview brief is `proposed`. Proposed values do not unblock candidate search,
do not freeze a gate and do not override a value already confirmed by the
acceptance issue. A record that disagrees with the frozen gate record blocks
candidate search until the user resolves it.

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

The runtime returns the same question objects to both presentations. A host may
render a native card; otherwise the Agent shows the same questions and options
as a numbered list. Both write answers through `task intake answer`, so the
normalized record is identical. Only the numbered text presentation has been
exercised so far; no host card adapter ships with this contract.
