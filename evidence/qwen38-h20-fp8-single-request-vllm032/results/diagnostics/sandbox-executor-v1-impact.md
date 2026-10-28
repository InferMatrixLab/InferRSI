# External export and official result binding verified

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**Fixed trusted readiness checks succeeded; campaign/model quality/E2E remain INCONCLUSIVE.**

CPU2018 completed with scheduler exit0:0 in186seconds on4CPUs and zeroGPUs;
the allocation is released. Accounting supplies the final state after the
controller's short job retention expired. One SSH collection attempt failed;
only evidence collection was retried. The experiment was submitted once.

Four exact handwritten fixtures passed through the parameterized external-export
entry and the pinned official EvalPlus call. The expected base/plus pairs were
correct pass/pass, plus-only error pass/fail, exception fail/fail, and input timeout
fail/fail. A deterministic comment made the original result1,145,014bytes, larger
than the old1MiB limit; its SHA256 is
`48b84ec5e8c77b8966b539cd201d4cb2d4482001b8d7f2fb9e2532f54de824a4`.
The exact result bytes, parsed solutions/task IDs, dataset MD5 and all input
SHA256 identities agree with the supervisor and execution record. The normal
sandbox call took23.39196834107861seconds, including entry and evaluation; this
is not a model service timing or comparison with the smaller prior fixture.

All9 exercise checks succeeded. Reusing the old output directory was rejected.
Wrong-policy and wrong-export controls each reached the authorized inner entry,
then exited1 with the exact expected digest-mismatch reason and empty score
stdout. All three namespace-init and launcher exits are confirmed, with stable
final output hashes, no fallback forced cleanup and no cleanup errors. These
controls reuse the previously verified pidfd/startup/finalizer implementation.

The25,249-entry readonly runtime inventory is unchanged across normal and negative
runs, with97packages and43 pinned evaluator Python sources. All12 postflight
checks pass. Installed packages and the original helpers were unchanged. Runtime
and wrapper bytes match the independently reviewed11-source lock. The new
readiness policy preserves official EvalPlus memory/timeout defaults while using
finite outer4GiB AS/120second CPU/180second wall bounds,64MiB files and256MiB work
tmpfs. It is not a complete164-task configuration or an aggregate16GiB hard cap.

Independent review corrected and retained the first incompatible four-field
export schema, stale supervisor/result-digest binding and missing result-row task
identity check. Eighteen host-only controls include those negative cases, binding
failure and timeout finalization. An initial timeout mock lacked a pipe reader
and produced BrokenPipeError; its original fixture is preserved. Runtime negative
controls also require exact error reasons, so unrelated startup errors cannot
satisfy the expected rejection. Original failed preparations remain available.

The runtime record remains `qualified:false` with a null frozen protocol. No
heldout task or model-generated program was executed. Full164-task resource and
generated-code qualification, owner-confirmed statistics/retrieval decisions,
complete command/validator freeze and formal paired performance runs remain
pending. **Measured E2E effect: not measured.** GPU readiness remains2388/7200
seconds, with the initial147seconds accounted separately.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand` revision `sha256:319081d07811969179c2fbfc31a9fb134f3f1962e25fa5fc4ca9cfa969a092b8`; readback verified.
