# Same-tier labels do not establish a pack ABI

## User Persona

Maintainer reviewing an accelerator deployment from source/config evidence,
without permission or resources for real model execution.

## Scenario Coverage

- Skill area: `model-runtime`.
- Capability: family-marker precedence, pack representation, shallow new-family
  routing, offline support and missing-native-evidence diagnosis.
- Difficulty: troubleshooting.
- Prompt file: `user_request.txt`.
- Fixture: `fixtures/mixed-family-plan.json`, a synthetic small projection;
  intentionally conflicting MiniMax installer and DeepSeek executable.
- Expected files: model-runtime router, model-and-memory/troubleshooting
  references and `audit_runtime_plan.py`.
- Trigger: the user names model-specific engines, equal-bit-width confusion,
  `--pack`, `--ple-gguf` and an unsupported simultaneous-decoding request.

## Expected Successful Behavior

Identify the explicit config conflict before discussing fit. Use the bundled
helper on the redacted projection, retaining `screening_conflict` as screening,
not model execution. Reject renaming cross-family metadata or equating nominal
bits with tensor/slot ABI. Explain Qwen's special route and current parallel
exclusion, while retaining its shallow-inspection and native gaps. Native CPU
tests cannot establish payload compatibility or accelerator execution.

This is a newly synthesized difficult usability case, not an upstream test.
It combines conditions not exercised by the selected pure budget, controller,
draft-policy or retention tests; those tests remain complementary evidence.

## Failure Signals

Recommend pack renaming, assert equal bits imply compatibility, resolve Qwen as
GLM or DeepSeek by one ambiguous marker, launch an installer, promise Qwen
parallel decode, conceal separate model licenses, or label a CPU simulation as
native model verification. Runtime dependency on the original checkout is also
a failure.
