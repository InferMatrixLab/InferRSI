# Frozen campaign contracts and execution checkpoint

The governing issue is [#297](https://github.com/InferMatrixLab/InferRSI/issues/297).
This tracking snapshot records actual execution; it does not authorize a new
budget, replace original B0 or establish campaign acceptance.

- [Execution manifest](execution-checkpoint.json): source/model identities, hardware,
  private-stack versions, workload, original deadline and outstanding scope.
- [Lossless contract](frozen-lossless-contract-v1.json): strict latent/schedule and
  decoded RGB24/PCM checks, qualified original source, and frozen timing protocol.
- [Lossy contract](frozen-lossy-contract-v1.json): original pre-search scorer bytes,
  revisions/weights, ten fixed samples, aggregation and automatic quality gates.
- [Requester decisions](requester-decisions.json): user-selected tracks, no human
  output checks, target and shared ceiling; later execution does not reset them.

Original B0 repeatability passed at 5 s and 15 s. Migration numerical comparison
passed at 5 s; default dense migration 15 s remains unqualified. C1 subsequently
passed full strict 5 s and15 s comparison,439 checks each. These are numerical conclusions, not latency
acceptance. The model's 81 files / 144051182613 bytes were fully SHA/LFS verified
in private preparation; the raw private manifest is not bundled.

Every actual diagnostic/native/operator run used the pinned InferRSI external
executor. The first native CLI clean 5 s AB pair completed: strict quality PASS35
plus the separate PASS439 audit, source integrity and cleanup passed. Performance
FAIL: 1.5729% reduction versus the required50%. Physical NPU discovery IDs1,2 map to the
four execution logical devices2,3,4,5; native inventory remains8physical/16logical.
The case-local driver owns fresh servers, readiness, warmups, measured requests,
media identities and native cleanup; it returns complete HTTP latency in ms.

Clean screening requires 2 warmups and 3 measured requests per fresh server.
Final confirmation requires 3 fresh pairs in AB/BA/AB order, the same inner
request counts, and each pair plus the aggregate reaching the 50% reduction bar.
Keep profiler, audits and CPU scoring out of clean timing. The completed
[5 s screening](../results/c1-clean-5s-screening.json) is not final confirmation;
15 s clean timing and complete four-track acceptance remain outstanding.

The current requester-authorized ceiling is 24 directions / 32 wall hours /
128 logical-device-hours, including preparation, failures, retries, scoring and
cleanup. It started at 2026-11-01 17:19 +08 and ends at 2026-11-03 01:19 +08.
The original 12-direction / 16-hour / 64-device-hour allowance is retained as
decision history in requester-decisions.json. The original start never changed.
All 24 families are charged. No extra final-confirmation amount is authorized.

[Replay and availability](reproduction.md) separates local byte checks from
device replay requiring the external artifacts and original private environment.
