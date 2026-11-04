# Shared engineering benchmarks

The `benchmarks` command exposes versioned task packages for Workbench and
offline artifact evaluation. The current device pilot is **Ascend affine
RMSNorm**, with a trusted NPU worker, independent scalar CPU oracle, synchronized
eager-call timing and separate device profiling. Existing CPU tasks remain
software controls. Packages own semantics, workload, oracle and metric;
consumers own comparison conditions. Search policy and agent execution remain
separate.

| Adapter | Task and submission | Execution boundary |
| --- | --- | --- |
| `torch-npu-rmsnorm-v1` | `rmsnorm-npu`; `compute(x, weight, *, eps)` | Reviewed source on one caller-allocated NPU; no formal device sandbox |
| `numpy-axis1-v2` | `softmax-cpu`, `rmsnorm-cpu`; `compute(x, *, eps)` | Trusted CPU worker; formal SkillEval also has a separate NumPy artifact sandbox |

## Run the NPU pilot

Discovery imports neither torch nor torch_npu. Execution requires the target's
compatible installed torch/torch_npu/CANN stack; this project does not install
or replace the device runtime. Enter an explicit single-NPU allocation before
executing any device command. The worker requires one visible device, uses its
logical index 0 and never falls back to CPU.

```bash
inferrsi benchmarks show rmsnorm-npu
inferrsi benchmarks check rmsnorm-npu --candidate <implementation.py> --output-dir <new-check-dir> --timeout-seconds <timeout>
inferrsi benchmarks profile rmsnorm-npu --candidate <implementation.py> --output-dir <new-profile-dir> --timeout-seconds <timeout>
inferrsi benchmarks compare rmsnorm-npu --candidate <implementation.py> --repo <checkout> --output-dir <new-run-dir> --repetitions <pairs> --max-minutes <budget> --min-improvement-pct <issue-gate>
```

The task is contiguous 2D float32 affine RMSNorm with nonuniform weights. Inputs,
weights, scalar double/math.fsum reference results and transfers are prepared
outside timing. The measured clock covers the eager call and completion
synchronization after an untimed pre-synchronization. Dispatch and synchronization
costs are included: this is **not pure kernel latency**. Every output is checked
outside the timer, including shape/dtype/device and input/weight preservation.

`profile` records real Ascend Hardware kernel events in `npu-trace.json`, separately
from latency sampling. Its local raw trace may contain private paths/identifiers;
review it before publication. The result includes a path-free kernel summary,
not a performance metric. Profiling includes verification copies, which must be
distinguished from compute kernels during diagnosis.

To qualify the path with correct, wrong, replay, same-code and fused-reference
controls through the existing Workbench:

```bash
python -m tools.npu_benchmark_validate --repo <checkout> --output-dir <new-evidence-dir> --repetitions <pairs> --min-improvement-pct <issue-gate> --max-aa-difference-pct <issue-noise-gate> --max-minutes <comparison-budget> --timeout-seconds <action-timeout>
```

The utility freezes policy and implementation identities before execution,
preserves every sample and checks actual device/CANN/runtime consistency across
actions, trials and final validation. The general runtime fingerprint binds
package versions and selected device IDs; it alone does not qualify device/CANN
equivalence or host contention. Qualification is an authored-control exercise,
not Agent/skill efficacy or service acceptance. See the [NPU plan and results](plans/issue-252/npu-pilot.md).

## Use the CPU regression tasks

Install with `pip install -e ".[dev,benchmarks]"`. Discovery and planning do not
import NumPy; execution requires it and never silently switches backend.

```bash
inferrsi benchmarks list
inferrsi benchmarks show softmax-cpu
inferrsi benchmarks check softmax-cpu --candidate /path/to/implementation.py --output-dir /path/to/check --timeout-seconds 30
inferrsi benchmarks profile softmax-cpu --candidate /path/to/implementation.py --output-dir /path/to/profile --timeout-seconds 30
inferrsi benchmarks measure softmax-cpu --candidate /path/to/implementation.py --output-dir /path/to/measurement --timeout-seconds 30
inferrsi benchmarks grade softmax-cpu --candidate /path/to/implementation.py --output-dir /path/to/grade --timeout-seconds 30
inferrsi benchmarks plan softmax-cpu --candidate /path/to/implementation.py --repo /path/to/git-checkout --output-dir /path/to/runs --repetitions 3 --max-minutes 2 --min-improvement-pct 0
```

Use `compare` instead of `plan` to execute the emitted RunSpec using existing
Workbench. Single-action output directories must be new. These are example
budgets, not campaign acceptance gates. The supplied Git checkout identifies
the source context; task and candidate files are additionally bound by hashes.

`compare` returns the retained `status.json` alongside `run_dir`. Its exit code
matches Workbench: PASS is 0, FAIL is 1, and INCONCLUSIVE is 2. A completed
comparison missing its gain gate is FAIL; an incorrect candidate that prevents
measurement leaves the comparison INCONCLUSIVE, even though artifact correctness
grading can independently report FAIL. Inspect the retained state and errors.

The candidate is a reviewed self-contained Python file with `compute(x, *, eps)`.
Use NumPy, math and local helpers. `load_task("softmax-cpu").root` locates its
baseline and example candidate. Copy `candidate.py` to `implementation.py` before
editing. The package and grader remain protected comparison inputs. This adapter
executes trusted source and is **not an untrusted-code sandbox**. Hash checks
detect drift, not malicious same-process code. Do not connect raw model output.

## CPU measurement and shared evidence

`TaskPackage` validates the schema/adapter/environment and freezes manifest,
package and grader identities. Commands bind candidate and runtime fingerprints.
The worker checks bindings before and after execution. Runtime captures Python,
NumPy version, OS and machine architecture; it does not prove an uncontended host
or a fully locked native dependency installation.

Finite float32 inputs include strided layouts. RMSNorm reduces axis 1, including
for four-dimensional arrays. Scalar double precision with math.fsum supplies the
independent oracle. Numerical tolerances, shapes, seeds, warmups and sample counts
are task-specific and fixed across both consumers.

`check` evaluates all six base cases plus the same varying-input sequence used
by measurement and profiling. `measure` checks first, times synchronous compute
calls, and verifies every invocation outside the timer. Inputs and references
are prepared in advance; all input objects stay alive and every timed input has
distinct bytes from precheck/warmup/other sampled inputs. This prevents an earlier
call from priming an identity/content memo for a later timed call. It does not
detect hostile code or public-suite overfitting.

The task's `measurement.case_ids` declares five varying workloads. The invariant
zero-input case remains a correctness case and contributes no timing score. Every
result retains the planned `input_sequence` and actual `executed_calls`; each
sample records its input hash. Invalid candidates may stop before the full
sequence, so planned inputs must not be described as completed execution.

Input generation, oracle, validation, startup and warmups are excluded; allocations
inside compute are included. The objective sums the five per-case medians for this
fixed suite, not a universal score. Inspect per-case regressions before adopting a
candidate. This protocol does not establish cold-start serving or statistical
resolution. The earlier `numpy-axis1-v1` repeated-input evidence remains historical;
its task/grader identities and six-case scores cannot be pooled with v2.

`profile` retains a separate CPU `profile.txt` with no performance metric/verdict.
It is not a device timeline. Hardware adapters need their own synchronization,
timing and qualification. Missing or failed execution never becomes qualification.

`grade` produces artifact-correctness PASS/FAIL/INCONCLUSIVE and SkillEval's
existing `passed`/`assertions` structure. `skill_verifier.task_descriptor` binds a
controller-reviewed retained artifact; `skill_verifier.py` plugs into the existing
`skill_evaluation.run_trial`. The answer supplies only `candidate_sha256`.
The shared oracle independently grades actual implementation behavior. This
offline handoff does not modify production engineering sandbox or paid execution.
Live artifact production and skill/search benefit need separate controlled runs.

For formal paired artifact evaluation, `tools.skill_eval_compare` supports
`engineering-benchmark-v1` for the CPU NumPy tasks only: freeze the common public task and two skill bundles,
retain each arm's actual `implementation.py`, and independently check its output
outside the artifact's Linux bubblewrap sandbox. Local stage/capture uses the
same controller. This adapter evaluates correctness only; it does not accept
child-reported timing, launch an unqualified default agent, or fall back to host
execution when the sandbox/NumPy runtime is unavailable. It is separate from the
trusted-source worker above. Formal loading uses canonical packaged resources,
independent of same-named cwd task folders; the trusted Workbench retains explicit
path loading. NPU tasks are explicitly rejected by the formal adapter until
device isolation is separately qualified. See [setup and handoff](plans/issue-252/formal-integration.md).

The offline harness-improvement controller and provider generation mode do not
yet support these tasks. See [the RSI integration audit](plans/issue-252/rsi-integration.md)
for decisions and remaining acceptance work.

Exceptions, missing dependencies, drift and timeouts leave incomplete evidence.
Wrong results emit no usable performance metric. Workbench statistics remain
descriptive; a local verdict is not service gain or campaign acceptance.

## Reproduce the historical CPU integration

```bash
python tools/engineering_benchmark_validate.py --repo /path/to/checkout --output-dir /path/to/new-validation --repetitions 3
```

The tool freezes copied tasks and candidate identities, executes both CPU tasks,
retains profiles and AB/BA samples, and runs the actual SkillEval trial path with
correct and deliberately wrong **authored controls**. No model is called.
`summary.json` separates integration checks from campaign acceptance. Local raw
bundles contain resolved paths; review/redact a copy before sharing.

See [#252 research and subtask plans](plans/issue-252/README.md). Formal Issue
acceptance, independent review, communication and memory-capacity coverage remain
distinct from each task's scoped qualification.

Start with the current [Chinese NPU pilot guide](plans/issue-252/npu-pilot.md).
The earlier [CPU walkthrough](plans/issue-252/walkthrough.md) retains its historical scope.
