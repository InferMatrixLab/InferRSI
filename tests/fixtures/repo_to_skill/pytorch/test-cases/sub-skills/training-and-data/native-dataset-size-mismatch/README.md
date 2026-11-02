# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: native-derived. Evidence: `torch/utils/data/dataloader.py`, `docs/source/notes/modules.md`, `docs/source/notes/amp_examples.md`, `torch/utils/checkpoint.py`, `torch/nn/functional.py`, `aten/src/ATen/native/transformers/cuda/sdp_utils.cpp`.

Expected behavior:

- Rejects unequal leading sample counts before concurrency.
- Checks a single aligned sample and collated batch with num_workers=0.
- Avoids presenting worker tuning as a data schema repair.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
