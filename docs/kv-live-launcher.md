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
