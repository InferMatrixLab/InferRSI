# Frozen plan and projection

Campaign [#297](https://github.com/InferMatrixLab/InferRSI/issues/297)
owns the acceptance criteria and source revisions. Retained original files keep
their exact bytes; the complete plan is also preserved in the external archive.

Configuration entry points:
- `plan/execution-checkpoint.json`
- `plan/frozen-lossless-contract-v1.json`
- `plan/frozen-lossy-contract-v1.json`

`archive-projection.json` declares which original source records supply the
compact summary, sample arrays and configuration references. The identical
projection and its digest are pinned in `results/artifacts.json`. It is a
read-only storage projection, not a new controller or retrospective freeze.
