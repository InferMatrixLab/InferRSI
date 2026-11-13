# Commands and measurements

The following are source-checked Bash command templates, not executed serving results and not recommended universal sizes. The target environment must contain a compatible installed vLLM/backend and an approved model. Inspect help on its actual revision first. `MODEL_PATH` is a placeholder; model access/tokenizer behavior must be resolved before execution. Avoid using a public endpoint for an unapproved load test.

```bash
# Inspect the actual target environment; no model launch here.
git rev-parse HEAD
python -c "from importlib.metadata import version; print(version('vllm'))"
vllm serve --help=all
vllm bench serve --help
```

```bash
# Illustrative baseline only. Replace MODEL_PATH with an approved local model.
vllm serve MODEL_PATH --host 127.0.0.1 --port 8000 \
  --max-model-len 4096 --max-num-batched-tokens 2048 --max-num-seqs 32 \
  --tensor-parallel-size 1 --enable-prefix-caching
```

```bash
# Illustrative random-token completion workload against that local server.
vllm bench serve --backend openai --model MODEL_PATH \
  --dataset-name random --random-input-len 512 --random-output-len 128 \
  --num-prompts 100 --request-rate 2 --save-result --result-dir results/baseline
```


Serve flags map to EngineArgs/config fields; host/port are generated from FrontendArgs; benchmark flags are registered in `serve.py` and the dataset parser. This preview checks option presence statically, not the imported CLI parser or full runtime compatibility. The backend `openai` follows the completion workload in this template; a chat workload needs the matching backend/endpoint/template and a separate representative corpus. A random-token smoke is not a production workload or quality test. [serve_flags](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/engine/arg_utils.py#L1708-L1750) [config_flags](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/engine/arg_utils.py#L1838-L1871) [frontend_flags](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/entrypoints/launchers/cli_args.py#L254-L286) [bench_flags](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/benchmarks/serve.py#L1590-L1667) [dataset](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/benchmarks/datasets/datasets.py#L1584-L1612) [lengths](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/benchmarks/datasets/datasets.py#L1885-L1903)

The default benchmark request rate is infinity, which sends all requests at time zero. Explicitly select a bounded offered rate for service SLO experiments, then sweep it around the saturation point. Keep rate, length distribution, generated-token settings and concurrency accounting in each result. Save raw JSON and errors; successful throughput without failures/admission rejection counts is incomplete. [bench_rate](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/benchmarks/serve.py#L1697-L1772)

## Observation contract

| Record | Meaning / comparison constraint |
|---|---|
| Full command, config, source/package/model/tokenizer revisions | Reproduce selection and prevent default drift |
| Hardware, topology, interconnect, runtime libraries | Explain compute/memory/communication differences |
| Input/output lengths and prompt/tokenization identity | Control work amount and cache eligibility |
| Offered request rate, concurrency, arrival distribution | Distinguish idle latency, saturation and burst behavior |
| Successful output tokens/s and requests/s; failure/rejection counts | Measure useful work rather than silently dropping requests |
| TTFT p50/p95/p99; queue/prefill components where available | Separate admission/queueing from model work |
| ITL and TPOT distribution with exact definitions | ITL is individual token intervals; per-request average TPOT can hide stalls |
| End-to-end latency and quality/equivalence checks | Prevent a faster but semantically different result |
| KV usage, prefix queries/hits, preemptions, peak device memory | Diagnose residency, reuse and recompute pressure |
| Warmup/compile/startup cost and warm steady-state repeats | Avoid mixing cold initialization with steady state |

`vllm:kv_cache_usage_perc`, prefix queries/hits, preemption and latency instruments are in the metric logger. Inspect labels/units on the actual endpoint and version before writing queries. In particular, a metric name ending in `_perc` must not replace checking the emitted gauge value's scale; do not combine histograms from different workloads without labeling. [metrics_cache](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/metrics/loggers.py#L619-L679) [metrics_latency](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/metrics/loggers.py#L930-L979)

## Scope of this preview's validation

Native metadata test `tests/test_zentorch_version_pin.py` was reviewed and attempted with pytest's repository conftest/plugin autoload disabled. Collection stopped because the local Python lacks `regex`; no source setup or dependency installation was performed. Torch is also absent, so engine/CLI/native GPU tests were not runnable here. AST parsing and source option checks are useful narrower evidence, not inference validation. The report outside the skill tree records exact commands and results. For implementation test selection, read [change validation](../../extend-validate/references/change-boundaries-and-validation.md).
