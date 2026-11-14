# Verification contract

## Freeze a claim-sized RunSpec

Record repository/source SHA and binary bytes; family; exact checkpoint, quant
recipe and tensor/file manifest; tokenizer/template and thinking mode; CUDA/HIP,
toolkit/driver and device architectures; ordered devices and effective TP groups;
context/KV layout; CPU thread semantics and affinity; RAM/VRAM/SSD budgets,
placement/profile state; draft artifact, mode and policy; parallelism; workload
and input hashes; sampling, seed and penalties; warmup and timing definitions;
validator and issue-owned gates. A matching source string or same-size weight
file is not byte authentication. Preserve baseline and failed controls.

Use a concrete falsifier: e.g. a greedy continuation diverges after a rejected
window under otherwise identical arithmetic; a completed operator comparison
violates its frozen tolerance; or a complete service comparison misses its
frozen SLO/gain/quality requirement. An unavailable backend, failed setup or
interrupted comparison instead leaves the dependent claim `INCONCLUSIVE`.

## Callsite and exactness boundaries

| Route | What the inspected implementation says | What it does not prove |
| --- | --- | --- |
| `spec::Controller` | Chooses none/lookup/MTP from acceptance EMAs and a cost model; only test callers were found | Production GLM control, measured speed, GPU execution |
| `spec::DraftPolicy` | Learns round cost by window and lookup acceptance by match bucket; current cap is 16 rows | Any universal prior, optimality, native correctness from a simulation |
| DeepSeek lookup | Production caller compares lookup against DSpark/plain rounds; alongside DSpark requires first-draft agreement and non-sampled drafts | That sampled-draft-dependent lookup selection is supported; same-seed equivalence to a different algorithm |
| One-GPU GLM MTP | `mtp_choose` is separate; window picks use the target sampler's row counter, retained prefix commits and NextN repair | CPU controller/policy tests qualify this route |
| GLM parallel MTP | Separate `mtpw_*` row windows, per-sequence backup/replay and scheduler acceptance | The one-GPU gate implies all parallel speculation is absent |
| MiniMax DSpark | Deterministic proposal acceptance with target probability, or optional sampled proposal `p/q` acceptance and residual draw | Distribution preservation means identical random-number consumption or same-seed output with drafting disabled |

Current `DraftPolicy` source priors include extrapolated cost shape past eight
rows; its source margin, `Controller`'s minimum gain and calibrator margins are
implementation choices, not InferRSI acceptance thresholds. The generic
`generate.cpp` DraftPolicy routes occur after `--glm-pack` dispatch returns to
the GLM-specific runner. DeepSeek's current caller is independent of those
generic routes. Do not infer applicability from shared class names or comments.

### GLM retained-state checklist

The one-GPU gate disables this particular path when no-spec/no-MTP is present,
the draft cap is zero, configured sequences exceed one, or DFlash is selected.
Explicit MTP-decode enablement still requires one model part; without override,
the HIP `gfx115` prefix is selected, while CUDA does not default-enable it.
This is route selection, not proof a requested artifact fits or performs well.

For a window of `T = 1 + drafts` rows, retained rows are **not** simply the number
of accepted drafts: a mismatch row still emits the target's replacement; full
acceptance can emit a bonus target token. Stop/forced-token handling can truncate
earlier. Verify the sampler counter advances only for emitted target picks and
that limits prevent unconsumable drafts.

When fewer than `T` rows survive, GLM restores/replays retained KDA convolution
and recurrent inputs from the pre-window backup, then sets position to
`window_start + retained_rows`. DSA speculative rows are left to be overwritten
before later reads; completed-pool visibility is part of that invariant. NextN
cache entries for retained rows are repaired with **trunk** hidden states, not
left as the draft block's provisional hidden states. Check subsequent tokens,
not only the output of the rejecting window. Drain/check asynchronous launch and
route errors before attributing correctness or speed.

The separate parallel MTP path defaults off (`MULTI_MTP` zero). Its scheduler
requires prepared rows, a loaded NextN block and no DFlash; split-row eligibility
also matters. It bounds group rows and performs per-conversation retained-state
replay across parts. Check two requests with different retained lengths, a stop,
forced thinking boundary and cancellation; one request's backup/cache/counter
must not stand in for another's.

MiniMax's current parallel runner explicitly decodes without DSpark. It warns
that concurrent CPU-lane assignment can change rounding compared with GPU-only
work. A request-local nonzero seed fixes that runner's RNG initialization, not
equivalence across all kernels, tier plans or speculative algorithms.

## Evidence ladder and native map

| Evidence | Legitimate scope | Still required for a broader claim |
| --- | --- | --- |
| GLM memory-policy host test | Budget/reserve/commit arithmetic on supplied synthetic numbers | Actual device allocation, pressure, driver behavior and model liveness |
| Controller simulation | Expected-token/cost decisions and rejection learning | Actual production caller, kernels, model and measured cost |
| Draft-policy simulation | Match buckets, simulated window cost, probes and caps | DeepSeek/other native verify behavior and retained state |
| Conversation-victim host test | Pure root/leaf retention-index selection | Snapshot bytes, restore correctness, prefix identity and service isolation |
| GPU synthetic parity | Only the shapes, formats and kernels actually launched | Matched model outputs, speculative state and service workload |
| Actual-pack graph/direct test | Single-device logits, ordinary snapshot/reset controls under its prerequisites | MTP: that test explicitly requires MTP absent; mixed CPU/GPU steps only check finite/liveness |
| Quality evaluator | Its frozen checkpoint/reference and scored positions/tasks | General models, untested quants, long-context or modality claims |
| Warmed engine benchmark | Its actual engine timing/workload | End-to-end HTTP TTFT, concurrent throughput/SLO, stability and quality |

The four selected CPU slices are intentionally narrow. No CPU substitute fully
qualifies native CUDA/HIP kernels, GPU allocations, GLM rollback, DSpark/DFlash,
physical TP/splits, multimodal execution or full-model quality. Community Qwen
dispatch/format/guard coverage is shallow; its native kernels/model behavior also
remain unverified rather than inheriting the other families' evidence.

Read execution text and work counts, not just exit codes: the inspected GLM
rows-kernel test returns zero when no GPU exists; the rows-attention test can
return zero when its tensor-core route is unavailable. These are skips, not
launch evidence. This source checkout lacks `tests/CMakeLists.txt`, so the
top-level automatic test-default predicate is false; do not interpret a default
build with no selected tests as a passed suite. CMake's declared engine version
also differs from `VERSION`; retain exact source and binary provenance.

## Calibration and fair measurement

- **GLM CPU/PCIe/read-chunk calibration:** one engine, per-request tuning,
  uncounted warmup, medians of successive three-prompt groups. Groups are fresh
  only until the finite pool wraps. Confirm sweep choice against engine defaults
  interleaved, then compare any existing incumbent **combination** interleaved;
  isolated knobs can miss a useful interaction. Work on a usage-file copy and
  strip learned-profile/routing-trace writes. This measures decode, not prefill.
- **GLM DFlash calibration:** separate starts, other first then DFlash; matched
  document/questions, seeds and sampling; uncounted warmup then total tokens over
  total decode time. It is sequential, not ABBA. Drafter memory changes expert
  capacity and costs; the no-DFlash side is not guaranteed to use MTP on every
  machine. Preserve too-short or failed-side rejection rather than ranking it.
- **DeepSeek/MiniMax DSpark calibration:** likewise without-drafter then with,
  sustained decode and profile copies. Removing the drafter also frees memory;
  this is a complete configuration comparison, not isolated kernel speed.
- **DeepSeek TP/CPU calibration:** separate starts, own baseline first, long-
  prompt floor and conditional confirmation. Rank **effective** grouping
  telemetry, not requested `--tp`: duplicate fallbacks are not distinct trials,
  unknown groups preserve the incumbent rather than guessing. MiniMax adapts
  this with layer split as its own baseline and different eligible group widths.
- **MiniMax prefill calibration:** chunk/GEMM tuning can consume expert-pool
  memory. Its wide-chunk check compares decode against another start and can
  write a persistent tune record keyed by GPU/runtime/driver. Prefill improvement
  alone does not establish decode improvement or a service win.

Source-specific sample counts, margins, long-prompt floors and search stopping
rules describe these algorithms only. Freeze independent issue-specific bars
before a campaign; do not turn source heuristics into global skill defaults.

The current standard benchmark uses each family's own prompt format, handles
request IDs when the engine advertises multi mode, performs one warmup answer,
then three greedy thinking-off answers of up to 256 tokens. Its arithmetic
decode mean normally excludes answers shorter than the source's minimum, but
uses all when every answer is short. Preserve that membership, actual lengths
and raw times: a mean of per-answer rates is not a token-weighted rate. Its
prefill uses selected documentation tokens and different openings. It launches
an engine directly, writes log/report files, and is not an HTTP load test;
multi-compatible protocol does not mean concurrent load was measured.

## Quality and negative evidence

The author-reported GLM Maya-S report compares one quantized recipe against FP8
on eight held-out sequences, 7,672 scored positions, top-64-plus-rest KL. Its
aggregate same-top-token rate is 83.3%, perplexity 4.19 versus FP8's 3.51, and
five-task mean accuracy 80.8 versus 82.5 (400 matched questions per task).
The reported 97.9% task-score recovery is neither token identity nor losslessness.
Fourteen long answers and a few retrieval contexts cannot certify universal
loop freedom or a maximum context. Do not transfer GLM figures to another
family, quant, optional weight edit or modality.

The historical October 6 report records silent DSA launch failure and a
duplicate expert-table edit race later fixed, plus prefetch approaches that
were not faster on that host. Retain these as historical author observations,
not current-head reproduced bugs or gains. They motivate launch-error checks,
tier-state controls and negative-result retention. Changing available RAM can
change expert staging and prefill reduction order; keep that control frozen.

## Offline record contract

`summarize_decode_records.py` is an original standalone descriptive reducer,
not a parser/importer of source-runner reports. Normalize caller-owned records
explicitly and retain their originals separately. No input command is executed.

Exact top-level fields: `schema_version` integer 1, `source_commit` lowercase
40-hex, `family` one of `glm`, `ds4`, `mm3`, `qwen`, `metric` exactly
`engine-decode`, `controls_sha256` lowercase 64-hex, and nonempty `samples`.
The controls digest is supplied metadata; the helper never reads or hashes the
claimed controls. One input describes one family, one source and one metric.

Each sample has exactly these fields:

| Field | Allowed value |
| --- | --- |
| `variant` | `baseline` or `candidate` |
| `phase` | `warmup` or `measured` |
| `execution` | `completed`, `skipped`, `failed`, or `blocked` |
| `tokens` | Positive integer for completed samples; otherwise null |
| `decode_ms` | Positive finite number for completed samples; otherwise null |
| `drafts_offered`, `drafts_accepted` | Nonnegative integers with accepted ≤ offered for completed samples; otherwise null |

For example, this deliberately synthetic input is valid schema, not a native
receipt. Supply its all-zero source identifier to the helper only when auditing
this example; replace identifiers with the caller's declared provenance for real
records, without claiming that the helper authenticated it.

```json
{
  "schema_version": 1,
  "source_commit": "0000000000000000000000000000000000000000",
  "family": "glm",
  "metric": "engine-decode",
  "controls_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "samples": [
    {"variant": "baseline", "phase": "measured", "execution": "completed",
     "tokens": 10, "decode_ms": 1000, "drafts_offered": 0, "drafts_accepted": 0},
    {"variant": "candidate", "phase": "measured", "execution": "blocked",
     "tokens": null, "decode_ms": null, "drafts_offered": null, "drafts_accepted": null}
  ]
}
```

Booleans are not numbers. Duplicate keys, unknown fields, nonfinite values and
malformed identities are errors. CLI input is limited to 8 MiB and 10,000
samples; these are defensive parser bounds, not acceptance gates. Partial
measurements from failed commands stay in original records; do not relabel them
completed to make this normalization accept them.

The JSON output counts every execution/phase, describes completed measured
samples per variant, and computes token-weighted decode rate, median per-sample
rate and draft acceptance fraction when denominators exist. An optional
candidate/baseline rate change describes **only that completed subset**. Missing
variants or failed/skipped/blocked work remain visible. No automatic winner,
numeric gate, model quality, native authenticity or campaign verdict is emitted.
Even entirely fabricated internally consistent records can be reduced.

## Source provenance

All locations below refer to `mw00/project-maya` at
`249f9a87d1a9d72bec2b684d704b0aa9296b1c9c`; they identify the inspected evidence,
not runtime dependencies or commands to run:

- `include/strata/spec/{controller,draft_policy}.hpp` and corresponding source/
  tests; `src/ds4/ds4_main.cpp` 236–340; `src/program/generate.cpp` 4535–4582.
- `src/core/glm_mtp.cu` 1–24,54–96,452–537,647–765;
  `glm_window.cu` 1–14,1742–1867; `glm_mtp_rows.cu`
  1–33,91–119,242–249,464–560; `generate.cpp` 2316–2342,2650–2709.
- `src/mm3/mm3_main.cpp` 455–626,654–669,1033–1042;
  `src/mm3/mm3_sample.hpp` 113–158.
- `tools/calibrate_glm.py` 146–354,384–404; `calibrate_draft.py` 1–25,104–175;
  `calibrate_ds4.py` 1–20,97–122; `calibrate_ds4_tp.py` 187–327;
  `tools/mm3/calibrate.py` 1–73; `calibrate_mm3_prefill.py` 96–155.
- `maya.py` 3865–4033; `tools/test_bench.py` 82–115;
  `bench/results/MAYA-S.md` 1–57; `bench/results/2026-10-06-glm-spec/README.md`
  1–67; `tools/maya_quant/kl_eval.py` 1–70.
- Four selected CPU test bodies and their local policy headers;
  `tests/glm_rows_kernels_test.cu` 298–314;
  `tests/glm_rows_attn_test.cu` 548–555; `tests/glm_pack_graph_test.cpp` 1–90;
  `CMakeLists.txt` 11–20,73–78,1014–1029,1384–1390.
