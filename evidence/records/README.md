# Optimization run records

From the InferRSI checkout, use the
[submit-optimization-record skill](../../.agents/skills/submit-optimization-record/SKILL.md)
to prepare optional public feedback after a run. Select one native campaign's
v1 result-delivery bundle and a prompt you may share. The skill creates a
redacted derivative and shows the exact staged files and PR text for review
before publication.
The campaign directory remains the runtime trace source and may hold private
material. Keep it and the original prompt outside the public commit.

## Layout

```text
evidence/records/<YYYYMMDDTHHMMSSZ>-<12-hex>/
  record.json
  model-config.json
  prompt.md
  trace/
    01-execution.json
    02-result.json
```

- `record.json` is the v1 manifest. It identifies the run's user-reported
  agent and InferRSI versions, source export schema, original execution and
  assessment status, gaps, and the relative paths and SHA-256 digests of
  included files. A public project acceptance issue or approved archive
  reference can accompany the snapshot.
- `model-config.json` separates allowlisted agent sampling/reasoning settings
  from optimized-model identity and runtime settings. Unavailable values are
  null with a corresponding omission.
- `prompt.md` includes only redacted user prompt text and selected user
  refinements. Its manifest entry records `withheld` or `unavailable` when
  omitted.
- The trace JSON files retain the source execution state, attempt history,
  result, existing verdict and its verification state. Metrics require a
  matching public acceptance issue and permission under the repository's
  [claim rules](../../docs/contributing.md#evidence-and-claims).

The UTC prefix uses the source's timezone-qualified run start truncated to a
second. The fallback is first preparation time. The manifest records the
timestamp basis. Keep the generated ID and prepared directory for retries.

Validate the inventory with `python tools/validate_evidence.py` from a checkout.
This checks layout, file digests, and the public JSON schema offline. The same
schema check rejects unknown or duplicate JSON fields before staging. User and
PR review remain essential for [privacy](../../docs/privacy-security.md). Follow the
[archive guide](../../docs/guides/evidence-archiving.md) for raw and oversized
records. The usual R6 reporting thresholds apply. The skill can reference a
previously approved versioned public archive or record an availability gap.
