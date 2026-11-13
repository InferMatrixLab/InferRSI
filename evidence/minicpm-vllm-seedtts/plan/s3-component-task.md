Acceptance issue: https://github.com/InferMatrixLab/InferRSI/issues/431
This subexperiment evaluates exact S3 CUDA replay at repeated 600/1200-frame shapes
with real tokenizer weights and deterministic synthetic mels. Quality requires
bit-identical codec tokens and lengths on those inputs and 16 distinct reference
WAVs from the disjoint tuning pool, with input hashes retained. The official
s3tokenizer 0.3.0 model source hash is checked, excluding the locally patched
shared installation. Metric is synchronized host latency per
call including graph copies. Three alternating process measurements and an
independent final compare to the pristine vLLM-Omni baseline's eager tokenizer.
No service RTF or generated-audio quality claim follows from this
component experiment. The separate Seed-TTS service gate remains mandatory.
