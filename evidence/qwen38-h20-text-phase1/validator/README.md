# Validator freeze

The proposed validator is `examples/qwen38_text/validate.py`, paired with
`examples/qwen38_text/trial.py`. Before GPU execution, snapshot both files here
(or in the private campaign bundle), record their SHA256 plus source revision in
plan and acceptance Issue #54, and retain the complete model manifest/workload.
This directory is currently a preparation record, not a frozen validator bundle.

Validation checks complete paired trials, matching identities, full-vocabulary
logit arrays, token coverage, finite values, file digests, numerical gates and
reset/replay consistency. Missing evidence returns exit 2; a completed numeric
rejection returns 1; scope-limited acceptance returns 0.
