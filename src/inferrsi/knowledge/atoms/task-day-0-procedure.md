## Run the procedure

1. Pin the upstream reference implementation, model revision, weights, tokenizer/processor, input and decoding settings. Save the exact reference command and expected output for each requested modality. Record any stochastic comparison rule before changing the adapter.
2. Map the checkpoint and I/O contract onto the engine's loader, preprocessing, stage boundaries, operators and postprocessing. On the target device, start with the smallest real-weight input. Compare each stage against the pinned reference in execution order.
3. At the first failing stage, replay its saved reference inputs through the target stage alone. If those pass, inspect the previous stage's handoff. Otherwise inspect the implementation or weights at that stage. Change one allowed adaptation at a time.
4. Run the complete user script with the agreed features and flags. Save inputs, revisions, stage checks, output and tolerance as a replayable regression fixture. State which features and devices the fixture covers.

