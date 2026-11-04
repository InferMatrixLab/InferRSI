# Repository provenance

Use this snapshot to detect drift before applying the guide. Source citations
are research provenance, not campaign baseline/candidate defaults.

```json
{
  "schema": "disco.repo-provenance.v1",
  "generated_at_utc": "2026-10-23T09:09:46Z",
  "repository": {
    "name": "lithos-metal",
    "remote_url": "https://github.com/lithos-ai/lithos-metal",
    "vcs": "git",
    "branch": "main",
    "tag": null,
    "commit": "6653b7df5f2c4392ec7b038960f2796b1499923f",
    "working_tree": "clean",
    "dirty_paths": []
  },
  "packages": [{"name": "lithos-metal", "version": "0.1.2", "import_names": ["monolith"]}],
  "evidence": {
    "source_roots": ["monolith/compiler", "monolith/core", "monolith/runtime", "monolith/spec", "monolith/serving", "runtime/src", "kernels/common"],
    "docs": ["README.md", "CONTRIBUTING.md", "docs/design"],
    "examples": [],
    "tests": ["tests/contract", "tests/runtime/test_toy_program.py"],
    "configs": ["pyproject.toml", "setup.py", "monolith/backends/metal/registry.py"]
  }
}
```

The [bounded source readset](source-notes.md) specifies inspected sections and
symbols rather than claiming complete directory coverage. Selected installed
API and CLI facts were inspected at 0.1.2; the source Python metadata minimum
and source-build interpreter guidance remain distinct. Candidate efficacy is
`not_run`; source inspection, CPU contracts and synthetic Metal checks do not
promote this guide or establish full-model/DSpark/service qualification.

Refresh when the upstream revision/dirty state, package version, public API,
backend recipe, layout or source file ownership changes. Compare changed
contracts and regenerate dependent guidance; do not merely replace the pin.
Missing source/runtime evidence stays unavailable rather than resolving to a
newer live implementation silently.

## Extraction boundary

Included: compiler coverage/regions/barriers/arena, Program and StepState ABI,
generation orchestration/DSpark commit, backend identity, serving assets,
pack/prefix validity and idle/session lifetime. Source tests are evidence and
separately selectable validation candidates; no tests are run by skill reads.

Excluded: model catalog completeness, new model/format implementations, MoE
qualification, exhaustive kernel tuning, external oracle code/weights, CI/release
automation, benchmark archives and client launchers. The owner has no complete
Apple GPU support or service-readiness claim. Exact citations to model-related
contracts do not imply those models were loaded or compared.

InferRSI `local-skill-v1` keeps only name/description in SKILL frontmatter.
The AREX license, `disable-model-invocation` and `metadata.disco-role` fields
are preserved in each sidecar and exposed by the effective metadata reader.
This destination normalization replaces AREX's raw-frontmatter gate; it does
not claim direct DisCo import compatibility.

AREX's repo2skill structure, source/script maps, installed inspection and
assertion-backed verification were adapted for an InferRSI candidate. InferRSI
owns discovery via its registry/catalog and two matrices. No DisCo fixed-taxonomy
projection or live importer is needed for this destination; review-only scope,
native candidates and usability artifacts stay outside the runtime skill tree.
