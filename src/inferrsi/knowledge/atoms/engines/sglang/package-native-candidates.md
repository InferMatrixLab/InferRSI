# Native candidates

These are repository-native candidates, not imported dependencies. Read the pinned file before applying it, then check the target checkout for changes. `.claude/skills` is a repository alias to `.agents/skills` at this snapshot; use actual `.agents` files for portable provenance. Script-bearing native skills remain reference-only here.

| Native skill | When useful | Disposition |
|---|---|---|
| [sglang-runtime-context](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/sglang-runtime-context/SKILL.md#L1-L35) | Config publication, override and per-forward state | Reference-only; inspect current contract |
| [kernel-organization](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/kernel-organization/SKILL.md#L1-L35) | Kernel ownership and migration | Reference-only; inspect current contract |
| [add-jit-kernel](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/add-jit-kernel/SKILL.md#L1-L35) | JIT implementation details | Reference-only; inspect current contract |
| [add-sgl-kernel](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/add-sgl-kernel/SKILL.md#L1-L35) | AOT wheel kernel work | Reference-only; inspect current contract |
| [write-sglang-test](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/write-sglang-test/SKILL.md#L1-L35) | CI registration and test entry points | Reference-only; inspect current contract |
| [kl-consistency-test](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/kl-consistency-test/SKILL.md#L1-L35) | Prefill/decode and cache-hit state checks | Reference-only; inspect current contract |
| [debug-distributed-hang](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/debug-distributed-hang/SKILL.md#L1-L35) | Collective ordering and rank diagnostics | Reference-only; inspect current contract |
| [debug-cuda-crash](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/debug-cuda-crash/SKILL.md#L1-L35) | Device failure localization | Reference-only; inspect current contract |
| [generate-profile](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/generate-profile/SKILL.md#L1-L35) | Capture profiling evidence | Reference-only; inspect current contract |
| [llm-torch-profiler-analysis](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/llm-torch-profiler-analysis/SKILL.md#L1-L35) | Analyze captured traces | Reference-only; inspect current contract |
| [sglang-prod-incident-triage](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/sglang-prod-incident-triage/SKILL.md#L1-L35) | Runtime symptom triage | Reference-only; inspect current contract |
| [speculative-naming](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/.agents/skills/speculative-naming/SKILL.md#L1-L35) | Speculative implementation naming and boundaries | Reference-only; inspect current contract |

Do not copy scripts merely because a native skill has them. The existing AREX `sglang_source_smoke.py` checks path/dependency markers; the external construction audit is more specific for this snapshot. No executable operating helper is bundled. Repository scripts used as documented commands are retained upstream and require the repository checkout.

For model integration, use the [model registry evidence](source-map.md#e18) and the [model guide](source-map.md#e37); `cookbook-add-model` authors deployment documentation and is not the model runtime implementation contract. Return to [parallelism and extension](parallelism-and-extension.md).
