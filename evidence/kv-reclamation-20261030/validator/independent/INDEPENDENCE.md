# Independent verifier provenance and handoff

## Provenance

Author role: independent verifier agent, separate from the optimized-reference
implementer. This bundle was created locally for the newly owner-authorized
bounded synthetic CPU KV-block reclamation task. It is not a historical holdout.
Only the neutral public interface and lifecycle contract were exchanged with the
implementer before freeze. The implementer agreed to wait for the hash freeze
before authoring its optimized reference control.

Repository context read: `AGENTS.md`, `pyproject.toml`, `docs/contributing.md`,
`docs/agent-collaboration.md`, `docs/privacy-security.md`, and the unrelated
`tests/test_local_executor.py` at the provided main checkout. Directory names and
test filenames were listed for navigation. No target knowledge body, target
implementation, upstream solution, or model response was read. No model,
provider, hardware, credential, network, or external publication call was made.

The independent oracle is a trusted full-history temporal specification. It
validates each call against accepted history and recomputes each lease's earliest
eligible prefix. It is intentionally not the queue/drain optimization submitted
as a candidate. The frozen static event observations are the correctness oracle;
fixture generation can be replayed byte-for-byte. Literal anchor tests separately
check the critical expected outcomes, rather than only asserting oracle agreement
with itself.

## Integration

- Keep this bundle evaluator-only. Publish `CONTRACT.md` as the candidate-visible
  task contract; development inputs may be exposed as designated by the trial
  plan. Do not mount this directory, oracle, expected fixture records, or grader
  traces into an untrusted candidate process.
- `verifier.load_traces(split)` returns dictionaries with `id`, `split`,
  `obligations`, `events`, and evaluator-only `expected`.
- Give an isolated candidate only `events`. Collect the JSON envelope
  `{"observations": [...], "pending": [...]}`. Each observation is either
  `{"reclaimed": [...], "pending": [...]}` or
  `{"error": "ValueError", "pending": [...]}`. Tuple structures in `pending`
  are represented as JSON arrays only after runtime type validation.
- Use `verifier.compare(trace, actual) -> bool` or
  `verify_observations(trace, actual)` in the trusted parent. Candidate event
  objects are disposable copies; candidate input mutation cannot change the
  trusted fixture, oracle, or expected observations. Input mutation is not a
  separate acceptance failure unless it changes required behavior.
- `python verifier.py --trusted-candidate <path> --split all` directly imports
  trusted authored controls only. It is not an untrusted-code security boundary.
- `python -m pytest -q test_verifier.py` checks reproduction, literal anchors,
  positive replay, negative mutations, atomic follow-through, types, and hashes.

The good control is exact finite replay. The bad controls are one-obligation
observable mutations, explicitly not claimed to be general executable flawed
algorithms. An independently authored optimized positive implementation and real
fault-injected implementations can be qualified against this frozen bundle after
freeze. A fixture pass establishes only this synthetic CPU correctness scope.
It does not establish A3 effectiveness, model superiority, queue performance,
production behavior, historical generalization, or efficacy of target knowledge.
