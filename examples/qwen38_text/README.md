# Qwen3.8 text correctness bootstrap

Parent [Issue #53](https://github.com/InferMatrixLab/InferRSI/issues/53) and
[acceptance #54](https://github.com/InferMatrixLab/InferRSI/issues/54) own the scope,
resource budget, pins, freeze and numerical gates. Preparation evidence is under
[`evidence/qwen38-h20-text-phase1`](../../evidence/qwen38-h20-text-phase1/plan/README.md).

This example compares **Transformers full-prefix recomputation with Transformers
incremental cache**. It validates a bounded raw-text teacher-forcing reference
self-check. It does **not** implement a nano-vllm Qwen3.8 engine, validate general
model/task quality, or establish a service speedup. Engine adaptation remains a
separate milestone. No engine candidate may inherit this reference check's PASS.

An explicit `native_text_smoke` scope additionally compares the trusted
Transformers full-prefix reference with the caller's native nano-vllm-derived
engine. It qualifies only the supplied raw-text teacher-forcing workload,
including declared replay cases. It is not whole-engine acceptance or a claim
about chat, batching, generation lifecycle, broad quality or performance.

## Contract

- `intake.py` verifies local model files against an immutable upstream revision
  and produces a complete SHA256 manifest. It does not download weights. Run the
  byte scan under a CPU Slurm allocation, after the existing download completes.
- `trial.py` verifies that manifest against actual file bytes before each model
  load. It requires a single visible CUDA GPU of the exact requested SKU,
  BF16, a local checkpoint and a local tokenizer. It loads with remote code
  disabled and rejects missing/mismatched required parameters.
  Hub kernels are explicitly disabled. This reference requires `fla` and
  `causal_conv1d` to be absent, fixes full attention to eager, and records that
  policy in every result. Eager attention alone does not disable optional
  DeltaNet kernels in Transformers. An optimized kernel path needs its own
  explicit candidate protocol and fresh reference qualification.
- Both trial modes produce full-vocabulary FP32 logits at every requested
  teacher-forced position. No sampled token is fed back; no token-rate metric is
  presented. Each request starts with fresh cache state.
- `validate.py` checks complete per-trial/case coverage, identity, dtype/device,
  token sequences, logit shape/digest/finiteness, numerical gates and explicit
  replay cases. Exit 0 means scoped acceptance, 1 a completed numerical rejection,
  2 incomplete or invalid evidence. Gate values have no defaults.
- `launch.py` uses the common InferRSI AB/BA runner with objective `correctness`.
  It binds source snapshots to the actual control checkout. The `nano_vllm`
  descriptor is the future integration route, not an assertion that nano-vllm
  executed: trial implementation and qualification scope name Transformers.
- `slurm-run.sh` sets all writable caches/tmp inside the caller's authorized task
  root and preserves Slurm device visibility. It refuses paths escaping that root.
  Model execution requires an active allocation. `--dry-run` writes no campaign
  freeze and is not authorization or qualification.

The raw-text smoke does not test chat templates, stochastic sampling, EOS
stopping, batching, preemption, prefix reuse, MTP, vision or context limits.
Explicitly qualify these before claiming them for the dedicated engine.

## Prepare and freeze

Use a dedicated uv environment inside the authorized remote task root. Runtime
requirements are CUDA PyTorch, a Transformers version implementing
`Qwen3_5ForConditionalGeneration`, Accelerate, NumPy, Safetensors and tokenizer
requirements, plus this InferRSI checkout. Record exact versions/import origins,
freeze a dependency lock and register the environment in the H20 skill's registry.
Do not treat a checkpoint's `transformers_version` string as an installed runtime.

The existing model downloader must finish first. Its exit status alone is not a
substitute for intake verification. Intake expects a model directory with
`config.json`, `tokenizer_config.json`, `tokenizer.json`,
`model.safetensors.index.json` and every indexed shard. Present optional tokenizer
and generation metadata are verified too.

Example intake inside an authorized **CPU** allocation, with all paths supplied
at runtime and `TMPDIR`/cache variables already rooted in the task workspace:

```bash
"$TASK_PYTHON" -m examples.qwen38_text.intake \
  --model-path "$MODEL_PATH" --model-revision "$MODEL_REVISION" \
  --output "$MANIFEST"
```

Before GPU execution, freeze the model manifest, workload, trial/validator source
hashes, baseline/candidate/control commits, dependency lock, GPU SKU, gates and
budget in acceptance #54 and the campaign's `plan/` / `validator/`. Copy the
validator files into the frozen bundle; do not overwrite historical freezes.

## Execute

Set runtime variables privately; placeholder paths below are templates:

```bash
export TASK_ROOT='<AUTHORIZED_REMOTE_TASK_ROOT>'
export CONTROL_REPO='<FROZEN_CONTROL_CHECKOUT>'
export TASK_PYTHON='<REGISTERED_ENV>/bin/python'
MODEL_PATH='<LOCAL_BF16_MODEL>'
MODEL_REVISION='<PINNED_MODEL_REVISION>'
MANIFEST='<FROZEN_MANIFEST_JSON>'
WORKLOAD='<FROZEN_WORKLOAD_JSON>'
DEVICE_MODEL='<EXACT_ALLOCATED_GPU_NAME>'
```

Set `REPETITIONS`, `MAX_MINUTES`, `MAX_NRMSE`, `MIN_TOP1`, `RMS_FLOOR`,
`CPU_COUNT`, `HOST_MEMORY` and `JOB_TIME` from the frozen acceptance plan. Submit
with explicit resources and output inside the authorized root:

```bash
mkdir -p "$TASK_ROOT/artifacts/qwen38-phase1"
sbatch --partition=h20 --nodes=1 --ntasks=1 --gres=gpu:1 \
  --cpus-per-task="$CPU_COUNT" --mem="$HOST_MEMORY" --time="$JOB_TIME" \
  --chdir="$CONTROL_REPO" \
  --output="$TASK_ROOT/artifacts/qwen38-phase1/slurm-%j.log" \
  "$CONTROL_REPO/examples/qwen38_text/slurm-run.sh" \
  --repo "$CONTROL_REPO" --model-path "$MODEL_PATH" \
  --model-revision "$MODEL_REVISION" --manifest "$MANIFEST" \
  --workload "$WORKLOAD" --device-model "$DEVICE_MODEL" \
  --max-nrmse "$MAX_NRMSE" --min-top1 "$MIN_TOP1" --rms-floor "$RMS_FLOOR" \
  --repetitions "$REPETITIONS" --max-minutes "$MAX_MINUTES" \
  --output-dir "$TASK_ROOT/artifacts/qwen38-phase1/runs"
```

`sbatch` accepts the script directly; its contents set shell options and execute
the registered interpreter. Do not reuse unrelated allocations. Retain the job ID
and confirm release. A missing queue entry does not prove success: inspect the
job log, `status.json`, `evaluation.json`, validation result, all trial artifacts
and `report.html`. Missing or interrupted evidence remains INCONCLUSIVE.

Raw InferRSI output includes operational paths and hardware identifiers. Keep it
in private task storage. Review and redact a separate copy before publication;
retain source/manifest hashes, failed attempts and verification limitations.

## Native candidate execution

After independently preparing and reviewing the native engine checkout, pass
`--qualification-scope native_text_smoke --candidate-repo '<ENGINE_CHECKOUT>'`
to the same launcher/Slurm script. Keep `--repo` pointed at the actual control
checkout. Use a new output location and freeze both source identities plus the
same explicitly supplied model/workload/gate arguments before the run.

The common InferRSI runner snapshots both checkouts and executes each side in
its own checkout. `native_trial.py` imports `load_checkpoint` and `RequestRunner`
from the requested engine; an already imported foreign package or an origin
escaping the checkout is rejected. The model class must originate in
`nanovllm.qwen38.model`. The adapter uses Transformers only for tokenizer
handling, and exports native teacher-forced logits through the same artifact
writer as the reference. Native execution is eager Torch with one GPU and no
tensor parallelism or CUDA Graphs.

Native records retain control/engine source identities, imported-file hashes,
checkpoint loading coverage and the distinct implementation role. Validation
checks these against the common runner's locked and per-trial source snapshots,
checks execution directories, and reuses full-vocabulary FP32, input-token,
GPU/runtime, numerical-gate and replay checks. A cached Transformers trace
cannot substitute for the native candidate. A native smoke PASS cannot be
relabelled as reference self-check or promoted to full engine acceptance.

These operational records contain private paths through the common runner;
keep originals in authorized private storage and publish reviewed redacted
copies only. Source-file verification during validation needs both checkouts
at the frozen revisions; absent or changed sources leave evidence incomplete.

## CPU checks

With the development environment and NumPy installed:

```bash
python -m pytest tests/test_qwen38_trial.py tests/test_qwen38_validation.py \
  tests/test_qwen38_intake.py tests/test_qwen38_launch.py
ruff check src tests examples/qwen38_text
```

These tests use synthetic inputs and mock runtime objects, not model evidence.
No GPU work or model download is added to the default CI lanes.

Native source evidence requires JSON objects for provenance, import records,
loading reports and source snapshots. Every declared, locked and before/after
identity must contain a lowercase hexadecimal Git object ID (40 or 64 digits)
and a 64-digit SHA-256 snapshot hash; imported-file hashes must be SHA-256.
Checkout paths and executed working directories must be nonempty strings.
Missing or malformed evidence writes an INCONCLUSIVE result and exits 2;
complete evidence rejected by the numerical gates still writes FAIL and exits 1.
