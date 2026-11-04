# Structured string-value tokenization v3: FAIL

[Report and per-case table](results/report.md). Production baseline b3549ce1; rejected candidate96788d26. MRR drops7/12→8/15 despite Hit4/6→5/6. No runtime promotion, heldout execution or #255 closure.

Frozen scripts are in validator/, inputs in validator/inputs/. For authorized replay set PREP_ROOT to validator/inputs/, ROOT to the pinned baseline or candidate tree, and create a new OUTPUT_DIR. Candidate patch/bundle is in patch/ (baseline prerequisite b3549ce1). Frozen report uses original artifact basenames; this README maps their packaged locations. The original local results integrity inventory is replaced by plan/publication-integrity.json for this relocated bundle; frozen artifact bytes are unchanged. pre-semantic-freeze.json records its pre-run state, not final execution status.

### Frozen preparation filename mapping
`plan/source-pins.json` is the exact original source-manifest.json snapshot (not a current-tree hash validator). For replay copy plan/ to a new external preparation directory and copy source-pins.json to source-manifest.json there; do not modify the evidence tree. Internal frozen references retain the original filename and hash. `plan/preparation-freeze.json` is the exact original freeze-manifest.json receipt, likewise renamed only for explicit snapshot classification. Publication-integrity validates both snapshot bytes, not historical corpus availability.
