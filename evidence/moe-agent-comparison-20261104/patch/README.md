# Immutable candidate sources

`candidates.csv` identifies all 54 submitted sources: 48 exploratory candidates
inside `exploration-candidates.zip` and six readable final sources in `final/`.
The ZIP contains only relative source names, with fixed timestamps; each member
retains its original bytes. SHA256 and byte counts are checked by `../verify.py`.
Final sources equal the selected exploratory round byte for byte. Failed and
slower candidates remain included. These snapshots are historical evidence,
not a dependency of the current library or a request to execute their code.

Some inherited source comments say padding does not execute an expert MLP.
After native routing this is not necessarily true: padded slots can enter the
GMM, but their probabilities are zero and they contribute no output. Original
comments remain unchanged to preserve source identity; the audit follows code.
