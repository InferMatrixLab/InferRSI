# Implementation revisions

- Source base: `0032649b8d8e68f709c2a50e9fa31aa3f866dffb`.
- v1 real-client seam: `4f50c70916bfeeb7a78d997836ff017a760bbe7b`.
- Revised final controller: `b8a66317a5da3b2f344e21d7f3d942fce9061525`.
- Delivery: [PR #69](https://github.com/InferMatrixLab/InferRSI/pull/69).

The first change adds the reader/client/executor outcome seam, driver, verifier,
CPU checks and operation documentation. The second clarifies the task contract,
selects revised final values and tests that distinction. Controller-file hashes
are checked before execution. Skills, dependencies and verifier bytes are
unchanged between phases. Evidence publication changes do not rerun or relabel
original model outputs.
