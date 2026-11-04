# Sandbox dependency resolution: preserved no-wheel failure

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE — no quality or performance qualification.**

The initial submission draft was rejected before execution: dependency compilation
could execute source build backends before lock review, and inherited UV/PIP
settings could alter package sources. Version2 explicitly disables builds,
clears inherited resolver settings, fixes the PyPI index and records that policy.
Independent review found no blocker for the bounded resolve-only step.

CPU job1985 failed1:0 after166 allocated seconds on4CPUs and zeroGPUs. Source
checkout and passive declaration parsing completed. The build-tool lock resolved
five packages, but the official wget>=3.2 dependency has no usable wheel under
the no-build policy. Runtime dependencies and the complete freeze manifest did
not resolve. The proposed environment was not created; nothing was installed,
and no dataset, model, generated solution or full evaluator was executed.
Allocation release was checked. Failed output and the original scripts remain
in controlled storage, with sanitized identities in sandbox-resolve-1985.json.

This is a readiness failure, not model failure. Do not silently allow unrestricted
source builds or remove official dependencies. The next proposed step is static
review of explicitly pinned source-only package archives and exact build tools,
followed by a separately reviewed bounded build if justified. The resulting
wheel bytes and their origin must be authenticated before retrying resolution.
No successor build, install or sandbox probe is claimed here.

No GPU budget was spent; readiness remains2388/7200GPU-seconds, with the earlier
147seconds accounted separately. There is no measured E2E performance effect.
The actual generated-code executor and full quality freeze remain unqualified.

Primary package reference: [wget3.2 release files](https://pypi.org/project/wget/3.2/#files).

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand`: `sha256:97f1b1cb31bd88aca212725cc15c0cdd75574bf31ea09071e81fa7831d2a9972`; readback verified and rejected draft retained.
