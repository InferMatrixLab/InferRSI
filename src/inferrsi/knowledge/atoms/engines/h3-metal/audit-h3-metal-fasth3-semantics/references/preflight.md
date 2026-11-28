# Offline preflight contract

The [bundled helper](../scripts/audit_fasth3.py) audits **caller-declared selected
fields**, not this host or an engine. It has no source-checkout dependency,
network, subprocess, model access, environment discovery or output-file option.
It prints JSON only. Run from the unpacked owner directory using an available
Python 3.10+ interpreter:

```sh
python scripts/audit_fasth3.py --example | python scripts/audit_fasth3.py
```

For an existing declaration, pipe its JSON to stdin. `--example` is synthetic
input, not an observed run. Exit0 means parsing and selected rules completed,
**not** compatibility, a conflict-free request or an acceptance PASS. Inspect
`issues`; exit2 means invalid input or arguments and prints a bounded JSON
diagnostic on stderr (`invalid_input` or `invalid_arguments`). Diagnostics do not
echo caller keys/values, malformed input, exception text or filesystem paths.
Malformed/deeply nested JSON and duplicate keys are rejected, not repaired.

## Input

- Required `fasth3`: explicit boolean. False preserves requested parameters and
  reports original-H3 dispatch as not audited; it does not apply FastH3 overrides.
- `requested`: selected integer fields `steps`, `dit_layers`, `denoise_reuse`,
  `core_reuse`, `token_reduction`, `ssd_streaming`. Omitted fields are unknown
  except source-defined FastH3 overrides. The helper's bounds are offline-input
  safeguards, not native parameter validation or campaign gates.
- `reference_count`: ordered references only, default0. Do not count FL2VA
  first/last-frame anchors here.
- `environment`: selected string-valued keys. Absent keys must be omitted;
  empty strings still count as **present** for presence-based disable switches.
  The helper allows token-reduction controls, sparse disable and reuse steps
  only. Other engine precision/cache/profile/dispatch keys still need a separate
  recorded audit; they are not implicitly clean because this helper omits them.
- `sparse_pipeline_available`: true/false/null. This is a declaration, not a
  probe. Unknown stays unknown unless a declared disable key selects fallback.
- Optional `requested_frames`: selected temporal alignment arithmetic, not
  proof that a decoder produced those frames.
- Optional paired `latent_shape: {t,h,w}` and `prefix_segments: [{kind,rows}]`:
  positive even latent h/w, and ordered `text`, `cond`, `audio` segments before
  the target video. This intentionally excludes ordered reference layouts.
  Prefix validity/order/row-source coverage and complete native layout limits
  are not certified. Values are bounded to avoid unbounded allocation.

Unknown fields, booleans in integer fields, malformed pairs, unsupported kinds
or invalid types fail visibly. Latent_t/frame mismatch becomes an issue. Input
is never corrected silently to claim an observed layout.

## Counterchecks

1. Synthetic example: requested20/45/reuse2/SSD1 becomes4/50/reuse1/SSD0;
   requested49 aligns56, latent_t17. The declared 17×28×48 latent yields120
   video tiles/top-k12. Sparse-disable value `0` still gives dense fine+coarse.
2. Remove sparse-disable key; null pipeline must give unknown, false fallback,
   true only conditional sparse selection. It cannot promise native dispatch.
3. Add `H3_TOKEN_REDUCTION: "1"`: an unsupported ambient conflict is reported
   despite normalized token_reduction0. Disable-key presence suppresses forward
   reduction, but does not erase configuration enable or its parsing obligations.
4. For `{t:5,h:10,w:10}`, video patch grid5×5×5 yields8 tiles, real row counts
   sum125 and edge counts include1,4,16,64. Two adjacent `cond` segments of32
   rows merge into one64-row prefix tile; splitting independently would be wrong.
5. Fixed QKV labels expose global concatenation; FC1 labels expose no-swap.
   Neither is numeric checkpoint conversion, schedule or sparse-kernel parity.

The histogram and tile counts summarize membership arithmetic; they do not
simulate attention scores, top-k ranking, BF16 accumulation, GPU scheduling,
device capacity or media. Use the [native candidate map](source-notes.md#native-candidates-and-script-dispositions)
when a separately authorized native check becomes possible.
