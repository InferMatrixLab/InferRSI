# Test design — portable scaffold

## Principles

- **Draft lane** must stay fast and CPU-only.  
- **Acceptance** gates live in issues with pinned SHAs; not every `main` push.  
- Status vocabulary matches claim contract: `PASS` / `FAIL` / `INCONCLUSIVE` in test names only where asserting enum behavior.

## Layers

| Layer | Location | Draft | Ready | Nightly |
| --- | --- | --- | --- | --- |
| Smoke | `tests/test_smoke.py` | ✓ | ✓ | ✓ |
| Package import / SIAS layout | `tests/test_sias_layout.py` | — | ✓ | ✓ |
| Evidence path helpers | `tests/test_evidence_paths.py` | partial | ✓ | ✓ |
| Claim enum | `tests/test_claim.py` | — | ✓ | ✓ |
| Bench harness stub | `tests/test_bench_stub.py` | — | path filter | ✓ |

## Cases (smoke)

1. Import `rsi_scaffold` and read version.  
2. Build minimal RunSpec dict and round-trip JSON fields.  
3. Resolve evidence subpaths for a dummy campaign id.  

## Cases (ready)

1. All SIAS subpackages import.  
2. `Verdict` rejects invalid labels.  
3. Benchmark README stub is present (filesystem smoke).  

## Out of scope

- GPU jobs, model download, e2e inference.  
- Comparing two real git SHAs in CI (acceptance issue responsibility).  
