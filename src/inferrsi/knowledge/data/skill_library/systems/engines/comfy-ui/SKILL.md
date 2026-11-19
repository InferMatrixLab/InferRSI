---
name: comfy-ui
description: Audit ComfyUI workflow-output cache validity, lazy dependencies and model-weight residency as separate state contracts using a pinned source revision and explicit runtime evidence.
---

# Audit ComfyUI cache and residency

Source-derived candidate for ComfyUI `b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c`
(`0.42.0`). Read [provenance](references/repo-provenance.md) before transferring
the procedure to another revision. The upstream source is GPL v3; its license
and attribution are retained with this owner.

Use when a ComfyUI workflow reruns unexpectedly, appears to reuse stale output,
or has unexplained model reload/offload behavior. This procedure produces an
audit and a discriminating validation plan. It does not launch ComfyUI, edit a
workflow, download models or change memory policy on its own.

Do not use it to configure an LLM KV/prefix cache, approximate diffusion-step
reuse, a training rematerialization solver, a frontend workflow, or arbitrary
third-party custom-node behavior. These are different contracts.

## Inputs

- Exact ComfyUI revision, API-format prompt and chosen output targets.
- Relevant node classes, constants, links, hidden inputs and external state
  such as file/model revisions or randomness.
- Effective cache mode and entry caller; model patcher class and effective
  dynamic/static VRAM mode when investigating residency.
- Available observations: executed/cached node IDs, model-load events,
  allocated/reserved/free device bytes, host/pinned bytes and phase timings.
  Missing observations remain explicit inputs to the validation plan.

## Procedure

1. **Classify the symptom.** Separate a wrong reused value, an unexpected cache
   miss, scheduler blocking and model memory pressure. A workflow output hit is
   not a promise that its model remains on the device.
2. **Draw the affected dependency cone.** Record producer → output socket →
   consumer/input and the intended output targets. Separate declared links
   from currently required lazy links and dynamically expanded nodes. A static
   reachability diagram cannot predict the exact runtime execution order.
3. **Build a validity ledger.** Follow
   [graph-cache invalidation](references/graph-cache-invalidation.md). For the
   affected node and its ancestors, list class, constants, link sockets,
   fingerprint/`IS_CHANGED`, conditional node identity and every external input.
   Mark external state without a fingerprint as unresolved; do not assert that
   identical JSON proves equal results. Distinguish output and object caches.
4. **Separate validity from retention.** Confirm the caller's selected classic,
   LRU, RAM-pressure or disabled mode. An eviction can explain recomputation
   without changing the key. A size/headroom setting is not a measured total
   process-memory bound. Never improve the hit rate by deleting a required key
   input or concealing an external-state change.
5. **Trace weight ownership when relevant.** Follow
   [model residency](references/model-residency.md). Name the concrete patcher
   type, requested/loaded/offloaded bytes, patch identity, active consumers and
   host-pinned state. Distinguish partial unload, full detach, patch restoration,
   cache-entry eviction and allocator-visible release. CPU does not exercise
   the dynamic accelerator path.
6. **Choose the smallest discriminating check.** Use the
   [validation boundaries](references/validation-boundaries.md). Keep prompt,
   output target, model, backend, precision, seed and cache mode fixed except
   for the one variable being tested. Validate values and executed node sets
   before interpreting timing. Device-memory claims require the actual backend.
7. **Return a bounded decision.** Report the cause supported by the evidence,
   competing explanation, invariant at risk, one preferred next action and the
   exact evidence needed to falsify it. Stop when the cause/action is supported
   or a required environment/backend/model is unavailable. Do not manufacture
   a cache hit, hardware result or performance threshold to finish the audit.

## Output

Return one table with `state`, `owner`, `key/identity`, `lifetime`, `consumer`,
`invalidation/release event`, `evidence`, and `unresolved boundary`; then the
chosen check and its actual pass/fail/not-run result. Keep CODE, TEST-SOURCE,
runtime observation and transfer hypothesis distinct. Passing reader or
catalog tests does not promote this candidate or qualify ComfyUI execution.
