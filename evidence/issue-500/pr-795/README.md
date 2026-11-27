# TorchNPU migration evidence for PR #795

The two records cover candidate commit `f019b55e910db92dd9048ca831d31747e091f048`, built on shared candidate `0312df99ecb7aba3e4a9003528eb084c660b4abe`.

- [Legacy public CLI ledger](legacy-cli-ledger.json) contains all 59 argument arrays, exit codes, and byte lengths and SHA-256 digests for both output streams. The `owners["checkout:torch-npu"]` entry also binds the original path, revision, provenance, and content digest for each of the 52 resources. File SHA-256 `7fd9c5679cd18310b824f6e5546d07199b54da9100fae91b71549d8f529599a2`.
- [Installed candidate Reader receipts](candidate-reader-receipts.json) contains the successful, denied, one-byte-short, and stale-revision receipts for L0–L3. File SHA-256 including the final LF `65f3f6fe03d08f466b6d1d3c1f07244ef8c8782ccc67d2644f2fb81f802493f8`. The canonical JSON bytes excluding that LF have SHA-256 `da51edb5638286c77ffc82dc6149d32babc545829ad7dfb280950e9e0e23d553`.

For the legacy replay, use a clean Windows environment with the published `inferrsi-0.3.4-py3-none-any.whl`. Its SHA-256 is `9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9` and the frozen source revision is `e2f3be102c66c358803ed2186ed67bf627ebcbdf`. Invoke the installed `inferrsi` executable with each ledger `args` list, capturing stdout and stderr as bytes separately. Compare those bytes and the exit status to the corresponding ledger entry.
