# Run an optional AISBench evaluator

This example accompanies the proposal in [issue #289](https://github.com/InferMatrixLab/InferRSI/issues/289). It runs the separately installed `ais_bench` CLI through InferRSI's existing external commands. The example targets AISBench tag `v3.1-20261013-master`, commit `5a63d936e40dd04addfcffb2401f84cd0e53bb46`. Its report readers cover one model, one dataset and a single generation per accuracy example. [AISBench source](https://github.com/AISBench/benchmark/tree/5a63d936e40dd04addfcffb2401f84cd0e53bb46) · [Adapter](../examples/aisbench_adapter.py)

## Freeze the comparison

Prepare AISBench in a separate environment on the client machine and start the baseline and candidate services. Use model and dataset configuration names discoverable by the installed AISBench CLI or under the target checkout’s `configs/` directory. Each invocation runs in an isolated directory, so use absolute paths for local model and dataset files referenced by those configs. Give each service its own model config pointing to its endpoint and verify the served model before measuring. Record in the campaign plan:

- The AISBench revision and executable, model and dataset config contents and hashes, dataset split, sample count, prompt and answer parser, generation settings, request rate, concurrency, retries, warmup and scoring policy.
- The model revision, served model alias, endpoint, actual engine checkout and loaded revision for each role. InferRSI changes the command's working directory with `--candidate-repo`. The campaign owner starts and identifies the two HTTP services.
- The approved reference accuracy and maximum permitted drop, both in percentage points. Before evaluating the candidate, save the reference JSON outside the trial directories and record its SHA-256 in the plan. The adapter verifies those bytes, the configured names/abbreviations and the expected sample coverage. The owner verifies the installed AISBench revision and the contents of the external configs.

This illustrative reference uses five samples, an 80-percent baseline and a tolerance of 0.5 percentage points. Replace them with the measured baseline, allowed drop and sample count from your frozen protocol.

```json
{
  "schema": "aisbench-accuracy-reference-v1",
  "model_config": "candidate_stream_chat",
  "dataset_config": "demo_gsm8k_gen_4_shot_cot_chat_prompt",
  "model_abbr": "vllm-api-stream-chat",
  "dataset_abbr": "demo_gsm8k",
  "expected_samples": 5,
  "accuracy": 80.0,
  "max_drop": 0.5
}
```

## Run the commands

The native commands below illustrate the two evaluator modes. Substitute the locally prepared model config names. AISBench `--mode all`, the default accuracy workflow, runs inference, evaluation and summarization. The performance switch belongs to the `ais_bench` child process. [AISBench accuracy CLI](https://ais-bench-benchmark.readthedocs.io/en/latest/base_tutorials/scenes_intro/accuracy_benchmark.html) · [AISBench performance CLI](https://ais-bench-benchmark.readthedocs.io/en/latest/base_tutorials/scenes_intro/performance_benchmark.html)

```bash
ais_bench --models candidate_stream_chat --datasets demo_gsm8k_gen_4_shot_cot_chat_prompt
ais_bench --models baseline_stream_chat --datasets demo_gsm8k_gen_4_shot_cot_chat_prompt --mode perf
```

For the InferRSI run, set `BASE_REPO` and `CANDIDATE_REPO` to the two engine checkouts, `AIS_BIN` to the absolute AISBench executable, `REF` to the frozen reference file, `REF_SHA` to its previously recorded SHA-256, and `MIN_GAIN` to the campaign's performance threshold. Run the example from the InferRSI checkout. The two service configs here use the same report abbreviation. Each trial has an independent output directory.

```bash
adapter="$PWD/examples/aisbench_adapter.py"
selection="--dataset-config demo_gsm8k_gen_4_shot_cot_chat_prompt --dataset-abbr demo_gsm8k --model-abbr vllm-api-stream-chat"
inferrsi run --mode config --repo "$BASE_REPO" --candidate-repo "$CANDIDATE_REPO" \
  --repo-type vllm --backend ascend --device-ids 0 --workload-id fixed-service-workload \
  --baseline-command "python '$adapter' perf --ais-bench '$AIS_BIN' --model-config baseline_stream_chat $selection" \
  --candidate-command "python '$adapter' perf --ais-bench '$AIS_BIN' --model-config candidate_stream_chat $selection" \
  --validation-command "python '$adapter' validate --ais-bench '$AIS_BIN' --model-config candidate_stream_chat $selection --reference '$REF' --reference-sha256 '$REF_SHA'" \
  --validation-inconclusive-exit-code 2 \
  --metric-key metrics.output_tokens_per_second --metric-unit token/s --direction maximize \
  --comparison-scope http_e2e --min-improvement-pct "$MIN_GAIN" --repetitions 3
```

InferRSI parses quoted command strings into argv. The adapter writes structured JSON to each trial's `INFERRSI_RESULT_PATH`. Shell redirection of AISBench's console table does not produce this metric file. For a standalone adapter invocation, pass an explicit fresh `--result` path.

## Read the evidence

Each adapter invocation creates an exclusive `aisbench/` work directory beside its result. It reads reports from the single timestamped run created by that invocation. In the tree below, `MODEL` and `DATA` are AISBench abbreviations, which can differ from the configuration names used on the CLI.

| Child | Fresh evidence under `aisbench/YYYYMMDD_HHMMSS/` | InferRSI result |
| --- | --- | --- |
| `perf` | `performances/MODEL/DATA.json` contains `Output Token Throughput.total` in `token/s` and request counts. | `metrics.output_tokens_per_second` is a positive number. Each A/B repetition needs a complete measurement. |
| `validate` | `results/MODEL/DATA.json` contains percentage `accuracy`. `predictions/MODEL/DATA.jsonl` must contain one successful string prediction for each expected ID, with the matching dataset abbreviation. | Compare the measured score with `accuracy - max_drop` from the frozen reference. Distinctly identify a regression or insufficient evidence. |

The result schema is `aisbench-adapter-v1`. Its `status`, `metrics` and `provenance` fields preserve the adapter outcome, metric values, child argv, run ID and report digest. The provenance field `report_schema_revision` names the adapter's supported AISBench source revision. The owner verifies the installed executable. A complete validation result includes the reference digest and the digest of the prediction JSONL with verified sample coverage.

Keep original reports and predictions under the campaign's data-handling policy. Prediction records can contain prompts and generated text. The measurement belongs to the tested endpoint, workload and configuration. [Pinned performance report writer](https://github.com/AISBench/benchmark/blob/5a63d936e40dd04addfcffb2401f84cd0e53bb46/ais_bench/benchmark/summarizers/default_perf.py) · [Pinned accuracy report reader and evaluator](https://github.com/AISBench/benchmark/blob/5a63d936e40dd04addfcffb2401f84cd0e53bb46/ais_bench/benchmark/tasks/openicl_eval.py)

| Accuracy evidence | Validation command | Quality gate |
| --- | --- | --- |
| Complete, score at or above the frozen floor | 0 | Satisfied |
| Complete, score below the frozen floor | 1 | Confirmed regression |
| Missing, malformed or incomplete evidence, or AISBench itself failed | 2 | `INCONCLUSIVE` with the explicit exit-code setting above |

A nonzero child status remains visible in the execution record. `--validation-inconclusive-exit-code 2` tells the quality gate how to interpret that validation status. Incomplete evidence takes precedence in the overall verdict. Once all evidence is complete, a performance threshold failure can make the run `FAIL` even if accuracy passes. Without the opt-in setting, any failed validation command retains its existing interpretation as a failed quality gate. [InferRSI experiment contract](quickstart.md#benchmark-result-contract)

For a CPU-only check, run `python -m pytest tests/test_aisbench_adapter.py` from an InferRSI development checkout. Its synthetic reports exercise a quality drop, an unchanged score and missing or malformed evidence, without starting an inference service or installing AISBench.
