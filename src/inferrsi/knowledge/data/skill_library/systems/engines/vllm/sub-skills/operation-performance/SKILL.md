---
name: operation-performance
description: "Operate and benchmark a pinned vLLM engine with bounded experiments for batching, memory, prefix reuse, speculation, parallelism, P/D transfer, compilation and quantization."
license: Apache-2.0
metadata:
  disco-role: operating
---

# Operation and performance

Read [experiment decisions](references/experiment-decisions.md) for symptom-to-control reasoning; read [commands and measurements](references/commands-and-measurements.md) before a live run.

Capture model/tokenizer revisions, device count/type/memory and interconnect, software/source versions, effective config, request length distribution, arrival pattern, cache state, and latency/quality objective. Select a known-good baseline on the intended hardware. If none exists, establish a small correctness smoke before optimizing.

Measure one primary hypothesis at a time. Keep the workload and quality constraints fixed; compare repeated warm runs and separately record startup/compile cost. Sweep offered load as well as configuration: unlimited-rate burst results alone cannot establish sustainable service capacity. Keep failed requests and admission rejections in the result.

Stop a candidate when correctness, quality, memory, or a declared latency bound fails. Revert the changed setting and retain logs. Diagnose preemption, queueing, or transfer/collective failure using their own signals; an apparently idle GPU is not proof that more batching will help.

Deliver a table with baseline/candidate config, success/error counts, throughput, TTFT and ITL/TPOT distributions, peak memory, cache/preemption signals and quality result, plus remaining uncertainty. Report only measured gains. If runtime resources are unavailable, return the exact experiment and expected observations as unexecuted.
