# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: native-derived. Evidence: `torch/distributed/distributed_c10d.py`, `torch/csrc/distributed/c10d/ProcessGroup.hpp`, `torch/csrc/distributed/c10d/ProcessGroupNCCL.cpp`, `docs/source/notes/ddp.md`, `docs/source/distributed/fsdp.fully_shard.md`, `docs/source/distributed/tensor.md`, `torch/serialization.py`, `torch/distributed/checkpoint/format_utils.py`, `SECURITY.md`.

Expected behavior:

- Uses the bundled state_roundtrip helper and only its self-created temporary file.
- Explicitly distinguishes value/state roundtrip from DCP trust or hostile-artifact safety.
- Keeps map_location cpu and checks actual output equivalence.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
