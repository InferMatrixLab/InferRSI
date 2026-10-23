# Engine architecture

Document the **implemented** model-loading, preprocessing, execution, decoding
and serving path. Explain the actual language/build layout, device ownership,
memory/parallelism strategy, configuration boundaries and extension contracts.
Separate implemented features from proposals and unsupported combinations.

![Engine architecture template](figures/architecture.svg)

The included SVG is an editable **template**, not a claim about this engine.
Replace it with the implemented topology and keep the same figure embedded in
the root README. The reference is the
[MiniCPM-o 4.5 single-GPU engine architecture](https://github.com/InferMatrixLab/minicpm-o-4.5-single-gpu-engine/blob/main/docs/figures/architecture.svg):
a readable request path with named modules, process ownership, device execution
and streaming boundaries. Adapt those documentation conventions, not its
model-specific stages, CUDA stack or hardware assumptions.

The delivered figure must identify:

- Client/API or offline entry, input preparation and response/output path.
- Scheduler/batching, model stages, cache or other persistent state and decoding.
- Process/thread and device boundaries; label data transfers and shared resources.
- Actual backend/kernel/graph paths where implemented, with fallbacks explained.

Map each box to real source/configuration paths below the figure. Omit absent
components; distinguish optional paths visually and explain when they execute.
Do not draw future optimizations as implemented. Check labels at README width.

```text
Entry / request contract: <actual-entrypoint-and-request-schema>
Model / weights: <actual-loading-and-model-boundary>
Backend / hardware: <actual-execution-interface-and-supported-scope>
Outputs / streaming: <actual-decoding-and-response-contract>
Build / runtime dependencies: <actual-toolchain-and-pinned-requirements>
Extension and affected consumers: <actual-interface-and-consumers>
```

Preserve upstream sources and licenses, and record local image ownership in
[assets](assets/README.md). There is no requirement to copy InferRSI's module
layout or add its runtime. Link real code after paths exist; leave substitution
examples in code fences until then.

Use [reproducibility](reproducibility.md) for environment and validation identity;
keep experiment-specific pins and numeric gates in the acceptance issue and
campaign evidence.
