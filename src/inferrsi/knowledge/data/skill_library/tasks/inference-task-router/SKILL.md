---
name: inference-task-router
description: Select the starting route for day-0 model support, inference performance optimization, debugging, accuracy repair, version alignment, derived-engine development or independent runtime bring-up.
metadata:
  inferrsi: |
    {
      "schema_version": 1,
      "profile": "local-skill-v1",
      "kind": "skill",
      "discovery_role": "task-entry",
      "status": "candidate",
      "origin": [
        "first-party"
      ],
      "consumption_mode": "packaged",
      "tags": [
        "task-routing",
        "model-onboarding",
        "performance",
        "debugging",
        "accuracy",
        "version-alignment",
        "inference-engine",
        "day-0",
        "cross-platform"
      ],
      "empirical_validation": "not_run",
      "searchspace_not_applicable": "This entry selects a task and its evidence requirements before resource-layer analysis.",
      "applicability": {
        "scope": "Classifying an inference engineering request and identifying reusable procedures.",
        "input_contract": "Goal, deliverable, known model, backend, OS, engine and workload constraints.",
        "produced_artifact": "Selected task cards, scoped references, unknowns and acceptance evidence.",
        "refusal_point": "If the execution owner, reference behavior or target compatibility is unknown, record the gap before making a target-specific recommendation."
      },
      "limitations": [
        "The cards describe routes and acceptance evidence; hardware support and task success require separate validation."
      ],
      "provenance_readsets": []
    }
---

# Choose an inference task

Choose one primary skill by the requested deliverable. Load its full procedure
before the first supporting evidence search. Record secondary tasks for follow-up.
When two primary skills remain plausible after reading the request, ask the user
which deliverable they want before loading either; do not guess a route.
The route cards remain available to callers that consume the JSON summaries.

| Primary skill | Choose it when | Route card |
| --- | --- | --- |
| `task-day-0` | First usable support for a new checkpoint or model architecture in an existing engine. | [day0-model](references/routes/day0-model.json) |
| `task-performance` | A correct baseline misses a specified latency, throughput, memory or cost objective. | [performance](references/routes/performance.json) |
| `task-debug` | A hang, crash, OOM or execution-path failure needs a reproducible cause. | [debug](references/routes/debug.json) |
| `task-accuracy` | Inference completes but output violates a reference, quality metric or tolerance. | [accuracy](references/routes/accuracy.json) |
| `task-version-alignment` | A dependency or engine upgrade must preserve API, ABI, operator or runtime behavior across a stack. | [version-align](references/routes/version-align.json) |
| `task-derived-engine` | The deliverable reuses the execution core of vLLM, vLLM-Omni or another pinned parent, as in a DeepInfer-like extension. | [derived-engine](references/routes/derived-engine.json) |
| `task-independent-engine` | A new runtime must own execution, memory and device integration on a distinct OS, model or hardware stack. | [independent-engine](references/routes/independent-engine.json) |

## Target conditions

Record model family as a list (LLM, Omni, TTS, Diffusion, RLT or another
specified family), model/checkpoint revision, hardware backend (CUDA, ROCm,
Ascend NPU, XPU or another specified target), device SKU, OS (Linux, Windows,
Android, iOS or another specified target), engine and revision, dtype, shape,
concurrency and constraints. An Omni pipeline may additionally include its TTS
or diffusion stages. Keep deployment form such as mobile/edge separate from OS.
An absent field is unknown. A routing label or a common-backend registration
does not establish device support. Check the selected owner's source and scope.

Failures that interrupt execution begin in debug. Correct execution with
unacceptable output begins in accuracy. A regression first observed after an
upgrade may use version-align as the primary route and either as a secondary
route. For engine work, decide who owns the execution core: an upstream fork
uses derived-engine; a new runtime owning its own execution and memory model
uses independent-engine, including on Windows or mobile. OS alone cannot
decide between them.

For a Windows vLLM fork with a TTS quality regression after an upgrade,
choose accuracy if the requested delivery is restored speech quality, or
version-align if the requested delivery is a validated upgrade matrix. Link
the other route and pin both revisions, the same audio input, and reference
output. Record fork lineage as context unless creating the fork is a deliverable.
If the delivery is unclear, state both routes and ask what must be accepted.

## Use and handoff

1. Load the selected primary procedure, for example
   `inferrsi skills enter task-version-alignment`. The compatibility card for
   machine readers is available through
   `inferrsi skills resource inference-task-router references/routes/version-align.json`.
2. Capture the actual run as the primary skill directs. Use observed triggers
   to choose supporting skills. Search for the named component or symptom with
   `inferrsi find`. Resolve candidate skill IDs via `skills show`, read their
   applicability, and retain only the source-backed matches. An exact owner
   or resource can also be opened directly. If only cross-platform methodology
   matches, return it as such, and list the missing target-specific evidence.
3. Record primary and secondary tasks, target conditions, fixed source references,
   gaps and acceptance evidence. A candidate skill is a starting point for
   inspection. Execution and promotion require the normal workbench contracts.

The cards contain seed IDs. For each affected stage and component, search the
full catalog as well. Report a target-validated owner, a methodological analogue
with its limits, or a missing owner. For a missing Windows/TTS or XPU match,
state the missing evidence and the smallest target check that would establish
it. Keep a general benchmarking procedure available as methodology. A project
policy or an unreviewed learning does not establish runtime compatibility.
