# Bounded KV live launcher (inactive implementation)

This is an Issue-scoped synthetic editing feasibility controller, not a default
CI lane, model benchmark, efficacy result or service qualification. The checked-in
locator is disabled, and the manual workflow contains **no credential binding**.
It cannot currently run a paid pilot. Ordinary tests use fake providers, fake
ledgers and synthetic keys only.

## Trust and execution boundaries

1. `kv_live_policy` validates an exact owner-authorized public freeze, immutable
   artifact/source digests, existing ledger anchors, pricing expiry and exact
   main/run identity. No missing-ledger initialization or retry is supported.
2. `prepare` stages the fixed A2/A3 allowlists. It requires prior hosted actor
   qualification plus same-host isolation, descendant cleanup and a scripted
   read/edit/check/benchmark/submit replay of the exact staged inputs. Preparation
   rejects a provider credential. Scripted performance failure is retained, not
   relabelled as an optimization success.
3. `execute` reserves and claims the entire pair before disclosing either arm.
   GitHub authority stays in the controller. The trusted child receives only the
   provider key, ephemeral broker capability and explicit minimal environment.
4. `GrantedSender` consumes one outer authorization for one canonical request,
   burns the attempt before sending, and invokes the existing transport once.
   Unknown/lost/late usage, cancellation and ambiguous ledger writes stop the
   pair without refund or relaunch. Each arm retains one absolute deadline.
5. Candidate code executes only in the existing network-free bubblewrap profile;
   unavailable isolation has no host fallback. The trusted worker is not itself
   claimed to be another OS sandbox.
6. `package` copies bounded final/revision sources and selected structured
   feedback/usage records, never raw provider bodies, worker logs or environment
   dumps. Unknown attempts and not-started/missing arms remain explicit.
7. A separate read-only, secret-free job downloads only this run's fixed artifact
   name using a pinned action. It verifies actual source bytes and run/plan/actor
   identities and current-revision feedback links before final hidden semantics
   and fixed performance evaluation. The public authorization snapshot is checked
   against the immutable locator offline; later revocation still stops spending
   without deleting already retained no-spend grading evidence.
   Missing results remain INCONCLUSIVE and never become actor feedback or retries.

## First-run evidence, including interruptions

The execution artifact contains the exact verified public authorization, a bounded
projection of preparation progress, staged workspace hashes and the actual
isolation/runtime/cleanup/replay receipts. Each preparation stage records its
start before running. Missing, failed or interrupted stages are explicit; no
exception text, process command, environment or arbitrary log is published.

The grader uploads only its dedicated `public/` projection, not its working
directory. `evidence.json` enumerates every assigned hidden trace and the fixed
alternating AB/BA timing trials plus quality validation. It binds the original
candidate, frozen trace/workload hashes, actual raw task-JSON hashes, measured
values, execution status/exit code and before/after source hashes where available.
The shared executor now records only status, return code and elapsed seconds
immediately after a candidate process returns, before any verifier early return
or JSON parsing. The projection accepts that exact three-field receipt. A process
killed before receipt persistence still has explicitly unavailable status; it is
never inferred from stdout or a PASS. Activation requires fresh model-free
qualification of this changed shared dependency, not the earlier receipt.

Only exact raw JSON conforming to the fixed KV result schema is copied. Its
strings must be known task request IDs or the fixed `ValueError` marker. Each
output is at most 4 MiB, the whole two-arm projection at most 32 MiB, with at most
256 semantic traces per arm. Arbitrary/malformed candidate-only stdout is withheld
with observed byte count, content hash, parsing/schema failure and truncation
status; oversized/unsafe files remain unhashed/unavailable. These diagnostics are
not a sanitizer for private inputs or provider logs. No claim is made to preserve
all arbitrary raw bytes. Failed and missing trials are never upgraded to PASS.
Projection completion is not full-evidence acceptance: every arm's
`raw_outputs_complete` and unavailable execution fields must be inspected even
when a retained grading summary says PASS.

`package-grade --bundle <same-run-bundle> --output <existing-grade-output>` runs in
a separate `always()` environment-cleared workflow step. It validates the same
captured authorization and run identity, then packages **only already generated
first-run evidence**; it cannot execute candidates, call a model or retry grading.
This covers a grader process interrupted before its final cleanup. It also leaves
`projection.json` with started/completed/failed-or-interrupted state and final
manifest hashes. A workflow/host loss that prevents even the always-step or upload
cannot guarantee artifact retention; missing evidence remains INCONCLUSIVE, not
a reason to rerun the paid trial. Both Actions artifacts have 30-day retention;
long-term public archive publication remains a separately approved action.

## Hosted qualification provenance

The frozen `qualification` record contains `run_id`, `run_attempt`, `head`
(GitHub run head), `revision` (actual qualified checkout), `artifact_id`, the
bounded downloaded `archive`, exact `receipt` and `dependencies_sha256`.
`head` and `revision` are separate because PR workflow run identity and checkout
identity need not be the same commit.

The archive must contain exactly `qualification.json` and `raw-evidence.zip`.
The launcher compares the receipt bytes and raw-evidence digest, verifies the
common actor dependency closure against this checkout, checks successful
isolation/cleanup/two-revision tool evidence and requires exact live exposure and
prompt hashes. A common-actor contract digest also binds client settings, input
ceiling, visible suite, baseline, edit limits, checks, metrics and exposed files;
only scripted callback/response-specific identity is excluded. Hosted and current
mount inventories need not have identical hashes: selective sensitive-file
hashing can differ. The canonical dependency closure binds the sandbox profile,
and a fresh current-host inventory/probe must independently PASS; both inventory
digests are retained. The live actor identity is deliberately distinct from the
scripted identity that also binds response fixtures.

Immediately before admission and each request, live metadata must identify the
successful pinned Ready run and the exact nonexpired
`kv-actor-qualification-<run_id>-<run_attempt>` artifact with matching archive
SHA-256. Generic green CI, a numeric task-only artifact or a locally authored
`PASS` JSON file cannot replace this receipt.

## Activation prerequisites (not supplied by this patch)

- Accepted final common task/workbench/development bytes, limits and arm order;
  exact A3 knowledge export audit and independent final-verifier inventory.
- Hosted actor qualification of the actual integrated dependency closure and
  exact exposure/prompt; same-host probes must also pass at execution time.
- One legitimate charge PR/head and audited existing PR/day ledger histories.
  Existing reservations/carryover remain obligations; a launcher PR does not
  create another allowance.
- Refreshed price evidence, supported authorization expiry and enough full-pair
  runway before expiry or Shanghai midnight. An expired plan is not renewed by
  an offline test or by the larger task ceiling.
- Reviewed public freeze/locator with actual hashes and provenance, and explicit
  resolution of the pending existing-key workflow binding/manual-execution step.

No deployment, credential or paid action is authorized by an inactive template.
An operator must not enable the locator, add a secret binding or dispatch merely
because repository tests passed. These tests establish software behavior only;
real hosted isolation, provider delivery, measured model output and efficacy
remain separate evidence.
