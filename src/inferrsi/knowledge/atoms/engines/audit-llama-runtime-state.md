---
name: audit-llama-runtime-state
description: "Audit llama.cpp context memory, partial decode progress, graph reuse and server cancellation when a retry, stale prefix, unexpected rebuild or unreleased slot needs an ownership explanation; requires pinned source or a concrete runtime trace."
metadata:
  inferrsi: |
    {
      "tags": [
        "llama.cpp",
        "context",
        "state",
        "graph-reuse",
        "cancellation",
        "correctness"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/ggml-org/llama.cpp",
          "commit": "707616feb5f379e99ff7442680a55b4a1704c7c9",
          "paths": [
            "LICENSE",
            "include/llama.h",
            "src/llama-context.cpp",
            "src/llama-context.h",
            "src/llama-memory.h",
            "src/llama-memory-recurrent.cpp",
            "src/llama-graph.cpp",
            "src/llama-graph.h",
            "ggml/src/ggml-backend.cpp",
            "tools/server/server-context.cpp",
            "tools/server/server-queue.cpp",
            "tools/server/server-queue.h",
            "tests/llama-context/cases-kv.cpp",
            "tests/llama-context/cases-rs.cpp",
            "tests/CMakeLists.txt",
            "tests/test-llama-archs.cpp",
            "tests/test-backend-ops.cpp",
            ".github/workflows/build-cann.yml",
            "tools/server/tests/unit/test_completion.py"
          ],
          "readset": "references/source-notes.md"
        }
      ],
      "applicability": {
        "scope": "Pinned llama.cpp context-memory, graph-reuse and server task-lifecycle diagnosis; concrete model/backend behavior requires native validation.",
        "prerequisites": "Pinned llama.cpp source or a concrete runtime trace, access to the relevant memory/graph/server ownership evidence and an identified caller recovery policy that remains in force.",
        "input_contract": "Source/build and model revisions, memory type, actual backend/device and execution mode, context/batch/ubatch parameters, sequence IDs/positions/output flags and return status; graph cases need dispatch evidence, server cases need correlated HTTP/task/slot/cache logs.",
        "produced_artifact": "An owner/event ledger of ubatch progress, retained memory, graph-gate decisions, input readiness and slot release/retention, with the first supported broken obligation or smallest missing observation.",
        "failure_modes": "Assuming whole-batch rollback after partial decode failure, treating token count as a complete graph-reuse key, or equating posted cancellation with released slots can hide retained state or misdiagnose correct deferred work.",
        "refusal_point": "Stop before reset or repair if revision, memory type, actual backend, sequence ownership or partial progress is unknown; escalate unsupported rollback or unresolved in-flight work."
      },
      "limitations": [
        "Source-derived candidate; native runtime and efficacy validation not run.",
        "No cross-backend preemption, model-quality or performance claim.",
        "KV, recurrent and hybrid state contracts must be checked independently."
      ],
      "provenance_readsets": [
        "references/source-notes.md"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Reconcile per-sequence retained positions with completed ubatches before retrying a failed logical batch.",
        "Check both graph allow_reuse and input can_reuse gates, then establish copy readiness independently of graph identity.",
        "Trace cancellation posting, normal task processing, slot release and prompt retention as separate events."
      ]
    }
---

# Audit llama.cpp runtime state

Status: candidate. Empirical validation: **not_run**. This is a source-grounded diagnostic procedure, not a qualified backend optimization or a full llama.cpp operating guide.

## Trigger and boundary

Use when a decode error may leave partial progress, a repeated batch rebuilds its graph, a cancelled request retains a slot or prompt, or a state replay differs. Establish the state owner before proposing a reset, cache policy or backend change.

Do not use for weight loading, NUMA/affinity tuning, quantization quality, model conversion, multimodal state, distributed RPC, or backend kernel optimization. Existing `weight-loading-optimization`, `os-process-placement` and LMCache-owned `kv-tier-management` cover different responsibilities; their source pins and hardware limits remain independent.

Source: ggml-org/llama.cpp `707616feb5f379e99ff7442680a55b4a1704c7c9`, MIT. Read the bundled [source notes](references/source-notes.md). **CODE** identifies an inspected implementation or public contract; **TEST-SOURCE** identifies assertions inspected but not run. The diagnostic procedure and proposed runtime checks are **HYPOTHESIS** until applied to a concrete case. The older loading/host source `3e390af18de1131dda27913c00511725b4274c8a` is not this runtime snapshot.

## Choose the scope

Select the owner by the state or configuration you need to explain. Loading and host placement retain their own source-scoped procedures.

| Question | Existing owner and readset | Fixed source snapshot | Carried static inspection |
| --- | --- | --- | --- |
| Loading modes, mapping/locking and lazy tensors | [weight-loading-optimization §6](../../../../playbooks/optimization/weight-loading-optimization/SKILL.md); [loading readset](../../../../playbooks/optimization/weight-loading-optimization/references/llama-loading-readset.md) | `3e390af18de1131dda27913c00511725b4274c8a` | 2026-10-22 |
| NUMA modes and generation/batch thread placement | [os-process-placement](../../../platforms/host/os-process-placement/SKILL.md); [NUMA/thread readset](../../../platforms/host/os-process-placement/references/llama-numa-thread-readset.md) | `3e390af18de1131dda27913c00511725b4274c8a` | 2026-10-22 |
| Decode progress, graph/input reuse and task/slot cancellation | [This runtime audit](#diagnostic-procedure); [runtime source notes](references/source-notes.md) | `707616feb5f379e99ff7442680a55b4a1704c7c9` | 2026-10-21 |

The dates are carried source inspections, not native results. Apply each owner's prerequisites and readset at its own pinned revision. These snapshots do not establish an intervening version range or cross-backend compatibility.

## Required inputs

Obtain source/build revision, model architecture/revision, memory type (KV, recurrent or hybrid), backend/device, offload/parallel mode, effective context parameters, logical batch and ubatch sizes, sequence IDs/positions/output flags, and the observed return/status or symptom. For graph cases also obtain graph reuse settings and actual dispatch evidence. For server cases correlate HTTP/reader lifetime, task ID, slot ID, request mode, prompt/cache policy, and queue/slot logs.

Keep missing facts explicit. A model name alone does not establish memory behavior; a compiled backend does not establish that it executed.

## Diagnostic procedure

1. **Map owners and the actual entry.** Separate model weights, context memory, batch allocation, reusable graph/input tensors, backend scheduler buffers/events, server task, slot prompt, and HTTP reader. For server decode, follow `llama_process(DECODE)` into the same context decoder rather than assuming every caller uses the legacy `llama_decode` wrapper (S1, C3).
2. **Classify the failure before retry.** Record the exact code: 1 means no memory slot, -1 invalid batch, 2 abort, and less than -1 fatal error. The public decode contract preserves completed ubatches after abort/fatal failure; it does not promise whole-batch rollback. Inspect `llama_memory_seq_pos_min/max` for each affected sequence and reconcile them with caller token accounting. Do not blindly resubmit the original logical batch or silently mark its entire prefix valid (S2).
3. **Check the concrete memory contract.** The decoder prepares an ubatch plan, then applies the current ubatch's memory state before graph execution. On that ubatch's failure it removes entries from the computed minimum positions. KV, recurrent and hybrid implementations can have different removal/rollback capabilities. Check the actual operation's return and model-specific constraints; do not invent arbitrary recurrent rollback or assume sequence copy means independent physical storage (S1, S3).
4. **Explain graph reuse with both gates.** Compare topology-relevant batch shape, sequence participation, output count, sampler identity/output routing, effective flags and adapter/cross-state identity against `allow_reuse`; then inspect the relevant input's `can_reuse` checks and memory-context rebinding. Reuse also requires the previous graph result to be active and reuse to be enabled. Token count alone is not a complete key. A miss builds/allocates a graph; a hit still updates its inputs (G1).
5. **Trace data readiness, not just graph identity.** In pipeline parallel mode the context synchronizes before overwriting reused inputs. The ggml scheduler protects per-copy input buffers with events or synchronization and may use synchronous copies. Record backend splits, copy ownership, allocation changes and completion boundaries. A successful async submission is not proof of completed work, overlap or a backend-native captured-graph hit (G2).
6. **Follow cancellation to the responsible owner.** A response reader stops waiting and posts high-priority cancellation tasks; posting removes matching pending/deferred/unhandled tasks. The normal task processor releases the matching active slot. While decode is yielding, metrics and slot-read tasks are accepted; state-mutating cancellation is deferred until compute leaves that yield. Check these events separately from a backend abort callback or device synchronization (C1, C2).
7. **Interpret release and recovery precisely.** `server_slot::release` clears prompts for child/stateless tasks; normal stateful prompts can remain for reuse. Explicit `prompt_clear` removes the sequence and prompt metadata. The server's fatal decode branch releases active slots and clears their prompts because partial progress is hard to reconcile; its source still contains TODOs for exact position reconciliation and abort handling. Do not claim fine-grained recovery or immediate accelerator preemption (C2, C3).
8. **Report the first supported broken obligation or the smallest missing observation.** Provide the owner/event ledger, applicable source facts, counter-signals, exact revision and unresolved edge. Propose a focused real native case before proposing a fix. Do not change live state, workload, acceptance gates, backend configuration or resource allocation as part of this audit.

## Expected outputs and verification

Produce a bounded ledger containing request/task/slot/sequence identity, input positions, ubatch progress, return status, retained memory range, graph gate decision, input-copy readiness and release/retention outcome. Explain which observations distinguish a correct retained prefix from stale state, a legitimate graph miss from faulty reuse, and deferred cancellation from a leaked slot.

Native verification candidates are KV sequence-isolation/state-replay cases, recurrent rollback/replay cases with their skip conditions, and the server cancellation test that checks slot release. A partial-ubatch abort test must establish that an earlier ubatch actually completed; otherwise it does not verify the partial-progress boundary. Reuse-on/off comparison must keep model, tokens, positions, output routing and effective settings fixed and prove which path executed. Compare outputs before measuring time. These checks have not run here (T1–T3).

CPU can validate selected public state/server behavior with a real fixed-pin build and fixtures. It cannot validate CUDA/Metal/CANN asynchronous execution or preemption. A Python harness/import is not C++ runtime verification. Missing a required native build, model fixture, backend or observed transition is an unresolved verification requirement, not a pass.

## Stop conditions and trade-offs

Stop before a reset or repair when the revision, memory type, actual backend, sequence ownership or partial progress is unknown. Preserve the caller's established recovery policy. Escalate an unsupported rollback, unresolved in-flight work, incomplete task-ID correlation, or unverified backend assumption.

The intended benefit is a correct ownership diagnosis and a smaller regression case. Required tracing costs host work; synchronization can reduce overlap; valid retained prompts consume memory; clearing a context can discard reusable computation. No latency, throughput, memory saving or efficacy gain is measured by this candidate.
