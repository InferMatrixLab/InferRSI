# Model

`protocols/` defines request and metric contracts. `validators/` owns output
quality checks with explicit campaign-supplied gates. The image validator's
optional dependencies are available through `inferrsi[image]`.

Model/revision pins and numeric acceptance gates stay in campaign plans. Frozen
historical snapshots remain in `tests/fixtures/legacy/`; current examples and
new modules serve new campaigns.

See [the architecture and compatibility boundary](../../../docs/architecture.md).

## Bounded edit/check protocol

`anthropic_edit_agent.run_edit_agent` is a separate fixed-tool protocol, not a
general coding agent and not the existing read/submit adapter. A trusted caller
supplies an explicit `EditPlan`, staged-file manifest, request allocation,
pre-send authorization, transport, visible check/benchmark callbacks and revision
storage. The only write tool replaces `candidate.py`; there is no shell, arbitrary
command, model-selected workload, discovery or default live transport.

The worker retains every candidate revision through the trusted storage callback,
returns the exact final source snapshot, and records bounded, typed public check
and measurement receipts bound to plan, attempt, arm and source revision. A write
invalidates both receipts. Unknown provider usage or uncertain transport stops
the shared request allocation without refund. Structured feedback permits only
frozen public check IDs and selected finite benchmark fields, not raw logs,
private paths, hidden-grader diagnostics or oracle/reference code.

Integration must supply the actual security and spending boundaries:

- Run the trusted provider worker under `execute_command` with the same absolute
  deadline passed to the protocol. Python deadline checks reject late results;
  they cannot interrupt a blocked transport/callback. Every tool must inherit
  this deadline; a nested `run_experiment` cannot extend it.
- Execute candidate bytes only in the qualified, network-free artifact sandbox,
  with no credentials, full repository, undeclared knowledge or hidden oracle.
  A callback is trusted host code, not a sandbox. No host-execution fallback.
- Compose visible measurement from the existing `run_experiment`/`evaluate`
  path. Validate full candidate output independently before accepting host timing.
  Final hidden grading is separate and occurs only after immutable submission.
- Reserve and claim the whole frozen cost in the existing durable PR/daily
  ledgers, bind one immutable campaign/attempt, and check live authorization
  before each send. `RequestSlots` adds nonrenewable per-arm in-process limits;
  it neither creates a durable claim nor makes restarts safe by itself.
- Freeze exact implementation, callback/dependency hashes, qualification receipt,
  exposed files, model/provider/pricing, byte/tool/request/time limits and budget
  before calls. Use `frozen_identity` for offline protocol identity. Its callback
  hash must cover transitive sandbox, executor, checker and workload dependencies.

`tests/test_anthropic_edit_agent.py` uses scripted callbacks and transport. It
does not execute candidate code, qualify a sandbox, make model calls or establish
optimization efficacy. There is no paid-launch CLI in this module.
