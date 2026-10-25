# PR9283 quality pilot — failed execution retained

INCONCLUSIVE. Baseline completed; candidate failed its frozen work-interval isolation gate when the registered benchmark process, which also runs CUDA scorers, was observed as a zombie. The pair stopped without a qualifying acceptance comparison. Both256-item quality files and512 private audio hashes exist; numeric results are descriptive only and cannot override the execution failure. Both postflight snapshots were empty, which does not erase the earlier work failure. No new foreign-job overlap is inferred from the zombie classification.

Retained ordered WER/UTMOS rows and all512 raw numeric audio request metrics are exact. No utterance IDs, generated text, reference/ASR text, audio payloads, PIDs, births, physical selectors or private paths are published. Logs, original tensors/audio and source/config/scorer/model manifests are hash-only. Identity-reason counts and time boundaries retain the failure timeline; detailed independent diagnosis remains separate. Sampled isolation does not establish behavior between samples.

Same actual source a83eb6ed38fde8c6964a0315420f52e69706d31c and two newly reserved GPUs as the performance pilot, but this failed quality execution does not qualify that performance result for promotion. Mean WER/UTMOS differences are not causal quality claims. No retry or selective row exclusion was performed.

Campaign https://github.com/InferMatrixLab/InferRSI/issues/112
Independent privacy/source review required before publication.
