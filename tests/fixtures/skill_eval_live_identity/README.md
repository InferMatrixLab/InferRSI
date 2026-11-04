# Observed automatic workflow identity

These are allowlisted fields from authenticated GitHub Actions run API responses
for the two Issue #215 rollout attempts on 2026-10-28. Each JSON contains its
public source URL. Actor profiles, commit authors, credentials and unrelated API
fields are deliberately omitted. The recorded runs completed planning and
publication but **skipped paid execution**; they are not successful paid evidence.

The fixture tests combine this real event metadata with explicitly synthetic
plans/artifacts. They establish that `pull_request_target` run `head_sha` is the
PR head, independently of its historical comparison base and trusted policy
version. They do not assert real provider calls, results, or charges.

`plan-identity-*.json` preserves the five original plan identity fields, canonical
full-plan SHA-256 and control status read from the original planner artifacts.
The full plans are deliberately not fixtures; tests build synthetic artifacts and
use the observed identity without claiming those synthetic bytes have the recorded
original fingerprint.

Sanitized original planner log excerpts corroborate the separate checkout/base:

- [PR 159 plan job](https://github.com/InferMatrixLab/InferRSI/actions/runs/40683638660/job/122800371556)
  - `2026-10-28T11:55:08.8345342Z   ref: e52f0a44cce92aa64a4664b6e2d09107ed0515bc`
  - `2026-10-28T11:55:15.9400078Z  * branch            51fa1d31cc4a805490ddfe8055a36c81d70c4f08 -> FETCH_HEAD`
  - `2026-10-28T11:55:15.9400630Z  * branch            refs/pull/159/head -> FETCH_HEAD`
- [PR 160 plan job](https://github.com/InferMatrixLab/InferRSI/actions/runs/40683653311/job/122800420081)
  - `2026-10-28T11:55:15.7344592Z   ref: e52f0a44cce92aa64a4664b6e2d09107ed0515bc`
  - `2026-10-28T11:55:25.5830247Z  * branch            51fa1d31cc4a805490ddfe8055a36c81d70c4f08 -> FETCH_HEAD`
  - `2026-10-28T11:55:25.5830813Z  * branch            refs/pull/160/head -> FETCH_HEAD`
