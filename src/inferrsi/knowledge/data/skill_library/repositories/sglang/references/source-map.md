# Pinned source map

All links resolve into the exact source commit below. Line ranges were checked against the local clean checkout. These are selected evidence excerpts, not whole-file certification. Native skills are source material and do not override the current user's scope.

`16176278d0180f1a1a578e53e6eef432577876c2`

## E01

Process/request flow. [python/sglang/srt/entrypoints/engine.py:243-258](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/entrypoints/engine.py#L243-L258)

## E02

Scheduler normal/overlap loops. [python/sglang/srt/managers/scheduler.py:1939-2045](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/managers/scheduler.py#L1939-L2045)

## E03

Chunk/prefill merge boundary. [python/sglang/srt/managers/scheduler.py:3766-3835](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/managers/scheduler.py#L3766-L3835)

## E04

ScheduleBatch to ForwardBatch to model. [python/sglang/srt/managers/tp_worker.py:603-651](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/managers/tp_worker.py#L603-L651)

## E05

Graph and forward-mode dispatch. [python/sglang/srt/model_executor/model_runner.py:1932-2031](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/model_executor/model_runner.py#L1932-L2031)

## E06

Memory layer ownership. [python/sglang/srt/mem_cache/README.md:8-83](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/mem_cache/README.md#L8-L83)

## E07

Radix prefix namespace and alignment. [python/sglang/srt/mem_cache/radix_cache.py:364-417](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/mem_cache/radix_cache.py#L364-L417)

## E08

Radix eviction and active locks. [python/sglang/srt/mem_cache/radix_cache.py:552-616](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/mem_cache/radix_cache.py#L552-L616)

## E09

Unified tree components and HiCache. [python/sglang/srt/mem_cache/unified_cache/components/README.md:1-121](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/mem_cache/unified_cache/components/README.md#L1-L121)

## E10

HiCache tier sharing and prefetch. [docs/docs/advanced_features/hicache_design.mdx:20-115](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/docs/docs/advanced_features/hicache_design.mdx#L20-L115)

## E11

Memory and HiCache knobs. [python/sglang/srt/arg_groups/fields/memory.py:26-170](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/arg_groups/fields/memory.py#L26-L170)

## E12

Admission and chunking knobs. [python/sglang/srt/arg_groups/fields/schedule.py:27-100](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/arg_groups/fields/schedule.py#L27-L100)

## E13

Speculative algorithm/draft knobs. [python/sglang/srt/arg_groups/fields/spec.py:28-108](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/arg_groups/fields/spec.py#L28-L108)

## E14

TP, replica DP, attention DP. [python/sglang/srt/arg_groups/fields/parallel.py:47-105](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/arg_groups/fields/parallel.py#L47-L105)

## E15

Legacy attention-DP migration. [python/sglang/srt/arg_groups/parallel_hook.py:39-61](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/arg_groups/parallel_hook.py#L39-L61)

## E16

PD roles and transfer settings. [python/sglang/srt/arg_groups/fields/disagg.py:52-79](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/arg_groups/fields/disagg.py#L52-L79)

## E17

PD allocation protocol constraints. [docs/docs/advanced_features/pd_disaggregation.mdx:23-72](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/docs/docs/advanced_features/pd_disaggregation.mdx#L23-L72)

## E18

Model registry and EntryClass. [python/sglang/srt/models/registry.py:20-159](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/models/registry.py#L20-L159)

## E19

Attention registry. [python/sglang/srt/layers/attention/attention_registry.py:41-79](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/layers/attention/attention_registry.py#L41-L79)

## E20

Kernel placement and lazy inventory. [python/sglang/kernels/README.md:11-91](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/kernels/README.md#L11-L91)

## E21

Runtime config ownership. [.agents/skills/sglang-runtime-context/SKILL.md:8-111](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/sglang-runtime-context/SKILL.md#L8-L111)

## E22

Native kernel organization. [.agents/skills/kernel-organization/SKILL.md:8-78](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/kernel-organization/SKILL.md#L8-L78)

## E23

CI layout, registration, execution. [test/README.md:12-101](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/test/README.md#L12-L101)

## E24

Serving benchmark CLI. [python/sglang/benchmark/serving.py:2260-2508](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/benchmark/serving.py#L2260-L2508)

## E25

Benchmark warmup and flush. [python/sglang/benchmark/serving.py:1482-1535](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/benchmark/serving.py#L1482-L1535)

## E26

One-batch CLI. [python/sglang/benchmark/one_batch.py:227-280](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/benchmark/one_batch.py#L227-L280)

## E27

KL consistency meanings. [.agents/skills/kl-consistency-test/SKILL.md:8-88](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/kl-consistency-test/SKILL.md#L8-L88)

## E28

Serve/version command dispatch. [python/sglang/cli/main.py:1-57](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/cli/main.py#L1-L57)

## E29

Deprecated launch module. [python/sglang/launch_server.py:68-86](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/launch_server.py#L68-L86)

## E30

Deprecated benchmark module. [python/sglang/bench_serving.py:1-22](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/bench_serving.py#L1-L22)

## E31

Dependency declarations. [python/pyproject.toml:1-106](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/pyproject.toml#L1-L106)

## E32

Dynamic SCM version. [python/pyproject.toml:259-264](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/pyproject.toml#L259-L264)

## E33

Source license. [LICENSE:1-25](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/LICENSE#L1-L25)

## E34

CLI field to option mapping. [python/sglang/srt/arg_groups/arg_utils.py:285-349](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/arg_groups/arg_utils.py#L285-L349)

## E35

CPU CI registration checker. [scripts/lint/check_registered_tests.py:91-141](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/scripts/lint/check_registered_tests.py#L91-L141)

## E36

Native CPU kernel tests. [test/registered/unit/kernels/test_kernels_namespace.py:1-77](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/test/registered/unit/kernels/test_kernels_namespace.py#L1-L77)

## E37

New model integration guide. [docs/docs/supported-models/support_new_models.mdx:8-76](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/docs/docs/supported-models/support_new_models.mdx#L8-L76)

## E38

Expert parallel size. [python/sglang/srt/arg_groups/fields/parallel.py:266-285](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/arg_groups/fields/parallel.py#L266-L285)

## E39

Benchmark warmup argument. [python/sglang/benchmark/serving.py:2659-2665](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/benchmark/serving.py#L2659-L2665)
