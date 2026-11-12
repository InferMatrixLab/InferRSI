# Replay and artifact availability

This snapshot records device experiments performed with InferRSI
`50c19da43e0b358e6f990c00719891ad308a8ac1`. The PR's repository base may be newer;
publishing evidence does not rerun or migrate those experiments.

## Checks available from this checkout

With the repository's development dependencies installed:

```sh
python tools/validate_evidence.py
python -m pytest tests/test_evidence_inventory.py tests/test_smoke.py tests/test_claim.py
```

The inventory checks the publication digest map and eight byte-preserved frozen
snapshots. Its external/unavailable list is expected: it does not download model
weights or raw media, replay NPU execution, certify privacy, or change a verdict.

Read [the experiment report](../results/report.md), then
[the execution snapshot](execution-checkpoint.json),
[the frozen lossless contract](frozen-lossless-contract-v1.json) and
[the frozen lossy contract](frozen-lossy-contract-v1.json). The lossy contract
includes fixed requests and loopback image URLs. Supply the original reference
image with the recorded SHA256; a replacement image changes the workload.
Held-out requests have not been generated or scored and remain reserved for
selection under that contract.

## Engine source reconstruction

The engine changes are patch artifacts under [patch/](../patch/README.md), not
changes to the installed InferRSI runtime. Each identity states the tested
private engine revision and patch base. The private commit object itself may
be unavailable publicly; the diff is supplied for source inspection.

For C1, use an isolated vLLM-Omni checkout at
`922f1e9f1cb85b9f2b66d86e1eb500e6872b2dcb`, then apply
`patch/c1-h3-bf16-prefix.patch`. Each C12/C13/C15–C23 patch is cumulative over
the `patch_base` recorded in its identity:

- C12, C13, C15, C16, C21, C22 and C23 use C1
  `be319692b96413918973b5bd399cdda3f320c574`. Chain: `922f1e9f` → C1 → one
  selected patch.
- C17, C18, C19 and C20 use C13 `e89b1d40d37f7f72767892a56fa7980ea572ba8e`.
  Chain: `922f1e9f` → C1 → C13 → one selected patch. Applying one of these
  directly over C1 omits C13's ten DLO/collective paths, although the patch
  still applies.

Candidates that share a base are alternative experiments, not a sequence to
stack. C10/C11 patch bases are stated separately in their identities.
Use `git apply --check` before applying a patch. Do not overwrite a shared checkout.

The identity's raw file hashes describe the tested Windows/Linux working bytes;
Git can normalize CRLF/LF while preserving the Git tree. A reconstructed checkout
does not recreate a private signed commit or prove numerical equivalence.

## Additional requirements for device replay

An authorized replay needs four idle logical 910C devices with 64 GiB each, the
exact original model and reference image, the recorded dependency stack,
isolated reference/candidate/evaluator environments and an independently frozen
resource/timing plan. The private Ubuntu namespace, CANN installation, request
driver, diagnostics and bootstrap scripts are not bundled. Full device replay
is therefore not self-contained from this PR.

The [strict validator](../validator/strict_compare.py) compares original audit
layouts and raw tensors/decoded media; the archived scoring scripts require the
dependency weights and directory layout recorded in the frozen contract. Those
scripts are preserved evidence, not a newly generalized public runner. Retained
source/weight hashes identify missing inputs but do not make them available.

Never substitute diagnostic request latency for a clean pair. Original B0 remains
the comparator; the migration branch and candidate use separate source identities.
Final confirmation still requires all four tracks and the prospective three-pair
protocol. Known quality failures remain FAIL and should not be rerun to select
favorable samples. No device replay is launched by this tracking publication.
