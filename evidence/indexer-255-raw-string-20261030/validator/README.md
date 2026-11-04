# Inspect retained evidence without rescoring

The archive retains the exact comparison runner (SHA-256
`7abe02af59ae06a5f2e7956d5236573172810b84025223714ded593c1e6c8061`) and fixture
(SHA-256 `70086b95ba74c182cb195c32d71fed7aed747bec975079160f10bf8fff673e18`).
Original protocol/runner/candidate freezes and source/module proofs are included.
No timing or quality conclusion follows from diagnostic duration/output bytes.

Extract into a separate scratch directory, then verify retained bytes:

```bash
tar -xzf <checkout>/evidence/indexer-255-raw-string-20261030/results/frozen-study.tar.gz
cd issue255-raw-string-results
sha256sum --check SHA256SUMS
python validator/show_demo.py results
```

The demo reads saved JSON only. Do not repeat the frozen comparison; the one-run
receipt and independent retained-output audit are the accepted historical result.
`independent_saved_audit.py` is explicitly a post-run supplemental audit, not a
replacement scorer. `plan/integrity.json` in the publication wrapper authenticates
all wrapper/archive files; it does not re-adjudicate the contract result.
