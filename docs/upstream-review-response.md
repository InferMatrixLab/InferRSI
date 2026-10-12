# Review feedback and revalidation

Refs [the roadmap issue](https://github.com/ThinkFlowLab/OmniRSI/issues/1) and
[the frozen acceptance issue](https://github.com/ThinkFlowLab/OmniRSI/issues/3).
The feedback originates in [vLLM-Omni PR8739](https://github.com/vllm-project/vllm-omni/pull/8739)
and this workbench PR. Portable guidance is in `skills/rsi-evidence/SKILL.md`
and the `upstream-review-gates` knowledge record; the record remains imported
review guidance, rather than a universal accelerator-performance claim.

## Executable harness corrections

- Fingerprint all tracked source. Exclude only generated untracked files in
  the current run, even when an output root is a source subdirectory.
- Resolve output files under their own trial. Reject reference aliases,
  duplicate paths within a trial and reuse across aggregate trials.
- Preserve failed manifests on cleanup/protected-source/guard/dependency/model
  probe errors, and record each unavailable check explicitly.
- Keep one `omnirsi` package, combining executable argv RunSpec with portable
  revision/backend/device/model/scenario snapshots, claim enum and evidence
  paths. Preserve the old contracts import as a compatibility alias.
- Use the four upstream CI lanes. CPU smoke, the ready suite and package checks
  do not establish GPU campaign acceptance.

## Upstream lessons

Optional compiler/NCCL requirements must remain opt-in until availability is
established consistently across ranks. Never introduce rank-local fallback
once collectives start. Geometry/cache lifetime follows the request; singleton
models must not retain prefix KV. Test success, error, interruption and dropped
step-mode requests, while keeping reusable graph buffers separate.

General exact math belongs in the target's common operator layer. Model-specific
channels-last/approximation policy remains in adapters. Moving code still needs
validation of all consumers, reduction order, casts, hooks, compiler/gradient
fallbacks and full generated output.

Use checked-in, model-neutral benchmark clients and portable commands. Publish
raw metrics and native output files with checksums; normalize storage paths in
publication copies, preserving originals. Distinguish frozen historical claims
from current-base/current-head results and configuration changes from code-only
comparisons.

## Evidence scopes

The unchanged issue3 historical campaign remains30.6009% for f69b1f2b →330d411d
with44 identical images. Its public archive/source Git bundle/checksum metadata
is in [the historical manifest](../evidence/qwen21-turbo-b300-20261010/results/archive-manifest.json).
The download is staged in the fork for the maintainer to mirror upstream;
`recompute.py` verifies checksums and reproduces the original verdict numerically.
No original record or threshold was rewritten.

The separate review matrix is in
[the review summary](../evidence/qwen21-turbo-b300-review-20261012/results/summary.json):
current main233f0842 versus fixed PR8310b74b, three arms, five fresh-server trials
per arm and three measured full-native-eight-step requests per trial. B300×4,
BF16,1280×704, CFG1, TP1/Ulysses4/Ring1/VAE1, eager, FLASH_ATTN, PNG/base64,
concurrency1 and two full-step warmup rounds were fixed.

| Comparison | Median E2E | Reduction |
| --- | --- | --- |
| Current-main default vs PR with explicit symmem |383.2439 →266.1680ms |30.5487% |
| Both sides with explicit symmem; code-only |374.1702 →266.1680ms |28.8645% |

The first comparison includes a declared communication setting change. All60
formal output files and16 additional feasibility/default/heldout outputs had
identical corresponding native RGBA. All samples remain included; medians/ranges
are descriptive and do not establish significance or tail-latency improvement.
The historical and review evidence must not be substituted for each other.
