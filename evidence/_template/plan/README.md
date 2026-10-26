# plan/ (template)

Copy `evidence/_template/` to `evidence/<campaign-id>/` when opening a campaign.

- [campaign-plan.md](campaign-plan.md) — the campaign plan: a header, one table
  with seven required rows, the row-4 entry format, the row-4 change log and a
  fill-in checklist.  
- [campaign-plan.yaml](campaign-plan.yaml) — the same rows as machine-readable
  keys, keeping the `plan.json` field vocabulary.  

Rows 1 (model), 2 (hardware), 3 (optimization goal), 5 (test plan), 6 (budget and
stop conditions) and 7 (control and authority) are frozen once the first candidate
search starts. Row 4 (iteration search plan and state) is versioned: every change
is appended to the change log, and an entry's hypothesis, mechanism and kill
criterion freeze at its first run. Editing a frozen row starts a new campaign ID
with its own plan and acceptance issue.

`freeze.json` records the hashes of `plan/campaign-plan.md`,
`plan/campaign-plan.yaml` and the validator. Retain the original snapshots and
manifest before search, and preserve each later revision and its manifest.
For each row-4 revision, manually compare every frozen field in both plan
representations against the originals and link the record in the change log.
Whole-file hashes establish revision integrity, not that frozen fields are
unchanged; validator hashes must remain unchanged. Missing required evidence
yields `INCONCLUSIVE`, never `PASS`.
