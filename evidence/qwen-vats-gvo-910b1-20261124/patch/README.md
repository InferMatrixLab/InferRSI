# Candidate sources

All arms used the packaged Qwen denoiser baseline and the exact replacements in
[the frozen edit vocabulary](../plan/edits.json). The two allowed edits compose in
either order. The experiment driver checks the baseline SHA-256, materializes
the four possible source files and identifies each selected candidate by its
file hash. Infra, the evaluator and the search implementation were common to all
arms. The [measured runtime revision](https://github.com/InferMatrixLab/InferRSI/tree/f5b9a1819d387e0a0a1a219da6dcc0f5504c4069)
contains the original baseline and the full Engine evaluation protocol.
