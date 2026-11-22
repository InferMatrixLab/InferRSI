---
name: comfy-ui
description: Audit ComfyUI workflow-output cache validity, lazy dependencies and model-weight residency as separate state contracts using a pinned source revision and explicit runtime evidence.
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
      "license": "GPL-3.0",
      "tags": [
        "comfyui",
        "workflow",
        "cache-invalidation",
        "model-residency",
        "state-ownership"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/Comfy-Org/ComfyUI",
          "commit": "b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c",
          "paths": [
            "execution.py",
            "comfy_execution/caching.py",
            "comfy_execution/graph.py",
            "comfy/model_management.py",
            "comfy/model_patcher.py",
            "comfy/sampler_helpers.py",
            "server.py",
            "main.py",
            "comfy_execution/graph_utils.py",
            "comfy_execution/cache_provider.py",
            "nodes.py",
            "comfy/sample.py",
            "comfy/samplers.py",
            "tests/execution/test_execution.py",
            "tests-unit/execution_test/test_execution_list.py",
            "tests-unit/comfy_test/model_management_test.py",
            "tests/inference/test_inference.py",
            ".github/workflows/test-execution.yml",
            "LICENSE",
            "pyproject.toml",
            "tests-unit/execution_test/test_cache_provider.py",
            "AGENTS.md"
          ],
          "readset": "references/repo-provenance.md"
        }
      ],
      "applicability": {
        "scope": "Source-grounded ComfyUI workflow-output cache and model-weight ownership audit; confirm the actual revision, node registry, cache caller and static/dynamic patcher before transfer.",
        "prerequisites": "Access to the pinned provenance and the actual node registry/cache caller; residency questions additionally require the concrete patcher and effective dynamic/static mode. Native memory conclusions need the actual backend.",
        "input_contract": "Exact revision, API-format prompt/output targets, relevant node classes/constants/links/hidden inputs and external state, selected cache caller/mode and patcher settings, plus available execution/load/memory/timing observations.",
        "produced_artifact": "A state/owner/key/lifetime/consumer ledger with invalidation or release events, evidence and unresolved boundaries, followed by a discriminating check and its actual result.",
        "failure_modes": "Treating identical JSON as proof of unchanged external inputs, confusing eviction with key validity, or equating workflow cache hits with device-resident model weights can explain the wrong state contract.",
        "refusal_point": "Stop when the cause/action is supported or required environment, backend or model resources are unavailable; do not manufacture a hit, hardware result or performance threshold."
      },
      "limitations": [
        "Source-derived candidate; no local executor-cache, device-residency or performance qualification.",
        "Seven self-authored cases exercised only the unchanged pure upstream graph_utils module; they do not verify PromptExecutor, cache signatures or model behavior.",
        "The dynamic native allocator and third-party custom-node behavior remain outside the verified scope."
      ],
      "provenance_readsets": [
        "references/repo-provenance.md"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Draw the affected dependency cone with declared, lazy and dynamically expanded links, then mark unfingerprinted external state unresolved.",
        "Separate output/object cache validity and retention from patch identity, partial unload, full detach and allocator-visible release.",
        "Change one test variable while fixing prompt, output target, model, backend, precision, seed and cache mode; check values and executed nodes before timing."
      ]
    }
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
