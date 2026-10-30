# Isolated replay of a cloud-generated parser pair

The manual `skill-eval-cloud-replay.yml` workflow removes any requirement that
an author host the verifier. It performs no model calls and receives no model
credentials. Generation is separate; neither remote replay nor green CI proves
producer isolation, causal comparability, generalization, or campaign acceptance.

## Data contract and transport

An operator first reviews and publishes the **data**, not executable controller
code, at `artifacts/skill-eval-cloud/bundle.json` in this repository. Publication
must be authorized and checked for private data. The dispatch takes only the
exact 40-character evidence commit and SHA256 of the complete bundle bytes.
The trusted controller is checked out from the dispatch's exact main revision,
not the evidence commit. Its unauthenticated HTTPS read uses one fixed repository
and path, rejects redirects, and reads at most 1 MiB plus one rejection byte.
There are no archive extraction, arbitrary URLs, user paths, custom graders,
configuration commands, or imports of uploaded Python.

The UTF-8 JSON object has exactly these keys (duplicate keys are rejected):

- `schema_version`: `engineering-cloud-replay-v1`.
- `task_id`: 1–128 ASCII letters, numbers, underscores, dots or hyphens; an opaque
  provenance identifier, not a path or executable task selector.
- `request_sha256`: SHA256 of the trusted `engineering.REQUEST` UTF-8 bytes.
- `grader_sha256`: SHA256 of the trusted `skill_eval_engineering.py` file bytes.
- `inputs_sha256`, `protocol_sha256`: lowercase 64-character provenance digests.
  These are retained, **not independently authenticated by this receipt**.
- `artifacts`: exactly two objects, ordered baseline then candidate, each with
  exactly `arm`, `source`, and `sha256`. Each source is nonempty UTF-8, at most
  65,536 bytes, and must match its digest. Both arms are validated before either
  is executed. JSON escaping does not change the source-byte hash.

## Execution and interpretation

The controller first requalifies the reviewed good and bad controls on this
same runner. If qualification is not PASS, neither submitted artifact runs.
Each parser then executes only through the existing bubblewrap verifier under
its filesystem, network and resource bounds. Missing isolation never falls back
to host execution. The shell clears inherited environment variables and never
passes its repository token to parser execution. No host security policy is
weakened. Model source and outputs are not echoed into workflow logs.

`replay.json` retains the qualification, controller/evidence identities, bundle
and source hashes, and separate per-arm checks. Its top-level PASS means **both
replays were delivered**, not that either parser passed or that a skill helped;
negative per-arm results are valid evidence. Invalid ingress, infrastructure
failure or lost isolation yields INCONCLUSIVE and a nonzero job. Original
producer/capture failures remain unchanged; reconcile the receipt against the
frozen experiment protocol and original evidence before any comparison claim.

The workflow is main-only and manual, independent of normal PR/merge CI. It does
not comment, accept, close or merge anything. A reviewer can independently
regenerate the bounded replay from the retained commit and bundle digest.
