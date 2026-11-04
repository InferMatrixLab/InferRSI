# Scope, excluded surfaces and source-specific rights

| Surface | Extracted depth / negative boundary |
| --- | --- |
| ModelContainer and generation | Selected public wrapper, package-private async mutex/transfer, iterator/worker/loop and exact test assertions; not a full ChatSession/cache-reconciliation audit |
| GatedDelta native/ops boundary | Actual embedded MSL, public gate, FP32 state and selected model callers/tests; dependency packing/stride/runtime behavior remains separately unverified |
| Model/loading/quantization/VLM | Narrow source caller context only; no catalog, loader/weight conversion, tokenizer/template/vision pipeline or output-quality qualification |
| Tools/grammar/LoRA/training/FoundationModels | Named package surfaces, not complete operating recipes; differentiable fallback distinction does not qualify training/gradients or the default-on adapter |
| Wired admission/memory/device | Selected call boundary only; process-wide manager/custom-kernel provider belongs to MLX Swift dependency, not invented from this repository |

The two routes add repository-specific Swift ownership and recurrent-kernel
contracts. They do not duplicate all generic MLX lazy-evaluation guidance or
claim that Python and Swift engine paths are interchangeable. Source-only
counter-signals are retained as gaps requiring discriminating native evidence,
not claimed runtime bugs, successful fixes or measured regressions.

The root [MIT LICENSE](../LICENSE), copyright ml-explore, is retained unchanged;
its original hash appears in the [source identity](source-identity.json). Newly
authored helpers retain MIT/source attribution. Vendored xgrammar is separately
Apache-2.0 licensed and is outside this extraction; no grammar implementation,
model/weight, binary metallib, dependency tree or native artifact is copied.
Dependency/model/tokenizer/prebuilt asset rights remain independent.

Every SKILL.md uses `license: NO_LICENSE` because the actual AREX gh API resolver
was unauthenticated and returned unavailable at this pin. It is a warning
fallback, not a legal conclusion that no license exists, and does not replace
retained source rights.

Source examples can download/load models and broad native/integration tests may
build dependencies or require credentials. They are source evidence only here,
not bundled execution instructions. Keep synthetic helper input free of prompts,
private paths/cache data, credentials and personal device identifiers. Helper
success authenticates neither an observation nor native correctness, memory
fit, quality or service performance.
