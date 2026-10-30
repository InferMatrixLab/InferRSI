# Source-conditioned cue feasibility: neutral FAIL

[Report](results/report.md):both arms Hit6/6, exactMRR29/36, complete relevant6/6; strictMRR improvement gate fails. Six source-conditioned synthetic cases, four mostly polite-framing edits and two byte-identical controls. Not broad normalization evidence. Earlier blind preparation-INCONCLUSIVE remains separate.

Frozen production baseline6e6ee245 is identical in both arms. For authorized replay only, create a new output directory and run validator/evaluate.py BASELINE_ROOT PREP_ROOT OUTPUT_DIR with PREP_ROOT set to a new external copy of plan/ after the source-pins.json → source-manifest.json restoration described below. Do not overwrite frozen results. No runtime changes, scorer candidate, model/hardware experiment or #255 closure. Original local integrity inventory is replaced by plan/publication-integrity.json for relocation; frozen outputs/protocol/inputs/runners remain exact bytes.

### Frozen preparation filename mapping
`plan/source-pins.json` is the exact original source-manifest.json snapshot (not a current-tree hash validator). For replay copy plan/ to a new external preparation directory and copy source-pins.json to source-manifest.json there; do not modify the evidence tree. Internal frozen references retain the original filename and hash. Publication-integrity validates both snapshot bytes, not historical corpus availability.
