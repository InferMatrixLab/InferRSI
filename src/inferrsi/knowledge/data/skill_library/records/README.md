# Engineering records

An engineering finding belongs in one `<stable-id>.json` file here. The ID encodes repository, backend, component and entry. Keep the source revision, applicability, verification state, limitations and negative results with the claim. The tier field expresses the source relationship (contribution, dependency or peer). Existing schema-1 contribution records may omit the tier.

Use `inferrsi knowledge list --tier peer --json` to browse a tier and `inferrsi knowledge show <stable-id>` to open the complete record. A procedure belongs with its own SKILL.md, metadata and resources. The catalog builds packaged-skill views from those owners. No per-record navigation list needs editing.

## Adding or updating a record

Choose a stable ID, pin the source and describe the observed scope. Separate an upstream report from a locally verified result. Include the environment and comparison needed to transfer the finding. Verify the record with `knowledge show` and search using its repository, backend and scenario. Frozen run output belongs under the repository's `evidence/` directory.
