# Engineering benchmark tasks

The library contains three executable optimization workloads. Each package
includes its task definition, baseline, input/model requirements, validation
protocol and license. All packages live directly under
`src/inferrsi/benchmark/tasks/`.

For a complete optimization benchmark driven by the current Agent, use the
[iterative session workflow](optimization-benchmarks.md). Its first task is
`qwen21-denoise-npu`. It binds knowledge delivery, candidate snapshots, round
feedback, selection, independent final evaluation and cumulative usage exports.
The entries in the table below are the individual task measurement operations.

| Package | Optimization target | Execution entry |
| --- | --- | --- |
| `moe-forward-npu` | Complete expert-parallel forward with routing, shared expert and communication on two NPUs | `inferrsi benchmarks run moe-forward-npu` |
| `qwen21-denoise-npu` | Prefill and all denoising steps of a scaled Qwen-Image 2.1 DiT on one NPU | `inferrsi benchmarks run qwen21-denoise-npu` |
| `qwen3-tts-npu` | Real 1.7B CustomVoice text-to-audio generation and service scheduling on one NPU | `inferrsi benchmarks run qwen3-tts-npu` |

## Discover the tasks

Discovery reads packaged resources and works without device libraries.

```bash
inferrsi benchmarks list
inferrsi benchmarks show moe-forward-npu
inferrsi benchmarks show qwen21-denoise-npu
inferrsi benchmarks show qwen3-tts-npu
```

The library's `index.json` registers the packages. Common Python reads this
registry without embedding case names. `show` returns the task manifest and
the package's files without interpreting workload-specific fields.
`run <package> ...` executes that package's `benchmark.py` with the remaining
arguments unchanged. Each package owns its entry, measurement and assessment code. Review the implementation and
prepare the required runtime and caller-managed NPU allocation before execution.

## Run a candidate

Task-specific Python stays beside its definition and reference implementation.
The generic launcher resolves the installed package and forwards the caller's
arguments. Examples below display the task's own supported arguments.

```bash
inferrsi benchmarks run moe-forward-npu --help
inferrsi benchmarks run qwen21-denoise-npu --help
inferrsi benchmarks run qwen3-tts-npu --help
```

MoE owns `benchmark.py`, `grader.py` and its torchrun cleanup helper. The application
adapter injects the generic Harness executor into its entry. Python callers
provide the `execute_trial` argument explicitly. TTS owns `benchmark.py` and
`evaluation.py`, alongside its inference and service implementation. The image
and TTS entries also run directly by file path.

## Directory ownership

```text
src/inferrsi/
  arguments.py                     Existing CLI argument assembly
  cli.py                           Existing command dispatch
  benchmark_operations.py          Application child launcher and executor injection
  harness/
    optimization.py                Current-Agent session budget, records and recovery
    usage.py                       Shared usage normalization and totals
  benchmark/
    registry.py                    Generic task discovery
    optimization.py                Task protocol preparation and resource freeze
    tasks/
      index.json                   Task-owned package registration
      <task-name>/
        task.json                  Task-specific definition
        TASK.md                    Task-specific optimization contract
        benchmark.py               Task-specific runnable entry
        ...                        Baseline, inputs, checks and license
```

Common code resolves a registered package, forwards arguments to its
`benchmark.py`, waits and returns its exit status. Device setup, workload
semantics, timing and correctness checks belong to the selected task package.
MoE's grader and process cleanup and TTS's inference, service and evaluation
therefore stay with their task definitions.

The application child adapter executes the entry with `runpy`, providing the
generic `execute_trial` callback as an initial global. MoE's script entry passes
that callback explicitly to `main` and `evaluate`. The task package depends on
the supplied execution function. The Harness executor holds no metric rule, so
the MoE entry passes its own metric validation (`metric=read_metric`) with the
metric key. The existing flat CLI and adapter are the
application assembly seam until the Apps path migration.

To add a task, create its package with the files shown above and register its
directory name in `index.json`. Registry schema version 1 accepts unique
lowercase alphanumeric names separated by hyphens. No shared Python change is
needed to expose its list, show and run entry points. Task qualification and
integration tests accompany the task. The common launcher forwards each
task's own arguments and preserves its result protocol.

- [MoE forward](moe-forward-benchmark.md) runs a reviewed candidate through the
  existing external executor. The worker performs two-rank validation and
  interleaved baseline/candidate measurement, then the parent verifies samples,
  source identity and cleanup.
- [Qwen-Image denoising](qwen21-denoise-benchmark.md) can be copied out of the
  package and run directly. It checks every latent step against an independent
  FP32 reference and measures complete requests with paired samples. Its model
  uses scaled dimensions, random weights and supplied text embeddings.
- [Qwen3-TTS](tts-benchmark.md) provides `prepare / serve / collect / assess`.
  It retains real model weights, text and voice inputs, PCM audio and request
  timing. Independent ASR and speaker scores supply the quality evidence.

## Use the result in RSI

```text
Freeze task and evaluation rules → Agent changes candidate
→ Run the task entry → Retain actual source, samples and costs
→ Assess the result → Caller advances the next round → Independent final
```

The caller selects Agent/model/knowledge settings, iteration count and search
policy. The task owns input semantics, measurement and correctness requirements.
The application supplies Harness execution and retained records to the task.
Profiling is available as a separate diagnostic when useful.

`benchmarks session` supplies the executable current-Agent handoff for the Qwen
task. It enforces the declared number of rounds and an independent final. It
retains negative attempts and supports collection of a completed attempt after
an interrupted coordinator. Automatic launch of a separate Agent remains a
future application adapter.

The #362 target architecture assigns task preparation, worker measurement
protocols and assessment to Benchmark. Apps assembles these with Harness
execution and Knowledge access. Task-specific Python currently ships as
resources under `benchmark/tasks`, with discovery under `benchmark/registry.py`.
The current flat application adapter and CLI assemble execution until their
#362 migration. Software tests and installed-wheel
resource checks establish their stated scope. Each task documents the device
and quality qualification still required for its current entry point.
