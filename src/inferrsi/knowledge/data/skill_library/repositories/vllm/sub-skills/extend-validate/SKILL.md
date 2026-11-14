---
name: extend-validate
description: "Implement a focused vLLM inference change at scheduler, KV connector, attention, quantization or compilation boundaries with correctness invariants and native test selection."
license: Apache-2.0
metadata:
  disco-role: operating
---

# Extend and validate

Use when configuration alone does not provide the requested behavior, or when fixing a demonstrated defect. Read [change boundaries and validation](references/change-boundaries-and-validation.md).

Write a small behavioral contract: trigger, current behavior, desired result, affected owners, allowed numerical differences, and the shortest failing observation. Locate the path on the user's revision and confirm the requested behavior is not already configurable.

Implement the smallest change at the owner of the behavior. Follow repository contributor instructions; use signed-off commits (`git commit -s`) when committing in this workspace. Avoid assuming a custom scheduler, connector or backend contract is stable across versions.

Validate in layers: static/source contracts → focused native unit tests → device-specific correctness → service/concurrency and failure paths → bounded performance comparison. Prefer existing tests at the changed boundary, adding a regression only when it detects the defect. Record tests actually run, dependency/hardware blockers and exact remote follow-ups.

Recovery: if a new backend, quantization or transfer path is unsupported, retain the last known-good implementation and isolate the unsupported combination; do not weaken validation or silently fall back in a way that changes semantics. Self-review cancellation, lifetime, concurrency and config hashing before handing off.
