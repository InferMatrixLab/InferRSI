## Run the procedure

1. Replay the supplied benchmark unchanged. Pin requests, shape/batch mix, concurrency, warmup, timing boundary, repetitions, aggregation rule and quality oracle. Capture the baseline distribution and end-to-end output on the actual engine and device.
2. Profile the stage dominating the target metric. Separate queueing, prefill, decode, transfer or modality generation where observable. Estimate how much changing that stage can move the end-to-end metric.
3. Choose one change inside the allowed search space whose mechanism matches the measured bottleneck and the installed hardware/engine. Record the predicted profile signature. Alternate unchanged baseline and candidate trials with the same workload, quality evaluation and resource conditions.
4. After each change, compare the target metric, uncertainty and quality gate. Restore the incumbent if quality fails or the benefit is indistinguishable. Re-profile when the bottleneck moves. Recheck the selected change end to end with the original script.

