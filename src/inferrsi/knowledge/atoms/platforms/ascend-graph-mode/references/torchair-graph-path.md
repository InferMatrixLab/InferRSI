# TorchAir configuration to ACL capture/replay: bounded source map

The [readset](torchair-graph-readset.json) records official `Ascend/torchair`
commit `e1118e8b0fc1b95190ab53b732c0872989550e20`, tree
`d035bf2bfa25f3824d5d7ae54daa04a7a9e4a487`, exact file blobs, SHA-256, byte/line
counts and one-based inclusive inspected ranges. It was read directly from a
clean official GitHub checkout on 2026-10-30. Full-file hashes identify bytes;
only listed ranges describe substantive inspection. Raw upstream code is not
vendored. [The retained license](torchair-LICENSE.md) is copied from that pin.

## Configuration and selected execution chain

The Python implementation and the documentation expose related but distinct
surfaces. `configs/compiler_config.py` owns `CompilerConfig.mode` and subconfigs;
`configs/aclgraph_config.py` declares only `use_custom_pool`.
`configs/npugraphex_config.py` maps supported `options` to those fields and
inverts three positive option names. `docs/zh/npugraph_ex/quick_start.md` instead
documents the registered TorchNPU-facing backend and `options` API; its
`api/npugraph_ex/compiler_config.md` lists that interface's config class. The
presence of this documentation does not prove backend registration in an
arbitrary installed TorchAir/TorchNPU pair.

| Inspected stage | Immutable implementation pointer | Contract used by the procedure |
|---|---|---|
| Backend/config entry | [npu_fx_compiler.py 871–915](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/npu_fx_compiler.py#L871-L915) | `get_npu_backend` returns a partial callback; `_npu_backend` applies options, obtains the compiler and enters AOT compilation. |
| AOT/runner selection | [npu_fx_compiler.py 496–710](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/npu_fx_compiler.py#L496-L710) and [930–1011](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/npu_fx_compiler.py#L930-L1011) | `_NpuFxCompiler` selects GE or ACL concrete graphs; `_CompiledFxGraph` compiles generated Python and obtains its `kernel` for the ACL path. |
| Generated runtime bridge | [fx2acl_converter.py 154–204](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/_acl_concrete_graph/fx2acl_converter.py#L154-L204), [519–563](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/_acl_concrete_graph/fx2acl_converter.py#L519-L563), [600–629](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/_acl_concrete_graph/fx2acl_converter.py#L600-L629) | Emits `AclGraph(fx_forward=forward, config=...)`, loads `AclGraphCacheInfo`, then calls the object. The generated size/stride assertion is inside a first-run guard, not a complete per-call validity proof. |
| Call state machine | [acl_graph.py 825–847](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/_acl_concrete_graph/acl_graph.py#L825-L847) | Graph eager override, key/capture, persistent fallback, input processing, replay and output reconstruction are separate branches. |
| Key and recapture | [acl_graph.py 230–278](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/_acl_concrete_graph/acl_graph.py#L230-L278), [931–1024](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/_acl_concrete_graph/acl_graph.py#L931-L1024), [1365–1385](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/_acl_concrete_graph/acl_graph.py#L1365-L1385) | Key contains selected unupdated symbolic/shape inputs and, unless frozen, parameter addresses. Mutated-input pointers/core limits can require recapture. The equality check at the capture limit occurs after a reusable key's early return. |
| Capture/input staging | [acl_graph.py 1070–1154](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/_acl_concrete_graph/acl_graph.py#L1070-L1154), [1183–1245](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/_acl_concrete_graph/acl_graph.py#L1183-L1245), [1271–1363](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/_acl_concrete_graph/acl_graph.py#L1271-L1363) | Creates `torch_npu.npu.NPUGraph`, enters `torch_npu.npu.graph`, distinguishes mutation/alias inputs, copies data into captured storage, then invokes a replay wrapper. TorchNPU checkpoint/graph primitives remain boundaries. |
| Replay/update | [acl_graph.py 526–577](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/_acl_concrete_graph/acl_graph.py#L526-L577) | `replay()` precedes dynamic-update handling; the separate stream/event/task protocol must not become an unconditional update-before-replay rule. Native event/task semantics are uninspected. |
| Output lifetime | [acl_graph.py 1387–1475](https://github.com/Ascend/torchair/blob/e1118e8b0fc1b95190ab53b732c0872989550e20/python/torchair/_acl_concrete_graph/acl_graph.py#L1387-L1475) | Single-key/disabled-reuse paths can return retained storage; eligible output cloning excludes identified input/output aliases. Multiple-key reconstruction warns that later executions can overwrite retained results. |

This path does **not** traverse the GE C++ graph executor merely because both
live in the same repository. AOT internals, FX transformation bodies,
static-kernel compiler bodies, TorchNPU native graph/allocator implementation,
CANN runtime and HCCL are not mined by this readset. Independent source pins
do not establish a compatible combined stack.

## Source definitions are not execution results

`tests/st/torchair_aclgraph_st.py` installs fake private-use NPU and stub
TorchNPU modules in setup (lines 1–79). Selected definitions cover initial
capture/replay (81–104), dynamic output reconstruction and disabled reuse
(1124–1200), and persistent fallback after the capture limit (1832–1879).
Their assertions illuminate the intended Python contract, not native behavior.

`tests/smoke/aclgraph_test.py` imports real `torch_npu` and uses NPU tensors.
Selected output-clone definitions (3129–3185) compare storage identity for
cloning enabled/disabled. These are remote-check starting points; they do not
by themselves cover old-output preservation with changed data or aliases.
Neither module was executed. No assertion is made about all tests or all
runtime branches in these files.

## Counterexamples and evidence to request

- Same shape with changed mutated storage can recapture; test address changes
  separately from shape changes and ordinary input copies.
- Passing one key once does not show later replay coverage. Cross a workload-
  chosen capture limit and revisit a prior key on the same instance.
- Holding two result objects does not imply independent storage. Change input
  data between calls and compare preserved results after the next call; include
  views and outputs that alias inputs.
- `clone_input=False` does not establish zero-copy. Disabling cross-key reuse
  does not eliminate single-key overwrite. Inspect the selected branches.
- Reduced launch gaps can coexist with unchanged or worse end-to-end latency.
  Freeze correctness, shape mix, cold/warm accounting, concurrency and memory
  limits before a separately authorized NPU/service evaluation.

These are proposed discrimination steps, not observed results. Candidate state,
empirical `not_run`, and the old import's unknown license remain intact.
