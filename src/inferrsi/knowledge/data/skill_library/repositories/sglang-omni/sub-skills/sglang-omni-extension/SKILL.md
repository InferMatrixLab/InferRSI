---
name: sglang-omni-extension
description: "Extend SGLang-Omni models, stages or runtime contracts and choose native configuration, lifecycle, streaming and hardware validation."
license: Apache-2.0
metadata:
  disco-role: operating
  repository: sgl-project/sglang-omni
  source-commit: 2cfb3b67becb437b70751defe37e63d3af4eedb0
  language: en
  skill-root: sglang-omni
  parent: sglang-omni
---

# Extension and validation

Use to add a model/stage or change a scheduler, payload, transport or configuration contract. Read [integration and test map](references/integration.md); preserve the repository's own `AGENTS.md` and referenced coding guidance in the target checkout.

1. State the supported model architecture, checkpoint, endpoint and expected input/output behavior. Choose the nearest working pipeline by scheduling and state requirements, not merely modality.
2. Map the change to the owner: model `config.py` for topology, request builder for normalization, scheduler for batching/lifecycle, runner for forward-specific work, comm layer for transport, platform manifest for dependencies.
3. Keep shared framework contracts model agnostic. Add the smallest adapter and explicit state/lifetime contract; use existing state, preprocessing, reference encoding and vocoder helpers only where their semantics match.
4. Validate successful execution and invalid input, cancellation while preparing, late stream chunk, EOS/flush, repeated requests and cleanup. Extend existing focused native tests for the affected contract; do not claim that mocked/no-GPU tests establish model quality.
5. On target hardware compare streaming and non-streaming output, usage/finish reason, quality and latency at baseline and concurrency. Keep unrun hardware checks explicit.

If discovery skips a model, read its import error and architecture registration before editing the registry. If a factory argument fails, trace its consumer rather than silently ignoring it. If shared-state behavior changes after splitting a process, move required state into a supported payload/service boundary or restore colocation. Return the minimal patch, test evidence, outstanding platform checks and rollback path.
