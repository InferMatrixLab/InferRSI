# H3-Metal FastH3 migration evidence

The ledger and receipts cover candidate commit `d3a08c7e4ed6cac6adb192c02ba9704e4a04a7ed` on shared candidate `0312df99ecb7aba3e4a9003528eb084c660b4abe`.

- [Legacy public CLI ledger](legacy-cli-ledger.json) records 16 invocations with arguments, status, and stdout and stderr digests. It binds all 10 resources to their original paths, content digests, revision, and provenance. File SHA-256 `9e8eb589ae4db849ccab0b5c29bb720b70f6a67884d4ee75056cc7f9c64004e9`.
- [Installed Reader receipts](candidate-reader-receipts.json) records successful and refused L0–L3 reads for generation `sha256:3c96bbde621a5b1b000fc9d6d93554af2464a32dee74d2b51c69309f8b5b65b5`. File SHA-256 `3cb9e347f1aa447aa29963ab926252d5826781a0f45ed0945dce22c01d54f8dc`.

Replay the legacy ledger on Windows with the published `inferrsi-0.3.4-py3-none-any.whl` (SHA-256 `9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`). The pinned source is `e2f3be102c66c358803ed2186ed67bf627ebcbdf`. Pass each recorded `args` list to the installed `inferrsi` executable and compare the exit code, output byte lengths, and SHA-256 digests. Capture stdout and stderr separately.
