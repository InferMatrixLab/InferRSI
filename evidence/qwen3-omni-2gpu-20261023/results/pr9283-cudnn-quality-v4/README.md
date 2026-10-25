# PR9283 v4 single-pair quality verification

Quality criterion PASS for this one fixed baseline→candidate pair: mean WER0.05030372124811463→0.03796659519799516. UTMOS3.334216554649174→3.331941317766905 is descriptive, with no UTMOS acceptance threshold. This does not establish causal quality improvement, repeated quality assurance, universal speedup or overall promotion. Overall campaign remains INCONCLUSIVE and endpoint RTF targets remain unmet; the separate performance pilot has mixed throughput/RTF/TTFA tradeoffs.

Both256-item arms completed source/scorer/input validation and livehold verification. The registered benchmark process remained live through final snapshot and monitor join; atomic release followed monitor closure, exit code0 and unchanged output hash were verified, and both postflight snapshots were empty. The earlier v3 known benchmark zombie failure remains separate and unchanged. New v4 protocol does not retrospectively qualify it.

Retained512 ordered WER/UTMOS rows,512 numeric audio request rows and512 private audio hashes are exact. Both arms use actual source a83eb6ed38fde8c6964a0315420f52e69706d31c with only the codec cuDNN flag changed. Process identities, control nonces, physical selectors, private paths, generated/reference/ASR text and audio payloads are omitted. Raw control files, logs, GPU scripts and model/scorer manifests remain hash-only. Identity-reason counts and lifecycle times retain sampled monitoring; no claim of continuous visibility between samples.

Campaign https://github.com/InferMatrixLab/InferRSI/issues/112
Independent privacy/source review required before publication.
