# Native service functional qualification

`service_launch.py` uses the existing correctness RunSpec and paired runner. Its
`native_service_functional` scope compares the native public `LLM.generate` entry
with the same snapshotted engine's HTTP/SSE service. This is functional L4 evidence;
it provides no latency, throughput, SLO, or broad model-quality claim. The separate
trusted-reference teacher-forcing check remains required for model correctness.
CPU fixtures and fake servers exercise the scaffold only. Real GPU/model evidence
is pending until the accepted campaign's frozen protocol is actually completed.

## Frozen protocol

Supply a JSON object with these required fields, using acceptance-issue values:

- `schema_version: 1`, `qualification_scope: "native_service_functional"`,
  `model_id`, and the exact `precision` profile from `profiles.precision(model_id)`.
- `timeouts`: positive seconds for `startup`, `request`, `release`, `poll`,
  `shutdown`, and `socket`. These are observation/cleanup budgets, not performance
  gates. The surrounding RunSpec also has a frozen overall `max_minutes`.
- `limits`: positive integers `max_context_tokens`, `max_active_requests`,
  `max_connections`, `max_body_bytes`, and `max_response_bytes`. Freeze sufficient
  response space for all stream events and request text. At least two active slots
  and two additional control connections are required by this protocol.
- `cases`: at least two objects with unique safe `id`, nonempty `prompt` (text or
  token IDs), and positive `max_tokens`. Include both text and token-ID inputs and
  suitable multilingual text in the campaign workload.
- `concurrent_case_ids`: distinct case IDs, including at least two distinct inputs,
  within the active capacity. Admission overlap must actually be observed.
- `eos_case_id`: a declared case that must actually finish with `stop`; changing the
  model's EOS configuration to force coverage is not permitted. Missing observed
  EOS is `INCONCLUSIVE`. At least one other case must actually finish with
  `length` at its requested token limit; otherwise runtime limit coverage is also
  `INCONCLUSIVE`.
- `survivor_case_id`: a declared case whose exact serial output must survive
  overlapping cancellation and disconnect of a separate request. Cancellation ACK
  metadata must show the survivor active at the atomic cancellation point; the
  disconnect terminal ledger must show it active when the victim is released.
  Earlier overlap snapshots alone cannot satisfy this requirement.
- `lifecycle`: a safe `id`, `prompt`, and `max_tokens` sufficient to observe active
  cancellation, disconnect, capacity saturation, active shutdown, and a second
  model call for fault injection. Early natural completion is a coverage gap.
- `queued_case`: a safe `id`, `prompt`, and `max_tokens` for observing a second
  admitted request cancelled before prefill. A race that already prefills the
  target leaves queued coverage `INCONCLUSIVE`.

All concrete prompts, limits, budgets, repetitions, revision pins, and numerical
quality gates belong in the acceptance issue and frozen campaign artifacts. The
adapter contains no defaults for timing gates and does not tune workloads during
candidate execution.

Run inside an authorized single-GPU Slurm allocation, with authenticated model
intake already completed:

```sh
python -m examples.qwen38_text.service_launch \
  --engine-repo '<engine-checkout>' --model-path '<authenticated-model-path>' \
  --model-id '<supported-model-id>' --model-revision '<model-revision>' \
  --manifest '<manifest.json>' --workload '<frozen-service-protocol.json>' \
  --device-model '<requested-GPU-model>' --max-minutes '<frozen-budget>' \
  --repetitions '<frozen-repetitions>' --output-dir '<private-run-root>'
```

## Observations and verdicts

The adapter records serial public/JSON/SSE tokens and decoded text, concurrent
admission and exact outputs, victim/survivor isolation, explicit cancel and real
socket disconnect, terminal ledgers, queued-before-prefill cancellation, saturated
capacity rejection with working control routes, invalid request/limit rejection,
active SIGTERM shutdown framing, descendant cleanup, and fresh-process generation.
SSE is consumed through connection EOF: missing terminal/DONE, duplicate DONE, and
trailing events cannot satisfy coverage. Concatenated deltas must equal the public
full decode, including Unicode boundaries.

A separate owned process runs `service_fault.py`, a harness-only bootstrap. After
a normal warmup request, it lets the designated request complete one real model
call and injects one `RuntimeError` on its next call. The runner-state identity,
successful call count, trigger flag, and control source digest are recorded. Its
SSE error terminal, state release, and subsequent normal generation are required.
This is injected error-path evidence, not a claim that a natural GPU fault occurred.
The normal production server exposes no failure endpoint and is not patched.

Each process reports model, actual GPU, precision, loader, runtime versions, and
validated import origins. FP8 runs additionally require every loaded FP8 linear
module to have a positive native call count and valid actual weight/scale dtypes;
module totals must agree. Restart and fault-process provenance is also checked.

`runner_state_bytes` means logical live request tensors (KV, convolution, recurrent
state), not allocator-reserved VRAM. State accounting is sampled at completed model
boundaries; cancellation is cooperative between model calls. The frozen deadlines
bound observation without asserting an instantaneous GPU interrupt.

Complete observed behavioral regressions are `FAIL`. Missing, malformed, timed-out,
wrong-source/device/precision, unobserved overlap/EOS, or incomplete cleanup evidence
is `INCONCLUSIVE`. Only complete protocol evidence can yield this limited scope's
`PASS`. Shared correctness evaluation performs no metric extraction or gain gating.

## Private artifacts

Raw ready/shutdown files, server logs, HTTP observation journals, and common-runner
operational snapshots may contain machine paths and stay in the private run root.
Before writing each final trial result, actual import paths/bytes are checked, then
origins become engine-relative; commands and listener addresses become placeholders.
Do not publish the raw run tree. Review/redact any additional artifacts before
publication under the repository privacy contract.
