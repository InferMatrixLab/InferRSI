---
name: omni-validation
description: "Extend vLLM-Omni pipelines, output contracts, runners or connectors and select correctness gates."
license: Apache-2.0
metadata:
  disco-role: operating
---

# Extension and validation

Read [extension and validation contracts](references/validation.md) before changing topology, streaming state, diffusion execution or transport. Select tests by the changed responsibility and by the actual backend.

Document the reference model semantics and the complete producer/consumer contract first. Preserve per-request RNG, accumulated output/state, replica affinity, abort semantics and resource lifetime. Validate ordinary completion and injected failure paths.

Escalate evidence from static checks to CPU/native contract tests, then required accelerator parity, real-model media quality and matched performance. An unavailable required backend leaves that claim `BLOCKED_REQUIRED_BACKEND`; do not substitute an import or mock test.

When a test fails, distinguish environment failure, native failure and a gap in this guidance. Make the smallest repair and repeat the affected checks. Report exact commands, revisions, input identity, observed output and unresolved limits. Return to [serving](../omni-serving/SKILL.md) only after the relevant correctness gates pass.
