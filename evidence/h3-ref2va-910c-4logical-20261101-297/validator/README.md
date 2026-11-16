# Archive replay and frozen validation

From the repository root, with Python 3.10+ and the standard library:

```bash
python tools/verify_evidence_archive.py evidence/h3-ref2va-910c-4logical-20261101-297/results/artifacts.json --download
# Download the pinned asset separately to <archive>; never run archived code.
python tools/rebuild_model_evidence.py evidence/h3-ref2va-910c-4logical-20261101-297/results/artifacts.json \
  --archive <archive> --output <new-output-directory>
python tools/verify_evidence_archive.py evidence/h3-ref2va-910c-4logical-20261101-297/results/artifacts.json \
  --archive <archive> --recomputed <new-output-directory>
```

Replay authenticates compressed bytes, bounds archive reads, checks every
original file and original integrity manifest, and checks that the local replay
implementation equals the pinned archived implementation. It neither extracts
nor executes archived code, and refuses an existing output directory. It scans
all published result JSON documents, including nested failed/cancelled attempts,
then regenerates the index and summary without reading retained views.
Structure, IDs, source pointers and integers compare exactly. Finite floats use
predeclared absolute and relative tolerances of 1e-12 across Python versions.

Only the sample distributions declared by `plan/archive-projection.json` are
recomputed. Frozen statistical/quality verdicts are labelled recorded results;
unavailable raw inputs are not requalified. The index is complete for published
structured observations, not unavailable private history or narrative-only
attempts. The original validators remain byte-preserved in the archive and
require their original model/device/input dependencies for model acceptance.
