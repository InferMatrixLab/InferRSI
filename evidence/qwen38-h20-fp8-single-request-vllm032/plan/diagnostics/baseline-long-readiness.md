# Baseline long-context feasibility

Prospective workload: [Issue67 comment](https://github.com/InferMatrixLab/InferRSI/issues/67#issuecomment-6347246284).
Infrastructure retry: [separate prospective comment](https://github.com/InferMatrixLab/InferRSI/issues/67#issuecomment-6347328808).
One H20,35-minute cap from readiness for each declared attempt;180-second request
and1200-second startup limits,2000-second outer command limit. Same authenticated
official FP8 weights, unmodified vLLM0.32.0 and pinned official client; exact
fixture/client/model/observer identities are recorded by the retained observer.

Sequential fixed inputs s0:32/8 warmup,32/8 framing,8192/32,65536/8,131072/8.
Greedy,ignoreEOS; validate every prompt echo, generated token ID, usage, terminal
reason and timing event. Stop on error. Log actual dispatch and clean only the
owned process group and allocation. This is a feasibility/cost probe, not the
2048-output performance matrix, retrieval validation or candidate search.

Necessary server settings: loopback/name,133120 maximum context, prefix caching
off, language-model-only. Dtype, quantization, KV, batching, compilation, Graph,
attention and kernel selection retain defaults. All file caches are task-root
scoped. Job1959 used filesystem IPC and lacked the environment bin on PATH.
CPU1960 confirms filesystem EOPNOTSUPP even at70-byte paths; abstract IPC works.
The retry exposes existing ninja/nvcc and uses a job-unique Linux abstract
namespace. No package/source change or filesystem socket outside the task root.
