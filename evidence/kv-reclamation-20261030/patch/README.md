# Software control identity

The correct starter is `tests/fixtures/kv_reclamation/candidate.py`; the optimized
headroom control is `tests/fixtures/kv_reclamation/reference.py`. Both are authored
software controls, not model-produced artifacts. Their exact source hashes are
retained in `results/trusted-control-correctness.json` and every hosted receipt.

The starter repeatedly scans pending leases. The reference maintains identity
lookups and a readiness heap, then sorts each newly reclaimed batch by allocation
sequence to preserve the visible contract. It was authored only after the
independent oracle and qualification plan were locally frozen.

Negative sources are deterministic fault injections of the frozen starter in
`tools/qualify_kv_reclamation.py`: omit save readiness, omit the write fence,
ignore generation, emit cached empty answers, skip save events, emit no output
or spoof an incomplete output envelope. Their source hashes and full verifier
coverage are retained by qualification. The no-op performance control uses the
exact starter bytes because this task deliberately has no configuration surface.

All target source changes are confined to this synthetic fixture. Runtime serving
code, historical trials, existing knowledge content and default adapters are
unchanged. The independent oracle and optimized reference must never be exposed
to an evaluated actor.
