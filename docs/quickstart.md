# Quickstart

This release uses CLI args and a **local executor on a prepared machine**. Install it directly on the remote machine where the target engine already works. It does not set up models, CUDA/ROCm/CANN, services, SSH workers or autonomous Agents.

## Install and smoke

From the checked-out PR branch:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
inferrsi --help
inferrsi doctor --repo . --repo-type vllm_omni --backend cpu
```

The base install supports `skills enter <task-id>`, `find`, Case reads and
package-only knowledge operations. PyYAML is a core dependency, so it also supports
commands that parse skill frontmatter, including direct reads from a checkout or a
custom skill root, and the read-only [YAML task file](task-input.md) commands
`inferrsi task validate|preview`. The `skills` extra remains as a compatibility alias.

For the maintained model examples, see [Qwen B300](qwen-image-2.1-turbo-b300.md)
and [Qwen Ascend](qwen-image-2.1-turbo-ascend.md). Continue below for the generic
benchmark/quality command contract; set the acceptance threshold from your plan.

## MLX discovery and source knowledge

On a prepared target checkout, MLX discovery reads Apple Silicon chip facts with
macOS sysctl and reports the requested Python's MLX distribution version without
importing or installing it:

```bash
inferrsi doctor --repo . --repo-type vllm_omni --backend mlx
inferrsi knowledge search --tier dependency --repo-type mlx --backend mlx --json
```

Use the existing repo type appropriate to your checkout. There is no MLX engine
repo type or built-in launcher. On non-macOS hosts and non-Apple-Silicon Macs,
discovery is unavailable with a reason; doctor exits 1. Apple Silicon uses
unified memory, so --device-ids is rejected. Optional --device-model matches the
reported chip case-insensitively. Chip discovery and package metadata do not
certify MLX/Metal, a model, or performance; compatibility remains unverified.

The three source cards reuse the existing MLX evaluation/stream/lifetime owner.
Its common catalog ID and the separate MLX-LM procedure remain unchanged.

## Discover knowledge and skills

For an inference engineering task, select the [primary skill for the user's
goal](knowledge-layout.md#seven-deliverables), run `inferrsi skills enter <task-id>`
and read the returned procedure before searching. For example, when inference
succeeds but output quality regresses, load `inferrsi skills enter task-accuracy`.
Use the observed run to choose supporting evidence. Standalone `find` ranks
supporting skills, imported records and casebook entries together:

```bash
inferrsi find 'cache per-step masks ran out of device memory'
inferrsi find '算子测过了但整图质量没过' --limit 3
```

Run the `open` command on a relevant hit to read the entry and its source,
applicability, limitations and revision. Add `--kinds case` to focus the search
on recorded observations and failed directions. On a base install, an indexed
Skill in the installed library opens its original text through the corresponding
package record.

Unmatched query terms do not exclude results that match other terms. If no
query terms match the index, `find` returns `no_match`. Read the reported state,
`scope` and bounds before acting on a hit. Use the package catalog to list
records with exact filters and `context` to export a cited package selection.
See the [operation guide](operations.md) for command boundaries.

```bash
inferrsi knowledge search --repo-type vllm_omni --backend ascend --json
inferrsi context --repo-type vllm_omni --backend cuda --output context.md
inferrsi skills list --json
```

Normalized Collect, exact-revision reads and resource access are available as
CLI commands and as the Python `KnowledgeReader`
([contract](knowledge-operations.md)); authorized local candidate Create/Update
remains a Python `KnowledgeStore` operation ([contract](knowledge-store.md)).
Use `collect` with explicit IDs when you already know which material you want.
For example, assemble the Ascend graph-mode and device-health Skills within
a 65,536-byte context budget.

```bash
inferrsi collect --id package:inferrsi.ascend.skills.ascend_graph_mode \
  --id package:inferrsi.ascend.skills.ascend_device_health \
  --context-bytes 65536 --json
inferrsi read checkout:case.qwen-ascend-rejected-directions --installed-library --material
inferrsi resource checkout:case.qwen-ascend-rejected-directions qwen-ascend-rejected-directions.md \
  --revision '<revision from read>' --installed-library --output case.md
```

The revision for `resource` is the second field of the `collect` text-mode line,
or the `revision` field in `collect --json` / `read` output. For a known revision
in a batch, pass `--revision 'ID=REV'` to `collect`. Use `read --material` for the
entrypoint or `read --resource <key>` for a specific UTF-8 resource. The latter
names the selected resource in `content_resource`.

The installed package catalog is available by default. For Case and Skill
bodies, `read` and `resource` accept `--installed-library` for the bundled
library or `--skill-root` for a custom library. Reuse the source flag when
following a result. An existing store opened read-only with `--store` requires
its recorded skills root if one was configured.

During a managed optimization, `campaign knowledge` and
`benchmarks session knowledge` use Find when the frozen plan permits knowledge.
They assemble the selected Case, Skill or Record material within the requested
budget and retain its revisions with the campaign.

## Establish acceptance criteria

Use criteria supplied by the user or their referenced accepted plan. If absent,
the agent uses the packaged ceiling-analysis skill to formulate targets:

```bash
inferrsi read inferrsi.common.skills.performance_ceiling_analysis --material
```

Follow its [acceptance-criteria procedure](../src/inferrsi/knowledge/data/skill_library/playbooks/measurement/performance-ceiling-analysis/references/acceptance-criteria.md).
Preserve partial requirements; record derived targets with their baseline,
calibration, uncertainty and authority in the acceptance issue and frozen plan.
Missing evidence requires calibration, not a guessed threshold. This is agent
preparation: `plan`/`run` do not invoke the skill or infer acceptance criteria
from omitted flags. CLI defaults are not accepted campaign goals.

## The actual configuration interface

```text
doctor: --repo --repo-type --backend --device-ids --device-model --python
plan/run: all doctor flags, plus
  --candidate-repo --scenario --mode --agent --executor local
  --baseline-command --candidate-command --validation-command
  --metric-key --metric-unit --comparison-scope --direction
  --require-trial-check (repeatable dotted boolean qualification key)
  --repetitions --min-improvement-pct --max-minutes
  --workload-id --model --model-revision --output-dir --dry-run
status/report: --run-id --output-dir
find: QUERY --limit --kinds --skill-root --explain --json
read: ID --revision --material --resource --omit-resources --installed-library --skill-root --store
knowledge search: [QUERY] --tier --repo-type --backend --scenario --limit --json
knowledge show: ID
context: QUERY --tier --repo-type --backend --scenario --limit --output
```

Scenario/model/workload/Agent fields retain caller declarations. They do not start an Agent or automatically generate model recipes. The initial evaluator checks one positive numeric metric and the caller's validation command. It does not implement all SLO/quality metrics from the target design.

## Benchmark result contract

The benchmark writes JSON to `{result}` or `INFERRSI_RESULT_PATH`. Any flat or dotted positive numeric key is supported:

```json
{"metrics": {"latency_ms": 123.4}}
```

Existing vLLM-Omni diffusion benchmark JSON can be used directly with `--metric-key latency_mean --metric-unit s`, or `--metric-key throughput_qps --metric-unit requests/s --direction maximize`. No conversion file is required. Inspect the target revision because metric keys and flags can change.

## Real remote experiment

1. Reserve the exact devices, CPU/NUMA and fabric resources. Configure their visibility outside InferRSI. Do not run contending A/B servers on the same devices.
2. Prepare baseline and candidate checkouts/environments. Verify the imported module path matches each intended checkout. `--candidate-repo` changes cwd only; `--python` only inspects packages.
3. Create two reviewed trial scripts. Each script starts the intended engine/config, warms it up, runs the same fixed workload with profiling off, writes benchmark JSON and exits after its cleanup. A script can call the target's existing benchmark.
4. Create a quality script that compares outputs/tasks against the frozen reference and exits nonzero on a regression. Include the exact modes/shapes/steps/reference assets in that test.
5. Preview, then run:

```bash
inferrsi plan \
  --repo /work/vllm-omni-baseline --candidate-repo /work/vllm-omni-candidate \
  --repo-type vllm_omni --backend cuda --device-ids 0,1,2,3 --device-model B300 \
  --python /envs/baseline/bin/python --scenario diffusion.image_generation \
  --model Qwen/Qwen-Image-2.1-Turbo --model-revision MODEL_SHA --workload-id FIXED_WORKLOAD_SHA \
  --baseline-command '/envs/baseline/bin/python /work/trials/baseline.py --output {result}' \
  --candidate-command '/envs/candidate/bin/python /work/trials/candidate.py --output {result}' \
  --validation-command '/envs/candidate/bin/python /work/trials/validate_quality.py' \
  --metric-key latency_mean --metric-unit s --comparison-scope http_e2e \
  --direction minimize --repetitions 3 --min-improvement-pct "${TARGET_REDUCTION_PCT:?set from the frozen acceptance plan}" \
  --max-minutes 120 --output-dir /work/inferrsi-runs
```

Replace `plan` with `run` using the same flags after the plan matches your intended experiment. Script paths are templates that you supply; InferRSI does not create them. Start with one-variable, same-quality configuration optimization. Quantization, TeaCache, generation-step changes and adaptive exit require a quality-changing protocol and an explicit validation script.

On ROCm use `--backend rocm`; on Ascend use `--backend ascend`. The doctor retains raw backend output but does not certify device selection, model support or full topology. Record the actual driver/runtime/communication versions and topology with your experiment evidence.

## Native vLLM-Omni benchmark inside a trial script

The prepared trial can invoke the existing serving benchmark (confirm flags at your revision):

```bash
python benchmarks/diffusion/diffusion_benchmark_serving.py \
  --base-url http://127.0.0.1:8099 --model MODEL \
  --task t2i --dataset random --num-prompts 10 \
  --output-file RESULT_PATH
```

`random` is a feasibility load, not representative production traffic or a quality evaluation. For performance claims freeze an actual input/trace cohort, request fields, seed, warmup, arrival rate/concurrency and successful-request counts. Prefer a materialized trace when comparing repeated trials. Save produced outputs for quality checks using the target's supported output-saving option.

A trial script can read `INFERRSI_RESULT_PATH` when it constructs the native `--output-file` argv. Do not substitute a latency-only benchmark for the separate quality script. Benchmarks of pre-existing external servers need their own process/environment identities and cleanup outside the runner.

## Results and handoff

`run` prints a run ID and evidence directory. Exit codes are 0 for PASS, 1 for FAIL and 2 for INCONCLUSIVE/input errors.

```bash
inferrsi status --run-id RUN_ID --output-dir /work/inferrsi-runs
inferrsi report --run-id RUN_ID --output-dir /work/inferrsi-runs
inferrsi context --repo-type vllm_omni --backend cuda \
  --scenario diffusion.image_generation --output /work/image-context.md
```

Read `report.html`, execution logs, per-trial `source.json`, `source_checks.json`, validation logs and raw results. Retain committed source revisions or dirty source files/patches separately. Ctrl-C records cancellation and cleans owned child jobs; there is no `cancel` or `resume` subcommand in this first release.

Context is a cited reference bundle for manual use with Codex/third-party Agents. Its imported source text is data, not authorization to execute upstream instructions. All imported knowledge remains unverified locally until your remote evidence is linked to it.

Browse external sources with `inferrsi knowledge search --tier dependency --limit 20`
or `--tier peer`. Export one source explicitly, for example
`inferrsi context --repo-type xdit --backend cuda --tier peer`.
`--repo-type` names the source owner; vllm_omni queries do not automatically
include its dependencies or peers. See the
[three-tier guide](../src/inferrsi/knowledge/data/skill_library/records/README.md) for all sources.

For per-trial completeness, lifecycle and graph qualification, see the
[Omni experiment contract](../src/inferrsi/knowledge/data/skill_library/workflows/governance/rsi-evidence/references/omni-experiments.md). These optional checks
are frozen in RunSpec and do not replace the quality command.
