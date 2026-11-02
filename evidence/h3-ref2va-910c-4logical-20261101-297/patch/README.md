# Patch status

[C1 patch](c1-h3-bf16-prefix.patch) changes exactly three H3 source/test files.
The [identity record](c1-source-identity.json) binds the tested private commit,
parent, Git tree and file hashes. The engine commit remains private/unmerged;
its diff is published here as an experiment artifact. Native focused
tests passed (10 tests). Two complete fixed requests per duration passed strict
comparison for both 5 s and 15 s, 439 checks each. The 15 s audit also recorded
2,500 actual prefix-attention calls per rank per request. Clean performance
screening measured a 1.5729% reduction at5s and failed the50% performance bar.
Final qualification remains pending; no50% HTTP gain is accepted.

The H3-owned override handles the explicit long-query BF16 fused selection with
independent BNSD head batches and valid K/V-prefix slicing. Default and unsupported
paths retain their parent behavior. It adds no generic backend API, MindIE binary
or common environment change. Other failed candidates are retained in results;
their existence does not establish upstream support. Any eventual engine PR
needs current author checks and the upstream human-review/AI-disclosure gates.

[C10 patch](c10-h3-audio-cache-guard.patch) changes four H3 source/test files.
Its [identity](c10-source-identity.json) binds private commit `0af99184` to the
native-tested bytes. Fifteen focused tests passed, including native NPU execution.
The first full5s-01 request had no failures among39 observed gates. Independent
5s-00 failed CLAP and audio-caption gates; the original C10 configuration is
rejected for5s. Diagnostic HTTP was236.9/243.0s, with no clean performance claim.
The second audit directly recorded50 actual wrapper forwards per rank and
42checks/27vetoes agreeing across all4ranks. The first audit's missing runtime
counters remain a historical evidence gap. No public API, dependency or frozen
quality-gate change is included.

## C12–C23 source artifacts

Each C12/C13/C15–C23 `*-source-identity.json` records its tested engine head,
parent, tree, raw file hashes and `patch_base`. The matching `*-candidate.patch`
is cumulative over C1 `be319692b96413918973b5bd399cdda3f320c574`; apply C1
first, then one selected cumulative patch. These branches are alternatives.
`published: false` in an archived identity describes the engine commit's status
at capture, not this evidence PR's publication state.

C13 adapts [vLLM-Omni PR #9351](https://github.com/vllm-project/vllm-omni/pull/9351)
ordering to the pinned chunked DLO implementation, retaining current manifests
and double staging slots. C15–C23 are local experiments; their native tests and
primitive results do not establish upstream support or complete model quality.
C14 is a prerequisite probe and has no adopted engine patch.

[The experiment report](../results/report.md) records dispositions and limits.
In particular, C21/C22/C23 failed frozen quality and are not promoted for use.
No vLLM-Omni or MindIE-SD PR is delivered by this evidence-only tracking PR.
MindIE-SD source, installed provider binaries and shared environments were not
modified. Future upstream engine contributions require their own focused checks
and review. [Source reconstruction notes](../plan/reproduction.md) state the
external artifacts needed for replay.


[C11 dual-sigma patch](c11-modality-sigma-residual.patch) changes five H3 paths.
Its [identity](c11-source-identity.json) binds61b8efa and20 native-focused tests.
Fn1/Bn0 failed5s-00 audio adherence; Fn1/Bn1 failed its frozen audio-level gate.
These are rejected configurations, not production acceleration claims.

[FP32 residual revision](c11-sigma-fp32-residual.patch) preserves the same
five-path overall boundary and adds a two-file delta over61b8efa. Its
[identity](c11-fp32-source-identity.json) bindsd4d25b4 and23 passed tests,
including three executed NPU tests. The native attempt projection retains two
test-reference failures and the later correction. The production bytes stayed
unchanged across these native attempts. Full5s-00 and15s-00 still failed frozen
quality guards; the patch is not promoted. No frozen scorer/threshold changed.
