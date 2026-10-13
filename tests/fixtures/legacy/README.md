# Frozen compatibility fixtures

These are byte-for-byte snapshots from OmniRSI commit
`ab343f98f7da55e428275c20c2324732201b9000`, retained for regression coverage after
removing obsolete LTX examples. They are test inputs, not maintained campaigns:

- `ltx25_b300.py` and `ltx25_quality.py`: historical helper and quality contracts.
- `qwen21_turbo_quality.py`: pre-cleanup Qwen validator; tests compare its behavior
  with the current example, whose only logic dependency change is importing the
  extracted shared artifact helpers.

Do not format or edit these files. Historical campaigns still require their own
original frozen source/input bundle; these snapshots do not replace old guards.
Current runnable Qwen examples live under `examples/`.
