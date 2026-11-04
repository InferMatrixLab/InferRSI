# Shared engineering benchmarks

The `benchmarks` commands check and measure an implementation against a versioned
task package. Packages define semantics, inputs, correctness rules and timing;
the existing Workbench runs paired comparisons and retains evidence. Agent
execution, knowledge selection and optimization search remain caller-owned.

| Task | Candidate entry point | Execution boundary |
| --- | --- | --- |
| [Ascend affine RMSNorm](../src/inferrsi/data/engineering_benchmarks/rmsnorm-npu/README.md) | `compute(x, weight, *, eps)` | Reviewed source on one caller-allocated NPU; no formal device sandbox |
| [CPU Softmax](../src/inferrsi/data/engineering_benchmarks/softmax-cpu/README.md) | `compute(x, *, eps)` | Reviewed NumPy source; a separate SkillEval artifact sandbox also supports this task |

The task READMEs retain source attribution, licenses and workload limits. To
optimize an implementation, copy the task's `baseline.py` to a separate
`implementation.py`. The packaged `candidate.py` is a reference control, not an
Agent-produced optimization. Keep task, oracle and baseline fixed while changing
the implementation. Review source before using the trusted worker: content
hashes detect drift, not malicious code.

## Run an NPU implementation

Discovery imports neither torch nor torch_npu. Execution requires the target's
compatible installed torch/torch_npu/CANN stack; InferRSI does not install or
replace that runtime. Enter a caller-managed single-NPU allocation before any
device execution. The worker requires one `ASCEND_RT_VISIBLE_DEVICES` entry,
uses logical device 0 and never falls back to CPU.

```bash
inferrsi benchmarks list
inferrsi benchmarks show rmsnorm-npu
inferrsi benchmarks check rmsnorm-npu --candidate <implementation.py> --output-dir <new-check-dir> --timeout-seconds <timeout>
inferrsi benchmarks compare rmsnorm-npu --candidate <implementation.py> --repo <checkout> --output-dir <new-run-dir> --repetitions <pairs> --max-minutes <budget> --min-improvement-pct <gain-gate>
```

RMSNorm uses contiguous 2D float32 inputs and nonuniform weights. Input and
weight generation, scalar double/math.fsum oracle computation and transfers
occur outside timing. The clock covers eager dispatch and completion
synchronization after an untimed pre-synchronization. It measures synchronized
eager-call latency, not pure kernel time. Shape, dtype, device, numerical values
and input/weight preservation are checked outside the timer for every call.

Profiling is optional and separate from measurement:

```bash
inferrsi benchmarks profile rmsnorm-npu --candidate <implementation.py> --output-dir <new-profile-dir> --timeout-seconds <timeout>
```

This retains real device events in `npu-trace.json` and a path-free kernel
summary, with no performance verdict. Distinguish verification copies from
compute kernels. Review raw traces for private paths/identifiers before sharing.

## Use the CPU software control

Install the development checkout with `pip install -e ".[dev,benchmarks]"`.
Discovery and planning do not import NumPy; CPU execution requires it.

```bash
inferrsi benchmarks show softmax-cpu
inferrsi benchmarks check softmax-cpu --candidate <implementation.py> --output-dir <new-check-dir> --timeout-seconds <timeout>
inferrsi benchmarks measure softmax-cpu --candidate <implementation.py> --output-dir <new-measure-dir> --timeout-seconds <timeout>
inferrsi benchmarks grade softmax-cpu --candidate <implementation.py> --output-dir <new-grade-dir> --timeout-seconds <timeout>
inferrsi benchmarks plan softmax-cpu --candidate <implementation.py> --repo <checkout> --output-dir <new-run-dir> --repetitions <pairs> --max-minutes <budget> --min-improvement-pct <gain-gate>
```

The Softmax contract reduces axis 1 and includes strided and boundary inputs.
The independent oracle uses scalar double precision and `math.fsum`. `check`
evaluates the base cases and the same varying-input sequence used by measurement.
Every timed input has distinct retained objects and bytes, so an earlier call
cannot prime an identity/content memo for a later sample. This public suite does
not prevent hostile implementations or establish held-out generalization.

Input generation, oracle evaluation, validation, startup and warmups are outside
timing; allocations inside `compute` are included. The score sums per-case
medians for the task's selected workloads. Inspect individual cases as well as
the aggregate. The zero-input case checks correctness but contributes no timing
score. CPU `profile` retains `profile.txt`, not a device timeline or speed score.

## Comparison and retained results

Replace `plan` with `compare` to execute through Workbench. `plan` prints a
RunSpec; `compare` constructs its own RunSpec rather than consuming a previously
printed one. Freeze the actual inputs and gates before candidate search using
the [acceptance procedure](contributing.md#acceptance-checklist). All placeholders
above come from that experiment, not repository defaults. Single-action output
directories must be new.

`TaskPackage` freezes task and grader identities. Commands also bind candidate
bytes and runtime fingerprints, checked before and after worker execution. The
Git checkout supplied by `--repo` identifies source context; task and candidate
files have additional hashes. Runtime fingerprints alone do not establish an
uncontended host, equivalent device/CANN installations or native dependencies.

Results retain the planned `input_sequence`, actual `executed_calls` and sample
input hashes. Failed candidates may execute only a prefix. Wrong outputs produce
no usable performance metric. Preserve unsuccessful trials and inspect
`execution.json`, per-trial `result.json`, `evaluation.json`, `status.json` and
source-integrity records.

`compare` returns `run_dir` and the retained status. Its exit codes are PASS = 0,
FAIL = 1 and INCONCLUSIVE = 2. A complete comparison missing its gain gate is
FAIL. A wrong candidate preventing measurement leaves the comparison
INCONCLUSIVE, while independent artifact correctness can be FAIL. Exceptions,
missing dependencies, drift and timeouts must not become successful comparisons.
Workbench statistics are descriptive; these results do not establish service
gains, statistical significance or Agent/knowledge efficacy.

`grade` returns artifact-correctness PASS/FAIL/INCONCLUSIVE with SkillEval's
`passed`/`assertions` structure. The lower-level
`benchmarks.skill_verifier.task_descriptor` binds an already reviewed artifact
for `skill_evaluation.run_trial`; its answer supplies `candidate_sha256`.
For actual CPU file handoff through `tools.skill_eval_compare`, see
[engineering task artifacts](engineering-task-artifacts.md). That formal adapter
checks correctness only and rejects NPU tasks. It does not automatically send
generated NPU code to this trusted worker. Provider generation mode and the
offline harness-improvement controller do not yet support this task adapter.

## Qualify the tools with authored controls

The NPU utility exercises correct, wrong, replay, same-code and reference
implementations through the worker and Workbench:

```bash
python -m tools.npu_benchmark_validate --repo <checkout> --output-dir <new-evidence-dir> --repetitions <pairs> --min-improvement-pct <gain-gate> --max-aa-difference-pct <noise-gate> --max-minutes <comparison-budget> --timeout-seconds <action-timeout>
```

It freezes policy and implementation identities before execution, retains all
samples and checks actual device/CANN/runtime consistency. The utility includes
profiling as a tool control; this does not make profiling mandatory for ordinary
optimization. `--timeout-seconds` caps its standalone actions, while paired
Workbench trials use the comparison deadline. It does not enforce a separate
whole-utility budget or the standalone cap on each paired trial. Establish the
required outer allocation/process deadlines and verify cleanup before relying
on those budget boundaries.

The CPU integration utility dynamically selects the packaged NumPy task:

```bash
python -m tools.engineering_benchmark_validate --repo <checkout> --output-dir <new-evidence-dir> --repetitions <pairs>
```

It retains profiles and AB/BA samples and runs the existing SkillEval trial path
with correct and wrong authored controls. Neither utility generates Agent
candidates. Their reports separate software controls from campaign acceptance.
Preserve experiment plans and original results with their tested revisions using
the [evidence conventions](contributing.md#evidence-and-claims); review/redact
copies of raw logs before publication. A successful control run does not finish
the Agent-to-NPU handoff or prove an optimization benefit.
