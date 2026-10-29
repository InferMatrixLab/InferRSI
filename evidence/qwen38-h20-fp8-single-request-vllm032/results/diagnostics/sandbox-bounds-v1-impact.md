# Missing pidfd API exposes a startup-gate and evidence race

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**Diagnostic FAIL; campaign, task quality and E2E INCONCLUSIVE.**

CPU2012 failed2:0 in81seconds on4CPUs/zeroGPUs; allocation released. Each of
five supervisor cases encountered AttributeError because the registered Python
does not expose os.pidfd_open. This establishes an absent Python API; kernel
pidfd syscall availability remains untested. The owned launchers were killed and
reaped with code-9, but namespace PID1 was never bound or observed exiting.

Full raw collection then disproved the initial live-report inference that no
payload ran. Closing the block pipe during failure cleanup permits bubblewrap's
ignored read result to reach EOF and continue setup. Actual late payload output
exists after supervisor failure: the bounds case reports17 true checks, normal
and timeout announce two children, and launcher-kill announces one child plus a
fork EAGAIN traceback. The synthetic evaluator also reaches worker creation and
fails fork with EAGAIN; no completed four-case score is retained. These late
observations are not accepted as a correctly supervised policy or cleanup test.
Thread-creation RuntimeError and EAGAIN are retained without assigning a sole
resource cause; concurrent late payloads may affect UID-scoped task accounting.

All five supervisor reports hashed stdout as empty. Four final stdout files are
nonempty and disagree with those digests; synthetic stdout remains empty with a
nonempty error log. Original reports, final output bytes and both identities are
preserved. The first local recording assertion caught the mismatch before any
incorrect public result or KnowledgeStore update. The live commentary was
corrected once the complete archive was inspected. This is a failed startup and
output-stability protocol, not merely a Python compatibility failure.

All10 postflight checks pass; before/after25,241-entry readonly inventories are
identical, with97packages and43 checked evaluator source files. Executed sources
match the reviewed proposal. No environment change, heldout task, model-generated
program or measured E2E effect occurred. Preparation failures and rejected drafts
remain retained, including the local-control capture conflict.

A subsequent proposal must check actual pidfd capability before launching the
sandbox and use a payload handshake that requires an explicit valid token; EOF
must reject execution. It must observe namespace exit before hashing final output.
Direct Linux bindings, if used, must preserve stable pidfd identity and explicit
ABI checks. No qualification or candidate-search activation follows this failure.
Readiness GPU usage remains2388/7200seconds; initial147seconds remain separate.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand` revision `sha256:acd39f49c345c3162d4160fbb0f780fb8f0682b6cc15d0a42dc63f1b8cbfd691`; readback verified.
