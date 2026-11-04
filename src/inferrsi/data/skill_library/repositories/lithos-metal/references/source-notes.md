# Pinned source readset

All Lithos links below resolve to
`6653b7df5f2c4392ec7b038960f2796b1499923f`. **Code** means inspected
implementation/contract; **Docs** means stated intent, support or measurement
scope; **Tests** means inspected assertions, not a claim that every test ran.
The procedures are proposed uses of this evidence. No upstream metric is a
local measurement, and no source test implies full-model qualification.

## Shared package and provenance

| Source and inspected scope | Evidence retained |
| --- | --- |
| [pyproject.toml L1–36](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/pyproject.toml#L1-L36); [setup.py L1–36](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/setup.py#L1-L36) | Code: distribution/version/Python requirement, extras, entry point, Darwin extension and bundled kernels |
| [monolith/cli.py L1–44](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/cli.py#L1-L44); [runtime/__init__.py L1–23](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/runtime/__init__.py#L1-L23) | Code: CLI dispatch, namespace, optional native import; import availability differs from execution |
| [README.md](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/README.md); [CONTRIBUTING.md L1–40](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/CONTRIBUTING.md#L1-L40) | Docs: startup/download behavior, model/hardware status, source-build Python 3.12 and Command Line Tools; performance section's target-compute scope |
| [LICENSE](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/LICENSE); [third_party/NOTICE](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/third_party/NOTICE); [MLX-LICENSE](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/third_party/MLX-LICENSE) | Attribution retained verbatim in owner-local resources |

## Compiler/fusion route

| Source, symbol and inspected lines | Evidence retained |
| --- | --- |
| [coverage.py L1–32](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/compiler/coverage.py#L1-L32), `check_coverage` | Code: missing binding fails before emission |
| [emit.py L1390–1480](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/compiler/emit.py#L1390-L1480), `emit_program`; [L1534–1620](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/compiler/emit.py#L1534-L1620), `lower_round`, `compile_program` | Code: roles/bounds, tail, backend finalize, dynamic speculative preconditions, commit ordering, policy fallback |
| [region_fusion.py](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/compiler/region_fusion.py), `fuse_regions`, `merge_labeled_regions` | Code: disjoint regions, normalized control, merge selection, StepState timeout guard |
| [static_fusion.py L53–210](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/compiler/static_fusion.py#L53-L210), `normalize`; [L929–1185](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/compiler/static_fusion.py#L929-L1185), `merge` | Code: option/geometry guards and fixed-worker/task/barrier source construction; middle normalization transforms not exhaustively audited |
| [decoder_fusion.py L1–68](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/compiler/decoder_fusion.py#L1-L68), `optimize`, `elide_dead_gdn_state` | Code: mixer/MLP boundaries and commit-rewritten state-store ownership |
| [barriers.py L1–74](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/compiler/barriers.py#L1-L74), `place_barriers`; [arena.py L1–62](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/compiler/arena.py#L1-L62), `reuse_arenas` | Code: conservative whole-buffer hazards, variants, cross-step boundary and physical scratch lifetime exclusions |
| [passes/fuse_norm.py L1–33](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/compiler/passes/fuse_norm.py#L1-L33), `fuse_norm_stat` | Code: BF16 producer statistic hoisting; distinct from commuted norm |
| [metal/base.py L1–85](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/backends/metal/base.py#L1-L85); [registry.py L1–61](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/backends/metal/registry.py#L1-L61) | Code: backend/device identity, cache digest, conservative base hooks, chip/family/core selection; no exhaustive recipe qualification |
| [design.md](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/docs/design/design.md), compilation/fusion/storage/numerics sections; [mixers.md](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/docs/design/mixers.md), input-normalization section | Docs: layer-wise scope, separate MLP, worker semantics, intentional commuted-norm rounding |

## Generation route

| Source, symbol and inspected lines | Evidence retained |
| --- | --- |
| [step_state.py L1–119](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/core/step_state.py#L1-L119), `StepStateLayout` | Code: complete ABI fields, bounds, alignment, host serialization |
| [program.py](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/runtime/program.py), spec dataclasses and `Program`; [engine.py L31–122](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/runtime/engine.py#L31-L122), `compile_pipelines`, `Engine` | Code: buffer/pipeline identity, program-specific params, ICB/run/profile boundaries and timeout reporting |
| [generate.py L81–112](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/generate.py#L81-L112), `Session.__init__`; [L475–697](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/generate.py#L475-L697), `reset`, `generate`, `_accept_stats`; [L741–774](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/generate.py#L741-L774), `load_session` | Code: prefill/cached tails, exact reference fallback, logical KV validity, context checks, pump/callback/cancel and productive rounds |
| [spec_ops.metal L108–195](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/kernels/common/spec_ops.metal#L108-L195), `verify_select`, `accept_scan`; [advance.metal L1–37](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/kernels/common/advance.metal#L1-L37) | Code: anchor/row bounds, committed output, prompt branch, ring/context/stop bookkeeping; stochastic sampler itself not exhaustively audited |
| [metal_core.mm L310–387](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/runtime/src/metal_core.mm#L310-L387), `drain_ring`, `Runner::run`, `drain` | Code: sequence-tagged ring, bounded submissions and completion ownership |
| [dspark/model.py L132–183](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/spec/dspark/model.py#L132-L183), drafter construction; [L364–441](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/spec/dspark/model.py#L364-L441), lowering/select/context update | Code: checkpoint/head ownership, target feature injection and no-op post-accept context hook; no external DeepSpec oracle inspection |
| [speculative-decoding.md](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/docs/design/speculative-decoding.md) | Docs: DSpark components, sampling distribution intent, fixed serving versus lower-level policies and target-only timing omissions |

## Serving/cache route

| Source, symbol and inspected lines | Evidence retained |
| --- | --- |
| [serving/cache.py L19–157](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/serving/cache.py#L19-L157), resolve/identity/validate/ensure pack | Code: local-only resolution, shard metadata identity, structural checks, locks and atomic publication |
| [serving/setup.py L22–142](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/serving/setup.py#L22-L142), `ServingAssets.options`, `prepare` | Code: fixed verification, pair/shape/tap checks, internal draft capacity, recipes and precision |
| [prefix_cache.py L1–169](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/runtime/prefix_cache.py#L1-L169), `PrefixCache` | Code: strict exact matching, declared state only, pre-copy eviction, fit-before-write, stale drop and flush outcome |
| [prefix_store.py L1–125](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/runtime/prefix_store.py#L1-L125); [L136–320](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/runtime/prefix_store.py#L136-L320); [L351–451](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/runtime/prefix_store.py#L351-L451), store/read/write/header/blob/quota paths | Code: ownership lock, private files, per-blob integrity, queue, fsync/rename, pin-aware eviction and miss fallback |
| [generate.py L285–378](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/generate.py#L285-L378), `prefix_identity`, release/adopt | Code: code/device/config/tokenizer-extra identity, payload size/mtime limit, allocation compatibility and state reset |
| [serve.py L103–263](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/serve.py#L103-L263), select/store/close/load/unload; [L425–710](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/serve.py#L425-L710), app/admission/stream/adapters | Code: one active generation, shared sequence cache, bounded flush and protocol/lifecycle surfaces; converter internals not exhaustively audited |
| [lifecycle.py L129–263](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/monolith/serving/lifecycle.py#L129-L263), load/release/probe/watch | Code: pending arrivals, GPU-lock recheck and failed-load sharing |
| [serving.md](https://github.com/lithos-ai/lithos-metal/blob/6653b7df5f2c4392ec7b038960f2796b1499923f/docs/design/serving.md), startup/session/request/prefill/idle/prefix sections | Docs: operational intent and protocol limits; timing anecdotes are not imported measurements |

## Inspected test assertions and script selection

Tests inspected for the stated contracts: `tests/contract/test_barriers.py`,
`test_arena.py`, `test_step_state.py`, `test_generate_speculative.py`,
`test_prefix_cache.py`, `test_prefix_store.py`, `test_serve.py`,
`test_serving_cache.py`, `test_idle_release.py`, and
`tests/runtime/test_toy_program.py`. They provide tiny/mock cases for hazards,
ABI, output limits/cancel, exact checkpoints, disk integrity and idle/HTTP
ownership; the runtime file provides synthetic ICB/reencode/ring/pipeline checks.
Their source presence is not an execution result or a full-model oracle.

Source script inventory was bounded by public entry points and relevant tools.
`monolith/cli.py`/`serve.py` parser and local-only behavior are distilled in the
bundled package/workflow references. `tools/pack_weights.py` writes large derived
packs; it is reference-only, with pack validity distilled here rather than a
checkout-dependent wrapper. `tools/profile_writer.py` performs large synthetic
GPU measurements and can write backend configurations; it is excluded from
automatic diagnostics. `tools/bench/profile_spec_round.py` and
`target_verify_latency.py` need model packs/accelerator execution and measure
different intervals; their scope informs measurement cautions, but they are
not bundled or recommended as automatic checks. Remaining benchmark, CI,
release, golden-generation and export tools are outside the selected scope.
The bundled `scripts/inspect_contract.py` adapts only safe public contract
inspection; no original source script is required at runtime.

AREX workflow provenance:
[create-repo-skill](https://github.com/VectorSpaceLab/AREX-Skill/blob/ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6/cli/packages/coding-agent/src/disco/skills/create-repo-skill/SKILL.md),
[verify-repo-skill](https://github.com/VectorSpaceLab/AREX-Skill/blob/ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6/cli/packages/coding-agent/src/disco/skills/verify-repo-skill/SKILL.md).
Only the source/extraction/verification process is reused; no live DisCo
deployment or fixed-taxonomy classification is claimed.
