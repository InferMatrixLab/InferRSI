---
name: strata
description: "Analyze, develop and tune Strata-style heterogeneous MoE inference engines using source-grounded design choices, conditional search spaces and correctness-gated experiments. Use for Strata architecture, CPU/GPU expert placement, cache and speculative-decoding tradeoffs, or engine validation."
license: MIT
metadata:
  disco-role: operating
---

# Strata inference engineering

Use the repository's mechanisms as an evidence-backed starting point for engine design and tuning. This skill is a candidate distilled from a pinned source revision; it does not certify GPU execution or a performance improvement. Read [provenance](references/repo-provenance.md) when using another revision or model family.

## Route the work

- For architecture analysis or an AI-generated engine search space, read [design-space](sub-skills/design-space/SKILL.md).
- For a concrete hardware/workload tuning plan, read [tune-execution](sub-skills/tune-execution/SKILL.md).
- Before declaring correctness or speed, and for build/benchmark failures, read [validate-engine](sub-skills/validate-engine/SKILL.md).
- For cross-cutting failures, read [troubleshooting](references/troubleshooting.md).

## Establish the contract

Record the model family and exact weights/quantization, source revision, backend and hardware topology, available VRAM/RAM, prompt/output lengths, concurrency, sampling policy, quality threshold and optimization goal. If hardware is unknown, produce conditional candidates; do not invent an optimal configuration.

Separate fixed model semantics from runtime parameters, replaceable algorithms and newly proposed capabilities. Strata's Flash-Next and Qwen3.6 paths are not interchangeable. Treat CPU/GPU arithmetic differences, KV quantization and routed-expert skipping as quality-sensitive. A native runtime and its Python server require different checks; `setup.py` is not a package installation entry point for `pip install .`.

## Produce a reviewable result

1. State the bottleneck hypothesis and evidence, then change one mechanism or a deliberately coupled set.
2. Reject incompatible or over-budget configurations before measurement; record the configuration actually activated by the engine, including fallback messages.
3. Verify numerical and state correctness before ranking performance. Report static, CPU-only and GPU-native evidence separately.
4. Compare identical experiment conditions, retain raw logs and counterexamples, and report uncertainty and remaining backend gaps.

For measured trial summaries, use the bundled [CSV contract](references/trial-format.md) and [summarizer](scripts/summarize_trials.py). The helper filters supplied validity/quality labels and computes descriptive medians; it does not establish those labels or statistical significance.
