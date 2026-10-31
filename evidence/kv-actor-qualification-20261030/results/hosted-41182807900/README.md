# Hosted actor qualification — original evidence

Source: [Ready run 41182807900, attempt 1](https://github.com/InferMatrixLab/InferRSI/actions/runs/41182807900) for [PR287](https://github.com/InferMatrixLab/InferRSI/pull/287). All five Ready jobs passed. The exact source/head/revision and original artifact identities are recorded in `manifest.json`.

- `qualification-artifact.zip` is the original downloaded Actions archive; it contains the exact `qualification.json` and original `raw-evidence.zip`. Neither archive is rebuilt.
- The independent raw/source/privacy check inspected fixed synthetic output and receipt allowlists, archive equality/CRC/hashes, source identities and bounded paths; it did not rerun candidates or models.
- Intentionally public synthetic grader data and pinned knowledge are included. Arbitrary host logs, provider captures, credentials and private conversations are excluded.

Independent raw checks reconstructed 198 semantic outputs (77 hidden per arm), 20 benchmark outputs and 201 execution records. Both arms retained four simulated slots and two edited revisions plus baseline revision 0. Visible timing was A2 FAIL/PASS and A3 PASS/PASS; qualification success does not relabel those timing outcomes. Runtime inventory observed 849 sensitive files, 16 escaped aliases and the host-parent cmdline probe (866 denied opens). Three cleanup modes each observed a five-process chain and no live survivors. The retained inventory hash and cleanup markers are trusted-host evidence; a complete inventory listing and live /proc snapshots are not archived.

This records model-free qualification only. It neither grants paid execution nor recovers the first paid run’s unknown cause or billing. Fresh exact freeze, current-host preflight and anchored budget admission remain separate. Historical artifacts are not replaced.
