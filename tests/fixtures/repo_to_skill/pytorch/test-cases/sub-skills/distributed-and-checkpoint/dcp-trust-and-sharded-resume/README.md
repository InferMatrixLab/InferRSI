# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: synthetic. Evidence: `torch/distributed/distributed_c10d.py`, `torch/csrc/distributed/c10d/ProcessGroup.hpp`, `torch/csrc/distributed/c10d/ProcessGroupNCCL.cpp`, `docs/source/notes/ddp.md`, `docs/source/distributed/fsdp.fully_shard.md`, `docs/source/distributed/tensor.md`, `torch/serialization.py`, `torch/distributed/checkpoint/format_utils.py`, `SECURITY.md`.

Expected behavior:

- Explicitly states DCP/conversion does not inherit torch.load weights_only protections and requires trusted infrastructure-produced storage.
- Constructs optimizer after fully_shard and calls model(x) so unshard hooks fire.
- Allocates target sharded state and validates keys/layout/topology before DCP load.
- Starts with first rank exception and collective-order/signature ledger; does not fix a mismatch just by extending timeout.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
