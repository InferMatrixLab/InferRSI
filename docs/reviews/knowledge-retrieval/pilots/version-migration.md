# Ascend graph-mode version migration

Can a release-reported graph setup be reused on Atlas A2?

The vLLM-Ascend release source pairs with upstream vLLM v0.27.1 and scopes its model examples to Atlas 800 A3 and 950DT. The pilot target is A2 with vLLM 0.27.1. The ACLGraph procedure declares empirical_validation=not_run. No locally verified stack or target replay is available.

## Reviewed source passages

### How should capture and replay be compared?

- `package:inferrsi.ascend.skills.ascend_aclgraph_capture_replay` at `sha256:182c537e8bb8856b97009726ec0b49d3aed267c2a1c29a32bf3ef44accd0f708`, resource `data/skill_library/systems/platforms/ascend/ascend-aclgraph-capture-replay/SKILL.md`. Compare capture and repeated replay with fixed input, path and outputs. (analogue, method).
  > same model, inputs, stack, workload and compilation settings

### Does the cited release cover the target stack?

- `package:inferrsi.ascend.skills.vllm_ascend` at `sha256:2b3427b1422c0c2a350d789c53ed1f830896bbb37059bc694687ad3ba5e09f56`, resource `data/skill_library/systems/engines/vllm-ascend/SKILL.md`. A2 is outside the cited RC declaration. Local compatibility is unknown. (conflict, conclusion).
  > For A2 or another model, report the combination as outside this RC's declared scope

## Missing observations and next experiment

- Installed plugin and runtime versions, known-good and target capture/replay results.

Record both installed stacks. Replay one fixed shape and checkpoint on the known-good and target combinations, capture the execution path, then compare outputs to eager.

Replay the [pinned request](version-migration.json) with `inferrsi knowledge round docs/reviews/knowledge-retrieval/pilots/version-migration.json`. The returned body, digest and quotation are independently checkable.
