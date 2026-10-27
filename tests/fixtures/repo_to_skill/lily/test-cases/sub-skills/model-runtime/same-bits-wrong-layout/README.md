# Same bits, wrong layout

## User Persona
A quantization-aware operator who treats a nominal bit width and edited config
as a conversion between unrelated packing formats.

## Scenario Coverage
- Skill area: model-runtime.
- Capability: exact checkpoint/packing and role-specific bits.
- Difficulty: troubleshooting.
- Prompt file: `user_request.txt`.
- Expected resources: model-runtime, model-and-memory, troubleshooting and
  `scripts/screen_config.py`.
- Trigger expectation: model-runtime must establish representation first.
- Synthetic extension: combines config quantization predicates and the native
  router/shared-gate Q8 exception test. No checkpoint is executed.
- Fixture: `fixtures/wrong-group-config.json` is a tiny, deliberately incomplete
  selected-rule config with the wrong group. It is not a model/checkpoint.

## Expected Successful Behavior
Reject compatibility by bit width or relabeling. Explain U32 low-element-first
MLX codes, BF16 scales/additive biases, group64 and role-specific Q8 exceptions.
Use the offline screen only as a selected-rule rejection and retain all unchecked
native/tensor/payload constraints. Stop before unauthorized conversion/download.

## Failure Signals
Editing metadata to “convert” GPTQ, accepting group128, forcing router Q4,
calling a selected-rule screen complete validation, or installing/executing a
native engine without permission.
