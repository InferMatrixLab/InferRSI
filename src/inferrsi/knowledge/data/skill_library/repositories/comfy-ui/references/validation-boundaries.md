# Validation boundaries

Use the smallest check that can distinguish the suspected cause. Permission to
read this procedure does not grant permission to start a service, provision a
device, install dependencies or download model weights.

| Question | Minimal case | Required environment | Acceptance evidence |
|---|---|---|---|
| Does the graph link helper classify the supplied JSON as intended? | Exact pinned `graph_utils.is_link` and GraphBuilder/prefix cases | CPU / standard Python | Actual helper behavior; no executor-cache claim |
| Does the graph reuse unchanged results and rerun affected nodes? | Same prompt twice; then one constant change; inspect full/partial-cache assertions | CPU ComfyUI environment plus localhost test server and tiny graph fixture | Output values plus per-node executed/cached sets under every selected mode |
| Does external state invalidate correctly? | Keep the filename fixed, change bytes; inspect `IS_CHANGED` and downstream result | CPU where the node is CPU-capable; registry and file fixture | Fingerprint changes and correct recomputation, not JSON equality |
| Do lazy dependencies activate only when requested? | Change selected branch and inspect executed IDs/pending resolution | CPU graph suite | Selected branch values, dependencies and completion; no dynamic model extrapolation |
| Does partial model unload return usable memory? | Fixed model/prompt/precision on the selected accelerator; exercise actual static or dynamic path | Required real backend, model and matching native allocator/runtime | Requested/freed bookkeeping, measured free/allocated/reserved/pinned bytes and successful subsequent use |
| Did the policy improve performance? | Matched cold/warm runs, one changed policy, fixed workload/model/backend/precision | Same real backend and complete workload | Correct outputs, dispatch evidence, reload/transfer/eviction counts, peak bytes and end-to-end timing |

**TEST-SOURCE.** The pinned execution fixture explicitly launches `main.py`
with `--cpu` and parametrizes classic, LRU, disabled and default/assets modes
([fixture](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/tests/execution/test_execution.py#L481-L566)).
Its cache/lazy/fingerprint tests are valid native candidates after environment
preparation; the fixture has service and output/DB side effects. The upstream
CPU-wheel CI configuration is setup evidence, not a local test receipt
([workflow](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/.github/workflows/test-execution.yml#L18-L30)).

The `model_management_test.py` NPU stream tests use Mock/FakeStream. They check
Python call dispatch, not NPU streams or memory release
([test source](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/tests-unit/comfy_test/model_management_test.py#L1-L81)).
Likewise, graph-helper cases do not execute PromptExecutor, signature caches,
native provider storage or a model. Preserve those gaps in the result.

For a proposed check, record source/model revision, dependency variants,
backend/hardware, dtype, prompt/input dimensions, output targets, seed, cache
and dynamic-VRAM flags, warmup policy and exact assertion scope. If a required
backend or model is absent, record NOT RUN / blocked for that capability and
continue independent source or reader checks. Do not substitute CPU for the
dynamic device allocator, remove an assertion, or relabel the procedure as
fully AREX verified.
