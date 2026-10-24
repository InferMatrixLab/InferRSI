# Patch

Candidate: vLLM-Omni branch `perf/ascend-drama3-full-decode-graphs`
(`[Perf][Ascend] Replay Drama 3 decode steps as FULL graphs`), based on
`c829af4`. Two files: `vllm_omni/deploy/fish_omni.yaml` and a CPU test in
`tests/model_executor/models/fish_omni/test_fish_omni_config.py`.

It is not vendored here; the candidate SHA belongs to the acceptance issue.
