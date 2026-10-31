# CPU reclamation task: model-free qualification

**Current retained local result: INCONCLUSIVE.** The required bubblewrap network
namespace was unavailable; no candidate was executed without isolation. The
existing Ready workflow will retain a separate host-specific qualification
receipt. Nothing here is a model efficacy, vLLM-conformance or service claim.

The task was deliberately constructed around the nominated knowledge's
dual-readiness mechanism. Independent oracle authorship is not independent task
selection. Both arms already receive the explicit readiness contract and a
correct starter; this is selected synthetic near-transfer, not an independently
sampled or historical held-out case. The post-freeze static owner audit found no
target-specific code, heap answer or grader leakage, but an actual exported A3
bundle/prompt audit remains pending.

| Question | Retained evidence | Meaning |
| --- | --- | --- |
| Is the oracle independently frozen? | [Original freeze](validator/independent/FREEZE.json), [provenance](validator/independent/INDEPENDENCE.md) | Neutral contract before reference implementation; 88 traces / 1,076 events |
| Are authored controls semantically valid? | [Trusted direct-import checks](results/trusted-control-correctness.json) | Starter and optimized software control each pass 88/88; not untrusted replay |
| Is this local host qualified? | [Initial receipt](results/local-isolation-unavailable.json), [post-review receipt](results/local-final/qualification.json) and its raw archive | Both INCONCLUSIVE before controls/timing; isolation unavailable |
| Is reference speedup established? | No completed timing receipt yet | Not run locally; retain hosted result separately |
| Does knowledge improve an agent? | No model trial | Unverified; no efficacy claim |

## Freeze and interpretation

- Accepted bounded scope: [execution record][scope]. Prospective numeric/input
  freeze: [published plan][freeze] and exact [plan bytes](plan/qualification-plan.json).
- Independent verifier freeze SHA-256:
  `163c21134a8155da2a6469d9dbddb6ea71cb162e14f53e1c4266fe8ce75126f7`.
- Plan SHA-256:
  `60cc479686aa2ba3772f627cc5179a3c0dc6d215c0fdeb57547fd58dc30859ed`.
- Independent benchmark-output [supplement](validator/supplemental-freeze.json)
  SHA-256: `717d7c1a4327f3bcaa9755c9b343a142e0223a651996893d7de3e4065cf6b6f0`.
  It was frozen after reference authorship but before any timing, by the same
  independent author without reading candidate/control/K or timing data. Its
  [derivation and checks](validator/BENCHMARK_PROVENANCE.md) supplement the original
  oracle without changing it or the numeric plan.
- The local verifier/plan freeze preceded optimized-control authorship. Public
  posting followed that authorship but preceded timing. This is not represented
  as a public prereference registration.
- The original independent files are byte-for-byte frozen. The temporal oracle
  is deliberately separate from the queue implementation. Hidden means withheld
  from the actor's filesystem/tools, not unpublished or a natural historical
  holdout. Candidate subprocesses necessarily receive replay inputs, not answers.
- In-process return-shape checks are compatibility checks, not tamper-proof API
  enforcement. External acceptance compares frozen observable trace envelopes
  and host whole-command timing; it does not certify immutable per-call driver
  behavior. Actor-level isolation and arbitrary descendant cleanup remain separate.
- Metrics are whole CPU-task command elapsed time including sandbox/interpreter
  startup. No warmup, trimming, rerun-until-pass or agent-claimed metric. Existing
  AB/BA scheduler, source snapshots and evaluator are reused.
- CI success checks software controls; numeric qualification verdict is reported
  separately. A green CI result alone cannot qualify a task or demonstrate gain.
- Any failed/incomplete control, environment failure or comparison stays in the
  denominator/evidence. No old serving-parser trial or knowledge result is rewritten. The second local receipt follows deadline/output/probe fixes and adds retained raw evidence; it does not replace the original unavailable-isolation receipt.

## Contents and reproduction

See [the operating guide](../../docs/kv-reclamation-qualification.md) for commands
and the sandbox boundary. [Patch notes](patch/README.md) identify the software
controls. `plan/publication-integrity.json` covers this immutable public bundle;
source/controller identities are recorded in each execution receipt.

Future A2/A3 work still requires actual actor read/tool isolation, complete pinned
knowledge exposure/contamination review, explicit model/adapter/usage protocol,
cost reservations and final-artifact independent grading. This bundle neither
implements nor authorizes a paid actor adapter.

[scope]: https://github.com/InferMatrixLab/InferRSI/issues/248#issuecomment-6526000390
[freeze]: https://github.com/InferMatrixLab/InferRSI/issues/248#issuecomment-6526223873
