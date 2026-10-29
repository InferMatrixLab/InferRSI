# Troubleshooting ownership

Platform-config owns lazy-import/entrypoint, backend-runner pairing, ABI/build, parser syntax, effective multimodal drift and setup side effects. Cache-lifecycle owns one-pool accounting, offload eligibility, duplicate destinations/pending writes, sleep/reuse, identity and store privacy. Qualification owns unsupported speculative pairing, low-precision recurrent rollback, pending output order, selector-versus-execution, sampler path and incomplete/incorrect metric accounting. Each has a symptom → discriminating check → recovery/stop table.
