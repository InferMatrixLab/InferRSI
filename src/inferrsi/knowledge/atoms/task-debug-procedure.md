## Run the procedure

1. Replay the supplied script with its original flags and capture the first observable error, stage, device, rank and timestamps. Keep a last-working revision or configuration as a control. For a hang, capture progress at each boundary before attributing a cause.
2. Minimize the input or configuration one variable at a time. Preserve the original signature and a closely matched passing control. Follow ownership across stages to locate the earliest difference.
3. State two explanations that predict different observations. Probe the smallest boundary that distinguishes them, such as a recorded handoff with a known-good producer or consumer. Apply one in-scope fix only when the observation implicates that boundary.
4. Repeat the minimal reproducer, then the original unmodified script and an unaffected control. Retain logs tying the original failure and recovery to the same boundary and save a regression check.

