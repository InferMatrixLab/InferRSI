# Advisory PR Review Score

Use this score on request after assessing the reviewed revision. Base each
rating on the pinned diff and evidence. Apply the existing PR review verdict
and campaign verdict rules independently of the score.

| Dimension | Weight | What to assess |
| --- | ---: | --- |
| Scope and intent | 15 | Governing Issue, accepted scope, hypothesis or requested behavior, and the fit between the diff and the delivery slice. |
| Correctness and safety | 25 | Architecture ownership, public contracts, failure handling, cleanup, and the correctness of any changed evaluator or validator. |
| Validation | 20 | Focused tests, relevant CI, and replay or verification of the affected artifacts. |
| Claim evidence | 30 | Frozen gates, source and environment pins, trial index, measured outputs, and a verdict supported by the bundle. Use the [evidence rules](../../../../docs/contributing.md#evidence-and-claims). |
| Simplicity | 10 | Focused changes, reuse of the owning API and validator, and avoidable duplication or state. |

## Hard scoring requirements

- **Claim evidence is 0/3** if any [required model artifact](#required-model-artifacts)
  is missing or inaccessible. Apply the zero even when the run has hashes,
  summary metrics, or a recorded campaign verdict.
- **Simplicity is 0/3** if the diff adds or rewrites any explanatory code
  comment in maintained source, tests, scripts, or config. License headers,
  shebangs, tool directives, and required docstrings are exempt. Treat
  byte-preserved historical evidence as data. Score a comment-only removal
  under the normal Simplicity criteria. A correction that leaves rewritten
  explanatory prose still triggers the hard zero. Express behavior through
  code, tests, or relevant docs.

## Required model artifacts

For each evaluated case, list the output modalities promised by the claim or
required by the frozen protocol. Use the request and protocol to determine the
required outputs. Provide the actual outputs and applicable raw benchmark
records from the pinned run. Label input media and generated outputs. For a
comparison, provide the required outputs for both sides.

- **Text output** requires the returned text or response payload.
- **Speech output** requires playable generated audio. For TTS, include the
  exact synthesis text.
- **Image generation or editing** requires decodable image files.
- **Video generation** requires playable video files and, for audio-video
  results, the generated audio track in playable form.
- **Music or sound generation** requires the generated audio and any prompt
  and conditioning inputs used by the run.

| Evaluated case | Evidence available to the reviewer | Effect on Claim evidence |
| --- | --- | --- |
| An Omni request uses video and audio input with a text-only output protocol. | Full returned text and all other required records are accessible. | Continue scoring. |
| The same workload has a frozen text-and-speech output requirement. | Returned text, input audio, and a digest for generated speech. | 0/3 because the generated audio is unavailable. |
| An image-only comparison runs through an Omni serving stack. | Both sets of images and the required benchmark records are accessible. | Continue scoring. |
| The claim requires generated video and audio. | The video plays and the generated audio track is inaccessible. | 0/3 because the generated audio is unavailable. |

Use attachments or stable links the reviewer can open. Match each file to
its revision, input, and frozen quality protocol. Hashes and metrics supplement
the actual files. The [campaign evidence rules](../../../../docs/contributing.md#evidence-and-claims)
govern the campaign verdict.

## Rating and delivery

Apply the hard scoring requirements first. For each remaining applicable
dimension, choose the highest rating supported by the evidence.

- **3** — the applicable checks are supported by matching evidence.
- **2** — the main checks are supported, with a bounded gap.
- **1** — some checks are supported, with a material gap or inconsistency.
- **0** — the dimension lacks usable evidence or a material contract violation
  is confirmed.

Use `N/A` when a dimension is outside the change's scope. For example, claim
evidence can be `N/A` for a scaffold-only change without a campaign claim.
Count each gap in its primary dimension. Identify the source of each rating,
including the difference between recorded experiment results and checks you ran.

The formula is `100 * sum(weight * rating) / (3 * sum(applicable weights))`.
Round to the nearest integer, with halves up. For a scaffold-only implementation
with Claim evidence `N/A` and the other ratings 3, 3, 2, and 3 in table order,
the applicable weight is 70. The score is `100 * 190 / (3 * 70)` rounded to
**90/100**.

Withhold the total if the snapshot is stale or a material portion of the diff
could not be reviewed. Report the base and head, total, dimension ratings with
evidence, and the highest-priority remaining action. Use the existing
conversation and formal review rules for delivery.
