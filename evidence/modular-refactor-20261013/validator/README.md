# Regression validation

The new `omnirsi.model.validators.image` implementation is frozen by candidate
commit `da842f5361e684822bb278f1147db28ee23c0c24` and the candidate's recorded
transitive helper hashes. The predeclared gate requires 1280×704 PNG/RGBA,
verified file hashes, SSIM 1, PSNR at least 100 dB and exact RGB/alpha pixels.
Zero mean squared error is represented as infinite PSNR.

`compare.py` additionally requires equal request protocols, dependency versions,
model manifests and engine revision, successful runner/integrity records, and
no surviving owned processes. It compares the first response and all three
retained output pairs. The script consumes the raw artifact root described in
[the evidence README](../README.md).

This validator serves the new regression run. Historical quality validators and
their transitive LTX helper were not edited or repointed.
