# Replay without a model call

From the repository root, using Python 3.10 or later:

```console
python evidence/skill-eval-v1-20261021/validator/replay.py
python tools/validate_evidence.py
```

`verify.py` is the exact frozen verifier used in both phases. `replay.py` checks
published task/answer identities and re-evaluates every available original
assertion set. Original v1 FAIL results are expected and retained. Incomplete
execution without check evidence stays unavailable, rather than becoming PASS.
The inventory command checks publication layout and byte integrity; it does not
adjudicate campaign success or verify unavailable historical external archives.

The verifier checks these fixed JSON tasks: report verdict, scope, exact material
findings, descriptive latency reduction (0.02 percentage-point tolerance),
required evidence keys and a nonempty explanation. It does not execute generated
code. Nonempty explanation is not proof of good reasoning; manual review covers
substance, next actions, correct skill use and observed access. All selected
fixed fixtures meet their spread gate; generic spread/seed/deployment validation
is outside this verifier's contract.
