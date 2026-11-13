---
name: sglang-tuning-validation
description: "Design bounded SGLang tuning experiments and source-backed correctness, latency, throughput, memory, and regression validation."
license: Apache-2.0
metadata:
  disco-role: operating
---

# Tuning and validation

Read [tuning and validation](../../references/tuning-and-validation.md) for commands, measurement design, recovery, and local/GPU gates. [Root routing](../../SKILL.md).

State the objective and hard constraints before searching: for example, completed-request throughput subject to p99 TTFT/ITL, an error budget, accuracy tolerance, and memory capacity. Specify workload distribution and a finite trial/time budget. A single random-input throughput score is not a production conclusion.

Label each candidate as an existing knob, implementation change, or research extension. Start from a reproducible baseline; change one causal family first, then explore measured interactions. Exclude invalid combinations using source validators before spending GPU time.

Preserve the same model/tokenizer, commit, topology, request set, arrival process, seed, cache policy, output caps/EOS behavior, warmup, and measurement duration for paired trials. Capture successful/failed requests, queueing, token counts, p50/p95/p99 latency, throughput, memory headroom, and cache/speculation statistics when available.

Correctness gates precede ranking: numerical reference and logits/logprobs; cache miss versus hit; chunked versus unchunked; speculative versus baseline; intended distributed topology; representative quality checks. Set tolerances from the reference path and dtype, not by relaxing them until the candidate passes.

Reject candidates that violate constraints. Repeat promising pairs enough to expose variance, retain failures and raw artifacts, and report the Pareto tradeoff. Stop at the declared budget or when the effect is below noise. If the environment cannot run the required gate, deliver a runnable validation plan and mark that gate unverified.
