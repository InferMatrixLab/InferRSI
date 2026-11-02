# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: synthetic. Evidence: `torch/utils/data/dataloader.py`, `docs/source/notes/modules.md`, `docs/source/notes/amp_examples.md`, `torch/utils/checkpoint.py`, `torch/nn/functional.py`, `aten/src/ATen/native/transformers/cuda/sdp_utils.cpp`.

Expected behavior:

- Starts with a zero-worker data/schema control and explicitly disables incompatible prefetch/persistent settings.
- Shards the iterable across worker and rank replicas and accounts for spawn pickling.
- Keeps a fixed scale through accumulation, unscales once after the full window, then clips/steps/updates.
- Sets SDPA dropout_p to zero at eval and checks its Boolean mask semantics.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
