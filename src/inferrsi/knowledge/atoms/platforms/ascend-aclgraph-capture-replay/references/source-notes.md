# Source Notes: Ascend ACLGraph Capture/Replay

Evidence origin: Dot's supplied 2026-10-15 implementation bundle. The ledgers below retain the supplier's pinned code/documentation inspection; local integration did not repeat those upstream reads. These are code/docs-derived contracts and proposed procedures, not paper-derived mechanisms or empirical results.

## Provenance and limits

- Repository: `vllm-project/vllm-ascend`.
- Immutable inspected commit: `8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf`.
- Retrieval: GitHub connector reads at that exact ref on 2026-10-15. This identifies inspected evidence, not the latest upstream or installed version.
- Method: manual, bounded Repo-to-Skill-style extraction from implementation into an evidence-gated procedure. No AREX or DisCo execution, skill installation, source modification, hardware run, benchmark, or empirical gain is claimed.
- Attribution: `acl_graph.py` declares Apache-2.0 and copyright contributors to the vLLM project. The test file includes an Apache-2.0 license header. These notes paraphrase behavior and identify symbols; they do not reproduce source bodies or relicense upstream code.
- Scope: ACLGraph wrapper/runtime contract and pinned graph-mode guidance. No allocator internals, TorchAir implementation, Xlite implementation, H2D/IPC transport, SSD, or network behavior was mined.

## Inspected source ledger

| ID | Immutable source | Blob SHA | Inspection reason |
|---|---|---|---|
| S1 | [vllm_ascend/compilation/acl_graph.py](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/vllm_ascend/compilation/acl_graph.py) | `da6f9c96861e22b22eec95a904c87e6670015475` | Capture/replay, inputs, lifetimes, ordering, error classifiers. |
| S2 | [docs/source/user_guide/feature_guide/graph_mode.md](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/docs/source/user_guide/feature_guide/graph_mode.md) | `1f2d8538b29586efe942969d4fe8fef3839c97a6` | Effective mode, runner/backend constraints, narrow resource mitigations. |
| S3 | [tests/ut/compilation/test_acl_graph.py](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/tests/ut/compilation/test_acl_graph.py) | `e49d4ba6dfd5766d78a97c51005629367bc979f2` | Concrete question: which pinned tests check bypass, initial capture, replay and positional-address assertions? Selected cases were inspected, not executed. |

No direct caller was needed to establish the wrapper-level contract. Caller ownership and external helper semantics remain boundaries, not inferred guarantees. Upstream links embedded in the guide were not followed; their current contents are not evidence for this pin.

## F: source facts

### F1. Mode and version boundaries

[S2 lines 14–47](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/docs/source/user_guide/feature_guide/graph_mode.md#L14-L47) says both Model Runner V1/V2 support graph mode and context-parallel `FULL` is not sufficiently supported. This supersedes an older indexed V1-only description for this extraction, without asserting that every V2 configuration works.

The guide separates compile-time optimization and runtime ACLGraph: FULL/FULL_DECODE_ONLY use Npugraph_ex FX optimization; PIECEWISE uses basic fusion; FULL_AND_PIECEWISE follows piecewise compilation with FULL-capable uniform-decode runtime behavior. NONE is eager. The guide's default statement is version-scoped, not an installed-default claim.

[S2 lines 72–122](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/docs/source/user_guide/feature_guide/graph_mode.md#L72-L122) says compatibility checks can adjust modes. It lists `attention_v1`/`context_parallel/attention_cp` as ALWAYS, and MLA/SFA variants as UNIFORM_BATCH. This is the pinned guide's declaration, not a cross-version compatibility certificate. A backend declaration does not erase its separate context-parallel FULL caveat.

### F2. Dispatch and cache key

[S1 `ACLGraphWrapper.__init__` and `__call__`, lines 91–188](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/vllm_ascend/compilation/acl_graph.py#L91-L188): initialization rejects NONE, records the global graph pool, and creates a dictionary keyed by `BatchDescriptor`. At call time, forward-context NONE or a runtime-mode mismatch bypasses capture/replay and calls the runnable. Matching calls create an entry if missing; `entry.aclgraph is None` triggers capture after `validate_cudagraph_capturing_enabled()`. Do not equate a top-level composite configuration mode with the wrapper's runtime mode.

### F3. Stable-address evidence has a narrow surface

[S1 class contract, lines 66–89](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/vllm_ascend/compilation/acl_graph.py#L66-L89), [capture/replay address code, lines 186–187 and 275–282](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/vllm_ascend/compilation/acl_graph.py#L275-L282): persistent buffers and input copying belong outside this wrapper. Capture records `data_ptr()` only for tensor objects directly in positional `args`. Replay compares that list only if DEBUG was active when the wrapper initialized. Equal addresses alone establish neither updated contents nor complete input/shape/metadata correctness; kwargs and nested tensor containers are not checked by this expression.

### F4. Capture and memory-lifetime boundaries

[S1 `ACLGraphWrapper.__call__`, lines 190–273](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/vllm_ascend/compilation/acl_graph.py#L190-L273): optional `gc_disable` patches collection/empty-cache operations during capture. The wrapper calls `get_offloader().sync_prev_onload()` before entering `torch.npu.graph(..., pool=self.graph_pool)` and `join_after_forward()` inside capture after the runnable. These are capture-ordering facts, not transfer-performance results.

Optional in-capture `weak_ref_output` is documented as safe only for the last piecewise graph whose output is not consumed by another graph. After capture, workspace slots and the cached entry output are weak-referenced; the capture call returns its local `output`, whereas replay returns `entry.output`. Preserve that distinction. [S1 `weak_ref_workspaces`, lines 322–328](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/vllm_ascend/compilation/acl_graph.py#L322-L328) skips absent parameters/slots. Nothing inspected quantifies HBM savings or proves all underlying storage can be released.

### F5. Replay/update sequencing is branch-specific

[S1 `ACLGraphWrapper.__call__` / `_updatable_graph_replay`, lines 284–319](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/vllm_ascend/compilation/acl_graph.py#L284-L319): FULL synchronizes the current stream when ENPU is disabled, except the draft-model-plus-EAGLE case. The comment assigns ENPU ordering to the model runner; that caller was not inspected.

FULL plus `use_updatable_graph(attn_backend)` takes the update-aware path, requiring a non-null `update_stream`. Draft graphs resolve `SharedSource(draft_model_metadata)`; others resolve `ContextSource(forward_context.attn_metadata)`. ENPU executes update then replay; non-ENPU executes replay then update. Other paths call replay directly. These branches cannot safely be flattened into a generic update-before-replay rule.

[S1 `update_full_graph_params`, lines 331–357](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/vllm_ascend/compilation/acl_graph.py#L331-L357) returns early for an updatable backend; otherwise it invokes the backend implementation under `set_current_vllm_config`. Its comment about vLLM >=0.27.1 describes a specific configuration-context API interaction, not a compatible-version range for this skill.

### F6. Exact failure classification and bounded mitigations

[S1 classifier symbols, lines 34–52](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/vllm_ascend/compilation/acl_graph.py#L34-L52) and [capture exception handling, lines 227–244](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/vllm_ascend/compilation/acl_graph.py#L227-L244):

- `_is_old_hdk_capture_error`: lowercased error contains `alloc sq cq fail`. This branch is checked first and recommends HDK 25.5.1 or later with matching CANN. Do not generalize that recommendation into a universal minimum or perform an upgrade under authoring authorization.
- `_is_stream_resource_capture_error`: either lowercased named marker (`insufficient_stream_resources` or `stream resources are insufficient`), or `207008` together with `stream resource`. Numeric code alone does not satisfy the classifier. It recommends reducing `cudagraph_capture_sizes` / `max_cudagraph_capture_size`, considering FULL/FULL_DECODE_ONLY for mostly uniform decode, or temporarily disabling graphs.
- Other RuntimeErrors propagate without this targeted diagnosis. Both recognized paths re-raise errors with guidance; they do not automatically retry or switch the running workload to eager.

[S2 lines 113–122](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/docs/source/user_guide/feature_guide/graph_mode.md#L113-L122) connects resource exhaustion with larger capture sets and the higher number of graphs in piecewise/mixed paths. The guide's “Fallback to Eager Mode” section supplies `enforce_eager=True` / `--enforce-eager` as temporary fallback configuration, not a wrapper error-recovery guarantee.

### F7. Observable verification hooks and test limits

S1 increments `compilation_counter.num_cudagraph_captured` on successful capture at line 268, and emits a once-only replay-active log at line 301. Neither is a per-request replay coverage metric.

The following S3 `TestACLGraphWrapper` cases are concrete candidate contract-check targets:

- [lines 220–267](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/tests/ut/compilation/test_acl_graph.py#L220-L267): `test_call_with_none_runtime_mode`, `test_call_with_mismatched_runtime_mode`.
- [lines 277–343](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/tests/ut/compilation/test_acl_graph.py#L277-L343): `test_call_capture_graph_first_time` checks entry creation, graph-pool invocation, counter, and capture return.
- [lines 416–488](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/tests/ut/compilation/test_acl_graph.py#L416-L488): `test_call_replay_graph` checks replay rather than reinvoking the runnable.
- [lines 497–613](https://github.com/vllm-project/vllm-ascend/blob/8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf/tests/ut/compilation/test_acl_graph.py#L497-L613): `test_call_with_debug_mode_input_address_check`, `test_call_with_debug_mode_input_address_mismatch` exercise stable/changed positional tensor addresses.

These tests mock graph/device interactions. Their presence is not a passing result, performance evidence, or proof of NPU correctness. No test was run, and no claim is made that the entire pinned test module passes.

## P: operational interpretation

The skill converts F1–F7 into a sequence of evidence gates: establish path and version; classify dispatch; verify inputs/lifetimes/order; select a narrow mitigation; plan correctness/resource observation before performance attribution. The hypotheses about amortization, coverage tradeoffs, and capture HBM cost need measurements on the user's stack. No numerical threshold, benefit, or resource budget was established.

## Resource scope

Accelerator / Graph runtime / HBM: effective-mode and capture-resource diagnosis, conditional configuration and proposed verification. Host launch overhead is an attribution question, not host allocator or Network coverage. Independent pins do not establish a compatible stack.

## Unknowns to retain

- Installed hardware/software compatibility, effective backend/mode, workload repetition, graph coverage and HBM/stream headroom.
- Caller-managed buffers, full keyword/nested/metadata input validity, ENPU runner ordering, and helper implementation semantics beyond visible call boundaries.
- Performance or memory benefit, correctness under real capture/replay, and whether reduced capture sizes change coverage acceptably.
- Separately pinned vLLM and TorchNPU studies do not establish joint compatibility.

The deliverable remains a candidate until separately authorized evaluation establishes useful behavior. No scripts are included because this extraction does not support a safe standalone runtime probe without the missing stack/workload context.
