# Generation feedback: trusted-host boundary

This documents the first-phase boundary accepted in
[#371, decision 7084973960](https://github.com/InferMatrixLab/InferRSI/issues/371#issuecomment-7084973960).
V25 assigns frozen feedback policy to Harness. The current
`inferrsi.harness.executor.prepare_generation`, when called without an explicit
`feedback_policy_ref`, does not enforce that policy:
it receives a host-built `candidate_context`, retains the delivered context and
seals the generation plan. There is no automatic next round on this path.

## What the host must decide

Before calling `prepare_generation`, the trusted host must establish which
feedback may be delivered under the frozen plan and protocol, and keep final-only
acceptance results out of the next candidate context.

1. Check the permitted feedback identities and scopes against the frozen inputs.
   `CampaignPlan.allowed_feedback` and `ProtocolV1.feedback_visibility` contain IDs;
   `CandidateContext.allowed_feedback` contains concrete `ArtifactRef` values.
   On the absent-policy path the host owns the mapping and authorization. The
   separate [opt-in profile](generation-feedback-policy.md) verifies original
   scope/check proof Refs when the host supplies a policy Ref and source records;
   it does not filter a whole assessment for the host.
2. Supply only the approved fixed feedback bytes and references. A complete
   `AssessmentRef` or `AssessmentSummary` can contain other claims and scopes;
   permission to reveal one check does not authorize forwarding the whole result.
3. Construct `candidate_context.allowed_feedback` from that approved material.
   Keep final-only information out of other delivered channels as well, including
   task material and context text. An empty feedback list alone does not prove
   that other content is free of final-only results.
4. When authorization or scope identity cannot be established, stop the host's
   next-generation handoff. Do not infer permission from a successful assessment,
   a readable artifact or the absence of an automatic loop.

The host may show complete retained results to an authorized human reviewer;
that is separate from supplying them to the next candidate generation.

## What the current ports establish

Apps `CandidateProvider` checks the declared artifact closure and prepares the
generation specification. H retains the bytes and commits the generation-plan
binding. Without the opt-in policy Ref those operations establish the identity
of supplied material, not that its feedback contents were authorized by a frozen
policy. Apps does not select
feedback visibility, and B continues to own grading.

Existing callers without a policy Ref retain their behavior. The restricted
opt-in implementation and its accepted reference/scope-mapping contract are
tracked in [#586](https://github.com/InferMatrixLab/InferRSI/issues/586) and the
[profile contract](generation-feedback-policy.md). Policy approval, free-text
content and unexpressed mixed scope use remain trusted-host responsibilities.
Neither path adds an automatic retry, search controller or whole-assessment
feedback grant.

## Acceptance wording

For the absent-policy path, the first-phase #371 acceptance record must describe
feedback authorization as **host precondition,
not proved by H** (宿主前置责任，未由 H 证明). Tests of retained bytes, declared input
closures, or a single generation cannot be reported as proof of feedback-policy
enforcement. V25 remains the architectural requirement; the implementation limit
and its follow-up stay explicit. Opt-in acceptance must name the restricted
profile and its checks rather than claiming unrestricted V25 enforcement.
