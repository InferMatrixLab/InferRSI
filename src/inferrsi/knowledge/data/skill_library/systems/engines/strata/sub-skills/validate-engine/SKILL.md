---
name: validate-engine
description: "Validate Strata engine changes with source checks, CPU tests, GPU operator parity, real-model API checks, cancellation and concurrency tests, and controlled quality/performance experiments. Use before accepting an AI-generated inference-engine candidate or claiming a speedup."
license: MIT
metadata:
  disco-role: operating
---

# Validate a Strata engine candidate

Use this leaf to turn a proposed optimization into a reproducible accept/reject decision. Read [the validation cookbook](references/validation.md) for complete commands, prerequisites, metrics, and recovery actions. Route variable selection to [design-space](../design-space/SKILL.md) and execution tuning to [tune-execution](../tune-execution/SKILL.md).

## Inputs and contract

Obtain the baseline/candidate source revision and executable, target GPU/backend, CPU/RAM/storage, model and quantization, model artifact hashes, tokenizer, effective config and environment, workload, quality tolerance, memory budget, and latency/throughput objective. A missing GPU or model does not prevent source/CPU review, but it prevents a claim that the inference engine works on that backend.

Strata's `setup.py` is an installer and launcher, not setuptools packaging. Do not use `pip install .` or import `strata` as the installation check. Run repository scripts from a source checkout. `requirements.txt` specifies the Python environment; native engines use CMake. Setup can install software and download large model artifacts, so it is not a validation smoke command.

## Workflow

1. **Freeze the experiment.** Record both revisions, build options, executable hashes, model hashes, resolved config/environment, and machine facts. Define the success threshold before trying variants; retain a held-out workload. Use one factor per first comparison, then test interactions.
2. **Check source and CPU behavior.** Run the selected no-download Python tests. If a C++20 toolchain is available, use the CPU-only CMake configuration in the cookbook. A successful configure or import is not runtime correctness evidence.
3. **Run the actual backend.** Build the changed backend, device self-test, and relevant GPU parity targets. Distinguish passed, failed, skipped, absent, and unavailable cases. A missing fixture, unsupported instruction set, or missing accelerator is never a pass.
4. **Check a real model.** Verify health, model identity, one deterministic response, prompt/decode behavior, and the feature touched by the change. Preserve raw token IDs or logits where the harness supports them. Exact-path optimizations need the applicable parity contract; numerical changes need explicit error and task-quality bounds.
5. **Exercise state transitions.** Check cache restore, long prompts, concurrent slots, cancellation, and the next request after cancellation. Batch versus solo exactness needs controlled CPU/GPU rounding settings; follow the cookbook rather than labeling every text difference a scheduler bug.
6. **Measure performance after correctness.** Use the same-day baseline, alternating A/B order, warm-up, repeated runs, actual token counts, cache state, and engine/client timing provenance. Report medians and ranges, and p95 only with its sample count. Separate fresh prompts, cache reuse, and first-load time.
7. **Review and decide.** Reject candidates that violate correctness, quality, memory, or required latency bounds. Keep a Pareto set for legitimate tradeoffs. Return a decision with commands, exit codes, raw-output locations, exclusions, risks, and remaining hardware checks; never promote a source-inspected idea to a measured default.

## Output

Produce a concise experiment record with `candidate`, `baseline`, `hardware`, `model`, `workload`, `changed_factor`, `correctness`, `quality`, `latency`, `throughput`, `memory`, `errors`, `evidence`, and `decision`. Mark each validation layer as `PASS`, `FAIL`, `BLOCKED_REQUIRED_BACKEND`, or an explicitly reasoned skip. For a required backend with no runtime evidence, the overall result remains partial.

## Execution boundary

This skill bundles the reasoning and command contracts. The native test binaries, model fixtures, and server are intentionally executed in the matching Strata checkout: they depend on that checkout's C++ implementation, tokenizer, model files, and backend libraries. Copying them into this skill would create a stale second engine. No model, runtime, or installer is bundled. The cookbook is sufficient to choose and interpret checks without opening upstream documentation; source links provide provenance.
