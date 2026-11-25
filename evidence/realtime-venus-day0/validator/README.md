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

Reserve **exclusive use of an initially unused local TCP port 8197** for the
entire baseline/candidate pair. Before each arm, confirm that no process is
listening there, and wait for the previous arm's service to exit. The frozen
harness polls `http://127.0.0.1:8197/health`; a different service on that port can
satisfy readiness while the new child is still starting, causing requests to
measure the wrong service. A successful health response alone does not prove
process ownership. Abort replay if exclusive ownership cannot be established;
do not stop an unrelated listener. The archived script remains unchanged.

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

## Revised lifecycle probe

`duplex_lifecycle.py` is the archived script used for the retained functional
observation. Its `run()` matches that execution, but review found that its gate
can accept an unrelated or failed audio-bearing response. It is preserved for
provenance and must not be used to qualify a new run. The command in the frozen
[follow-up plan](../plan/duplex-followup.md) describes that historical version.

For a new functional check, use the maintained
[revised probe](../../../tools/realtime_venus_lifecycle.py) from the InferRSI
repository root, with the same question WAV preparation described in the plan:

```bash
python tools/realtime_venus_lifecycle.py \
  --url ws://127.0.0.1:8091/v1/realtime \
  --model /path/to/Realtime-Venus/Realtime-Venus-Omni \
  --input-wav question.wav --output lifecycle.json
```

This version requires `websockets` and Pillow. It waits for the targeted
response's `cancelled` terminal and then for `input_audio_buffer.cleared` before
sending blue input. Only a response first created after that fresh input was
sent can satisfy the gate, and it must produce nonempty audio and terminate as
`completed`. The ordered cancellation/clear barriers bind the response to the
new input phase; they do not establish that its answer is semantically correct.
An early response cannot be credited by a late or duplicate terminal event.
Audio from the cancelled response after its acknowledgement still fails.

The revised probe records version 2, the fresh-input marker and the credited
response ID, without retaining resume tokens. Offline sequence and mocked
WebSocket tests cover these gates. It has not been rerun against the live model;
the historical result is not retroactively qualified by the revised validator.
The archived Python scripts, plans and results retain their original bytes.
Only explanatory README entries in the integrity manifest are refreshed for
these review corrections.
