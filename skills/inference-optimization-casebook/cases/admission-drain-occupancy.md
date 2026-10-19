# Admission occupancy is not whole-run occupancy

Kind: Case. Origin: internal experience. State: historical observation;
campaign INCONCLUSIVE. This extraction adds no performance validation.

## Observation

In the recorded Drama3 B300 C64 continuous-admission diagnostic (256 requests),
the owning CPU annotations counted 802 scheduler steps: 1 prefill, 37 mixed,
762 decode and 2 empty. During the client-admission interval, pure decode averaged
60.718 active requests out of 64; final drain averaged 8.793. The whole-trace
pure-decode average was 28.146. Scheduled prompt entries may be chunks, not
unique requests. These are recorded diagnostic observations, not new measurements.

## Action

The original investigation separated the client-admission and drain intervals,
counted scheduler execution annotations rather than PIECEWISE graph fragments,
and retained the full request cohort for acceptance. No measurement is rerun by
reading this case.

## Interpretation

A whole-run mean batch can be dominated by drain. Using it as sustained-admission
occupancy can misidentify scheduling headroom. Conversely, a near-full batch in
a selected interval does not establish a service speedup. Client in-flight counts
also include queueing and codec work; CPU/GPU clock alignment was approximate.
This interpretation is narrower than a causal diagnosis of the service limit.

## Applicability and counter-signals

Use for finite autoregressive service cohorts with ongoing admission, mixed
prefill/decode and a final drain. Retain phase definitions and actual generated
work. Counter-signals include no ongoing admission, incomparable input/output
lengths, clocks that cannot be aligned and missing owning annotations. Kernel
sums, annotation unions and SM utilization are different quantities.

Keep all requests and complete quality/repetition groups in the end-to-end
acceptance metric. Do not replace it with a selected-phase rate or a model-only
microbenchmark. Hardware, model and runtime scope comes from the original frozen
plan; another engine or device needs its own evidence.

## Preserved evidence

- [Acceptance issue #10](https://github.com/InferMatrixLab/InferRSI/issues/10).
- [Original diagnostic section at the inspected repository snapshot](https://github.com/InferMatrixLab/InferRSI/blob/c13027983b853fee3700de6aabde52b72e61885a/evidence/drama3-b300-scale150/results/diagnostic-lessons.md#continuous-admission-profile-and-mixed-backbone-2026-10-16).
- [Frozen plan](https://github.com/InferMatrixLab/InferRSI/blob/c13027983b853fee3700de6aabde52b72e61885a/evidence/drama3-b300-scale150/plan/plan.json).
- Original artifact identity: `drama3-mixed-20261016/vllm-continuous-schedule.json`.
  Recorded raw trace SHA256:
  `29e5cafe329cb85eaba69db7536a28a83fb7e3ac29bc154fc8747f317f6a4b3f`;
  request metadata SHA256:
  `bd50166976a4753b33c8aeb5a774ebb5711c74ccbba0df1843885f353ecdc996`.
  Raw bytes were not independently retrieved or rehashed for this extraction.
- [Typed source and scope record](admission-drain-occupancy.json).

The local frozen evidence remains untouched. Observation is carried from its
2026-10-16 report; extraction inspected that section on 2026-10-16. No missing
model pin, runtime revision or repeated acceptance outcome is reconstructed.
