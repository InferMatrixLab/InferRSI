# Task-local bubblewrap build stopped at mandatory libcap preflight

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE for isolation, quality and E2E; build execution failed.**

CPU2000 ended FAILED1:0 after1allocated second with4CPUs/zeroGPUs; allocation
released. The reviewed wrapper authenticated its inputs and recorded the compiler,
then pkg-config could not resolve libcap development metadata. Its truthful terminal
record identifies dependency_preflight. Neither the build environment nor install
prefix was created; no compilation, utility test, namespace probe, evaluator or
model ran. This does not establish whether a runtime libcap library exists.

Preparation used the official bubblewrap0.13.1 archive, matching its published
SHA256, and two exact official wheels (Meson1.12.1, Ninja1.13.2) checked against
actual CPU1997 target tags. Historical readset.json predates the download; its
state is preserved, while inputs.json records later successful preparation.
Raw archives/wheels/metadata and scheduler details remain outside this public
bundle. The six-input checksum file records their identities, not local availability
or an inventory-tool verification of those external bytes.

Two initial local extraction guards failed before source extraction/wheel fetching:
normal root-directory spelling and two upstream license symlinks. The final guard
allows those exact entries with data-filter extraction. Two independent review P2s
also rejected unexecuted build wrappers: inherited DESTDIR could redirect install,
and inherited NINJA could bypass the locked tool. Both rejected wrappers are
preserved. Final wrapper explicitly clears/overrides DESTDIR and selects the locked
Ninja path. Exact-line controls passed; the DESTDIR control binds the preceding
wrapper, whose relevant lines are unchanged in the final version. Independent
review cleared final ed569b39 and the authenticated source/wheel closure for this
bounded build only. No declined version executed remotely.

Next preparation must supply a reviewed task-local libcap development dependency;
do not weaken the isolation options or use a system installation. Existing97-package
EvalPlus environment remains unchanged and unqualified. There is no measured E2E
effect. GPU readiness stays2388/7200seconds, initial147separate; formal performance
and quality acceptance remain incomplete.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand` revision `sha256:322c399b99fd3de65975b865e99e751d29b660e38bf41bcd5364227cb8c3b135`; readback verified.
