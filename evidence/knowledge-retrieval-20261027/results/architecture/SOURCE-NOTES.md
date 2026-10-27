# InferRSI knowledge architecture diagrams

Original SVG author configuration: **gpt-6.1-sol / xhigh**, explicitly configured for this delegated diagram task. The SVGs use editable text and vector shapes. No unknown-author draft or code was reused. The supplied reference image informed only the visual treatment: four horizontal panels, light backgrounds, green retrieval panel, blue contracts, solid data-flow arrows, dashed reference/review lines and an evidence strip.

Evidence baseline: the explicitly selected baseline checkout at commit `4817f92121df73fd9cd5fb4a319e3c56a68b4a5b`. All diagram files and the rendering script stay in the selected output directory; the baseline is read-only.

Content sources read:

- `docs/knowledge-base.md`: canonical ownership, authority boundary, registry versus generated catalog, matrices, frozen evidence, explicit use.
- `docs/knowledge-operations.md`: default Collect, independent relevance/context opt-ins, exact revisions, complete mandatory resources and byte accounting.
- `docs/knowledge-store.md`: explicitly authorized local store, candidates only, immutable history, reviewed repository maintenance.
- `src/inferrsi/catalog.py`: legacy catalog search tokenization, filtering, occurrence-count ordering and ID tie-break.
- `src/inferrsi/knowledge_operations.py`: Bundle revision, package/checkout/store identity rules, record.json material, API filters, limits and omission behavior.
- `src/inferrsi/_skill_selection.py`: generated packaged skill validation, deterministic lexical weights, complete-file context, licenses/notices and optional resource selection.
- `tools/build_skill_index.py`: stable registry input, fixed committed source snapshot, source-file hashes and generated `kind=knowledge` catalog records.

Interpretation limits:

- Canonical skill content is organized under `hardware/`, `frameworks/`, `repositories/`, `methods/` and `workflows/`. These ownership categories are distinct from Skill/Knowledge/Case kinds, contribution/dependency/peer relationships, and backend compatibility qualification. Applicability is a metadata field.
- This is an architecture/contract diagram, not a count of skills or proof of task performance, hardware compatibility, licensing clearance or empirical validation.
- `knowledge search` and Collect remain separate retrieval modes. Collect's metadata filters are labeled as Reader API features; the figure does not imply that every API filter has a corresponding Collect CLI flag.
- Generated packaged skill records retain `kind=knowledge`. Packaged `material` returns the record entrypoint (`record.json`); the separate context view supplies canonical SKILL.md and complete mandatory references within an explicit UTF-8 resource-body byte budget.
- If mandatory context resources exceed the context byte budget, that owner's context is omitted. The selected item can still be returned in `items`; context omission is not item omission.
- The projection is not an editable content authority, and the stable-ID registry is not the generated catalog. Source commits, local Bundle revisions and tested engine revisions have different meanings.
- Local store writes do not mutate package/checkouts, evidence or matrices, and they do not promote candidates. The bottom dashed connections describe references/review, not automatic feedback or execution.
- A performance implementation that reuses digest/path work inside one manifest does not add a new database, persistent cache or scoring method; it does not change this architecture.

From this architecture-artifact directory, rebuild with the existing bundled Python runtime:

```powershell
& '<bundled-python>' './build_diagrams.py'
```

Pillow checks text widths and card heights; SVG XML parsing checks structure; CairoSVG renders 3200 × 2100 PNG previews from the 1600 × 1050 vector source. Fonts are Segoe UI (English) and Microsoft YaHei with Noto Sans SC fallback (Chinese). Text remains editable in SVG; preview rendering uses installed system fonts.

Independent review clarified the English fourth-column budget line to
“Required set over budget: omit context.” Codex `gpt-6.1-sol` / `xhigh` applied
that one-line source correction, regenerated the assets/layout checks and
visually inspected the English PNG. The Chinese text already expressed the
required-set boundary and was unchanged. This states the context omission
contract without implying that optional-resource overflow omits the whole
context.
