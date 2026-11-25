# Workload and scoring

The service-reuse protocol covers one warmed service per attempt. The readiness check verifies an attempt-specific served model and the retained source root. The driver streams the frozen prompts directly as token IDs. Each performance row requires the requested input count, every returned output token ID, a terminal length event and the final usage receipt. TTFT is separate. Compute each TPOT in milliseconds from the first and last token-bearing events, divide by 1,023, then take the unweighted median of the twenty request values. The driver retains the time and token count of every event.

For each LongBench v2 item, render the pinned zero-shot template with its stripped context, question and four choices. Tokenize the complete string once. Keep the template and any token crossing a document boundary once. Cycle the token sequence wholly within the document to fill the remaining input budget, truncating the last cycle on the right. Verify all twenty individual digests over compact JSON token arrays. The ordered input JSONL has one compact object per line with fields `id` and `prompt`. Input revisions and digests are in [inputs.json](inputs.json). The historical freeze publishes the original item counts, row order and independent token digests. [LongBench input freeze](https://github.com/InferMatrixLab/InferRSI/issues/613#issuecomment-7120848813)

The quality adapter loads the local ModelScope dataset with its original README schema. It renders EvalScope's AIME26 prompts in dataset order, sends them serially and saves each response before moving on. The scorer applies the published answer extractor and integer matching routine. A complete pass has thirty item judgments. Re-score the stored responses against their frozen prompts and reconcile the sum against the service receipt.

The runtime receives the model path, native vLLM environment and local campaign data root through environment variables. The scorer runs in an independent EvalScope environment under that data root. Keep raw HTTP responses, token arrays, per-rank service logs and private filesystem metadata in restricted storage.

## Reconstruct the requests

Fetch the source JSON and zero-shot template at the revisions in the input manifest. Run the builder with the same checkpoint tokenizer. The output file is replaced only after the entire ordered JSONL matches its frozen digest.

```bash
python build_requests.py --data "$LONGBENCH_JSON" --template "$ZERO_SHOT_TEMPLATE" \
  --tokenizer "$MODEL_PATH/tokenizer.json" --out "$INPUT_DIR/requests.jsonl"
```

Run `python check.py` from this directory to recompute the public timing and score summaries. The audit uses the observed first and last event timestamps in nanoseconds and the actual output-token count. Model generation and independent AIME re-scoring used the raw records in the private archive.

## Service-reuse replay

Set `HY4_WEIGHTS` to the checkpoint directory, `HY4_ENGINE_VENV` to the CUDA vLLM virtual environment, and `HY4_SOURCE` to a Git repository containing the measured revisions. The adapter reads generated native build artifacts from the vLLM checkout immediately above that virtual environment. Use clean Git worktrees for the baseline and candidate so declared source inputs contain tracked files only. Set `HY4_CAMPAIGN` to a private data root with `inputs/requests.jsonl`, the original ModelScope dataset directory at `inputs/aime26/`, and an EvalScope 1.15.0 environment at `scorer/`. Use the separately installed InferRSI CLI for campaign commands.

Copy the three executed scripts to a protocol directory outside the engine project. Supply a separate session directory on local storage. The caller's allocation must cover all four GPUs for each execution.

```bash
cp driver.py quality.py lifecycle.py "$PROTOCOL_DIR/"
"$INFERRSI" campaign start --evaluation-mode service_reuse \
  --evaluation-config protocol.json --repo "$BASELINE_CHECKOUT" \
  --include vllm --include examples/deployment --protocol "$PROTOCOL_DIR" \
  --instructions ../plan/README.md --session "$SESSION" --knowledge on \
  --rounds "$ROUND_BUDGET" --max-minutes "$CAMPAIGN_MINUTES" \
  --evaluation-timeout-seconds "$ATTEMPT_SECONDS" --final-reserve-seconds "$FINAL_SECONDS" \
  --python "$HY4_ENGINE_VENV/bin/python"
"$INFERRSI" campaign baseline --session "$SESSION"
```

Record the measured bottleneck with `campaign diagnose` and retrieve the supporting material with `campaign knowledge` before starting a candidate round. Pass the selected Git worktree to `campaign round`. The controller binds `campaign final` to the accepted comparison parent, source revision, conditions and protocol.
