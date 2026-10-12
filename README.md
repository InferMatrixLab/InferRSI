# OmniRSI

A **CLI experiment workbench and tuning knowledge base** for inference systems. It connects source identity, parameters, baselines, candidates, quality validation, and raw results in a single evidence trail.

The first release implements the first runnable slice of the reviewed plan: users provide real benchmark and validation commands, and OmniRSI repeats, records, compares, and reports the results. All run configuration uses **CLI arguments**, with no YAML task input. The control package has no mandatory third-party runtime dependencies and imports neither torch nor an inference engine.

## Implemented features

- `doctor`: inspects a prepared local Git checkout, Python package versions, and backend tools; for CUDA, it records devices, drivers, and topology. Tool availability alone does not establish model or feature compatibility.
- `plan` / `run --dry-run`: displays the resolved RunSpec and environment checks without starting an experiment.
- `run`: repeats explicit baseline/candidate argument vectors in alternating AB/BA order, saving results, logs, source fingerprints, and quality-command evidence within a global experiment deadline.
- `status` / `report`: reads run status and regenerates a standalone HTML report.
- `knowledge search/show`: searches bundled knowledge with pinned sources, filtered by repository, backend, and scenario.
- `context`: exports Markdown with sources, applicability, verification status, and limitations for manual handoff to Codex or third-party agents.

The first release does not automatically generate or apply patches, invoke agents, deploy models, activate production services, orchestrate SSH from a control host, lease devices, or recover from crashes. **Install the package on a prepared remote machine and use its local executor.** `--agent` only records the handoff target; it does not invoke that agent.

## Quickstart

Requires Python 3.10+, Git, and an environment capable of running the target repository.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
omnirsi --help
omnirsi --version
```

For PowerShell, activate with `.\.venv\Scripts\Activate.ps1`. Run the following commands from the OmniRSI root after checking out this PR.

### CPU contract smoke test: no performance or quality measurement

```bash
omnirsi doctor --repo . --repo-type vllm_omni --backend cpu

omnirsi run \
  --repo . --repo-type vllm_omni --backend cpu \
  --scenario smoke.synthetic \
  --baseline-command 'python examples/synthetic_benchmark.py --value 100 --output {result}' \
  --candidate-command 'python examples/synthetic_benchmark.py --value 80 --output {result}' \
  --validation-command 'python examples/synthetic_validation.py' \
  --metric-key metrics.latency_ms --metric-unit ms \
  --comparison-scope synthetic_fixture --direction minimize \
  --repetitions 3 --min-improvement-pct 5 --max-minutes 2 \
  --output-dir runs
```

This fixture writes preset values of 100 / 80, yielding an expected `PASS` and a 20% numerical difference. It verifies execution, evidence collection, and verdict handling; it does not measure model acceleration. Replace the fixture commands with the target repository's benchmark and quality checks for a real experiment.

Each trial replaces `{result}` with a unique JSON path, also available through `OMNIRSI_RESULT_PATH`. Commands execute as argument vectors with `shell=False`; shell pipes, environment variables, and redirection are not expanded. Use a script you have reviewed when these operations are needed.

```bash
omnirsi status --run-id RUN_ID --output-dir runs
omnirsi report --run-id RUN_ID --output-dir runs
```

See the [full quickstart](docs/quickstart.md) and [remote test plan](docs/test-plan.md).

The [four-B300 / Qwen-Image-2.1-Turbo phase 2 plan](docs/qwen21-turbo-b300-phase2-plan.md) is the active campaign: the target is now a **30% reduction in E2E latency** relative to the earliest frozen source baseline. It retains the 720p resolution class, native eight-step schedule, BF16, RGBA PNG output, and accuracy gates. Fresh profiles guide framework, pipeline, and operator tasks, with links to pinned KDA skills. Acceptance uses five AB/BA groups and complete image validation.

The [local measurement report](docs/qwen21-turbo-b300-results.md) records 385.07→335.42 ms across five AB/BA groups, a **12.89%** reduction that missed the 20% target. All final and held-out RGBA images had identical decoded pixels. Rejected iterations and infrastructure failures remain in the report; a GPU test plan is not performance evidence.

The [phase 2 results](docs/qwen21-turbo-b300-phase2-results.md) record a fresh original-source baseline of **384.16→266.60 ms, a 30.60% reduction**, or 30.76% relative to the earliest recorded 385.07 ms. Five AB/BA groups and validation of 40 native RGBA images passed. The slower fifth group and the previous formal FAIL at 29.81% are retained.

The earlier [LTX-2.5 plan](docs/ltx25-b300-test-plan.md) and [model-access blocker record](docs/ltx25-b300-local-status.md) remain as history; the active task no longer depends on access to that model.

## Knowledge base

```bash
omnirsi knowledge search 'MiniMax-H3' --repo-type vllm_omni --backend cuda
omnirsi knowledge search --repo-type vllm_omni --backend ascend --scenario diffusion.video_generation --json
omnirsi knowledge show vllm_omni.common.diffusion.measurement_and_profiling
omnirsi context 'MiniMax-H3' --repo-type vllm_omni --backend ascend --output runs/h3-context.md
```

Search filters by keyword, repository, backend, and scenario. Records retain device, model, software, and workload boundaries, which require manual checking in this first release. `common` methods can be retrieved alongside specific diffusion scenarios; `diffusion.t2i/t2v` are image/video scenario aliases.

The initial import includes two specified skills and eight MiniMax-H3 PRs:

| Entry | Key lesson |
| --- | --- |
| diffusion-perf-opt | Freeze the three-part reproduction commands; separate performance measurement from profiling; control experimental variables |
| production-add-diffusion-model | Distinguish loading support from production readiness; validate each model/task/backend combination |
| [#5990](https://github.com/vllm-project/vllm-omni/pull/5990) | Shape, platform, and output boundaries for fused Q/K norm and RoPE |
| [#6281](https://github.com/vllm-project/vllm-omni/pull/6281) | Rounding differences in fused modulation and guards for non-CUDA platforms |
| [#5783](https://github.com/vllm-project/vllm-omni/pull/5783) | Evaluate AdaLN cache capacity savings separately from speed gains |
| [#5952](https://github.com/vllm-project/vllm-omni/pull/5952) | Task calibration, step counts, and quality requirements for Ref2VA TeaCache |
| [#7024](https://github.com/vllm-project/vllm-omni/pull/7024) | Call-count and device-memory tradeoffs in VAE stacked tiling |
| [#7988](https://github.com/vllm-project/vllm-omni/pull/7988) | MXFP8 is an approximate deployment option requiring quality and loading-memory validation |
| [#7514](https://github.com/vllm-project/vllm-omni/pull/7514) | Ascend SP communication buckets and still-incomplete overall quality-equivalence validation |
| [#8072](https://github.com/vllm-project/vllm-omni/pull/8072) | Reference KV cache placement, parallel ownership, and regression counterexamples |

Source skills are pinned to `ee81f33001922f8d91dd09da0a57ee1531a8df82`; each PR retains its head revision and observed status at import. **All entries are `imported` with `locally_verified=false`.** Merge/open status, upstream reports, actual measurement hardware, and unknown quality boundaries are recorded separately. ROCm experience from other models is not presented as H3 evidence.

See the [knowledge index, sources, and usage guidance](src/omnirsi/data/repo_packs/vllm_omni/knowledge/README.md).

## Repository layout

```text
src/omnirsi/
  arguments.py / cli.py / contracts.py     CLI and frozen contracts
  inspection.py                           Environment and repository inspection
  execution.py                            Explicit local command execution
  evaluation.py / reporting.py            Evidence verdicts and HTML reports
  catalog.py                              Read-only knowledge retrieval
  data/
    repo_packs/{vllm,vllm_omni,afd_plugin,vllm_rlt}/
    platform_packs/{cuda,rocm,ascend}/
    repo_packs/vllm_omni/knowledge/experiences/
      common/diffusion/...
      cuda/diffusion/...
      ascend/diffusion/...
examples/                                 CPU smoke fixture
tests/                                    Runtime, CLI, and knowledge contracts
docs/                                     Usage, architecture, and remote test plans
runs/                                     Generated locally; ignored by default
```

`src/omnirsi/data/` is the single authoritative location for knowledge and descriptor packs. These ship as wheel package data, avoiding a source-checkout dependency after installation or duplicate knowledge copies. The four repository descriptors currently declare external command entry points; they do not implement complete model launchers. Compatibility matrices for the three accelerator backends remain unverified.

## Components and workflow

See the [component structure, complete workflow, and actual first-release boundary](docs/architecture.md). A user-supplied candidate command provides an implementation for Phase 3 to validate. The first release performs measurement, quality validation, verdict handling, and reporting; planned stages that are not implemented remain explicitly identified as such.

The English diagrams below show the target architecture and long-term workflow from the reviewed plan. See the architecture document for the implemented subset.

![OmniRSI component architecture (English)](docs/assets/component-architecture-en.svg)

![GPU inference optimization workflow (English)](docs/assets/gpu-workflow-en.svg)

The original Chinese diagrams are also available: [component architecture](docs/assets/component-architecture.svg) and [GPU workflow](docs/assets/gpu-workflow.svg).

## Verdict and reproducibility boundaries

- `PASS`: all requested trials are complete, commands succeed, metrics are valid, source fingerprints are unchanged, explicit validation succeeds, and the positive median improvement meets the threshold.
- `FAIL`: a command fails or times out, the quality command fails, or complete measurements miss the required gain.
- `INCONCLUSIVE`: the quality command is missing, JSON or metrics are invalid, source identity is uncertain or changes, the run is cancelled, or evidence is insufficient.
- Medians and ranges are descriptive statistics, not proof of statistical significance. A quality command exiting with code 0 covers only the checks it actually performs; it does not automatically establish model equivalence or service readiness.
- The caller declares metric units, measurement scope, and model/workload identity. Actual external-server versions, workload consistency, failed requests, and fair GPU resource allocation require separate checks.
- Git records include HEAD, hashes of dirty diffs and untracked files, and before/after fingerprints; they do not archive the complete dirty source tree. Reproduce with committed baseline/candidate sources, or separately preserve patches and untracked files.
- `--device-ids` is metadata; it neither sets visible devices nor acquires a resource lease. Allocate resources and configure backend visibility first.
- `--python` only inspects packages for that interpreter; benchmark and validation commands use the interpreter specified in their commands. `--candidate-repo` only changes the working directory, not installed packages. Candidates need a separate environment or an explicit import path.
- Deadlines limit launching and waiting for measurement and quality commands. Source checks, cleanup, and final reporting may take additional time. The first release caps the budget at seven days. Ctrl-C saves status and evidence, but resuming across control-process restarts is not supported.

## Validation and contribution

```bash
python -m unittest discover -s tests -v
python -m pip wheel --no-deps . -w dist
```

Record local CPU contract checks separately from actual GPU/NPU measurements. Users validate remote CUDA / ROCm / Ascend, model quality, Linux process groups, and production stability according to the test plan. Development follows plan → code → test → review; use `git commit -s` for every commit.

## Portable scaffold and CI

The canonical package is `omnirsi`; it includes the CLI RunSpec and the portable
revision/backend/device/model/scenario snapshot fields, claim verdict helpers,
evidence paths, and the `harness`, `model`, and `infra` seams. There is no second
scaffold package.

See [the playbook](docs/repo-template.md),
[test design](docs/scaffold-test-design.md), and
[scaffold usage](docs/using-the-scaffold.md).
The four CI lanes are draft, ready, merge and nightly. Draft runs lint and CPU
smoke; ready runs the full CPU suite; merge checks the layout; nightly provides
the CPU safety net. Accelerator acceptance remains issue-scoped, independent
of green CI. Use `pip install -e ".[dev]"`, `pytest`, and
`ruff check src tests benchmarks/harness` for local checks.
