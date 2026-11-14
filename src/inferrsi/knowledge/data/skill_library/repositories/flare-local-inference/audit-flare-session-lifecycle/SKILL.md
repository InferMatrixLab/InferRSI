---
name: audit-flare-session-lifecycle
description: Audit Flare complete prefix/session restoration, inbound transfer tickets, publication/use/retirement fences and host-restore admission outcomes. Use when a lookup hit does not become reused tokens, a cancelled waiter leaves transfers in flight, or a restarted session must recover KV pages together with recurrent, convolution and partial-tail state.
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
| What may leave Python preparation and be reconstructed by Rust? | Existing [weight-loading owner](../../../methods/weight-loading-optimization/SKILL.md#10-separate-preparation-from-serving), including its Flare preparation reference |
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
