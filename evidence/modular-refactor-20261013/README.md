# Modular refactor regression evidence

Scope: [OmniRSI issue #1](https://github.com/ThinkFlowLab/OmniRSI/issues/1) and
[PR #2](https://github.com/ThinkFlowLab/OmniRSI/pull/2). This is a functional
regression check of module extraction, not a new optimization campaign or
backend qualification.

- [Frozen controls and success criteria](plan/plan.json)
- [Four-B300 runner comparison](results/summary.json): four corresponding pairs
  (first response plus three formal request outputs), all native 1280×704 RGBA
  pixels identical. Both runners completed six warmups and three full native
  eight-step requests; source/dependency/model/helper checks passed; owned
  process groups exited cleanly. GPUs returned to zero allocated memory.
- [Full CPU suite](results/cpu-tests.txt): 123 passed, 60 subtests, including new
  scenario/target/backend composition, real HTTP collection and quality gates.
- [Independent installed-wheel CLI smoke](results/wheel-smoke.json): real external
  processes, AB/BA ordering, validation, source checks, status/report and Ascend
  context export. Metrics are synthetic fixtures, not a model performance result.
- [Historical files preserved byte for byte](results/frozen-compatibility.json).

The one-run HTTP request means were 276.1044 ms before extraction and 276.4625 ms
after extraction. These are descriptive smoke timings only: no performance
improvement, regression bound or statistical significance is inferred. Existing
B300/NPU campaign claims retain their original source and hardware scope.

The full local raw records, server logs, exact executed commands and eight native
PNG files are retained at
`/home/zjy/code/hsliu/tmp/omnirsi-modular-e2e-20261013/`. This repository stores the
summary, source/guard/output hashes and validator, **not the 28 MiB PNG bundle**.
The comparisons were executed against those native images, not resized figures.
`validator/compare.py <artifact-root>` recomputes the comparison with
`omnirsi[image]` installed and the raw artifact tree available.

The inference engine source and prepared runtime were unchanged; the only A/B
variable was the pre-refactor versus modular OmniRSI runner. Each arm started a
fresh server sequentially on the same four devices and reused the prepared
model/cache. Real `/health` readiness, startup and warmups were recorded
separately. The new generic image validator was committed before execution;
its exact-pixel gate was declared in the plan before either arm ran.
