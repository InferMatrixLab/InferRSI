# D023 null-timeout binding vector

`d023-null-timeout.json` is derived from the unchanged canonical
`docs/contracts/fixtures/t108-v4/execution-spec.json`: add the frozen preparation's
`recipe.code_sha256` as `steps[0].expected_code_sha256`, and set
`steps[0].timeout_seconds` to null. The accepted #429 PR-1 vector is 2069 bytes,
with request digest
`sha256:62ce11e6d458b5c581245d0988189e1bd834f2ed1e1880d15242faf70c5b6fe9`.

This is immutable contract-conformance input, not observed execution evidence or
an available worker implementation. Tests compare the canonical Apps binder,
Harness digest and read-only prepared projection. No process is started. T37
entry verification and production T40 replay remain separate PR-2/PR-3 work.
The original documentary fixtures are not rewritten.
