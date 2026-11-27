## Run the procedure

1. Pin model format, reference inputs and outputs, target OS/ABI, device/driver, available runtime APIs and resource limits. Map required operators, dtypes, layouts and memory lifetimes to target capabilities. Mark fallback, missing implementations and unverified capabilities.
2. On the actual target, load the model and run one reference-checked operator with a dispatch trace. Extend to the shortest connected path that produces an output. Test the first missing operator or allocation boundary before expanding coverage.
3. Run the complete input through preprocessing, execution and postprocessing. Verify device placement or any explicitly permitted fallback. Exercise repeated requests and teardown to expose ownership or retained-memory errors.
4. Replay the user's script on the target OS/device. Check end-to-end output, resident or peak memory, cold/warm behavior and the user-specified resource gates. Record unsupported operators and model features.

