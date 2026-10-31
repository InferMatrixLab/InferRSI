# Hosted task qualification — original evidence

Source: [Ready run 41182807900, attempt 1](https://github.com/InferMatrixLab/InferRSI/actions/runs/41182807900) for [PR287](https://github.com/InferMatrixLab/InferRSI/pull/287). All five Ready jobs passed. The exact source/head/revision and original artifact identities are recorded in `manifest.json`.

- `qualification-artifact.zip` is the original downloaded Actions archive; it contains the exact `qualification.json` and original `raw-evidence.zip`. Neither archive is rebuilt.
- The independent raw/source/privacy check inspected fixed synthetic output and receipt allowlists, archive equality/CRC/hashes, source identities and bounded paths; it did not rerun candidates or models.
- Intentionally public synthetic grader data are included; pinned knowledge is included only in the companion actor archive. Arbitrary host logs, provider captures, credentials and private conversations are excluded.

Independent raw checks reconstructed 792 control outcomes and 51 benchmark outputs. The optimized reference passed; seven incorrect controls and the unchanged/no-op controls retained their expected FAIL outcomes. These are software-control qualification results, not paid model outputs or knowledge efficacy.

This records model-free qualification only. It neither grants paid execution nor recovers the first paid run’s unknown cause or billing. Fresh exact freeze, current-host preflight and anchored budget admission remain separate. Historical artifacts are not replaced.
