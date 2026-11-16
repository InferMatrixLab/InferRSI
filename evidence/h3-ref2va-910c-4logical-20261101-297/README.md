# MiniMax-H3 Ref2VA: 910C four-logical-device campaign

Governing acceptance issue: [InferRSI #297](https://github.com/InferMatrixLab/InferRSI/issues/297).
Accountable owner: the requester's Codex H3 session, operating under Dong1017.
Claim and plan: [owner receipt](https://github.com/InferMatrixLab/InferRSI/issues/297#issuecomment-6555458151).
Final campaign acceptance remains with the requester.

**Status: Draft tracking snapshot; campaign verdict INCONCLUSIVE.**
No accepted 50% complete-HTTP latency reduction exists. All four final tracks
remain incomplete. C1 passed 439 strict checks on each fixed 5 s/15 s request;
one clean 5 s screening pair measured 291.248→286.667 s, a 1.5729% reduction,
below the unchanged 50% bar. This is not final confirmation.

C0–C23 cover 24 charged direction families. The tested fast lossy profiles have
observed frozen quality failures. Most recently, C21/C22/C23 completed 5s-00
but failed seven/nine/eight quality checks. C23 V2 passed 44 native tests and
reduced a static 50-call attention cycle by 66.46%; its full 5 s diagnostic HTTP
was 199.065 s. These observations do not qualify model quality or HTTP gains.
No 15 s or clean timing extension follows for those rejected profiles.

Start with the [experiment report and 24-direction ledger](results/report.md),
[four-track execution snapshot](plan/execution-checkpoint.json), and
[replay/availability notes](plan/reproduction.md). The inventory's publication
hash map verifies available files; it does not qualify device or model behavior.

Downstream code is tracked in [vLLM-Omni Draft PR #9745](https://github.com/vllm-project/vllm-omni/pull/9745).
It ports only C1 to main, preserving newer piecewise/query-range dispatch, and
passed [12 source-bound native tests](results/c1-upstream-main-native.json).
The historical full-model C1 results remain tied to `be319692`; full-model
quality and clean HTTP have not been rerun on the new upstream base.

The scope is 5s/15s × lossless/lossy, 1344×768 at 24 FPS, 124/362 frames,
original BF16 dense Ref2VA, 50 steps, four logical 910C devices. This is separate
from the eight-device 910B1 campaign in #294 and the original eight-device requirement.

- `plan/`: execution identity, original budget, protocol and frozen contract bytes.
- `results/`: scoped numerical results, rejected operator variants and automatic quality comparisons.
- `patch/`: tested private C1 and C10–C23 identities and their exact engine patches.
- `validator/`: byte-preserved validator/scorer snapshots and checksums.

The original B0 is retained. Migration and candidate sources are separate.
Diagnostic HTTP values, operator improvements, unit tests and numerical equality
are distinct conclusions. Missing quality samples remain incomplete; failures are
not removed because other samples pass. The heldout clips have not been generated.
See [execution checkpoint](plan/execution-checkpoint.json) and [results](results/README.md).

Private connection details and original raw captures stay outside this repository.
This Draft tracking snapshot contains sanitized projections and engine patch
artifacts. Independent review, four-track acceptance and production qualification
remain incomplete. The inventory registration checks layout/bytes only.
