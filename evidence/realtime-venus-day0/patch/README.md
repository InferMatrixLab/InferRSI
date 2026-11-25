# Compared sources

The acceptance issue links the downstream vLLM-Omni PR and pins its upstream
base, model revision and InferRSI revision. Both measured variants include the
adaptation. They differ only in `.local/venus/profile.json`:

- baseline: `{"enforce_eager": true}`
- candidate: `{"enforce_eager": false}`

Managed source fingerprints are retained in [the RunSpec](../plan/runspec.json),
under `baseline_source_sha256` and `candidate_source_sha256`. A later explicit
`isinstance(entry, dict)` guard only narrows a type already implied by the
existing `full`-mapping validation; it fixed mypy without changing accepted
configuration behavior. The final PR also contains documentation and tests
outside the measured source inputs. No final performance remeasurement is
claimed for these static-check fixes.
