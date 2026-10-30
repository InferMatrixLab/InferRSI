# Bounded cloud parser comparison: both artifacts pass, no observed gain

**Result:** baseline and candidate both pass the same 19 public parser checks. The measured pair is a tie (19/19 → 19/19, delta 0). This completes an actual source-generation → independent isolated replay evidence path without requiring a contributor's local Linux/WSL machine. It does **not** demonstrate skill improvement or authorize merging the historical target PR.

The task reconstructs the HTTP-200/error-stream classification failure described in the historical casebook contribution. It is a public development fixture, not the original service, an SSE byte parser, a hidden test, a hardware benchmark, or an iterative coding-agent experiment. The selected historical revisions and prospective bounds remain in the [Issue-scoped execution specification](https://github.com/InferMatrixLab/InferRSI/issues/253#issuecomment-6518412099), not shared automation defaults.

| Evidence | Baseline | Candidate |
| --- | ---: | ---: |
| Independent artifact checks | 19/19 | 19/19 |
| Provider requests | 1 | 1 |
| Reported input tokens | 12,875 | 17,488 |
| Reported output tokens | 1,883 | 1,995 |
| Usage receipt complete | yes | yes |

## Evidence and interpretation

- [Actual generation run](https://github.com/InferMatrixLab/InferRSI/actions/runs/41028614568): one independent request per arm with the same client/model configuration and bounded limits; only the assigned frozen skill bundle changes. No generated source runs in the credential-bearing job.
- [Independent secret-free replay](https://github.com/InferMatrixLab/InferRSI/actions/runs/41029566717): same-host qualification passes first; known-correct control passes 19/19 and deliberately bad starter fails. Both retained source hashes then pass 19/19 in bubblewrap.
- [`bundle.json`](bundle.json) retains exactly two generated source strings; [`replay.json`](replay.json) identifies their hashes and every check; [`capture.json`](capture.json) preserves the original capture state.
- Original capture remains `INCONCLUSIVE / artifact_verification_deferred`. The independently derived artifact result is **both pass / tie**, not a retroactive claim that generation executed inside the verifier sandbox.
- Input length differs because the candidate bundle contains more knowledge. Equal configured bounds do not mean equal realized token consumption. There is one fixed-order pair, no replication or order counterbalancing; no causal/general efficacy inference is supported.

The result supports the bounded parser artifact-delivery path. It does not establish that the historical PR's CUDA Graph/FP8 or hardware claims are correct, nor that the entire PR is merge-ready. Current-head source review, integration and claim-specific evidence remain separate.

## Reproducing only the artifact replay

Use the trusted-main manual workflow [`.github/workflows/skill-eval-cloud-replay.yml`](https://github.com/InferMatrixLab/InferRSI/actions/workflows/skill-eval-cloud-replay.yml), with `evidence_commit` and `bundle_sha256` copied exactly from [`replay.json`](replay.json). The original run used evidence commit `ca684ed407e19aec60c271f0032790ab0973bff1` and bundle digest `a401b170080e87ce5af14d1f3a49a5495d76d4db8da1353882841c5733b26547`. Verify the trusted controller/grader still match the receipt; a changed grader is a new verification revision, not an identical rerun.

This path requalifies the Linux host before executing either retained source, receives no model key and makes no model call. It is **not** permission to rerun generation or spend again. Any new workflow dispatch still requires the applicable manual authorization; unavailable isolation remains INCONCLUSIVE, with no unprotected fallback.

## Accounting

Exactly two model requests were captured. At the frozen owner-attested applicable rate class, usage implies approximately **US$0.398024**; this is a rate-based estimate, not an invoice. The durable ledger conservatively retains the full **US$20.34** claim, with no automatic refund or retry. Previously outstanding daily claims remain intact; no ledger reset was used.

## Scope disposition

The [accepted implementation coordination](https://github.com/InferMatrixLab/InferRSI/issues/253#issuecomment-6497134501) explicitly separates the first deterministic delivery from later judge and full-library decisions.

| Item | Evidence-backed disposition |
| --- | --- |
| Frozen engineering task and public criteria | Delivered; task choice/contract in [the original freeze](https://github.com/InferMatrixLab/InferRSI/issues/253#issuecomment-6497259826). |
| Local author entrypoint software | Delivered separately by #258/#261; this cloud trial does not certify a local iterative agent or Windows sandbox. |
| Bounded cloud generation and isolated replay | Actual two-arm execution delivered here, using #266/#267/#269 software. |
| Wrong-artifact control | Observed on the same replay host; missing evidence, changed input, stale-version and unavailable-isolation guards remain separately covered by software tests/reviews, not fabricated as events in this trial. |
| First-screen readable result | This report states tie, limits and relevance before audit details. |
| Optional semantic judge | Not used; deterministic first-task checks suffice under the existing decision. Later semantic rubric/calibration remains unresolved, not completed. |
| Repository-wide evidence levels / no-environment admission | Still proposed policy, not enacted by this experiment. |
| Full-library evaluation | Not performed; a single development case does not complete it. Shared tasks (#252) and retrieval effectiveness (#255) remain separate. |
| Tracker acceptance / historical PR admission | Owner disposition still required for the broader tracker; this report does not close an Issue or approve a PR. |

<details>
<summary>Exact audit identifiers</summary>

- Generation archive SHA256: `f0cc1da4f2acf41f275362ed1a4ba68084372e1715d4a00a9f4e82db9aec49c0` (artifact `12965020905`).
- Replay archive SHA256: `85f54e8f1c149356357b10c7e09d320eb5791736c5451a61c82b7ede73ac014c` (artifact `12965092373`).
- Bundle SHA256: `a401b170080e87ce5af14d1f3a49a5495d76d4db8da1353882841c5733b26547`.
- Protocol SHA256: `ab806f0dc3c2e36cb8718c30f04f63bf8413baa20e5b6c1b588c23b815a49391`.
- Frozen plan SHA256: `127110f2a2d81ee96368e777d5fd9aade2bb18bef7cb89ef279befe86d836625`.
- Historical approval SHA256: `0e57eb146bdbdbc07f4b19409e25a417bdb6e09881fc66060b3e5a683e181722`.
- Baseline source SHA256: `a671e4e1f9a9079b1cf0bb91be6a27ced248f8633ba71d491e3586c95021daab`.
- Candidate source SHA256: `3e3115e4e97eba8c8b998ac3bff931d7790414d31cb6e09c190e62ac4bf15219`.
- Full controller/evidence revisions, image and verifier identities are retained in `replay.json`; historical skill revisions are recorded in the linked acceptance Issue.

Both downloaded archives were digest-checked. Independent inspection reconciled frozen resource bytes against Git, protocol/config/approval bindings, both parser hashes, the exact 19 grader checks and same-host controls. No source was executed during that inspection.
</details>
