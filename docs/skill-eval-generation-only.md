# Engineering parser generation-only mode

This opt-in #253 transport lets a provider produce parser source without running
model-produced code on the controller. It is **not** an iterative workspace-agent
experiment and does not replace the Linux/bubblewrap verifier.

In a trusted comparison configuration set both:

```json
{
  "adapter": "engineering-artifact-v1",
  "execution_mode": "provider-generation-only-v1"
}
```

The adapter name must match the current engineering adapter constant. The client
must be the existing `anthropic-messages-full-context-v1` client, with reviewed
model, pricing and spend limits. Both arms use the same configuration. Preparation
freezes task, starter, skill snapshots, schema and execution mode before calls.
No default PR mapping or provider configuration is changed by this feature.

The provider receives the frozen task, starter and its assigned skill only. Its
sole tool returns `artifact`, `summary`, and `artifact_source`; it cannot execute
commands or modify files. A trusted writer accepts exactly one `parser.py` source
string of 1–65,536 UTF-8 bytes and writes those bytes only after checking that the
starter is unchanged. Path alternatives, extra fields and malformed or oversized
payloads fail closed. Source is retained as data; it is not imported or executed
by the writer. Summary claims are not grading evidence.

Execution always requires the existing request authorization broker, even if a
caller omits the general authorization flag. A stub is usable only in offline
unit tests. This does not authorize paid calls: current provider pricing,
per-request reservations, PR lifetime/day accounting and the precise experiment
identity must be independently authorized and frozen. A new accounting PR must
not be represented as the historical skill revisions being compared.

Generation never invokes the artifact verifier, even on a capable host. The
original trial remains `INCONCLUSIVE` with `artifact_verification_deferred`. Its
capture report is also non-executing. A separately qualified Linux
reviewer may replay the retained artifact after frozen-input/source integrity
checks. The report preserves that original result and separately exposes
`artifact_verdict`, the 19 artifact checks and `replayed_artifact_outcome`.
Tampered inputs/source, malformed output and other execution errors are not
eligible for this deferred replay. Existing workspace-agent execution is
unchanged. A passing artifact comparison is not evidence of author-agent
isolation, general skill efficacy or causal improvement from a single pair.

Offline regression coverage: `tests/test_skill_eval_generation.py`. Real sandbox
qualification, artifact transport and paid trial execution are separate steps;
these unit tests do not establish that a particular host is qualified.

After the authorized two-call capture, export only retained source and provenance:

```sh
python -m tools.skill_eval_cloud_export --run /path/to/frozen-run \
  --protocol /path/to/prospective-protocol.json --output /path/to/bundle.json
```

The exporter refuses incomplete usage, modified inputs, mismatched receipts or
source, additional pairs and a changed public request. It does not upload the
bundle or establish the timing of protocol approval; the execution admission
controller must bind that protocol hash before calls. Treat both sources as
untrusted until independent qualified replay.
