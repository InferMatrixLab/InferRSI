# Retained measurement protocol

`check.py` and `measure.py` are byte-for-byte copies of the scripts frozen by
`campaign start`. They are not automatic CI or portable benchmark defaults.
The first checks config identity; the second owns a three-stage service, warms
it, validates speech WAV structure, measures fixed requests and compares exact
baseline/candidate text. The candidate script expects the baseline result in
the managed round's sibling `measurement-001-baseline` directory.

Use the issue-pinned downstream checkout, model snapshot and environment.
Reserve a GPU using the host's allocator. Supply its device through
`CUDA_VISIBLE_DEVICES`; the script inherits that allocation. The local model
path must point to the Omni child beside its root YAML.

Create `.local/venus/profile.json` with `{"enforce_eager": true}` in the downstream
checkout. Then, with the variables below resolved to absolute paths:

```bash
inferrsi campaign start \
  --repo "$OMNI_SOURCE" \
  --include vllm_omni --include .local/venus/profile.json \
  --protocol "$PROTOCOL_DIR" --instructions "$TASK_FILE" \
  --measure-command "{python} {protocol}/measure.py --source {candidate} --model $MODEL_PATH --result {result}" \
  --quality-command "{python} {protocol}/check.py --source {candidate} --model $MODEL_PATH --result {result}" \
  --metric-key latency_seconds --metric-unit seconds \
  --quality-key quality_passed --scope 'C1 warm text/image HTTP exploratory pair' \
  --direction minimize --min-improvement-pct 0 --repetitions 1 --warmups 0 \
  --decision point --session "$SESSION_DIR" --rounds 1 --max-minutes 50 \
  --evaluation-timeout-seconds 2400 --final-reserve-seconds 60 --knowledge off
inferrsi campaign diagnose --session "$SESSION_DIR" \
  --bottleneck "$MEASURED_DIAGNOSIS" --evidence "$DIAGNOSIS_FILE"
# Change only profile.json to {"enforce_eager": false}, then:
inferrsi campaign round --session "$SESSION_DIR" --candidate "$OMNI_SOURCE" \
  --hypothesis 'Compiled Thinker reduces warm HTTP latency while preserving text'
```

`PROTOCOL_DIR` contains the two retained Python files. `TASK_FILE` points to
`plan/TASK.md`. `SESSION_DIR` is a new directory outside the source/protocol.
The numeric choices above reconstruct this issue's exploratory experiment;
they are not recommendations for another campaign.

`warmups=0` prevents an additional whole-service measurement invocation; the
script itself performs one text and one image warmup per service. The speech
request is a structural correctness check, not a timed speech comparison.
Do not run `campaign final` for this historical run: the operator explicitly
limited measurement to one baseline and one candidate. The managed session
therefore has no finalized acceptance result.

## Tokenizer diagnostic

`tokenizer_probe.py` is a public copy of the separate CPU diagnostic with the
local checkpoint path replaced by an argument. It is not part of the frozen
performance protocol. Run it once in each reference/current dependency
environment, then compare the `ids` mappings:

```bash
python tokenizer_probe.py "$OUTPUT_JSON" "$MODEL_PATH"
```

The current environment must import the downstream vLLM-Omni checkout so its
native config registration is available. The isolated reference uses the
released tokenizer with Transformers 4.51.3. Direct HF5 loading without native
registration reproduced the config API failure before tokenization.
