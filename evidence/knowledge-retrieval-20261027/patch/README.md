# Runtime patch boundary

The evaluation-material author changed no runtime source. `candidate.json`
records the independently authored runtime commit and exact Python-source
digest used by the formal comparison. The implementation reuses digest/path
work within a manifest call; it introduces no cross-call mutable cache.

Runtime integrity tests and independent review belong beside those revision
records. Exact-output parity does not replace mutation or unsafe-path regression
checks. Later evidence/documentation integration must preserve the tested
runtime bytes; merge and issue closure remain with the authorized owner.
