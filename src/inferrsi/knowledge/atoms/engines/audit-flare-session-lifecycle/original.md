---
name: audit-flare-session-lifecycle
description: Audit Flare complete prefix/session restoration, inbound transfer tickets, publication/use/retirement fences and host-restore admission outcomes. Use when a lookup hit does not become reused tokens, a cancelled waiter leaves transfers in flight, or a restarted session must recover KV pages together with recurrent, convolution and partial-tail state.
metadata:
  inferrsi: |
    {
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "license": "Apache-2.0",
      "tags": [
        "Flare",
        "flare-local-inference",
        "local-inference",
        "cuda",
        "session-state",
        "kv-cache",
        "recurrent-state",
        "convolution",
        "restore-admission",
        "transfer-ticket",
        "fences",
        "offload"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/NVIDIA/flare-local-inference",
          "resolved_url": "https://github.com/NVIDIA/local-inference",
          "commit": "bce032c014bae34502ba22d3304fa084d5b40afe",
          "paths": [
            "README.md",
            "LICENSE",
            "docs/runtime-package-design.md",
            "docs/prefix-cache-offload.md",
            "helios/src/runtime_package/format.rs",
            "helios/src/runtime_package/model.rs",
            "helios/src/execution/manifest.rs",
            "helios/src/model/contract.rs",
            "helios/src/model/catalog.rs",
            "helios/src/cache.rs",
            "helios/src/offload/mod.rs",
            "helios/src/offload/geometry.rs",
            "helios/src/offload/index.rs",
            "helios/src/offload/record.rs",
            "helios/src/offload/transfer.rs",
            "helios/src/scheduler.rs",
            "helios/src/server/runtime.rs",
            "tests/server/test_prefix_cache_offload.py",
            "qualify/performance.py",
            "qualify/provenance.py"
          ],
          "readset": "references/source-notes.md",
          "identity": "references/source-ledger.json",
          "license": "Apache-2.0"
        }
      ],
      "construction": {
        "anchor_kind": "source",
        "distillation_form": "task-agnostic",
        "strategy": "reuse-existing",
        "status": "source-derived-candidate",
        "method": "AREX scope/ground/construct/verify and repository evidence/usability methods adapted to InferRSI native owners and packaging; no DisCo runtime or managed import."
      },
      "applicability": {
        "scope": "Pinned Flare complete-session restore and admission audit for its NVIDIA SM120/SM121 research prototype. CUDA catalog scope is content classification, not device or backend qualification.",
        "prerequisites": "Access to package/source identity and bounded restore traces, with preparation compatibility established before cache-state diagnosis. Running, freeing resources or changing configuration requires separate authority.",
        "input_contract": "Execution ABI and prepared-contract version, ordinary/speculative configuration, model/layout identity, request IDs and consumed-token endpoints, GPU/host prefixes, continuation row, ticket/waiter identities, transfer events, fences and resource counts.",
        "produced_artifact": "A checkpoint/ticket ownership table, five-outcome admission ledger and diagnosis identifying the earliest unsupported transition and smallest missing observation.",
        "failure_modes": "A KV-only lookup hit can omit continuation state; admission can be mistaken for actual reuse; client cancellation can be mistaken for transfer completion; mixing absolute timestamps from client and native clocks can corrupt the diagnosis.",
        "refusal_point": "Stop with an unresolved edge when package identity, layout, transfer completion or clock provenance is unknown."
      },
      "limitations": [
        "Source-only candidate; native Flare/model/GPU/service and skill efficacy were not evaluated.",
        "GDS/Direct transport is deferred and explicitly rejected by the pinned implementation.",
        "Multi-rank source branches do not establish multi-GPU, multi-host or hardware failure qualification.",
        "Root Apache-2.0 attribution does not grant model, asset or separately licensed dependency rights.",
        "Only the selected symbols/sections were inspected; kernels, exporter implementation and whole-repository behavior are outside coverage."
      ],
      "provenance_readsets": [
        "references/source-notes.md",
        "references/source-ledger.json"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Pair the immutable KV parent chain with the complete continuation row at the same consumed-token endpoint before calling a checkpoint restorable.",
        "Distinguish lookup outcomes, destination reservation, ticket creation, transfer completion, publication and actual reused-token evidence.",
        "Follow scheduler-owned tickets through waiter cancellation and check write/use fences before allowing storage reuse."
      ]
    }
---

# Audit Flare session lifetimes

Use this procedure for a concrete Flare request, prefix key or restore trace.
It produces a state/owner/event ledger and identifies the earliest unsupported
transition. The mechanism is specific to the pinned Flare implementation; it is
not a KV backend configuration recipe.

Status: **candidate**; empirical validation: **not_run**; skill efficacy:
**not evaluated**. [Source notes](references/source-notes.md) bind the CODE,
DOC and unexecuted TEST-SOURCE evidence to one immutable revision. The source
repository is a research prototype targeting NVIDIA SM120/SM121. GDS is deferred.
No native execution, model correctness, service gain or multi-rank qualification
is supplied by this knowledge.

## Choose the owner

| Question | Route |
|---|---|
| What may leave Python preparation and be reconstructed by Rust? | Existing [weight-loading owner](../../../../playbooks/optimization/weight-loading-optimization/SKILL.md#10-separate-preparation-from-serving), including its Flare preparation reference |
| What constitutes a restorable Flare checkpoint? | [Complete state and lifetimes](references/lifecycle.md#complete-state) |
| Why did a host match fail to save prefill? | [Admission outcomes](references/diagnostics.md#admission-outcomes) |
| What must remain live after cancellation? | [Transfer and fence ledger](references/lifecycle.md#ownership-and-completion) |
| Is this vLLM connector retention or LMCache MP tier policy? | Their separate [vLLM](../../vllm/audit-vllm-kv-lifetimes/SKILL.md) and [LMCache](../../lmcache/kv-tier-management/SKILL.md) owners; do not transplant those contracts |

## Inputs

Obtain the exact source/package identity, execution ABI and prepared-contract
version, selected ordinary/speculative configuration, model identity and cache
layout fingerprint. For bounded request IDs, retain consumed-token endpoints,
GPU-resident prefix, host chain/page count, continuation row, ticket key,
waiters, submit/completion events, fences and resource counts. Mark absent
observations as missing. A directory name, a lookup counter or a client response
alone cannot establish complete restoration.

## Procedure

1. **Check preparation compatibility.** Use the existing loading owner before
   diagnosing cache state. Execution ABI 4, prepared contract 2 and payload/carrier
   formats are independent version domains. An old ABI/contract requires
   re-export; changing a version field does not reconstruct compatible graphs.
2. **Prove the endpoint is complete.** Pair the parent-linked immutable KV page
   chain with the endpoint's complete continuation row. Check the exact
   consumed-token count, row presence, required parent-chain readability and
   model/layout/ordinary-versus-speculative namespace. Partial pages, recurrent
   matrices and convolution histories cannot be replaced by a KV-only hit.
3. **Classify admission before calling it reuse.** Trace lookup and cost checks,
   destination reservation, new or shared ticket and fetch enqueue separately.
   Record all five `LookupOutcome` values; several cost-rejected endpoints can
   precede a shallower admitted endpoint. `Admitted` still needs completion,
   publication and actual reused-token evidence.
4. **Trace transfer ownership through cancellation.** An inbound request waits
   without running model work. Cancelling that waiter removes the request from
   the ticket, while the scheduler-owned ticket retains its destination pages,
   snapshot and parent pin until transfer completion. Do not return them because
   the client disconnected. Distinguish rejected enqueue, confirmed failed
   completion and a store that has lost the ability to account for transfers.
5. **Check each readiness and reclamation condition.** Successful inbound
   completion calls `finish_inbound`, publishes/restores the checkpoint and
   attaches surviving waiters. GPU publication readiness, later-use fences,
   logical eviction and permission to reuse storage are separate transitions.
   Check the maximum relevant write/use fence, not just request completion.
6. **Compare observations within their domains.** Correlate request metadata,
   actual reused tokens and settled metric deltas. Preserve SSE token groups.
   Compute client delivery timing and native core timing separately; never
   subtract their absolute timestamps. Use [diagnostic cases](references/diagnostics.md)
   to choose the next missing observation.

## Actions, cost and stopping point

Read package metadata, source and existing traces; produce a checkpoint/ticket
ownership table, a five-outcome admission ledger and a diagnosis with the
smallest missing observation. This guidance grants no running, repair, freeing,
backend replacement or configuration-change authority.

Correct retention can consume device pages, snapshots, registered RAM and disk
staging while work drains. Restoration may save prefill yet lose on transfer
cost; more cache hits alone are not a benefit measure. Stop with an unresolved
edge when the package, layout, transfer completion or clock provenance is
unknown. Native model/device and end-to-end checks require a separately frozen,
authorized plan; the source candidate remains unpromoted.
