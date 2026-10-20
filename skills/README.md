# Skills have moved

The complete collection now lives in
[`src/inferrsi/data/skill_library/`](../src/inferrsi/data/skill_library/README.md).
All 48 former root skills retain their IDs, full procedures, metadata, references
and cases. This directory is navigation only.

- [Hardware: Ascend](../src/inferrsi/data/skill_library/hardware/ascend/),
  [CUDA](../src/inferrsi/data/skill_library/hardware/cuda/) and
  [host](../src/inferrsi/data/skill_library/hardware/host/)
- [Frameworks](../src/inferrsi/data/skill_library/frameworks/) and
  [repositories](../src/inferrsi/data/skill_library/repositories/)
- [Methods](../src/inferrsi/data/skill_library/methods/) and
  [workflows](../src/inferrsi/data/skill_library/workflows/)
- [Existing English / Chinese engine skills](../src/inferrsi/data/skill_library/README.md#five-engine-knowledge--推理引擎知识)

`inferrsi skills list` defaults to the installed library's 48 registered skills
with the optional `skills` extra. To select this checkout explicitly, use
`inferrsi skills --root src/inferrsi/data/skill_library list`.
Core `knowledge search`, `knowledge show` and normalized `read` also expose the
packaged procedures without that optional parser. Reading does not execute
instructions or change a skill's verification state.
