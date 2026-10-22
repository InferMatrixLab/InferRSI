# Baseline long-context probe: retained observer rejection

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**Campaign INCONCLUSIVE; original job remains FAILED1:0.**

The infrastructure retry1961 loaded the official FP8 model and executed all five
requests:32/8 warmup,32/8 framing,8192/32,65536/8,131072/8. Every returned token,
input echo, usage count, terminal reason and unique final DONE was independently
checked against the raw SSE. The last request has8 output tokens in7 choices,
with token counts[1,2,1,1,1,1,1], and6 ITLs. The retained observer rejected its
extra assumption that each choice contains exactly one token; earlier four
requests satisfied that assumption. No original valid flag or verdict is edited.

Pinned upstream RequestOutputCollector explicitly aggregates DELTA outputs when
the producer gets ahead of the consumer. The official HTTP client timestamps
choices and derives TPOT from usage token count, independently of choice count.
Thus the observed aggregation is supported default behavior, not evidence of
missing tokens or invalid model execution. A future observer must preserve
this timing semantics, check timing-event count against choices, and separately
check all token IDs against usage. It must not infer one ITL per generated token.
The diagnosis does not activate a new acceptance validator or rescore the job.

## Descriptive feasibility and cost observations

No paired candidate, only one fixed input per length and short outputs. These
numbers estimate workload cost; they are not the2048-output matrix or parity.

| Input / output tokens | TTFT (s) | HTTP latency (s) | Original observer |
| --- | ---: | ---: | --- |
| 8192 /32 | 1.690560 | 2.015406 | valid |
| 65536 /8 | 18.649625 | 18.718206 | valid |
| 131072 /8 | 49.592377 | 49.654687 | rejected: aggregated choice |

Startup455.555469s; full allocation537s. Cumulative readiness1509/7200 GPU
seconds (0.419167 GPU-hours), remaining5691s. Initial147 seconds are separate.
All allocations released. Server returned0 and observer did not force-kill;
its group was empty. However, vLLM's default abort teardown (timeout0) did
force-kill its EngineCore and logged a semaphore cleanup warning. Do not call
this an entirely graceful shutdown. All original private startup/SSE/client
records are retained; selected diagnostics contain no private endpoints.

Startup logs selected FlashInfer GDN prefill, FlashAttention3, norm_quant and
act_quant fusions, and built the fp8_blockscale_gemm_90 JIT module. This confirms
actual initialization/warmup activity; no per-request kernel trace or complete
FP8 branch accounting is claimed. Runtime flags leave kernel/Graph/compile
choices automatic. OMP_NUM_THREADS=8 was explicitly inherited from the wrapper,
and vLLM warned about CPU spin contention: this probe is not a certified default
CPU-thread performance baseline. Future formal settings must bind this choice
prospectively, preferably retaining vLLM's normal single-thread serving policy.

The prior1959 failure and CPU1960 fix remain separate. No engine optimization or
dependency change occurred. No shortened request becomes final quality evidence.

Sources: pinned upstream
[DELTA collector](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/v1/engine/output_processor.py)
and
[official request client](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/benchmarks/lib/endpoint_request_func.py).

KnowledgeStore candidate `case.qwen38-vllm032-infrastructure-readiness-cand`,
revision `sha256:760988acd4e5f2485d9fc66fe653c50ae140389e513dac300ad170494188e5e0`,
retains1959/1960/1961 and prior snapshot with verified readback.
