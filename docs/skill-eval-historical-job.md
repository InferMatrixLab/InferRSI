# Fixed historical generation job

This manual main-only job is the bounded cloud-generation half of the #253
public parser pilot. It uses the existing repository provider secret; it does
not create credentials, execute generated source, accept PR code, or replace
independent secret-free artifact replay.

## Authority and freeze

There are no dispatch inputs. Main retains only a reviewed issue-comment locator
(issue, comment ID, author and complete body SHA256). The acceptance Issue owns
the experiment ID, accounting identity, historical revisions, limits and
qualification identity. Shared workflows/controllers contain no campaign pins.
The generic admission ceiling remains two requests and USD 20.34; no retry is
permitted. The dedicated configuration retains the
existing daily ledger and the audited empty #267 genesis; it does not reset
prior daily reservations. Its pricing group is an owner attestation, not an
independent invoice audit. Unknown/changed pricing or expired configuration
blocks execution.

The first step checks main/manual/operator/first-attempt identities, fetches the
exact public issue comment from the fixed repository API without redirects, and
verifies its issue, author, full body hash and strict JSON schema (including
duplicate-key rejection). Only validated hexadecimal revisions are passed as
Git argv, never interpolated into a shell; both arms use raw pinned Git objects. It freezes the task, starter, full-context
client configuration, skill manifests, protocol and approval receipt before
provider-secret injection. The receipt adds the actual immutable main revision
and deterministic plan/protocol hashes; it is not supplied by a PR, a dispatch
input or a model. Its authority comes from the reviewed main selection of the issue-scoped
authorization and the trusted prepare-to-execute path, **not from possession of a self-generated hash**.

The execution step rechecks the pinned issue comment before admission and each
request grant, as well as every frozen digest, current main, live Actions run
identity, operator, qualification run, provider pricing and both durable ledgers.
A stable logical experiment identity prevents a new run ID or replacement receipt
from replenishing the experiment. Workflow reruns and attempt > 1 are rejected.
Partial/uncertain reservations remain charged conservatively; this job does not
refund or retry automatically.

## Credential and execution boundary

Only the trusted controller step receives the existing provider secret and the
repository token. The repository token is used for live checks and ledger CAS;
it is excluded from the provider subprocess environment. The provider worker
receives its existing key and a loopback authorization broker, never a repository
write credential. The full-context client has only structured submit output.

Generation and its automatic capture report do not invoke the parser verifier,
even if the host can run bubblewrap. The provider cannot write workspace files;
a trusted writer accepts only bounded parser bytes. No supplied parser is
imported, compiled, run, or passed to another agent in this job.

A separate environment-cleared step packages only fixed public inputs, bounded
parser data, hashes and selected numeric/status observations. Raw provider logs,
private environment values and arbitrary model metadata are not uploaded. A
complete valid pair yields `bundle.json`; an incomplete pair retains its capture
status and available source bytes without inventing a result. The independent
replay workflow still requalifies its own host and receives no model secret.

## Operation

After current-head review and CI, a qualified operator manually dispatches
`.github/workflows/skill-eval-historical.yml` on main. It cannot be used for a
new experiment or expanded budget by changing dispatch parameters. Changing the
issue record invalidates its pinned body hash until a separately reviewed main
selection is made; deletion, unknown author, transport failure or mismatched
bytes fail closed. Inspect the
retained `historical-generation-<run>-1` artifact, reconcile the frozen plan and
source hashes, then use the separate fixed-data replay path. Neither a successful
job nor two passing parsers establishes skill benefit or closes #253.

Offline tests cover rejected identities/retries, changed policy/freeze,
qualification failure, pre-secret preparation and fixed workflow structure.
Real provider execution and measured comparison remain separate evidence.
