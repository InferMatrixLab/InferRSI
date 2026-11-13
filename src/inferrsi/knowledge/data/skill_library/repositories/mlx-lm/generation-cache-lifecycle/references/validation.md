# Validation plan

The candidate is source-derived. It has no installed API, native backend, real-model or HTTP qualification.

- Inspect test class setup before selecting a native method. Both TestGenerate and TestPromptCache load `mlx-community/Qwen1.5-0.5B-Chat-4bit`; a short method selection does not avoid setup. Use an already authorized local fixture and an offline dependency configuration, or leave it not_run. Never change the test's assertions or replace its real model with a fake to claim a pass.
- For row lifecycle, validate different prompt lengths, per-row stop/max-token settings, prompt-stage removal, generation-stage removal and a surviving request. Then issue another request and check that removed state did not shift identities.
- For prefix reuse, compare copied cache state against a non-reused reference under identical model/tokenizer/adapter/draft identity. Exercise exact/shorter/longer keys, trimmable versus non-trimmable cache classes and count/byte eviction. Separate logical token trimming from physical-memory release.
- For stopping, distinguish EOS, length, text stop, disconnect and shutdown; record the last token submitted and yielded, cleanup and subsequent request. A source flag is not an instantaneous prefill/kernel-abort guarantee.
- CPU state checks may validate selected row/cache logic. Required Metal/CUDA dispatch and serving behavior need the matching actual backend, model and workload. A CPU import is not a replacement.

Keep passed/failed/not-run evidence separate. Serving latency/throughput needs a separately frozen end-to-end comparison; this skill supplies no performance threshold or reproduced gain.
