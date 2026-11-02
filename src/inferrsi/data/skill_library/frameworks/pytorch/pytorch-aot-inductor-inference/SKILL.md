---
name: pytorch-aot-inductor-inference
description: "Package a torch.export program with AOTInductor for Python or C++ inference, and keep dynamic dims, dtype and stride distinct from CUDA-graph lifetime. Use for the deployment contract, not a measured latency win."
---

# AOTInductor inference packaging

Status: candidate. Empirical validation: **not_run**. Pin: `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457`.

CUDA-graph guards, capture shapes and output lifetime stay on the existing dependency card. The v2.15 CUDA-graph trees document matches that card's SHA-256; see the [router](../pytorch-inference-operating-graph/SKILL.md). This skill does not restate those constraints as new results.

## Procedure

1. F: the AOTInductor document says to `torch.export.export` first, then `torch._inductor.aoti_compile_and_package`, producing a PT2 archive aimed at non-Python deployment. P: export soundness is the document's claim about `torch.export`, not a local proof.
2. F: with CUDA available and a CUDA build, the example compiles a CUDA library; otherwise it compiles CPU. `TORCHINDUCTOR_FREEZING=1` is suggested for CPU inference. The same paragraph mentions Intel GPU. P: do not read that as NPU, ROCm or a required freezing default for CUDA.
3. F: the example marks one batch dim dynamic with `torch.export.Dim`. It says inference inputs must match export size, dtype and stride except for dims marked dynamic. The C++ loader constructs `c10::InferenceMode` and runs the package. P: a second batch size works in the example only because that dim was dynamic. Do not generalize to ranks, dtypes or strides.
4. F: `inductor_configs={"max_autotune": True}` is an optional example. The Dynamo overview says Inductor lowers to Triton on GPU or C++/OpenMP on CPU, and points at a training dashboard. P: neither the flag nor the dashboard is a measurement from this extraction. Do not copy a dashboard number into a claim.
5. F: Dynamo is described as a Python bytecode front end that extracts an FX graph for `torch.compile`. P: that overview is not the guard or recompilation implementation. Recompile diagnosis stays with the older compiler card until that card is deliberately refreshed.

## Limits

`torch.export` implementation, Inductor codegen and the C++ loader were not read beyond this document. No package was built.
