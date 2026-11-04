# Frozen task: serving response classification v1

This is a reconstructed CPU regression fixture derived from the public observation
in [PR 90](https://github.com/InferMatrixLab/InferRSI/pull/90), not the original
server code, hardware experiment, or qualification of that whole PR.

Source: [silent capacity and error failures](https://github.com/InferMatrixLab/InferRSI/blob/86f003364804d116b3202c4d807cc898a3a02ade/src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/qwen38-silent-capacity-and-error-failures.md).
Source base: `a1ee3266466194c16f4e2159ab845b758ed9561b`.
Source candidate: `86f003364804d116b3202c4d807cc898a3a02ade`.
Controller implementation baseline: `ab03f3ffb8f2e5bc02c304828c5c41890eef673e`.
Task contract frozen before adapter implementation and before any agent trial.

## Starter and allowed change

`parser.py` SHA-256:
`6d9d97fbf9b973c532447ad794a7a87c5c18a4d5d57979d91384f0861836b7c6`.
Only `parser.py` may change. Its API is
`evaluate(status, frames, requested_tokens) -> {"success": bool, "reason": str}`.
The starter incorrectly accepts every HTTP 200 response. Artifacts are bounded
UTF-8 Python source, at most 64 KiB. No dependency installation is needed.
Task JSON, selected skill bundle, schema, validator and all other workspace files
are frozen; additions outside this single allowed file invalidate the trial.

## Public decision contract

Inputs are an HTTP status integer, a list of already decoded frames, and a
positive integer requested token count. This is not a wire-format SSE parser.
Content frames have exactly `{"content": <string>}`. A terminal frame has exactly
`{"finish_reason": "length" | "stop", "completion_tokens": <nonnegative int>}`.
At most one optional final string `[DONE]` is allowed; it is not a terminal frame.
A terminal may not be followed by content or another terminal. Boolean counts
are not integers. All test vectors and this contract are public, not held out.

Apply HTTP failure first; otherwise inspect frames in order. An error dictionary
(containing `error`) gives `stream_error`; invalid fields, duplicate/post-terminal
frames, or a misplaced/duplicate DONE give `malformed_frame`. Then require a
terminal (`missing_terminal`). For length, completion_tokens must equal requested;
for stop, it may be any integer in [0, requested]. Otherwise `token_mismatch`.
Only a valid length or stop completion returns success=true, with reason `length`
or `stop`. Every failure returns success=false with its specified reason.
HTTP non-200 returns `http_error`. Expected verdict checks both fields, not merely
the boolean. Capacity planning, exception logging and GPU timing are out of scope.

## Controls, execution and evidence

Independent public checks cover length, early stop, HTTP error, mid-stream error,
missing terminal, length/stop token mismatch and malformed frames. Software
controls include known-correct and incorrect artifacts, missing artifact, frozen
input tamper, changed/stale PR head and unavailable isolation. These controls are
not model outcomes or evidence that a skill improves an agent.

The controller retains the actual parser bytes and their hash independently of
the final agent message. Report revalidates those bytes using the trusted in-tree
verifier; agent-reported PASS is not authoritative. Artifact code is executed only
inside a verified bubblewrap namespace with clean environment, no network/home,
read-only runtime and bounded process/time/output resources. Isolation unavailable
means INCONCLUSIVE; there is no unsandboxed fallback. Verifier tests are outside
the writable artifact and are not mounted into its execution view.

Baseline/candidate get identical starter and task, separate sessions and explicit
selected skill exposure. This does not test retrieval. Existing Codex
`danger-full-access` is not OS confinement and must not be represented as such.
Real agent execution is blocked until its environment/access, oracle and other-arm
visibility, model/settings and trustworthy cost bounds are verified and recorded
in an authorized frozen plan. Local wall-clock/token-stop observations alone are
not a per-call dollar cap. No model run is authorized by this fixture.

Before a real run freeze exact source/bundle/task/controller/verifier hashes,
execution image/runtime, order/repeats, tool access, timeout and whole-run budget
(including setup, selector, retries and any judge). No silent retries. A later
head change requires explicit revalidation before a PR recommendation. No gain or
negative evidence is valid delivery, not automatic PR rejection; a task PASS is
not whole-PR acceptance. Author posts report and accessible artifacts; reviewer
independently verifies scope/results. No CI result-import or automatic acceptance.
