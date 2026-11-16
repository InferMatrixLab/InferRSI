# Optimize a task through RSI in its execution Agent session

An optimization benchmark covers the Agent's complete search under a frozen
task and budget. The execution Agent proposes changes, uses permitted knowledge,
submits candidates, reads independent feedback and completes the declared rounds.
The session controller retains each attempt, selects the best valid candidate
and independently retests it before emitting the final optimization result.

This path and ordinary `campaign start/round/final` now use the same Harness
controller and dashboard read model. See the
[shared workflow and sequence diagram](optimization-workflow-unification.md).
Ordinary projects default to the current conversation; a benchmark task defaults
to a fresh conversation on the same host. The initiator resolves the task and
sends a self-contained request through the generic native handoff. The execution
Agent owns the complete start/knowledge/round/final lifecycle below; the initiator
only observes and collects its results. Benchmark supplies task resources and
task-specific rules. Harness freezes those inputs, runs the checks, assesses
retained outputs and manages the lifecycle; it does not invent project acceptance.

The first task with this session protocol is `qwen21-denoise-npu`. MoE and TTS
currently expose their single-candidate task entries. New session tasks provide
their own `optimization.py` alongside the task definition and evaluator.

## Start the complete workflow

In the execution conversation, run in the prepared NPU environment. The example declares eight optimization
rounds and a three-hour total budget, including the final measurement. The
allocator obtains one available NPU for each measurement. The current Agent
continues its analysis and edits between measurements.

```bash
inferrsi benchmarks session start qwen21-denoise-npu \
  --session ./outputs/qwen-rsi \
  --rounds 8 --max-minutes 180 --evaluation-timeout-seconds 1200 \
  --condition current-agent-with-rsi \
  --evaluation-prefix 'npu run --gpus 1 --timeout 18m --wait 1m --' \
  --evaluation-args '--pairs 2 --samples 3 --warmups 1'
```

The command returns the frozen task instructions, editable candidate path,
remaining budget and next action. Read the returned `frozen/TASK.md` and begin
with `work/candidate.py`, which starts as the original baseline.
Keep allocator wait plus run time below the evaluation timeout, including
cleanup margin; increase all related budgets together when longer queues are expected.
Final evaluation reserves one evaluation timeout from the total budget by
default; `--final-reserve-seconds` changes that explicit reservation. Use
`--knowledge off` for a condition that disables managed knowledge retrieval.

## Retrieve knowledge and propose a change

When the chosen experimental condition permits RSI knowledge, retrieve it through
the session. This calls the existing KnowledgeReader and retains the exact
delivered context with its hash.

```bash
inferrsi benchmarks session knowledge --session ./outputs/qwen-rsi \
  --query 'Ascend denoising conditioning reuse normalization fusion' \
  --context-bytes 16384
```

Read the returned content. Make one justified candidate change. Knowledge
selection method and the external Agent configuration are caller-controlled
variables. A retained delivery establishes what was supplied. Model consumption
and access to material outside this session require their own observation.

## Submit a round and use its feedback

```bash
inferrsi benchmarks session round --session ./outputs/qwen-rsi \
  --candidate ./outputs/qwen-rsi/work/candidate.py \
  --hypothesis 'Reuse request-invariant conditioning across denoising steps'
```

The controller freezes the candidate and hypothesis before executing the
task-owned evaluator through the existing Harness executor. The task protocol
checks candidate binding, complete case coverage, source identities, raw timing
samples and aggregation. The response includes the assessment, previous/best
candidate and next action. Read it before the next change.

Incorrect candidates consume a round and remain in the history. Only valid
performance scores can select a successor. Infrastructure failure blocks the
session. Concurrent submissions are rejected by an OS lock. A persisted pending
attempt prevents a second launch after an interrupted coordinator.

Repeat this operation until the declared round budget is consumed. Use
`session status --session ./outputs/qwen-rsi` to inspect progress. Each call
evaluates a newly retained candidate snapshot and returns independent feedback.
Profiling is available to the Agent as an optional diagnostic.

## Independently retest and report

```bash
inferrsi benchmarks session final --session ./outputs/qwen-rsi
```

The controller selects the best valid retained source and evaluates it in a
fresh process and output directory. In `exact` mode it rejects finalization before
the planned rounds are complete. In `up_to` mode, at least one round and an explicit
stop reason are required. Both reject additional search rounds beyond the budget.
The final result remains tied to the selected source. A failed final leaves the
session `blocked`, without a successful final result. When the original baseline remains
selected, the report records baseline selection and an optimization speedup of
1.0 only after its final evaluation completes. The independent raw A/A ratio
remains available in the final assessment.

`summary.json` records the final assessment, selected candidate, full wall time,
per-round hypotheses, failed results, best-score curve, cumulative token exports
and delivered knowledge references. Round snapshots, execution records and raw
task measurements remain under `rounds/` and `final/`.
`dashboard --input <session-directory> --output <report.html>` reads the same
state and renders the objective and cumulative observed-token curves. Missing
usage remains unknown. Final acceptance is displayed separately from search
rounds; reopening a completed campaign does not increase its recorded duration.

## Tokens and interruption recovery

The current conversation's Agent runs outside the InferRSI process. Import
actual per-round token exports with `session round --usage-export usage.json`.
The JSON contains `input_tokens`, `output_tokens` and optionally
`cached_input_tokens`. Missing observations remain unknown. Cached input is a
subset of input. A whole-session export can be supplied to `session final` and
is retained separately from the per-round cumulative series. These are labelled
caller exports. Monetary cost remains unknown.

For an interrupted coordinator, run `session recover --session <directory>`.
It collects the existing execution record and task output and settles the same
attempt. Recovery performs no new candidate execution. If the execution record
is unavailable, inspect the original process and resource cleanup before further
action. Recovery also regenerates a summary from already settled state.

## Ownership and future automatic Agent launch

Benchmark owns task definitions and task-specific assessment scripts. Harness
owns resource freezing, protocol loading, execution, retained-result assessment,
session budget, attempts, records and final. The CLI resolves a task directory
only at start and injects KnowledgeReader when requested. Later operations use
the frozen task without consulting the registry. Ordinary projects enter the
same Harness directly, without importing Benchmark. The current Agent drives
the change and feedback cycle. A complete result requires the prescribed rounds
and final.

The [native Agent handoff](native-agent-sessions.md) prepares the task request
before an optimization campaign exists. Harness records one creation attempt
and the native identity; the initiator calls the actual host tool, observes it,
and retains delivered artifacts. The child creates the campaign and completes
its independent final before returning. Generic `agents prepare/dispatch` does
not itself create a conversation. DSH native launch and automatic Agent CLI
drivers remain follow-up work. InferRSI's existing SkillEval CodexClient is not
used by this native host path.

AMD AgentKernelArena follows a similar separation. The task contract stays
independent of Agent configuration, and `agents/codex/launch_agent.py` builds the
`codex exec --json` command with model, effort, workspace and budget settings.
Its backend utilities retain terminal events and process lifecycle records.
This reference was inspected at revision
`50bf68d8d53fbd579f494d07192b9aad468b1bce`.

- [AgentKernelArena overview](https://github.com/AMD-AGI/AgentKernelArena/blob/50bf68d8d53fbd579f494d07192b9aad468b1bce/README.md)
- [Codex Agent adapter](https://github.com/AMD-AGI/AgentKernelArena/blob/50bf68d8d53fbd579f494d07192b9aad468b1bce/agents/codex/launch_agent.py)
- [Backend process and event handling](https://github.com/AMD-AGI/AgentKernelArena/blob/50bf68d8d53fbd579f494d07192b9aad468b1bce/agents/backend_cli.py)
