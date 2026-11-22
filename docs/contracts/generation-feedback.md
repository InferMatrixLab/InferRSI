# Generation feedback: trusted-host boundary

This documents the first-phase boundary accepted in
[#371, decision 7084973960](https://github.com/InferMatrixLab/InferRSI/issues/371#issuecomment-7084973960).
V25 assigns frozen feedback policy to Harness. The current
`inferrsi.harness.generation.prepare_generation` does not enforce that policy:
it receives a host-built `candidate_context`, retains the delivered context and
seals the generation plan. There is no automatic next round on this path.

## What the host must decide

Before calling `prepare_generation`, the trusted host must establish which
feedback may be delivered under the frozen plan and protocol, and keep final-only
acceptance results out of the next candidate context.

1. Check the permitted feedback identities and scopes against the frozen inputs.
   `CampaignPlan.allowed_feedback` and `ProtocolV1.feedback_visibility` contain IDs;
   `CandidateContext.allowed_feedback` contains concrete `ArtifactRef` values.
   The host owns the mapping and authorization. H currently provides no production
   port that establishes that mapping or filters an assessment for the host.
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
binding. Those operations establish the identity of supplied material, not that
its feedback contents were authorized by a frozen policy. Apps does not select
feedback visibility, and B continues to own grading.

Existing function signatures and callers are unchanged. This boundary adds no
policy-reference argument, schema, automatic retry or new enforcement claim.
Policy enforcement is tracked separately in
[#586](https://github.com/InferMatrixLab/InferRSI/issues/586); its detailed reference
and scope-mapping contract must be accepted before implementation.

## Acceptance wording

The first-phase #371 acceptance record must describe this as **host precondition,
not proved by H** (宿主前置责任，未由 H 证明). Tests of retained bytes, declared input
closures, or a single generation cannot be reported as proof of feedback-policy
enforcement. V25 remains the architectural requirement; the implementation limit
and its follow-up stay explicit until independently reviewed enforcement lands.
